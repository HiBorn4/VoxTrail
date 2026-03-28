from loguru import logger
import os
from dotenv import load_dotenv
import json
import requests
from requests.auth import HTTPBasicAuth
from pathlib import Path
from fuzzywuzzy import fuzz, process
from ...services.redis_manager import RedisJSONManager

load_dotenv()

ES_USERNAME = os.getenv("SAP_BASIC_USER")
ES_PASSWORD = os.getenv("SAP_BASIC_PASS")
EMP_API_KEY = os.getenv("EMP_API_KEY")

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
responses_dir = os.path.join(base_dir, "responses")
os.makedirs(responses_dir, exist_ok=True)

# file_path = os.path.join(responses_dir, "es_get_response.json")

# Initialize Redis manager once at the beginning
redis_mgr = RedisJSONManager()

def remove_metadata(obj):
    """
    Recursively remove all __metadata fields from a nested dictionary/list structure.
    """
    if isinstance(obj, dict):
        return {
            key: remove_metadata(value)
            for key, value in obj.items()
            if key != "__metadata" and not key.startswith("__")
        }
    elif isinstance(obj, list):
        # Process each item in the list
        return [remove_metadata(item) for item in obj]
    else:
        # Return primitive values as-is
        return obj


def enrich_with_airport_codes(travel: dict) -> dict:
    """
    Always enrich origin_code and destination_code using fuzzy matching
    against city_airport_data.json and pick the best (top-1) match,
    irrespective of similarity score.

    JSON structure:
        {
          "cities": [
            { "VALUE": "Mumbai", "CITY_AIRPORT": "BOM" },
            ...
          ]
        }
    """

    # ----------------------------
    # Load city-airport mapping
    # ----------------------------
    mapping_file = os.path.join(os.path.dirname(__file__), "city_airport_data.json")
    logger.info(f"Loading city-airport mapping from: {mapping_file}")

    try:
        with open(mapping_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.exception(f"Failed to load city_airport_data.json: {e}")
        return travel  # fail-safe: return original travel dict

    # Convert cities array to dictionary: { "Mumbai": "BOM", ... }
    city_airport_map: dict[str, str] = {}
    for city_entry in data.get("cities", []):
        city_name = city_entry.get("VALUE", "")
        airport_code = city_entry.get("CITY_AIRPORT", "")
        if city_name and airport_code:
            city_airport_map[city_name] = airport_code

    if not city_airport_map:
        logger.warning("city_airport_map is empty; cannot enrich airport codes.")
        return travel

    # ----------------------------
    # Helper to fuzzy match a city name
    # ----------------------------
    def _match_city(city_name: str, label: str) -> str:
        """
        Fuzzy match a city_name against the keys in city_airport_map and
        return the corresponding airport code of the best match.

        If no match is found (very unlikely with extractOne and non-empty map),
        returns the existing code (if any) or empty string.
        """
        city_name = (city_name or "").strip()
        if not city_name:
            logger.debug(f"No {label} city provided; skipping fuzzy match.")
            return travel.get(f"{label}_code", "")

        try:
            best = process.extractOne(
                city_name,
                city_airport_map.keys(),
                scorer=fuzz.ratio,
            )
        except Exception as e:
            logger.exception(f"Fuzzy matching failed for {label} city '{city_name}': {e}")
            return travel.get(f"{label}_code", "")

        if not best:
            logger.warning(f"No fuzzy match found for {label} city '{city_name}'.")
            return travel.get(f"{label}_code", "")

        best_city, score = best[0], best[1]
        code = city_airport_map.get(best_city, "")

        logger.info(
            f"Fuzzy matched {label} city '{city_name}' -> '{best_city}' "
            f"with score={score}, airport_code={code!r}"
        )
        return code or travel.get(f"{label}_code", "")

    # ----------------------------
    # Always fuzzy match and overwrite origin_code / destination_code
    # ----------------------------
    origin_city = travel.get("origin_city", "")
    dest_city = travel.get("destination_city", "")

    travel["origin_code"] = _match_city(origin_city, "origin")
    travel["destination_code"] = _match_city(dest_city, "destination")

    logger.debug(
        "Final enriched travel codes: origin_city=%r, origin_code=%r, "
        "destination_city=%r, destination_code=%r",
        origin_city,
        travel.get("origin_code"),
        dest_city,
        travel.get("destination_code"),
    )

    return travel



def post_es_get(travel_details: dict, PERNR: str, session_id: str):
    """
    Build and POST the ES_GET payload for NON-FLIGHT modes (Bus / Own Car / Company Arranged / Train).

    Parameters
    ----------
    travel_details : dict
        Trip preferences and metadata used to construct the ES_GET payload.
        Expected keys (subset):
          - "start_date", "end_date"           (YYYYMMDD)
          - "start_time", "end_time"           (HHMM | HH:MM | HH:MM:SS | HHMMSS)
          - "origin_city", "destination_city"
          - "country_beg", "country_end"
          - "origin_code", "destination_code"
          - "travel_mode", "travel_mode_code"
          - "travel_class", "travel_class_text"
          - "booking_method_code", "booking_method"
          - "travel_purpose"  (maps to REASON)
          - "journey_type"    ("One Way" | "Round Trip")

    Side Effects
    ------------
    - Logs the full payload and raw HTTP response.
    - Writes the API response (cleaned) to Redis and to `<PERNR>_es_get.json` in `responses/`.
    - Uses Redis `header` JSON to enrich payload.

    Returns
    -------
    dict
        Normalized result object:
        {
          "ok": bool,           # True if HTTP 201 Created, else False
          "reason": str | None  # None on success; error/diagnostic message on failure
        }
    """
    from datetime import datetime  # local import to avoid touching module-level imports

    logger.info("📡 Calling ES GET API (non-flight)")

    # -------------------------------------------------------------------------
    # Enrich origin_code / destination_code using city_airport_data.json
    # -------------------------------------------------------------------------
    travel_details = enrich_with_airport_codes(travel_details)

    # -------------------------------------------------------------------------
    # HTTP setup
    # -------------------------------------------------------------------------
    headers = {
        "Accept": "application/json",
        "X-Requested-With": "X",
    }
    # Only include Authorization if provided (same pattern as flight)
    if EMP_API_KEY:
        headers["Authorization"] = EMP_API_KEY

    auth = HTTPBasicAuth(ES_USERNAME, ES_PASSWORD) if (ES_USERNAME or ES_PASSWORD) else None

    # -------------------------------------------------------------------------
    # Local helpers (date + time normalization)
    # -------------------------------------------------------------------------
    def _det_date(val: str) -> str:
        """YYYYMMDD -> YYYY-MM-DDT00:00:00, else ''."""
        if not val or len(val) != 8 or not val.isdigit():
            return ""
        return f"{val[:4]}-{val[4:6]}-{val[6:]}T00:00:00"

    def _ensure_hhmmss(val: str) -> str:
        """Accept HHMM, HH:MM, HH:MM:SS, HHMMSS (or empty) → HHMMSS (fallback 000000)."""
        if not val:
            return "000000"
        v = str(val).strip()
        try:
            if ":" in v:
                parts = v.split(":")
                if len(parts) == 2:
                    dt = datetime.strptime(v, "%H:%M")
                else:
                    dt = datetime.strptime(v, "%H:%M:%S")
                return dt.strftime("%H%M%S")
            if len(v) == 4 and v.isdigit():
                return datetime.strptime(v, "%H%M").strftime("%H%M%S")
            if len(v) == 6 and v.isdigit():
                return v
        except Exception:
            pass
        return "000000"

    def _ensure_hh_colon_mm(val: str) -> str:
        """Accept common time formats → 'HH:MM' (fallback 00:00)."""
        hhmmss = _ensure_hhmmss(val)
        return f"{hhmmss[:2]}:{hhmmss[2:4]}" if hhmmss else "00:00"

    # -------------------------------------------------------------------------
    # Load ES header from Redis
    # -------------------------------------------------------------------------
    try:
        es_header = redis_mgr.load_json(
            user_id=PERNR,
            session_id=session_id,
            data_type="header",
        )
        logger.info(f"Successfully loaded ES header for {PERNR} with keys: {list(es_header.keys())}")
    except FileNotFoundError as e:
        logger.error(f"Header file not found for user {PERNR}: {e}")
        raise FileNotFoundError(f"Missing header file for {PERNR}: {e}")
    except PermissionError as e:
        logger.error(f"Permission denied while accessing header file for {PERNR}: {e}")
        raise PermissionError(f"Cannot access header for {PERNR} due to permission issue: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse header JSON for {PERNR}: {e}")
        fallback_path = os.path.join(responses_dir, f"{PERNR}_header.json")
        if os.path.exists(fallback_path):
            with open(fallback_path, "r", encoding="utf-8", errors="ignore") as f:
                snippet = f.read(1000)
            logger.debug(f"Header file snippet that failed to parse:\n{snippet}")
        raise ValueError(f"Invalid JSON in header for {PERNR}: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error while reading header for {PERNR}: {e}")
        raise RuntimeError(f"Unexpected error loading header for {PERNR}: {e}")

    # -------------------------------------------------------------------------
    # Normalize core fields
    # -------------------------------------------------------------------------
    start_date = travel_details.get("start_date", "")
    end_date = travel_details.get("end_date", "")
    start_time = travel_details.get("start_time", "")
    end_time = travel_details.get("end_time", "")

    time_beg_hhmm = _ensure_hh_colon_mm(start_time)
    time_end_hhmm = _ensure_hh_colon_mm(end_time)

    origin_city = travel_details.get("origin_city", "")
    destination_city = travel_details.get("destination_city", "")

    country_beg = travel_details.get("country_beg", "") or "IN"
    country_end = travel_details.get("country_end", "") or "IN"

    origin_code = travel_details.get("origin_code", "")
    destination_code = travel_details.get("destination_code", "")

    travel_mode_code = (
        travel_details.get("travel_mode_code")
        or travel_details.get("travel_mode")
        or ""
    )

    travel_class = travel_details.get("travel_class", "*")
    travel_class_text = travel_details.get("travel_class_text", "")

    journey_type_raw = (travel_details.get("journey_type") or "").strip().lower()
    is_one_way = journey_type_raw.startswith("one")
    is_round_trip = journey_type_raw.startswith("round")

    # For safety: if journey_type is missing/unknown, default to round trip (old behaviour was 2 legs)
    if not is_one_way and not is_round_trip:
        logger.warning(
            "journey_type not explicitly set to 'One Way' or 'Round Trip'; "
            "defaulting to round trip payload with 2 legs."
        )
        is_round_trip = True

    # -------------------------------------------------------------------------
    # Build NAV_TRAVELDET based on journey_type
    # -------------------------------------------------------------------------
    nav_travel_det = []

    # Leg 1: Outbound (origin -> destination)
    leg_outbound = {
        "PERNR": PERNR,
        "DATE_BEG": _det_date(start_date),
        "TIME_BEG": _ensure_hhmmss(start_time),
        "DATE_END": _det_date(end_date),
        "TIME_END": _ensure_hhmmss(end_time),
        "LOCATION_BEG": origin_city,
        "COUNTRY_BEG": country_beg,
        "ORIGIN_CODE": origin_code,
        "LOCATION_END": destination_city,
        "COUNTRY_END": country_end,
        "DEST_CODE": destination_code,
        "TRAVEL_MODE": travel_mode_code,
        "TRAVEL_MODE_CODE": travel_mode_code,
        "TRAVEL_CLASS_TEXT": travel_class_text,
        "TRAVEL_CLASS": travel_class,
        "PREFERRED_FLIGHT": "",
        "MRC_1_2_WAY_FLAG": "",
        "ITENARY": "",
    }
    nav_travel_det.append(leg_outbound)

    # Leg 2: Return (destination -> origin) only for Round Trip
    if is_round_trip:
        leg_return = {
            "PERNR": PERNR,
            "DATE_BEG": _det_date(end_date),
            "TIME_BEG": _ensure_hhmmss(end_time),
            "DATE_END": _det_date(end_date),
            "TIME_END": "000000",
            "LOCATION_BEG": destination_city,
            "COUNTRY_BEG": country_end,
            "ORIGIN_CODE": destination_code,
            "LOCATION_END": origin_city,
            "COUNTRY_END": country_beg,
            "DEST_CODE": origin_code,
            "TRAVEL_MODE": travel_mode_code,
            "TRAVEL_MODE_CODE": travel_mode_code,
            # Your roundtrip sample keeps TRAVEL_CLASS, but TRAVEL_CLASS_TEXT empty for return
            "TRAVEL_CLASS_TEXT": "",
            "TRAVEL_CLASS": travel_class,
            "PREFERRED_FLIGHT": "",
            "MRC_1_2_WAY_FLAG": "",
            "ITENARY": "",
        }
        nav_travel_det.append(leg_return)

    # -------------------------------------------------------------------------
    # Final ES_GET payload (aligned with your car one-way / roundtrip samples)
    # -------------------------------------------------------------------------
    payload = {
        "FLAG": "",
        "PERNR": PERNR,
        "REINR": es_header.get("REINR", "0000000000"),
        "ACTION": "",
        "SEARCHVISIBLE": es_header.get("SEARCHVISIBLE", ""),
        "SEARCHMANDT": es_header.get("SEARCHMANDT", ""),
        "REASON": travel_details.get("travel_purpose", ""),
        "MOBILE": es_header.get("MOBILE", ""),
        "TRAVADV": es_header.get("TRAVADV", ""),
        "ADDADV": es_header.get("ADDADV", ""),
        "PAYMODE": es_header.get("PAYMODE", ""),
        "LOCSTART": "",
        "DATE_BEG": start_date,
        "DATE_END": end_date,
        "TIME_BEG": time_beg_hhmm,
        "TIME_END": time_end_hhmm,
        "LOC_START": origin_city,
        "LOCATION_END": destination_city,
        "OTHERREASON": "",
        "OLOC_START": "",
        "OLOCATION_END": "",
        "PERSK": es_header.get("PERSK", ""),
        "PERSA": es_header.get("PERSA", ""),
        "NAV_TRAVELDET": nav_travel_det,
        "NAV_J12WAY": [],
        "NAV_GETSEARCH": [],
        "NAV_APPROVERS": [],
        "NAV_PREFERRED_FLIGHT": [],
        "NAV_REPRICE": [],
    }

    logger.warning(f"ES_GET payload (non-flight): {payload}")

    # -------------------------------------------------------------------------
    # Call ES_GET API and persist cleaned response
    # -------------------------------------------------------------------------
    try:
        api_url = "https://emssq.mahindra.com/domestictravel/ES_GET?sap-client=500"

        # Save payload for debugging
        dynamic_file_path_payload = os.path.join(responses_dir, f"{PERNR}_es_get_payload.json")
        with open(dynamic_file_path_payload, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        resp = requests.post(api_url, auth=auth, json=payload, headers=headers, timeout=(500, 1000))

        logger.info("ES_GET raw response (%s): %s", resp.status_code, resp.text)

        # Save cleaned response
        dynamic_file_path = os.path.join(responses_dir, f"{PERNR}_es_get_response.json")

        try:
            response_data = resp.json()
            cleaned_data = remove_metadata(response_data)

            # Save to Redis
            success = redis_mgr.save_json(
                data=cleaned_data,
                user_id=PERNR,
                session_id=session_id,
                data_type="es_get",
            )

            # Also save to file as backup
            with open(dynamic_file_path, "w", encoding="utf-8") as f:
                json.dump(cleaned_data, f, ensure_ascii=False, indent=2)

            if success:
                logger.info(f"Saved cleaned ES_GET response to Redis for PERNR: {PERNR}")

        except ValueError:
            logger.error("ES_GET response is not valid JSON")

    except requests.exceptions.RequestException as e:
        logger.error(f"ES_GET request failed: {e}")
        return {"ok": False, "reason": f"ES_GET request failed: {e}"}

    if resp.status_code == 201:
        logger.info("ES_GET (non-flight) posted successfully (201).")
        return {"ok": True, "reason": None}
    else:
        reason = f"ES_GET failed status {resp.status_code}: {resp.text[:400]}"
        logger.error(reason)
        return {"ok": False, "reason": reason}
