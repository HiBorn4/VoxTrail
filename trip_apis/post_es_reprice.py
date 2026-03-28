from loguru import logger
import os
from dotenv import load_dotenv
import json
import requests
from requests.auth import HTTPBasicAuth
from pathlib import Path
from .post_es_get import remove_metadata
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

def post_es_reprice(PERNR: str, session_id: str, journey_type: str):
    """
    Build and POST the ES_REPRICE payload for flight repricing.

    This function:
    1. Loads the user's selected preferred flights from Redis ("preffered_flights")
    2. Uses the provided journey_type to validate flight count:
       - "One Way" → expects 1 flight
       - "Round Trip" → expects 2 flights
    3. Builds the ES_REPRICE payload with NAV_REP_FLT array
    4. Posts to SAP ES_REPRICE endpoint
    5. Saves the cleaned response back to Redis as "es_reprice"

    Parameters
    ----------
    PERNR : str
        Personnel number / employee identifier for the logged-in user.

    session_id : str
        Session identifier used as part of the Redis key-space to load
        the correct preferred flights.

    journey_type : str
        Journey type preference: "One Way" | "Round Trip".
        This determines how many flights are expected in the repricing payload.

    Returns
    -------
    dict
        Normalized result object:
        {
          "ok": bool,           # True if HTTP 200 or 201, else False
          "reason": str | None  # None on success; error/diagnostic message on failure
        }

    Side Effects
    ------------
    - Reads from Redis:
        * "preffered_flights" → user's selected flights from frontend
    - Writes to Redis:
        * "es_reprice" → cleaned ES_REPRICE response
    - Writes to disk (responses_dir):
        * {PERNR}_es_reprize_payload.json → outbound payload for debugging
        * {PERNR}_es_get_reprize_response.json → cleaned response for debugging

    Notes
    -----
    - Success criteria: HTTP 200 or 201 from the ES_REPRICE endpoint.
    - On transport errors (timeouts, connection errors, etc.), returns {"ok": False, "reason": "..."}.
    - Journey type validation ensures data integrity before calling SAP.
    """

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Requested-With": "X",
        "Authorization": EMP_API_KEY,
    }
    auth = HTTPBasicAuth(ES_USERNAME, ES_PASSWORD) if (ES_USERNAME or ES_PASSWORD) else None

    logger.info("📡 Calling ES REPRICE API:")
    logger.info(
        f"Starting ES_REPRICE process | PERNR={PERNR} session_id={session_id} journey_type={journey_type}"
    )

    # -------------------------------------------------------------------------
    # 1) Validate journey_type parameter
    # -------------------------------------------------------------------------
    journey_type_norm = (journey_type or "").strip()
    
    if journey_type_norm not in {"One Way", "Round Trip"}:
        logger.warning(
            f"Invalid journey_type received: '{journey_type}'. Defaulting to 'Round Trip'"
        )
        journey_type_norm = "Round Trip"

    is_one_way = (journey_type_norm == "One Way")
    expected_flight_count = 1 if is_one_way else 2

    logger.info(
        f"Journey type validated: '{journey_type_norm}' → expecting {expected_flight_count} flight(s)"
    )

    # -------------------------------------------------------------------------
    # 2) Load preferred flights from Redis
    # -------------------------------------------------------------------------
    try:
        selected = redis_mgr.load_json(
            user_id=PERNR, 
            session_id=session_id, 
            data_type="preffered_flights"
        ) or []
        
        logger.info(
            f"Loaded preferred flights from Redis | PERNR={PERNR} session_id={session_id} count={len(selected)}"
        )
    except Exception as e:
        logger.error(f"Failed to load preffered_flights from Redis: {e}")
        return {
            "ok": False, 
            "reason": f"Failed to load preferred flights from Redis: {e}"
        }

    if not isinstance(selected, list) or not selected:
        logger.warning(f"No preferred flights found in Redis | PERNR={PERNR} session_id={session_id}")
        return {
            "ok": False, 
            "reason": "No preferred flights found in Redis (preffered_flights)."
        }

    # -------------------------------------------------------------------------
    # 3) Validate flight count matches journey type
    # -------------------------------------------------------------------------
    actual_flight_count = len(selected)

    if actual_flight_count != expected_flight_count:
        error_msg = (
            f"Flight count mismatch: journey_type='{journey_type_norm}' expects {expected_flight_count} flight(s), "
            f"but {actual_flight_count} flight(s) were selected."
        )
        logger.error(error_msg)
        return {
            "ok": False,
            "reason": error_msg
        }

    logger.info(
        f"✅ Flight count validation passed: {actual_flight_count} flight(s) for '{journey_type_norm}' journey"
    )

    # -------------------------------------------------------------------------
    # 4) Build NAV_REP_FLT from selected flights
    # -------------------------------------------------------------------------
    nav_rep_flt = []
    for idx, item in enumerate(selected[:expected_flight_count], start=1):
        if not isinstance(item, dict):
            logger.warning(f"Preferred flight at index {idx-1} is not a dict, skipping: {type(item)}")
            continue
        
        flt = dict(item)  # shallow copy
        
        # Ensure PERNR is set
        if not flt.get("PERNR"):
            flt["PERNR"] = PERNR
            logger.debug(f"Added PERNR to flight {idx}: {PERNR}")
        
        nav_rep_flt.append(flt)
        logger.debug(
            f"Added flight {idx} to NAV_REP_FLT | "
            f"FLIGHT_NAME={flt.get('FLIGHT_NAME')} "
            f"FLIGHT_NUMBER={flt.get('FLIGHT_NUMBER')} "
            f"SOURCE_CITY={flt.get('SOURCE_CITY')} → "
            f"DESTN_CITY={flt.get('DESTN_CITY')}"
        )

    if not nav_rep_flt:
        logger.error("NAV_REP_FLT is empty after processing preferred flights")
        return {
            "ok": False, 
            "reason": "Preferred flights list is malformed or empty."
        }

    if len(nav_rep_flt) != expected_flight_count:
        logger.error(
            f"After processing, NAV_REP_FLT has {len(nav_rep_flt)} flight(s), "
            f"expected {expected_flight_count}"
        )
        return {
            "ok": False,
            "reason": f"Flight processing resulted in {len(nav_rep_flt)} valid flight(s), expected {expected_flight_count}"
        }

    logger.info(f"Built NAV_REP_FLT with {len(nav_rep_flt)} flight(s)")

    # -------------------------------------------------------------------------
    # 5) Compose ES_REPRICE payload
    # -------------------------------------------------------------------------
    payload = {
        "PERNR": PERNR,
        "NAV_REP_FLT": nav_rep_flt,
        "NAV_REPRICE": [],
    }

    logger.info(f"ES_REPRICE payload composed: PERNR={PERNR}, NAV_REP_FLT_count={len(nav_rep_flt)}")

    # -------------------------------------------------------------------------
    # 6) Save payload to disk (non-fatal if it fails)
    # -------------------------------------------------------------------------
    try:
        dynamic_file_path_payload = os.path.join(responses_dir, f"{PERNR}_es_reprize_payload.json")
        with open(dynamic_file_path_payload, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved ES_REPRICE outbound payload → {dynamic_file_path_payload}")
    except Exception as e:
        logger.warning(f"Could not write ES_REPRICE payload to disk: {e}")

    # -------------------------------------------------------------------------
    # 7) POST to ES_REPRICE endpoint
    # -------------------------------------------------------------------------
    api_url = "https://emssq.mahindra.com/domestictravel/ES_REPRICE?sap-client=500"
    
    try:
        logger.info(f"Posting to ES_REPRICE: {api_url}")
        resp = requests.post(
            api_url, 
            auth=auth, 
            json=payload, 
            headers=headers, 
            timeout=200
        )
        logger.info(f"Received response from ES_REPRICE | status_code={resp.status_code}")
    except requests.exceptions.Timeout as e:
        error_msg = f"ES_REPRICE request timed out: {e}"
        logger.error(error_msg)
        return {"ok": False, "reason": error_msg}
    except requests.exceptions.RequestException as e:
        error_msg = f"ES_REPRICE request failed: {e}"
        logger.error(error_msg)
        return {"ok": False, "reason": error_msg}

    # -------------------------------------------------------------------------
    # 8) Parse and save response
    # -------------------------------------------------------------------------
    try:
        response_data = resp.json()
        logger.debug(f"ES_REPRICE response parsed as JSON | keys={list(response_data.keys())}")
    except ValueError as e:
        logger.error(f"ES_REPRICE response is not valid JSON: {e}")
        logger.debug(f"Raw response text (first 500 chars): {resp.text[:500]}")
        return {
            "ok": False,
            "reason": f"ES_REPRICE returned invalid JSON: {e}"
        }

    # Clean metadata from response
    try:
        cleaned_data = remove_metadata(response_data)
        logger.debug("ES_REPRICE response cleaned (metadata removed)")
    except Exception as e:
        logger.warning(f"Failed to clean metadata from ES_REPRICE response: {e}")
        cleaned_data = response_data

    dynamic_file_path_payload = os.path.join(responses_dir, f"{PERNR}_es_reprize_response.json")
    with open(dynamic_file_path_payload, "w", encoding="utf-8") as f:
        json.dump(cleaned_data, f, ensure_ascii=False, indent=2)

    # Save cleaned response to Redis
    try:
        success = redis_mgr.save_json(
            data=cleaned_data,
            user_id=PERNR,
            session_id=session_id,
            data_type="es_reprice"
        )
        if success:
            logger.info(f"✅ Saved cleaned ES_REPRICE response to Redis | PERNR={PERNR} session_id={session_id}")
        else:
            logger.warning(f"Redis save_json returned False for es_reprice | PERNR={PERNR} session_id={session_id}")
    except Exception as e:
        logger.error(f"Failed to save ES_REPRICE response to Redis: {e}")
        # Continue even if Redis save fails (non-fatal)

    # Optional: Save to disk for debugging
    try:
        dynamic_es_get_reprice_response = os.path.join(
            responses_dir, 
            f"{PERNR}_es_get_reprize_response.json"
        )
        with open(dynamic_es_get_reprice_response, "w", encoding="utf-8") as f:
            json.dump(cleaned_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved ES_REPRICE response to disk → {dynamic_es_get_reprice_response}")
    except Exception as e:
        logger.warning(f"Could not write ES_REPRICE response to disk: {e}")

    # -------------------------------------------------------------------------
    # 9) Validate SAP response and return result
    # -------------------------------------------------------------------------
    if resp.status_code in (200, 201):
        logger.info(f"✅ ES_REPRICE posted successfully | status_code={resp.status_code}")
        
        # Optional: Check for business errors in SAP response
        try:
            d = cleaned_data.get("d", {}) if isinstance(cleaned_data, dict) else {}
            validation_chk = (d.get("VALIDATION_CHK") or "").strip().upper()
            validation_msg = (d.get("VALIDATION_MSG") or "").strip()
            validation_type = (d.get("VALIDATION_TYPE") or "").strip()
            
            if validation_chk == "E":
                logger.warning(
                    f"⚠️ ES_REPRICE returned validation error | "
                    f"VALIDATION_MSG={validation_msg} VALIDATION_TYPE={validation_type}"
                )
                return {
                    "ok": False,
                    "reason": f"ES_REPRICE validation failed: {validation_msg or 'Unknown error'}"
                }
        except Exception as e:
            logger.debug(f"Could not check for SAP validation errors: {e}")
        
        return {"ok": True, "reason": None}
    else:
        reason = f"ES_REPRICE failed | status_code={resp.status_code} | response={resp.text[:400]}"
        logger.error(reason)
        return {"ok": False, "reason": reason}