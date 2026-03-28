from loguru import logger
import os
from dotenv import load_dotenv
import json
import requests
from requests.auth import HTTPBasicAuth
from pathlib import Path
from ...services.redis_manager import RedisJSONManager

load_dotenv()

ES_USERNAME = os.getenv("SAP_BASIC_USER", "")
ES_PASSWORD = os.getenv("SAP_BASIC_PASS", "")
EMP_API_KEY = os.getenv("EMP_API_KEY", None)

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
responses_dir = os.path.join(base_dir, "responses")
os.makedirs(responses_dir, exist_ok=True)

# Initialize Redis manager once at the beginning
redis_mgr = RedisJSONManager()

def safe_get_nested(data: dict, *keys, default=None):
    """
    Safely get nested dictionary values with a default.
    """
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key, default)
            if current is default:
                return default
        else:
            return default
    return current

def _unwrap(obj):
    """
    Accept {"d": {...}} or {...}; return the inner dict or {}.
    """
    if isinstance(obj, dict):
        inner = obj.get("d")
        return inner if isinstance(inner, dict) else obj
    return {}

def _results(container: dict, key: str):
    """
    OData list extractor: container[key].results[] or [].
    """
    node = (container or {}).get(key)
    if isinstance(node, dict) and isinstance(node.get("results"), list):
        return node["results"]
    return node if isinstance(node, list) else []

def _strip_metadata_list(lst):
    """
    Remove __metadata from each dict in a list.
    """
    cleaned = []
    for item in lst or []:
        if isinstance(item, dict):
            cleaned.append({k: v for k, v in item.items() if k != "__metadata"})
    return cleaned

def _hhmmss(t):
    """
    Normalize time strings to HHMMSS.
    Accepts '13:00' -> '130000', '0700' -> '070000', already-good values pass through.
    """
    if not t:
        return ""
    if isinstance(t, str):
        s = t.strip()
        if len(s) == 5 and s[2] == ":" and s[:2].isdigit() and s[3:].isdigit():
            return s.replace(":", "") + "00"
        if len(s) == 4 and s.isdigit():
            return s + "00"
        # If already 6 digits or something else, return as-is
        return s
    return str(t)

