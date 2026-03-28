from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, Optional, Tuple, List
import concurrent.futures
from fastapi import HTTPException
import requests
from travel_assist_agentic_bot.tools.function_tools.sap_csrf import get_csrf_token
from loguru import logger  # type: ignore
from dotenv import load_dotenv  # type: ignore
from fuzzywuzzy import fuzz, process  # type: ignore
from travel_assist_agentic_bot.services.redis_manager import RedisJSONManager
# from travel_assist_agentic_bot.services.gcs_storage import upload_json_to_gcs_for_user

# -----------------------------------------------------------------------------
# Env & constants
# -----------------------------------------------------------------------------
load_dotenv()

SAP_CLIENT = os.getenv("SAP_CLIENT", "500")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESPONSES_DIR = os.path.join(BASE_DIR, "responses")
os.makedirs(RESPONSES_DIR, exist_ok=True)
BEARER_TOKEN_OLD = os.getenv("SAP_BEARER_TOKEN")

# IMPORTANT: Single, correct endpoint (no extra path concatenation)
API_URL = "https://emss.mahindra.com/sap/opu/odata/sap/ZHR_DOMESTIC_TRAVEL_SRV/ES_GET"

# Initialize Redis manager once
redis_mgr = RedisJSONManager()

def split_flights_by_direction(
    flights: List[Dict[str, Any]],
    origin_code: str,
    destination_code: str,
) -> Dict[str, List[List[Dict[str, Any]]]]:
    """
    Split flights into [outgoing, return] based on airport codes.

    outgoing:      ORIGIN_CODE == origin_code       and DEST_CODE == destination_code
    return_flights: ORIGIN_CODE == destination_code and DEST_CODE == origin_code
    """
    outgoing: List[Dict[str, Any]] = []
    return_flights: List[Dict[str, Any]] = []

    origin_lower = (origin_code or "").strip().lower()
    dest_lower = (destination_code or "").strip().lower()

    for flight in flights:
        src_code = (flight.get("ORIGIN_CODE") or "").strip().lower()
        dst_code = (flight.get("DEST_CODE") or "").strip().lower()

        if src_code == origin_lower and dst_code == dest_lower:
            outgoing.append(flight)
        elif src_code == dest_lower and dst_code == origin_lower:
            return_flights.append(flight)

    return {"results": [outgoing, return_flights]}


def _infer_direction_from_payload(payload: Dict[str, Any]) -> Tuple[str, str]:
    """
    Infer (origin_code, destination_code) from payload.NAV_TRAVELDET.
    Uses first leg: ORIGIN_CODE -> DEST_CODE.
    """
    legs = payload.get("NAV_TRAVELDET", [])
    if isinstance(legs, dict) and "results" in legs:
        legs = legs["results"]

    if not legs:
        return "", ""

    first = legs[0]
    origin_code = (first.get("ORIGIN_CODE") or "").strip()
    dest_code = (first.get("DEST_CODE") or "").strip()
    return origin_code, dest_code

def remove_metadata(obj):
    if isinstance(obj, dict):
        return {
            key: remove_metadata(value)
            for key, value in obj.items()
            if key != "__metadata" and not key.startswith("__")
        }
    elif isinstance(obj, list):
        return [remove_metadata(item) for item in obj]
    else:
        return obj

def get_sap_bearer_token(user_id: str) -> str:
    """
    Fetch the final SAP bearer token for a given user from Redis.

    Token is stored once per user under:
        user_id = <pernr>, session_id = "sap_global", data_type = "sap_bearer_token"
    """
    sap_data: Optional[Dict[str, Any]] = redis_mgr.load_json(
        user_id=str(user_id),
        session_id="sap_global",
        data_type="sap_bearer_token",
    )

    if not sap_data:
        raise HTTPException(
            status_code=401,
            detail="SAP bearer token not found. Please login again."
        )

    access_token = sap_data.get("access_token")
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="SAP bearer token is invalid or missing. Please login again."
        )

    return access_token

