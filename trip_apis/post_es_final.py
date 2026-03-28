from loguru import logger
import os
from dotenv import load_dotenv
import json
# import redis
import requests
from requests.auth import HTTPBasicAuth
from pathlib import Path
from ...services.redis_manager import RedisJSONManager

load_dotenv()


ES_USERNAME = os.getenv("SAP_BASIC_USER")
ES_PASSWORD = os.getenv("SAP_BASIC_PASS")
EMP_API_KEY = os.getenv("EMP_API_KEY")

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
responses_dir = os.path.join(base_dir, "responses")
os.makedirs(responses_dir, exist_ok=True)

# Initialize Redis manager once at the beginning
redis_mgr = RedisJSONManager()

def post_es_final(travel: dict, PERNR: str, session_id: str):
    """
    Send a booking request to the SAP ES_FINAL API to confirm and create a trip.

    Builds the ES_FINAL payload using:
      - Header data from Redis ("header")
      - ES_GET response from Redis ("es_get") for NAV_FIN_TO_IT legs
      - Scalar travel fields (purpose, dates, WBS, advances, comment, journey_type)

    Handles both One Way and Round Trip by controlling NAV_FIN_TO_IT length
    based on travel["journey_type"].
    """

    global REINR
    logger.info("📡 Calling ES FINAL API:")

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Requested-With": "X",
    }
    if EMP_API_KEY:
        headers["Authorization"] = EMP_API_KEY

    auth = HTTPBasicAuth(ES_USERNAME, ES_PASSWORD) if (ES_USERNAME or ES_PASSWORD) else None

    # -------------------------------------------------------------------------
    # Load header and ES_GET response from Redis
    # -------------------------------------------------------------------------
    try:
        es_header = redis_mgr.load_json(
            user_id=PERNR,
            session_id=session_id,
            data_type="header",
        )
        logger.info("Loaded ES header for PERNR=%s with keys: %s", PERNR, list(es_header.keys()))
    except Exception as e:
        logger.exception("Failed to load ES header for PERNR=%s: %s", PERNR, e)
        return {
            "success": False,
            "trip_id": None,
            "error": f"Failed to load ES header: {e}",
            "status_code": None,
            "raw_response": None,
        }

    try:
        es_get_response = redis_mgr.load_json(
            user_id=PERNR,
            session_id=session_id,
            data_type="es_get",
        )
        logger.info("Loaded ES_GET response for PERNR=%s", PERNR)
    except Exception as e:
        logger.exception("Failed to load ES_GET response for PERNR=%s: %s", PERNR, e)
        return {
            "success": False,
            "trip_id": None,
            "error": f"Failed to load ES_GET response: {e}",
            "status_code": None,
            "raw_response": None,
        }

    # -------------------------------------------------------------------------
    # Decide one-way vs round-trip based on journey_type
    # -------------------------------------------------------------------------
    journey_type_raw = (travel.get("journey_type") or "").strip().lower()
    is_one_way = journey_type_raw.startswith("one")
    is_round_trip = journey_type_raw.startswith("round")

    if not is_one_way and not is_round_trip:
        logger.warning(
            "journey_type not explicitly 'One Way' or 'Round Trip'; "
            "defaulting to round trip behavior in ES_FINAL."
        )
        is_round_trip = True

    # Extract NAV_TRAVELDET from ES_GET response
    nav_traveldet_results = (
        es_get_response.get("d", {})
        .get("NAV_TRAVELDET", {})
        .get("results", [])
    )

    if not isinstance(nav_traveldet_results, list) or not nav_traveldet_results:
        msg = "ES_GET response NAV_TRAVELDET.results is empty or invalid"
        logger.error(msg)
        return {
            "success": False,
            "trip_id": None,
            "error": msg,
            "status_code": None,
            "raw_response": es_get_response,
        }

    # Determine how many legs to include
    desired_legs = 1 if is_one_way else 2
    available_legs = len(nav_traveldet_results)
    if available_legs < desired_legs:
        logger.warning(
            "ES_GET returned only %d legs but journey_type expects %d; "
            "using %d legs.",
            available_legs,
            desired_legs,
            available_legs,
        )
        desired_legs = available_legs

    # Helper to construct NAV_FIN_TO_IT entry from NAV_TRAVELDET leg
    def _build_fin_to_it_row(src: dict) -> dict:
        return {
            "CITY_CLASS": src.get("CITY_CLASS", ""),
            "COUNTRY_BEG": src.get("COUNTRY_BEG", ""),
            "COUNTRY_END": src.get("COUNTRY_END", ""),
            "DATE_BEG": src.get("DATE_BEG", ""),
            "DATE_END": src.get("DATE_END", ""),
            "DEL_BUTTON_READ_ONLY": src.get("DEL_BUTTON_READ_ONLY", ""),
            "DEST_CODE": src.get("DEST_CODE", ""),
            "EDIT_BUTTON_READ_ONLY": src.get("EDIT_BUTTON_READ_ONLY", ""),
            "ITENARY": src.get("ITENARY", ""),
            "LOCATION_BEG": src.get("LOCATION_BEG", ""),
            "LOCATION_END": src.get("LOCATION_END", ""),
            "MRC_1_2_WAY_FLAG": src.get("MRC_1_2_WAY_FLAG", ""),
            "ORIGIN_CODE": src.get("ORIGIN_CODE", ""),
            "PERNR": PERNR,
            "PREFERRED_FLIGHT": src.get("PREFERRED_FLIGHT", ""),
            "TIME_BEG": src.get("TIME_BEG", ""),
            "TIME_END": src.get("TIME_END", ""),
            "TRAVEL_CLASS": src.get("TRAVEL_CLASS", ""),
            "TRAVEL_CLASS_TEXT": src.get("TRAVEL_CLASS_TEXT", ""),
            "TRAVEL_MODE": src.get("TRAVEL_MODE", ""),
            "TRAVEL_MODE_CODE": src.get("TRAVEL_MODE_CODE", ""),
            "TICK_METH_TXT": src.get("TICK_METH_TXT", ""),
            "TICKET_METHOD": src.get("TICKET_METHOD", ""),
        }

    nav_fin_to_it = [
        _build_fin_to_it_row(nav_traveldet_results[i])
        for i in range(desired_legs)
    ]

    # -------------------------------------------------------------------------
    # Numeric fields from travel
    # -------------------------------------------------------------------------
    try:
        travadv_val = float(travel.get("travel_advance", 0.0) or 0.0)
    except Exception:
        travadv_val = 0.0

    try:
        addadv_val = float(travel.get("additional_advance", 0.0) or 0.0)
    except Exception:
        addadv_val = 0.0

    try:
        reimb_pct = float(travel.get("reimburse_percentage", 100.0) or 100.0)
    except Exception:
        reimb_pct = 100.0

    # -------------------------------------------------------------------------
    # Build ES_FINAL payload (aligned with car one-way / roundtrip examples)
    # -------------------------------------------------------------------------
    payload = {
        "ACTION": "",
        "ADDADV": f"{addadv_val:.2f}",
        "AGE": es_header.get("AGE", ""),
        "ATTACHMANDT": es_header.get("ATTACHMANDT", ""),
        "ATTACHVISIBLE": es_header.get("ATTACHVISIBLE", ""),
        "COMMENT": travel.get("comment", ""),
        "CREAT_DATE": es_header.get("CREAT_DATE", ""),
        "DATE_BEG": travel.get("start_date", ""),
        "DATE_END": travel.get("end_date", ""),
        "DOB": es_header.get("DOB", ""),
        "EMAIL": es_header.get("EMAIL", ""),
        "FNAME": es_header.get("FNAME", ""),
        "ISSFUSERID": es_header.get("ISSFUSERID", ""),
        "LNAME": es_header.get("LNAME", ""),
        "LOC_START": travel.get("origin_city", ""),
        "LOCATION_END": travel.get("destination_city", ""),
        "MNAME": es_header.get("MNAME", ""),
        "MOBILE": es_header.get("MOBILE", ""),
        "MODE": "",
        "NAV_FIN_BOOK": [],
        "NAV_FIN_COMING": [],
        "NAV_FIN_COST": [
            {
                "AUFNR": "",
                "KOSTL": es_header.get("NAV_COSTASSIGN", [{}])[0].get("KOSTL", ""),
                "PERCENT": f"{reimb_pct:.2f}",
                "POSNR": travel.get("project_wbs", ""),
                "POSNR2W": "",
            }
        ],
        "NAV_FIN_EMPFLIGHTS": [],
        "NAV_FIN_FILES": [],
        "NAV_FIN_GOING": [],
        "NAV_FIN_J12WAY": [],
        "NAV_FIN_ONEWAY": [],
        "NAV_FIN_REPRICE": [],
        "NAV_FIN_SEGMENT": [],
        "NAV_FIN_TO_IT": nav_fin_to_it,
        "NO_VALIDATIONS": "X",
        "OLOC_START": es_get_response.get("d", {}).get("OLOC_START", ""),
        "OLOCATION_END": es_get_response.get("d", {}).get("OLOCATION_END", ""),
        "OTHERREASON": es_get_response.get("d", {}).get("OTHERREASON", ""),
        "PAYMODE": es_get_response.get("d", {}).get("PAYMODE", ""),
        "PERNR": es_get_response.get("d", {}).get("PERNR", PERNR),
        "PERSA": es_get_response.get("d", {}).get("PERSA", ""),
        "PERSK": es_get_response.get("d", {}).get("PERSK", ""),
        "REASON": travel.get("travel_purpose", ""),
        "REINR": es_get_response.get("d", {}).get("REINR", "0000000000"),
        "SEARCHMANDT": es_get_response.get("d", {}).get("SEARCHMANDT", ""),
        "SEARCHMODE": es_header.get("SEARCHMODE", ""),
        "SEARCHVISIBLE": es_get_response.get("d", {}).get("SEARCHVISIBLE", ""),
        "SEX": es_header.get("SEX", ""),
        "TIME_BEG": travel.get("start_time", ""),
        "TIME_END": travel.get("end_time", ""),
        "TITLE": es_header.get("TITLE", ""),
        "TRAVADV": str(travadv_val),
        "TRIPDEL": es_header.get("TRIPDEL", ""),
        "TRIPEDIT": es_header.get("TRIPEDIT", ""),
        "WAERS": es_header.get("WAERS", ""),
        "WBSMAND": es_header.get("WBSMAND", ""),
    }

    logger.warning(f"ES_FINAL payload: {payload}")

    api_url = "https://emssq.mahindra.com/domestictravel/ES_FINAL"

    # Save payload for debugging (non-fatal on failure)
    dynamic_file_path_payload = os.path.join(responses_dir, f"{PERNR}_es_final_payload.json")
    try:
        with open(dynamic_file_path_payload, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("Failed to write ES_FINAL payload for PERNR=%s: %s", PERNR, e)

    # -------------------------------------------------------------------------
    # Call ES_FINAL API
    # -------------------------------------------------------------------------
    try:
        logger.info("Posting to ES_FINAL: %s", api_url)
        resp = requests.post(api_url, auth=auth, json=payload, headers=headers, timeout=(250, 300))
    except requests.exceptions.Timeout as e:
        msg = f"ES_FINAL timeout: {e}"
        logger.error(msg)
        return {"success": False, "trip_id": None, "error": msg, "status_code": None, "raw_response": None}
    except requests.exceptions.RequestException as e:
        msg = f"ES_FINAL request failed: {e}"
        logger.error(msg)
        return {"success": False, "trip_id": None, "error": msg, "status_code": None, "raw_response": None}

    text_head = (resp.text or "")[:2000]
    try:
        data = resp.json()
    except ValueError:
        data = None

    # Extract REINR if present
    reinr = None
    if isinstance(data, dict):
        d = data.get("d", data)
        if isinstance(d, dict):
            reinr = d.get("REINR")
            if reinr is None:
                results = d.get("results")
                if isinstance(results, list) and results and isinstance(results[0], dict):
                    reinr = results[0].get("REINR")
    
    dynamic_file_path = os.path.join(responses_dir, f"{PERNR}_es_final_response.json")
    with open(dynamic_file_path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        
    # Save REINR to Redis if available
    if reinr:
        try:
            success = redis_mgr.save_json(
                data={"trip_id": reinr},
                user_id=PERNR,
                session_id=session_id,
                data_type="es_final",
            )
            if success:
                logger.info("Saved REINR=%s to Redis for PERNR=%s, session=%s", reinr, PERNR, session_id)
            else:
                logger.warning("Failed to save REINR to Redis for PERNR=%s, session=%s", PERNR, session_id)
        except Exception as e:
            logger.error("Error saving REINR to Redis: %s", e)

    # Success path
    if resp.ok:
        if reinr:
            logger.info("SAP trip created – REINR: %s", reinr)
        else:
            logger.warning("ES_FINAL success but REINR not found")
        return {
            "success": True,
            "trip_id": reinr,
            "error": None if reinr else "REINR missing or unparseable",
            "status_code": resp.status_code,
            "raw_response": data if data is not None else text_head,
        }

    # Error path
    reason = f"ES_FINAL failed {resp.status_code}: {text_head[:800]}"
    logger.error(reason)
    return {
        "success": False,
        "trip_id": None,
        "error": reason,
        "status_code": resp.status_code,
        "raw_response": data if data is not None else text_head,
    }