def post_es_final_flight(travel: dict, PERNR: str, session_id: str):
    """
    Send a booking request to the SAP ES_FINAL API to confirm and create a flight trip.

    This function composes and posts the ES_FINAL (flight) payload to SAP using:
      - Employee/header data loaded from Redis ("header").
      - ES_GET flight search details loaded from Redis based on journey_type:
          * "One Way" → "es_get_flight_oneway"
          * "Round Trip" → "es_get_flight_roundtrip"
      - ES_REPRICE response loaded from Redis ("es_reprice").
      - Additional scalar fields from the `travel` dict (e.g., project_wbs, comment).

    It is journey-type aware:
      - For "One Way" journeys, it populates NAV_FIN_ONEWAY and leaves
        NAV_FIN_GOING / NAV_FIN_COMING empty.
      - For "Round Trip" journeys, it populates NAV_FIN_GOING and NAV_FIN_COMING 
        while leaving NAV_FIN_ONEWAY empty.

    All required data for segments (going / coming) is derived from the
    ES_GET + ES_REPRICE payloads in Redis.

    Parameters
    ----------
    travel : dict
        Additional flight booking details collected from the agent:
          - "project_wbs": str (optional)
                WBS element to be associated with the trip.
                Mapped to POSNR in NAV_FIN_COST.
          - "comment": str (optional)
                Free-text comment / justification.
                Mapped to COMMENT in ES_FINAL.
          - "journey_type": str (required)
                Journey type preference: "One Way" | "Round Trip".
                Controls which Redis key to load and whether NAV_FIN_ONEWAY 
                or NAV_FIN_GOING/NAV_FIN_COMING are populated.

    PERNR : str
        Personnel number / employee identifier for the logged-in user.

    session_id : str
        Session identifier used as part of the Redis key-space to load
        the correct header, ES_GET, and ES_REPRICE data.

    Returns
    -------
    dict
        A structured result describing the ES_FINAL booking outcome:

        {
          "success": bool,                 # True if ES_FINAL returned HTTP 200/201
          "trip_id": str | None,           # SAP trip number (REINR) if available
          "error": str | None,             # Error/warning message or None
          "status_code": int | None,       # HTTP status code from ES_FINAL
          "raw_response": dict | str | None
              # Parsed JSON from SAP if available, else truncated text
        }

    Side Effects
    ------------
    - Reads the following JSON blobs from Redis via RedisJSONManager:
        * header                       → ("header")
        * ES_GET flight data (journey-specific) → ("es_get_flight_oneway" or "es_get_flight_roundtrip")
        * ES_REPRICE                   → ("es_reprice")
    - Saves the final ES_FINAL flight payload to
        `<responses_dir>/<PERNR>_es_final_flight_payload.json`
      for debugging.
    - On success (with a non-empty REINR), stores:
        { "trip_id": REINR }
      back into Redis under:
        data_type = "es_final_flight"
    """

    logger.info("📡 Calling ES FINAL FLIGHT API:")
    logger.info(f"Starting ES_FINAL flight booking process for PERNR={PERNR}")
    logger.info(f"Working directory: {responses_dir}")

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Requested-With": "X",
        "Authorization": EMP_API_KEY,
    }
    auth = HTTPBasicAuth(ES_USERNAME, ES_PASSWORD) if (ES_USERNAME or ES_PASSWORD) else None

    # -------------------------------------------------------------------------
    # 1) Determine journey type and corresponding Redis key
    # -------------------------------------------------------------------------
    journey_type_raw = ""
    if isinstance(travel, dict):
        journey_type_raw = (
            travel.get("journey_type")
            or travel.get("journey_type_text")
            or ""
        )

    journey_type_norm = journey_type_raw.strip()
    
    # Determine which Redis key to load based on journey_type
    # "One Way" → es_get_flight_oneway
    # "Round Trip" → es_get_flight_roundtrip
    if journey_type_norm == "One Way":
        redis_flight_key = "es_get_flight_oneway"
        is_one_way = True
    elif journey_type_norm == "Round Trip":
        redis_flight_key = "es_get_flight_roundtrip"
        is_one_way = False
    else:
        # Default to Round Trip if journey_type is missing or unrecognized
        logger.warning(
            f"Unknown or missing journey_type: '{journey_type_raw}'. Defaulting to Round Trip."
        )
        redis_flight_key = "es_get_flight_roundtrip"
        is_one_way = False

    logger.info(
        f"Journey type: '{journey_type_raw}' → Using Redis key: '{redis_flight_key}' (is_one_way={is_one_way})"
    )

    # -------------------------------------------------------------------------
    # 2) Load inputs from Redis
    # -------------------------------------------------------------------------
    try:
        es_header = redis_mgr.load_json(
            user_id=PERNR,
            session_id=session_id,
            data_type="header",
        )

        # Load journey-type-specific flight data
        es_get_flight_d = redis_mgr.load_json(
            user_id=PERNR,
            session_id=session_id,
            data_type=redis_flight_key,
        )

        # If the primary key is missing, try the fallback
        if not es_get_flight_d:
            fallback_key = (
                "es_get_flight_roundtrip" if redis_flight_key == "es_get_flight_oneway"
                else "es_get_flight_oneway"
            )
            logger.warning(
                f"Primary flight data key '{redis_flight_key}' not found. "
                f"Trying fallback key: '{fallback_key}'"
            )
            es_get_flight_d = redis_mgr.load_json(
                user_id=PERNR,
                session_id=session_id,
                data_type=fallback_key,
            )
            
            if es_get_flight_d:
                logger.info(f"Successfully loaded fallback flight data from '{fallback_key}'")
                # Update is_one_way based on fallback key
                is_one_way = (fallback_key == "es_get_flight_oneway")
            else:
                logger.error(f"Both primary and fallback flight data keys are missing")

        # Cleaned ES_REPRICE response
        es_get_reprice_response = redis_mgr.load_json(
            user_id=PERNR,
            session_id=session_id,
            data_type="es_reprice",
        )

    except (FileNotFoundError, PermissionError, ValueError) as e:
        logger.error(f"Failed to load required files from Redis: {e}")
        return {
            "success": False,
            "trip_id": None,
            "error": f"Failed to load required files: {e}",
            "status_code": None,
            "raw_response": None,
        }

    # -------------------------------------------------------------------------
    # 3) Unwrap and validate basic structure
    # -------------------------------------------------------------------------
    try:
        if not isinstance(es_header, dict):
            raise KeyError("ES header missing or not a dict")
        if not isinstance(es_get_flight_d, dict):
            raise KeyError(f"Flight data from '{redis_flight_key}' missing or not a dict")
        if not isinstance(es_get_reprice_response, dict):
            raise KeyError("es_get_reprice_response missing or not a dict")

        # Unwrap all ("d" vs flat JSON)
        d_header = _unwrap(es_header)
        d_flight = _unwrap(es_get_flight_d)
        d_reprice = _unwrap(es_get_reprice_response)

        if not d_header:
            raise KeyError("ES header empty after normalization")
        if not d_flight:
            raise KeyError(f"Flight data from '{redis_flight_key}' empty after normalization")
        if not d_reprice:
            raise KeyError("ES_REPRICE payload empty after normalization")

        # Preferred flights (need at least 2 slots, pad if fewer)
        nav_pref_results = _results(d_flight, "NAV_PREFERRED_FLIGHT") or []
        while len(nav_pref_results) < 2:
            nav_pref_results.append({})
        es_pref = nav_pref_results[0]
        es_pref2 = nav_pref_results[1]

        logger.debug("Preferred flights loaded successfully")

    except (KeyError, IndexError, TypeError) as e:
        logger.error(f"Required data structure missing: {e}")
        return {
            "success": False,
            "trip_id": None,
            "error": f"Required data structure missing: {e}",
            "status_code": None,
            "raw_response": None,
        }

    # -------------------------------------------------------------------------
    # 4) Build payload (journey-type aware)
    # -------------------------------------------------------------------------
    try:
        # Cost assignment
        cost_assign_results = _results(d_header, "NAV_COSTASSIGN")
        cost_assign = cost_assign_results[0] if cost_assign_results else {}

        # Itinerary legs & J12WAY summary
        travel_det_results = _results(d_flight, "NAV_TRAVELDET")
        j12way_results = _results(d_flight, "NAV_J12WAY")
        j12way = j12way_results[0] if j12way_results else {}

        # Search results for going/coming segments
        getsearch_results = _results(d_flight, "NAV_GETSEARCH")
        reprice_segment_results = _results(d_reprice, "NAV_REPRICE")

        # Segment-based split by SEARCHSEGMENTID
        # For One Way: only SEARCHSEGMENTID == "0" segments exist
        # For Round Trip: SEARCHSEGMENTID == "0" (going) and "1" (coming) exist
        going_segments = _strip_metadata_list(
            [x for x in (getsearch_results or []) if x.get("SEARCHSEGMENTID") == "0"]
        )
        coming_segments = _strip_metadata_list(
            [x for x in (getsearch_results or []) if x.get("SEARCHSEGMENTID") == "1"]
        )

        # Validate segment counts based on journey type
        if is_one_way:
            if not going_segments:
                logger.error("One Way journey but no outbound segments (SEARCHSEGMENTID=0) found")
                return {
                    "success": False,
                    "trip_id": None,
                    "error": "No outbound flight segments found for One Way journey",
                    "status_code": None,
                    "raw_response": None,
                }
            if coming_segments:
                logger.warning(
                    f"One Way journey but found {len(coming_segments)} return segments. "
                    "These will be ignored."
                )
        else:  # Round Trip
            if not going_segments:
                logger.error("Round Trip journey but no outbound segments (SEARCHSEGMENTID=0) found")
                return {
                    "success": False,
                    "trip_id": None,
                    "error": "No outbound flight segments found for Round Trip journey",
                    "status_code": None,
                    "raw_response": None,
                }
            if not coming_segments:
                logger.error("Round Trip journey but no return segments (SEARCHSEGMENTID=1) found")
                return {
                    "success": False,
                    "trip_id": None,
                    "error": "No return flight segments found for Round Trip journey",
                    "status_code": None,
                    "raw_response": None,
                }

        # Journey-type–aware mapping:
        #   - One Way   → NAV_FIN_ONEWAY populated, GOING/COMING empty
        #   - Round Trip → GOING/COMING populated, ONEWAY empty
        if is_one_way:
            nav_fin_oneway = going_segments
            nav_fin_going = []
            nav_fin_coming = []
            logger.info(
                f"ES_FINAL flight: One Way journey → NAV_FIN_ONEWAY with {len(going_segments)} segments"
            )
        else:
            nav_fin_oneway = []
            nav_fin_going = going_segments
            nav_fin_coming = coming_segments
            logger.info(
                f"ES_FINAL flight: Round Trip journey → "
                f"NAV_FIN_GOING ({len(going_segments)} segments), "
                f"NAV_FIN_COMING ({len(coming_segments)} segments)"
            )

        # Numeric/optional fields from travel
        project_wbs = (travel or {}).get("project_wbs", "")
        comment = (travel or {}).get("comment", "")

        payload = {
            "PERNR": d_flight.get("PERNR", PERNR),
            "MOBILE": d_flight.get("MOBILE", ""),
            "TRAVADV": d_flight.get("TRAVADV", ""),
            "ADDADV": d_flight.get("ADDADV", ""),
            "PAYMODE": d_flight.get("PAYMODE", ""),
            "LOC_START": d_flight.get("LOC_START", ""),
            "OLOC_START": d_flight.get("OLOC_START", ""),
            "LOCATION_END": d_flight.get("LOCATION_END", ""),
            "OLOCATION_END": d_flight.get("OLOCATION_END", ""),
            "DATE_BEG": d_flight.get("DATE_BEG", ""),
            "DATE_END": d_flight.get("DATE_END", ""),
            "TIME_BEG": _hhmmss(d_flight.get("TIME_BEG", "")),
            "TIME_END": _hhmmss(d_flight.get("TIME_END", "")),
            "COMMENT": comment,
            "REASON": d_flight.get("REASON", ""),
            "REINR": d_flight.get("REINR", "0000000000"),
            "ACTION": d_flight.get("ACTION"),
            "MODE": "",
            "TRIPEDIT": "",
            "TRIPDEL": "",
            "SEARCHVISIBLE": d_flight.get("SEARCHVISIBLE", ""),
            "SEARCHMANDT": d_flight.get("SEARCHMANDT", ""),
            "SEARCHMODE": "",
            "ATTACHVISIBLE": "",
            "ATTACHMANDT": "",
            "CREAT_DATE": "",
            "WAERS": "",
            "WBSMAND": "",
            "ISSFUSERID": "",
            "OTHERREASON": d_flight.get("OTHERREASON", ""),
            "DOB": d_header.get("DOB", ""),
            "SEX": d_header.get("SEX", ""),
            "AGE": d_header.get("AGE", ""),
            "EMAIL": d_header.get("EMAIL", ""),
            "FNAME": d_header.get("FNAME", ""),
            "LNAME": d_header.get("LNAME", ""),
            "MNAME": d_header.get("MNAME", ""),
            "TITLE": d_header.get("TITLE", ""),
            "PERSK": d_header.get("PERSK", ""),
            "PERSA": d_header.get("PERSA", ""),
            "NO_VALIDATIONS": "X",

            "NAV_FIN_COST": [
                {
                    "AUFNR": cost_assign.get("AUFNR", ""),
                    "KOSTL": cost_assign.get("KOSTL", ""),
                    "PERCENT": cost_assign.get("PERCENT", ""),
                    "POSNR": project_wbs,
                    "POSNR2W": cost_assign.get("POSNR2W", ""),
                }
            ],

            # itinerary legs as-is, but without __metadata
            "NAV_FIN_TO_IT": _strip_metadata_list(travel_det_results),

            "NAV_FIN_J12WAY": [
                {
                    "PERNR": PERNR,
                    "REINR": j12way.get("REINR", ""),
                    "SOURCE": j12way.get("SOURCE", ""),
                    "SOURCE_CODE": j12way.get("SOURCE_CODE", ""),
                    "DESTINATION": j12way.get("DESTINATION", ""),
                    "DESTINATION_CODE": j12way.get("DESTINATION_CODE", ""),
                    "START_DATE": j12way.get("START_DATE", ""),
                    "START_TIME": _hhmmss(j12way.get("START_TIME", "")),
                    "RETURN_JRN_FLAG": j12way.get("RETURN_JRN_FLAG", ""),
                    "RETURN_DATE": j12way.get("RETURN_DATE", ""),
                    "RETURN_TIME": _hhmmss(j12way.get("RETURN_TIME", "")),
                    "ITENARY_RETURN_WAY": j12way.get("ITENARY_RETURN_WAY", ""),
                    "TWO_WAY_FLIGHT_SEARCH_LA": j12way.get("TWO_WAY_FLIGHT_SEARCH_LA", ""),
                    "TRAVEL_CLASS": j12way.get("TRAVEL_CLASS", ""),
                    "TRAVEL_CLASS_RET": j12way.get("TRAVEL_CLASS_RET", ""),
                }
            ] if j12way else [],

            # Journey-type–aware segments
            "NAV_FIN_COMING": nav_fin_coming,
            "NAV_FIN_GOING": nav_fin_going,
            "NAV_FIN_ONEWAY": nav_fin_oneway,

            "NAV_FIN_EMPFLIGHTS": [],  # populated below if preferred flights exist
            "NAV_FIN_FILES": [],

            "NAV_FIN_BOOK": [
                {
                    "SEARCHFORMDATA": d_reprice.get("SEARCHFORMDATA", ""),
                    "CARTDATA": d_reprice.get("CARTDATA", ""),
                    "CARTBOOKINGID": d_reprice.get("CARTBOOKINGID", ""),
                    "FNAME": d_header.get("FNAME", ""),
                    "LNAME": d_header.get("LNAME", ""),
                    "MOBILE": d_header.get("MOBILE", ""),
                    "EMAIL": d_header.get("EMAIL", ""),
                    "PAYMENTMODE": d_reprice.get("ENABLEDPAYMENTMEDIUM", ""),
                    "TITLE": d_header.get("TITLE", ""),
                }
            ],

            "NAV_FIN_REPRICE": [
                {
                    "OPTIONID": d_reprice.get("OPTIONID", ""),
                    "SEARCHFORMDATA": d_reprice.get("SEARCHFORMDATA", ""),
                    "FAREJUMPAMOUNT": d_reprice.get("FAREJUMPAMOUNT", ""),
                    "CARTDATA": d_reprice.get("CARTDATA", ""),
                    "CARTDATA2": d_reprice.get("CARTDATA2", ""),
                    "CARTSUMMARY": d_reprice.get("CARTSUMMARY", ""),
                    "CARTBOOKINGID": d_reprice.get("CARTBOOKINGID", ""),
                    "TERMSURL": d_reprice.get("TERMSURL", ""),
                    "ISNONREFUNDABLEFARE": d_reprice.get("ISNONREFUNDABLEFARE", ""),
                    "ENABLEDPAYMENTMEDIUM": d_reprice.get("ENABLEDPAYMENTMEDIUM", ""),
                    "PERNR": PERNR,
                    "TRIPID": d_reprice.get("TRIPID", ""),
                }
            ],

            "NAV_FIN_SEGMENT": _strip_metadata_list(reprice_segment_results),
        }

        # Build NAV_FIN_EMPFLIGHTS if preferred flights exist
        if es_pref or es_pref2:
            emp_flights = []
            for pref_flight in [es_pref, es_pref2]:
                if not pref_flight:
                    continue
                flight_entry = {}
                flight_keys = [
                    "PERNR",
                    "PRIARITY_FLIGHT",
                    "FLIGHT_NAME",
                    "FLIGHT_NUMBER",
                    "SOURCE_CITY",
                    "DESTN_CITY",
                    "VIA_FLIGHT",
                    "DEPT_DATE",
                    "DEP_TIME",
                    "ARR_DATE",
                    "ARR_TIME",
                    "AIR_FARE",
                    "FLIGHT_KEY",
                    "ITENARY",
                    "ORIGIN_CODE",
                    "DEST_CODE",
                    "ONE_WAY_OR_ROUND_TRIP",
                    "FARE_TYPE",
                    "FLIGHT_KEY2",
                    "AIR_FARE2",
                    "FARETYPE_CHECK",
                    "AIRLINE_LOGO",
                    "DEPART_HEAD",
                    "ARRIVAL_HEAD",
                    "NORMAL_FARE_HEAD",
                    "CORP_FARE_HEAD",
                    "OPTION_HEAD",
                    "REFUND_NONREFUND",
                    "CORP_REFUND_NONREFUND",
                    "DURATION",
                    "DURATION_HEAD",
                    "FLIGHT_TYPE",
                    "FLIGHT_CODE",
                    "OPTION_ID",
                    "ISFREEMEAL",
                    "ISSUPPORTFRIQUENTFLIER",
                    "DEPARTURETERMINAL",
                    "ARRIVALTERMINAL",
                    "FAREBASIS",
                    "BOOKINGCLASS",
                    "DISPLAYGROUP",
                    "ORIGIN_AIRPORT_NAME",
                    "DEST_AIRPORT_NAME",
                    "VIA_CITY_NAME",
                    "VIA_CITY_CODE",
                    "VIA_AIRPORT_NAME",
                ]
                for key in flight_keys:
                    flight_entry[key] = pref_flight.get(key, "")
                emp_flights.append(flight_entry)
            payload["NAV_FIN_EMPFLIGHTS"] = emp_flights

    except Exception as e:
        logger.error(f"Failed to build ES_FINAL flight payload: {e}")
        return {
            "success": False,
            "trip_id": None,
            "error": f"Failed to build payload: {e}",
            "status_code": None,
            "raw_response": None,
        }

    logger.info("ES_FINAL flight payload successfully created")
    logger.debug(f"Payload preview: {str(payload)[:1000]}...")

    # -------------------------------------------------------------------------
    # 5) Save payload (non-fatal if it fails)
    # -------------------------------------------------------------------------
    dynamic_file_path_payload = os.path.join(
        responses_dir, f"{PERNR}_es_final_flight_payload.json"
    )
    try:
        with open(dynamic_file_path_payload, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        logger.info("Saved ES_FINAL flight payload to %s", dynamic_file_path_payload)
    except Exception as e:
        logger.warning(
            "Failed to write ES_FINAL flight payload to %s: %s",
            dynamic_file_path_payload,
            e,
        )

    # -------------------------------------------------------------------------
    # 6) Call ES_FINAL API
    # -------------------------------------------------------------------------
    api_url = "https://emssq.mahindra.com/domestictravel/ES_FINAL?sap-client=500"
    try:
        logger.info("Posting payload to ES_FINAL API endpoint: %s", api_url)
        resp = requests.post(
            api_url,
            auth=auth,
            json=payload,
            headers=headers,
            timeout=(250, 300),  # (connect, read)
        )
        logger.info("Received response from ES_FINAL (status=%s)", resp.status_code)
    except requests.exceptions.Timeout as e:
        msg = f"ES_FINAL request timed out: {e}"
        logger.error(msg)
        return {
            "success": False,
            "trip_id": None,
            "error": msg,
            "status_code": None,
            "raw_response": None,
        }
    except requests.exceptions.RequestException as e:
        msg = f"ES_FINAL request failed: {e}"
        logger.error(msg)
        return {
            "success": False,
            "trip_id": None,
            "error": msg,
            "status_code": None,
            "raw_response": None,
        }

    # -------------------------------------------------------------------------
    # 7) Parse response and extract REINR
    # -------------------------------------------------------------------------
    dynamic_file_path_payload = os.path.join(responses_dir, f"{PERNR}_es_final_flight_response.json")
    with open(dynamic_file_path_payload, "w", encoding="utf-8") as f:
        json.dump(resp, f, ensure_ascii=False, indent=2)
        
    data = None
    text_head = (resp.text or "")[:2000]
    try:
        data = resp.json()
        logger.debug("ES_FINAL response preview: %s", str(data)[:1000])
    except ValueError:
        logger.debug("ES_FINAL raw response text: %s", text_head[:1000])

    reinr = None
    if isinstance(data, dict):
        try:
            reinr = safe_get_nested(data, "d", "REINR")
        except Exception:
            reinr = None
        if not reinr:
            d = data.get("d") if isinstance(data.get("d"), dict) else data
            results = d.get("results") if isinstance(d, dict) else None
            if isinstance(results, list) and results and isinstance(results[0], dict):
                reinr = results[0].get("REINR")

    # -------------------------------------------------------------------------
    # 8) Return & save REINR
    # -------------------------------------------------------------------------
    if resp.status_code in {200, 201}:
        if reinr:
            logger.info("SAP trip created successfully - trip_id (REINR): %s", reinr)
            try:
                saved = redis_mgr.save_json(
                    data={"trip_id": reinr},
                    user_id=PERNR,
                    session_id=session_id,
                    data_type="es_final_flight",
                )
                if saved:
                    logger.info(
                        "Saved REINR to Redis for PERNR=%s, session=%s",
                        PERNR,
                        session_id,
                    )
                else:
                    logger.warning(
                        "Redis save returned False for PERNR=%s, session=%s",
                        PERNR,
                        session_id,
                    )
            except Exception as e:
                logger.error(
                    "Error saving REINR to Redis (PERNR=%s, session=%s): %s",
                    PERNR,
                    session_id,
                    e,
                )

            return {
                "success": True,
                "trip_id": reinr,
                "error": None,
                "status_code": resp.status_code,
                "raw_response": data if data is not None else text_head,
            }

        logger.warning("SAP ES_FINAL success but REINR (trip_id) not found in response")
        return {
            "success": True,
            "trip_id": None,
            "error": "REINR missing in SAP response",
            "status_code": resp.status_code,
            "raw_response": data if data is not None else text_head,
        }

    reason = f"ES_FINAL failed status {resp.status_code}: {(text_head or '')[:800]}"
    logger.error(reason)
    return {
        "success": False,
        "trip_id": None,
        "error": reason,
        "status_code": resp.status_code,
        "raw_response": data if data is not None else text_head,
    }