# -----------------------------------------------------------------------------
# Small utils
# -----------------------------------------------------------------------------
def _det_date(val: str) -> str:
    """YYYYMMDD -> YYYY-MM-DDT00:00:00, else ''."""
    if not val or len(val) != 8 or not val.isdigit():
        return ""
    return f"{val[:4]}-{val[4:6]}-{val[6:]}T00:00:00"


def _ensure_hhmmss(val: str) -> str:
    """Accept HHMM, HH:MM, HH:MM:SS, HHMMSS (or empty) → HHMMSS (fallback 000000)."""
    if not val:
        return "000000"
    v = val.strip()
    try:
        if ":" in v:
            parts = v.split(":")
            if len(parts) == 2:
                dt = datetime.strptime(v, "%H:%M")
            else:
                dt = datetime.strptime(v, "%H:%M:%S")
            return dt.strftime("%H%M%S")
        # Already HHMM or HHMMSS
        if len(v) == 4:
            return v + "00"
        if len(v) == 6:
            return v
    except Exception:
        pass
    return "000000"


def _ensure_hh_colon_mm(val: str) -> str:
    """Accept common time formats → 'HH:MM' (fallback 00:00)."""
    hhmmss = _ensure_hhmmss(val)
    return f"{hhmmss[:2]}:{hhmmss[2:4]}" if hhmmss else "00:00"


def _norm(s: Optional[str]) -> str:
    return (s or "").strip()


# -----------------------------------------------------------------------------
# Data classes for flight de-duplication / reporting
# -----------------------------------------------------------------------------
@dataclass
class FlightKey:
    """
    Represents a deduplication key for a flight.
    Adjust fields as needed (e.g. ignore fare differences).
    """
    departure_datetime: str
    arrival_datetime: str
    origin: str
    destination: str
    airline: str
    flight_number: str
    travel_class: str

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "FlightKey":
        return cls(
            departure_datetime=_norm(row.get("DEP_DATETIME", "")),
            arrival_datetime=_norm(row.get("ARR_DATETIME", "")),
            origin=_norm(row.get("ORIGIN", "")),
            destination=_norm(row.get("DESTINATION", "")),
            airline=_norm(row.get("CARRIER", "")),
            flight_number=_norm(row.get("FLTNO", "")),
            travel_class=_norm(row.get("CLASS", "")),
        )


@dataclass
class FlightDedupeReport:
    total_rows: int
    unique_rows: int
    duplicates_removed: int
    sample_keys: List[FlightKey]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_rows": self.total_rows,
            "unique_rows": self.unique_rows,
            "duplicates_removed": self.duplicates_removed,
            "sample_keys": [asdict(k) for k in self.sample_keys],
        }


def _dedupe_and_report(es_get_cleaned: Dict[str, Any]) -> FlightDedupeReport:
    """
    De-duplicate flights from ES_GET "NAV_GETSEARCH" table
    and return a report. We assume es_get_cleaned is already metadata-stripped.
    """

    d = es_get_cleaned.get("d", {})
    nav_getsearch = d.get("NAV_GETSEARCH", {})
    if isinstance(nav_getsearch, dict):
        rows = nav_getsearch.get("results", [])
    elif isinstance(nav_getsearch, list):
        rows = nav_getsearch
    else:
        rows = []

    logger.info(f"🔍 NAV_GETSEARCH total rows before dedupe: {len(rows)}")

    unique_map: Dict[FlightKey, Dict[str, Any]] = {}
    for r in rows:
        key = FlightKey.from_row(r)
        if key not in unique_map:
            unique_map[key] = r

    unique_rows = list(unique_map.values())
    duplicates_removed = len(rows) - len(unique_rows)
    logger.info(
        f"✂️  Deduplicated flights: {len(rows)} → {len(unique_rows)} "
        f"(removed {duplicates_removed} duplicates)"
    )

    sample_keys = list(unique_map.keys())[:10]
    return FlightDedupeReport(
        total_rows=len(rows),
        unique_rows=len(unique_rows),
        duplicates_removed=duplicates_removed,
        sample_keys=sample_keys,
    )


# -----------------------------------------------------------------------------
# Enrich travel with airport codes (like post_es_get)
# -----------------------------------------------------------------------------
def enrich_with_airport_codes(travel: Dict[str, Any]) -> Dict[str, Any]:
    """
    Use city_airport_data.json to fill in origin_code/destination_code if missing,
    using fuzzy matching.
    """
    mapping_file = os.path.join(os.path.dirname(__file__), "city_airport_data.json")
    logger.info(f"Loading city-airport mapping from: {mapping_file}")

    try:
        with open(mapping_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.exception(f"Failed to load city_airport_data.json: {e}")
        return travel

    city_airport_map: Dict[str, str] = {}
    for c in data.get("cities", []):
        city = (c.get("VALUE") or "").strip()
        code = (c.get("CITY_AIRPORT") or "").strip()
        if city and code:
            city_airport_map[city] = code

    if not travel.get("origin_code"):
        oc = (travel.get("origin_city") or "").strip()
        if oc:
            match: Optional[Tuple[str, int]] = process.extractOne(
                oc, city_airport_map.keys(), scorer=fuzz.ratio
            )
            if match and match[1] >= 80:
                travel["origin_code"] = city_airport_map[match[0]]
                logger.info(
                    f"Added origin_code: {oc} -> {travel['origin_code']} (score={match[1]})"
                )

    if not travel.get("destination_code"):
        dc = (travel.get("destination_city") or "").strip()
        if dc:
            match = process.extractOne(
                dc, city_airport_map.keys(), scorer=fuzz.ratio
            )
            if match and match[1] >= 80:
                travel["destination_code"] = city_airport_map[match[0]]
                logger.info(
                    f"Added destination_code: {dc} -> {travel['destination_code']} (score={match[1]})"
                )

    return travel


# -----------------------------------------------------------------------------
# OData list helpers
# -----------------------------------------------------------------------------
def _extract_list(section: Any) -> List[Dict[str, Any]]:
    """Return list from SAP OData shape: list or {'results':[...]}."""
    if isinstance(section, dict) and "results" in section and isinstance(section["results"], list):
        return section["results"]
    return section if isinstance(section, list) else []


def _flight_key(row: Dict[str, Any]) -> Tuple[str, str, str, str, str, str, str]:
    """
    A more verbose key for intersection between preferred flights, etc.
    """
    return (
        _norm(row.get("DEP_DATETIME")),
        _norm(row.get("ARR_DATETIME")),
        _norm(row.get("ORIGIN")),
        _norm(row.get("DESTINATION")),
        _norm(row.get("CARRIER")),
        _norm(row.get("FLTNO")),
        _norm(row.get("CLASS")),
    )


# -----------------------------------------------------------------------------
# Payload builder
# -----------------------------------------------------------------------------
def _build_payload(
    PERNR: str,
    travel: Dict[str, Any],
    es_header: Dict[str, Any],
    is_round_trip: bool,
) -> Dict[str, Any]:
    """
    Build ES_GET payload specifically for **flight** search (one-way or round-trip).
    This reuses the structure pattern you tested manually.
    """

    start_date = travel.get("start_date", "")
    end_date = travel.get("end_date", "") if is_round_trip else travel.get("start_date", "")
    start_time_str = travel.get("start_time", "")
    end_time_str = travel.get("end_time", "")

    origin_city = travel.get("origin_city", "")
    destination_city = travel.get("destination_city", "")
    origin_code = travel.get("origin_code", "")
    destination_code = travel.get("destination_code", "")
    country_beg = travel.get("country_beg", "IN")
    country_end = travel.get("country_end", "IN")

    travel_mode = travel.get("travel_mode_code") or travel.get("travel_mode") or "F"
    travel_class = travel.get("travel_class", "EC")
    travel_class_text = travel.get("travel_class_text", "Economy Class")
    ticket_method = travel.get("ticket_method") or "1"
    ticket_method_text = travel.get("ticket_method_text") or "Self Booked"

    leg_1 = {
        "PERNR": PERNR,
        "DATE_BEG": _det_date(start_date),
        "TIME_BEG": _ensure_hhmmss(start_time_str),
        "DATE_END": _det_date(end_date),
        "TIME_END": _ensure_hhmmss(end_time_str),
        "LOCATION_BEG": origin_city,
        "COUNTRY_BEG": country_beg,
        "ORIGIN_CODE": origin_code,
        "LOCATION_END": destination_city,
        "COUNTRY_END": country_end,
        "DEST_CODE": destination_code,
        "TRAVEL_MODE": "F",
        "TRAVEL_MODE_CODE": "F",
        "TRAVEL_CLASS": "EC",
        "TRAVEL_CLASS_TEXT": "Economy Class",
        "PREFERRED_FLIGHT": "",
        "MRC_1_2_WAY_FLAG": "",
        "ITENARY": "",
        "TICKET_METHOD": "3",
        "TICK_METH_TXT": "Company Booked",
    }

    nav_traveldet = [leg_1]

    if is_round_trip:
        leg_2 = {
            "PERNR": PERNR,
            "DATE_BEG": _det_date(end_date),
            "TIME_BEG": _ensure_hhmmss(end_time_str),
            "DATE_END": _det_date(end_date),
            "TIME_END": "000000",
            "LOCATION_BEG": destination_city,
            "COUNTRY_BEG": country_end,
            "ORIGIN_CODE": destination_code,
            "LOCATION_END": origin_city,
            "COUNTRY_END": country_beg,
            "DEST_CODE": origin_code,
            "TRAVEL_MODE": "F",
            "TRAVEL_MODE_CODE": "F",
            "TRAVEL_CLASS": "EC",
            "TRAVEL_CLASS_TEXT": "Economy Class",
            "PREFERRED_FLIGHT": "",
            "MRC_1_2_WAY_FLAG": "",
            "ITENARY": "",
            "TICKET_METHOD": "3",
            "TICK_METH_TXT": "Company Booked"
        }
        nav_traveldet.append(leg_2)

    payload = {
        "FLAG": "",
        "PERNR": PERNR,
        "REINR": es_header.get("REINR", "0000000000"),
        "ACTION": "",
        "SEARCHVISIBLE": es_header.get("SEARCHVISIBLE", "X"),
        "SEARCHMANDT": es_header.get("SEARCHMANDT", "X"),
        "REASON": travel.get("travel_purpose", ""),
        "MOBILE": es_header.get("MOBILE", ""),
        "TRAVADV": es_header.get("TRAVADV", ""),
        "ADDADV": es_header.get("ADDADV", ""),
        "PAYMODE": es_header.get("PAYMODE", ""),
        "LOCSTART": "",
        "DATE_BEG": start_date,
        "DATE_END": end_date,
        "TIME_BEG": _ensure_hh_colon_mm(start_time_str),
        "TIME_END": _ensure_hh_colon_mm(end_time_str),
        "LOC_START": origin_city,
        "LOCATION_END": destination_city,
        "OTHERREASON": "",
        "OLOC_START": "",
        "OLOCATION_END": "",
        "PERSK": es_header.get("PERSK", ""),
        "PERSA": es_header.get("PERSA", ""),
        "NAV_TRAVELDET": nav_traveldet,
        "NAV_J12WAY": [],
        "NAV_GETSEARCH": [],
        "NAV_APPROVERS": [],
        "NAV_PREFERRED_FLIGHT": [],
        "NAV_REPRICE": [],
    }

    return payload


# -----------------------------------------------------------------------------
# ES_GET caller (single)
# -----------------------------------------------------------------------------
def _call_es_get_api(
    payload: Dict[str, Any],
    headers: Dict[str, str],
    cookies: Dict[str, Any],
    trip_type: str
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Make single ES_GET API call.
    Returns: (response_dict, error_msg)
    """
    try:
        logger.info(f"🚀 Calling ES_GET API for {trip_type}")
        resp = requests.post(
            API_URL,
            json=payload,
            headers=headers,
            cookies=cookies,
            params={"sap-client": SAP_CLIENT},
            timeout=1000,
        )

        if resp.status_code not in {200, 201}:
            error = f"ES_GET {trip_type} failed ({resp.status_code}): {resp.text[:400]}"
            logger.error(error)
            return None, error

        response_data = resp.json()
        cleaned = remove_metadata(response_data) or {}
        d = cleaned.get("d", {}) or {}

        # Check for validation errors
        validation_chk = (d.get("VALIDATION_CHK") or "").strip()
        validation_msg = (d.get("VALIDATION_MSG") or "").strip()
        validation_type = (d.get("VALIDATION_TYPE") or "").strip()

        if validation_chk.upper() == "E":
            msg = validation_msg or f"{trip_type} validation failed."
            logger.warning(
                f"❌ Validation error for {trip_type}: {msg} (type: {validation_type})"
            )
            return None, msg

        # Check if we got any flight results
        nav_getsearch = d.get("NAV_GETSEARCH", [])
        if isinstance(nav_getsearch, dict):
            nav_getsearch = nav_getsearch.get("results", [])

        flight_count = len(nav_getsearch) if isinstance(nav_getsearch, list) else 0
        logger.info(f"✅ {trip_type} search returned {flight_count} flights")

        # Log warning if no flights but no validation error
        if flight_count == 0 and validation_chk.upper() != "E":
            logger.warning(
                f"⚠️  {trip_type} search returned 0 flights but no validation error. Check payload."
            )

        return d, None

    except requests.exceptions.RequestException as e:
        error = f"ES_GET {trip_type} request failed: {e}"
        logger.error(error)
        return None, error
    except Exception as e:
        error = f"ES_GET {trip_type} parse failed: {e}"
        logger.exception(error)
        return None, error


# -----------------------------------------------------------------------------
# Main entry (parallel calls for one-way + round-trip)
# -----------------------------------------------------------------------------
def post_es_get_flight(travel: Dict[str, Any], PERNR: str, session_id: str) -> Dict[str, Any]:
    """
    Build and send ES_GET payload for BOTH one-way and round-trip flights in parallel.
    Stores separately: es_get_flight_oneway and es_get_flight_roundtrip
    """
    logger.info("📡 Calling ES GET FLIGHT API (parallel: one-way + round-trip)")
    travel = enrich_with_airport_codes(travel)

    try:
        logger.info(f"[ES_GET_FLIGHT] Fetching SAP bearer token for PERNR={PERNR}...")
        # BEARER_TOKEN = get_sap_bearer_token(PERNR)
        BEARER_TOKEN = BEARER_TOKEN_OLD
        logger.info(f"[ES_GET_FLIGHT] Bearer token fetched successfully.")

        logger.info(f"[ES_GET_FLIGHT] Fetching CSRF token from SAP...")
        token_data = get_csrf_token(BEARER_TOKEN)

        csrf_token = token_data.get("csrf_token")
        cookies = token_data.get("cookies")

        logger.info(
            f"[ES_GET_FLIGHT] CSRF token fetched successfully. "
            f"Token length={len(csrf_token) if csrf_token else 0}, "
            f"Cookies={list(cookies.keys())}"
        )

    except Exception as e:
        logger.exception(
            f"[ES_GET_FLIGHT] ❌ Failed to fetch CSRF token for PERNR={PERNR}: {e}"
        )
        return {
            "ok": False,
            "reason": f"Failed to fetch CSRF token: {e}",
        }
    headers = {
        "Accept": "application/json",
        "X-Requested-With": "X",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {BEARER_TOKEN}",
        "X-CSRF-Token": csrf_token,
    }

    # Load header
    try:
        es_header = redis_mgr.load_json(
            user_id=PERNR,
            session_id=session_id,
            data_type="header",
        )
    except Exception as e:
        logger.exception(f"Failed to load header for {PERNR}")
        return {
            "status_code": 500,
            "status": "error",
            "error": f"Header load error: {e}",
        }

    # Build both payloads
    try:
        payload_oneway = _build_payload(
            PERNR, travel, es_header, is_round_trip=False
        )
        payload_roundtrip = _build_payload(
            PERNR, travel, es_header, is_round_trip=True
        )
    except KeyError as e:
        return {
            "status_code": 500,
            "status": "error",
            "error": f"Payload build error: {e}",
        }

    # Save payloads for debugging
    # ---------------- Save Oneway + Roundtrip Payloads Locally + GCS ----------------
    try:
        # File names
        fname_ow = f"{PERNR}_es_get_flight_oneway_payload.json"
        fname_rt = f"{PERNR}_es_get_flight_roundtrip_payload.json"

        # # 2) Upload to GCS (best effort)
        # try:
        #     uri_ow = upload_json_to_gcs_for_user(
        #         pernr=str(PERNR),
        #         filename=fname_ow,
        #         payload=payload_oneway,
        #     )
        #     uri_rt = upload_json_to_gcs_for_user(
        #         pernr=str(PERNR),
        #         filename=fname_rt,
        #         payload=payload_roundtrip,
        #     )

        #     if uri_ow or uri_rt:
        #         logger.info(
        #             "Uploaded ES_GET flight payloads to GCS",
        #             extra={
        #                 "pernr": PERNR,
        #                 "gcs_uri_oneway": uri_ow,
        #                 "gcs_uri_roundtrip": uri_rt,
        #             },
        #         )
        #     else:
        #         logger.warning(
        #             "GCS upload returned no URI for ES_GET flight payloads "
        #             "(bucket config missing or upload failed).",
        #             extra={"pernr": PERNR},
        #         )
        # except Exception:
        #     logger.exception(
        #         "Unexpected error during GCS upload for ES_GET flight payloads",
        #         extra={"pernr": PERNR},
        #     )

    except Exception as e:
        logger.warning(
            "Failed to handle ES_GET flight payload persistence",
            extra={"pernr": PERNR, "error": str(e)},
        )


    # Parallel API calls
    logger.info(f"✈️  ES_GET Flight → POST {API_URL} (parallel calls)")

    results: Dict[str, Any] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_ow = executor.submit(
            _call_es_get_api, payload_oneway, headers, cookies, "one-way"
        )
        future_rt = executor.submit(
            _call_es_get_api, payload_roundtrip, headers, cookies, "round-trip"
        )

        results["one-way"], error_ow = future_ow.result()
        results["round-trip"], error_rt = future_rt.result()

    # Persist + dedupe
    try:
        d_oneway = results.get("one-way")
        d_roundtrip = results.get("round-trip")

        success_count = 0
        report_ow: Optional[FlightDedupeReport] = None
        report_rt: Optional[FlightDedupeReport] = None

        # -------------------- ONE-WAY --------------------
        if d_oneway:
            # 1) Dedupe
            report_ow = _dedupe_and_report(d_oneway)

            # 2) Split by direction
            origin_code, dest_code = _infer_direction_from_payload(payload_oneway)
            flights_ow = _extract_list(d_oneway.get("NAV_GETSEARCH", []))
            split_result_ow = split_flights_by_direction(
                flights=flights_ow,
                origin_code=origin_code,
                destination_code=dest_code,
            )

            # Replace NAV_GETSEARCH with split structure
            d_oneway["NAV_GETSEARCH"] = split_result_ow
            logger.info(
                "✅ One-way flights split: %s outgoing, %s return",
                len(split_result_ow["results"][0]),
                len(split_result_ow["results"][1]),
            )

            # 3) Upload the *split* JSON to GCS (best-effort)
            # fname_ow_resp = f"{PERNR}_es_get_flight_oneway_response.json"
            # try:
            #     gcs_uri_ow = upload_json_to_gcs_for_user(
            #         pernr=str(PERNR),
            #         filename=fname_ow_resp,
            #         payload=d_oneway,  # already split
            #     )
            #     if gcs_uri_ow:
            #         logger.info(
            #             "Uploaded ES_GET flight ONE-WAY (split) response JSON to GCS",
            #             extra={"pernr": PERNR, "gcs_uri": gcs_uri_ow},
            #         )
            #     else:
            #         logger.warning(
            #             "GCS upload for ES_GET flight ONE-WAY (split) response returned no URI",
            #             extra={"pernr": PERNR, "filename": fname_ow_resp},
            #         )
            # except Exception as e:
            #     logger.exception(
            #         "Unexpected error during GCS upload for ES_GET flight ONE-WAY (split) response",
            #         extra={"pernr": PERNR, "filename": fname_ow_resp, "error": str(e)},
            #     )

            # 4) Save to Redis
            redis_mgr.save_json(
                d_oneway, PERNR, session_id, "es_get_flight_oneway"
            )
            logger.info("✅ One-way data saved: es_get_flight_oneway")
            success_count += 1

        # -------------------- ROUND-TRIP --------------------
        if d_roundtrip:
            # 1) Dedupe
            report_rt = _dedupe_and_report(d_roundtrip)

            # 2) Split by direction
            origin_code_rt, dest_code_rt = _infer_direction_from_payload(
                payload_roundtrip
            )
            flights_rt = _extract_list(d_roundtrip.get("NAV_GETSEARCH", []))
            split_result_rt = split_flights_by_direction(
                flights=flights_rt,
                origin_code=origin_code_rt,
                destination_code=dest_code_rt,
            )

            # Replace NAV_GETSEARCH with split structure
            d_roundtrip["NAV_GETSEARCH"] = split_result_rt
            logger.info(
                "✅ Round-trip flights split: %s outgoing, %s return",
                len(split_result_rt["results"][0]),
                len(split_result_rt["results"][1]),
            )

            # # 3) Upload the *split* JSON to GCS (best-effort)
            # fname_rt_resp = f"{PERNR}_es_get_flight_roundtrip_response.json"
            # try:
            #     gcs_uri_rt = upload_json_to_gcs_for_user(
            #         pernr=str(PERNR),
            #         filename=fname_rt_resp,
            #         payload=d_roundtrip,  # already split
            #     )
            #     if gcs_uri_rt:
            #         logger.info(
            #             "Uploaded ES_GET flight ROUND-TRIP (split) response JSON to GCS",
            #             extra={"pernr": PERNR, "gcs_uri": gcs_uri_rt},
            #         )
            #     else:
            #         logger.warning(
            #             "GCS upload for ES_GET flight ROUND-TRIP (split) response returned no URI",
            #             extra={"pernr": PERNR, "filename": fname_rt_resp},
            #         )
            # except Exception as e:
            #     logger.exception(
            #         "Unexpected error during GCS upload for ES_GET flight ROUND-TRIP (split) response",
            #         extra={"pernr": PERNR, "filename": fname_rt_resp, "error": str(e)},
            #     )

            # 4) Save to Redis
            redis_mgr.save_json(
                d_roundtrip, PERNR, session_id, "es_get_flight_roundtrip"
            )
            logger.info("✅ Round-trip data saved: es_get_flight_roundtrip")
            success_count += 1

        # If we get here, at least the function completed
        return {
            "status_code": 200,
            "status": "ok",
            "errors": {
                "one-way": error_ow,
                "round-trip": error_rt,
            },
            "reports": {
                "one-way": report_ow.to_dict() if report_ow else None,
                "round-trip": report_rt.to_dict() if report_rt else None,
            },
            "successful_calls": success_count,
        }

    except Exception as e:
        logger.exception(f"Redis save / parse failed: {e}")
        return {
            "status_code": 500,
            "status": "error",
            "error": f"Persist/parse error: {e}",
        }
