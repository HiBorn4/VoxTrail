"""
reimbursement_submit.py

Submit SAP ES_CREATE_EXP reimbursement using OCR + trip details fetched from Redis.

Inputs:
  - PERNR (str): Employee number
  - REINR (str): Trip number
  - session_id (str): Current session scope for Redis keys
  - claimda (str): DA amount to claim (e.g., "3000.00")

Output:
  - None on success
  - dict {"status_code": int, "error": str} on failure (kept for backward compatibility)
"""

from __future__ import annotations

import os
import json
from typing import Any, Dict, List, Optional

from loguru import logger  # type: ignore
from dotenv import load_dotenv  # type: ignore
import requests
from requests.auth import HTTPBasicAuth

# Adjust the import path below to your project layout
from ...services.redis_manager import RedisJSONManager  # type: ignore

load_dotenv()

# --- Environment / Auth ------------------------------------------------------
ES_USERNAME = os.getenv("SAP_BASIC_USER", "")
ES_PASSWORD = os.getenv("SAP_BASIC_PASS", "")
EMP_API_KEY = os.getenv("AUTHORIZATION", "")

ES_BASE_URL = os.getenv(
    "SAP_BASE_URL",
    "https://emssq.mahindra.com/sap/opu/odata/sap/ZZHR_TRAVEL_EXP_SRV",
)
ES_CREATE_EXP_URL = f"{ES_BASE_URL}/ES_CREATE_EXP"

# --- Redis Manager -----------------------------------------------------------
redis_mgr = RedisJSONManager()

# --- Helpers ----------------------------------------------------------------
def _sap_date(d: str) -> str:
    """Return YYYYMMDD (SAP date) from 'YYYY-MM-DD' or return '' if empty."""
    if not d:
        return ""
    return d.replace("-", "")

def _redis_get_json(user_id: str, session_id: str, data_type: str) -> Optional[Dict[str, Any]]:
    """Fetch a JSON blob from Redis using shared manager (supports get_json/load_json)."""
    try:
        if hasattr(redis_mgr, "get_json"):
            data = redis_mgr.get_json(user_id=user_id, session_id=session_id, data_type=data_type)  # type: ignore[attr-defined]
        else:
            data = redis_mgr.load_json(user_id=user_id, session_id=session_id, data_type=data_type)  # type: ignore[attr-defined]
        return data
    except Exception as e:
        logger.error(f"Redis fetch failed for {data_type}: {e}")
        return None

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
    
# Expense codes (domain keys)
CODES = {
    "food":   {"ExpenseType": "ABZM", "SPKZL": "ABZM"},
    "travel": {"ExpenseType": "CNPE", "SPKZL": "CNPE"},
    # Add others when needed: "hotel": {...}, "tolls": {...}
}

def _header_row_common(PERNR: str, REINR: str, expense_type: str) -> Dict[str, Any]:
    """Base header row (FieldName='X', BELNR='') with common empty nested arrays."""
    return {
        "PERNR": PERNR,
        "REINR": REINR,
        "ExpenseType": expense_type,
        "ExpenseSubtype": "",
        "BELNR": "",               # header row must have empty BELNR
        "FieldName": "X",          # marks header/mapping row
        "NAV_EXPENSEDATA_GST_HDR": {},
        "NAV_EXPENSEDATA_GST_DET": [],
        "NAV_EXPENSEDATA_META": [],
        "NAV_EXPENSEDATA_ATTACH": [
            {
                "SPKZL": "",
                "PERNR": "",
                "REINR": "",
                "BELNR": "",
                "SUBTY": "",
                "DOCUMENTID": "",
                "FILENAME": "",
                "MIMETYPE": "",
                "FILECONTENTS": "",
                "FILESIZE": "",
                "CALL_LOCAL": "",
            }
        ],
    }

def _detail_row_common(
    PERNR: str, REINR: str, expense_type: str, belnr: int, spkzl: str, attach_filename: str
) -> Dict[str, Any]:
    """Base detail row with BELNR set and attachment BELNR matching."""
    belnr_str = f"{belnr:03}"
    return {
        "PERNR": PERNR,
        "REINR": REINR,
        "ExpenseType": expense_type,
        "ExpenseSubtype": "",
        "BELNR": belnr_str,       # detail row must carry BELNR
        "FieldName": "",          # marks detail row
        "NAV_EXPENSEDATA_GST_HDR": {},
        "NAV_EXPENSEDATA_GST_DET": [],
        "NAV_EXPENSEDATA_META": [],
        "NAV_EXPENSEDATA_ATTACH": [
            {
                "SPKZL": spkzl,
                "PERNR": PERNR,
                "REINR": REINR,
                "BELNR": belnr_str,                      # match top-level BELNR
                "SUBTY": "",
                "DOCUMENTID": str(abs(hash(attach_filename)))[:13],
                "FILENAME": attach_filename or "",
                "MIMETYPE": "",                          # leave empty unless sending binaries
                "FILECONTENTS": "",
                "FILESIZE": "",
                "CALL_LOCAL": "",
            }
        ],
    }

# --- Field Mapping Blocks ----------------------------------------------------
def _append_food_block(nav: List[Dict[str, Any]], ocr: Dict[str, Any], PERNR: str, REINR: str, belnr_counter: int) -> int:
    """
    Append one FOOD (ABZM) header + all FOOD detail rows to NAV_CRE_EXPDATA.
    Field mapping (header row):
      Field1..Field10 = BETRG, ELIG_AMT, DESCR, ANZAL, PLACE, DATV1, FOODTYP, BLDAT, DATB1, uniqueId
    """
    items = ocr.get("food")
    if not isinstance(items, list) or not items:
        return belnr_counter

    # Header row (once per block)
    hdr = _header_row_common(PERNR, REINR, CODES["food"]["ExpenseType"])
    hdr.update({
        "Field1":  "BETRG",
        "Field2":  "ELIG_AMT",
        "Field3":  "DESCR",
        "Field4":  "ANZAL",
        "Field5":  "PLACE",
        "Field6":  "DATV1",
        "Field7":  "FOODTYP",
        "Field8":  "BLDAT",
        "Field9":  "DATB1",
        "Field10": "uniqueId",
    })
    nav.append(hdr)

    # Details
    for exp in items:
        data = exp.get("data", {}) if isinstance(exp, dict) else {}
        filename = exp.get("filename", "") if isinstance(exp, dict) else ""
        claim = data.get("claim_amount") or data.get("amount") or 0
        try:
            claim_num = float(claim)
        except Exception:
            claim_num = 0.0

        place = data.get("location", "") or data.get("place", "")
        date  = _sap_date(data.get("receipt_date") or data.get("date", "") or "")
        food_type = (data.get("food_type") or "").upper()  # e.g., B/L/D
        qty = str(data.get("quantity") or "1")
        unique_id = str(abs(hash(filename)))[:13]

        row = _detail_row_common(
            PERNR, REINR, CODES["food"]["ExpenseType"], belnr_counter, CODES["food"]["SPKZL"], filename
        )
        row.update({
            "Field1":  f"{claim_num:.2f}",  # BETRG
            "Field2":  f"{claim_num:.2f}",  # ELIG_AMT (mirror if not calculated)
            "Field3":  data.get("narration", ""),  # DESCR
            "Field4":  qty,                 # ANZAL
            "Field5":  place,               # PLACE
            "Field6":  date,                # DATV1
            "Field7":  food_type[:1],       # FOODTYP (single letter if required)
            "Field8":  date,                # BLDAT
            "Field9":  date,                # DATB1
            "Field10": unique_id,           # uniqueId
        })
        nav.append(row)
        belnr_counter += 1

    return belnr_counter

def _append_travel_block(nav: List[Dict[str, Any]], ocr: Dict[str, Any], PERNR: str, REINR: str, belnr_counter: int) -> int:
    """
    Append one TRAVEL (CNPE) header + all TRAVEL detail rows to NAV_CRE_EXPDATA.
    Field mapping (header row):
      Field1..Field13 = BETRG, ELIG_AMT, DESCR, ANZAL, DATV1, FROM_LOCATION, TO_LOCATION, CONMODE, KMS, DATB1, PLACE, BLDAT, uniqueId
    """
    items = ocr.get("travel")
    if not isinstance(items, list) or not items:
        return belnr_counter

    # Header row (once per block)
    hdr = _header_row_common(PERNR, REINR, CODES["travel"]["ExpenseType"])
    hdr.update({
        "Field1":  "BETRG",
        "Field2":  "ELIG_AMT",
        "Field3":  "DESCR",
        "Field4":  "ANZAL",
        "Field5":  "DATV1",
        "Field6":  "FROM_LOCATION",
        "Field7":  "TO_LOCATION",
        "Field8":  "CONMODE",
        "Field9":  "KMS",
        "Field10": "DATB1",
        "Field11": "PLACE",
        "Field12": "BLDAT",
        "Field13": "uniqueId",
    })
    nav.append(hdr)

    # Details
    for exp in items:
        data = exp.get("data", {}) if isinstance(exp, dict) else {}
        filename = exp.get("filename", "") if isinstance(exp, dict) else ""
        claim = data.get("claim_amount") or data.get("amount") or 0
        try:
            claim_num = float(claim)
        except Exception:
            claim_num = 0.0

        date  = _sap_date(data.get("date", "") or data.get("receipt_date", "") or "")
        from_loc = data.get("from_location", "") or data.get("source", "")
        to_loc   = data.get("to_location", "") or data.get("destination", "")
        mode     = (data.get("transport_mode") or data.get("mode") or "").upper()[:1]  # e.g., 'C','O','T' etc
        kms      = str(data.get("kms") or data.get("distance") or "")
        place    = data.get("route", "") or (f"{from_loc} - {to_loc}" if from_loc or to_loc else "")
        descr    = data.get("narration", "") or data.get("description", "")
        unique_id = str(abs(hash(filename)))[:13]

        row = _detail_row_common(
            PERNR, REINR, CODES["travel"]["ExpenseType"], belnr_counter, CODES["travel"]["SPKZL"], filename
        )
        row.update({
            "Field1":  f"{claim_num:.2f}",  # BETRG
            "Field2":  f"{claim_num:.2f}",  # ELIG_AMT
            "Field3":  descr,               # DESCR
            "Field4":  "1",                 # ANZAL
            "Field5":  date,                # DATV1
            "Field6":  from_loc,            # FROM_LOCATION
            "Field7":  to_loc,              # TO_LOCATION
            "Field8":  mode,                # CONMODE (domain code)
            "Field9":  kms,                 # KMS
            "Field10": date,                # DATB1
            "Field11": place,               # PLACE
            "Field12": date,                # BLDAT
            "Field13": unique_id,           # uniqueId
        })
        nav.append(row)
        belnr_counter += 1

    return belnr_counter

def _build_nav_cre_expdata(ocr: Dict[str, Any], PERNR: str, REINR: str) -> List[Dict[str, Any]]:
    """
    Build NAV_CRE_EXPDATA ensuring:
      - Exactly ONE header row per ExpenseType block
      - All detail rows follow their header
      - BELNR sequence increments and is consistent across detail rows and attachments
    """
    nav: List[Dict[str, Any]] = []
    belnr = 1
    belnr = _append_food_block(nav, ocr, PERNR, REINR, belnr)
    belnr = _append_travel_block(nav, ocr, PERNR, REINR, belnr)
    # Add other blocks (hotel, tolls) with their own headers/detail mapping if/when needed.
    return nav

# --- Main Submit -------------------------------------------------------------
def reimbursement_submit(PERNR: str, REINR: str, session_id: str, claimda: str):
    """
    Submit reimbursement to SAP using OCR ('reimbursement_analyze') and trip details ('es_trip_det') from Redis.
    Returns None on success; dict with {"status_code": int, "error": str} on failure.
    """
    logger.info("📡 reimbursement_submit: start PERNR=%s REINR=%s session=%s", PERNR, REINR, session_id)

    # 1) Load inputs from Redis
    ocr = _redis_get_json(PERNR, session_id, "reimbursement_analyze")
    if not ocr:
        reason = "Missing 'reimbursement_analyze' in Redis."
        logger.error(reason)
        return {"status_code": 500, "error": reason}

    trip = _redis_get_json(PERNR, session_id, "es_trip_det")
    if not trip:
        reason = "Missing 'es_trip_det' in Redis."
        logger.error(reason)
        return {"status_code": 500, "error": reason}

    # 2) Extract DA defaults from trip (best-effort)
    try:
        d = trip.get("d") or {}
        da0 = (d.get("NAV_TRIP_DA") or {}).get("results", [])
        da0 = da0[0] if da0 else {}
    except Exception:
        d, da0 = {}, {}

    # 3) Sum claimed amount from OCR if needed (optional)
    try:
        total_claim = float(ocr.get("total_amount_claimed") or 0)
    except Exception:
        total_claim = 0.0

    # 4) Build NAV_CRE_EXPDATA with strict structure (one header per type; BELNR consistent)
    nav_cre_expdata = _build_nav_cre_expdata(ocr, PERNR, REINR)

    # 5) Build final payload
    payload = {
        # Header-level fields (fallbacks from trip 'd' if present)
        "DisclaimerCheck": d.get("DisclaimerCheck", ""),
        "Remarks": d.get("Remarks", ""),
        "PaidAdvance": d.get("PaidAdvance", ""),
        "ReiumAmount": f"{total_claim}",
        "PERNR": PERNR,
        "RecoveryPayable": f"{total_claim}",
        "Flag": "D",
        "REINR": REINR,

        # DA section
        "NAV_CRE_DA": [
            {
                "PERNR": PERNR,
                "REINR": REINR,
                "Currency": da0.get("Currency", ""),
                "LocationText": da0.get("LocationText", ""),
                "LocationCode": da0.get("LocationCode", ""),
                "NoofDays": da0.get("NoofDays", ""),
                "EligibleDA": da0.get("EligibleDA", ""),
                "ClaimDA": str(claimda),
                "WaivedDA": da0.get("WaivedDA", ""),
            }
        ],

        # Other sections (empty unless you fill them)
        "NAV_CRE_HOTELDA": [],
        "NAV_CRE_OWN_STAY": [],
        "NAV_CRE_ACC": [],
        "NAV_CRE_EXPDATA": nav_cre_expdata,
        "NAV_CRE_APPROVER": [],

        # Trip timing/cities (best-effort from d)
        "StartDate": d.get("StartDate", ""),
        "StartTime": d.get("StartTime", ""),
        "EndDate": d.get("EndDate", ""),
        "EndTime": d.get("EndTime", ""),
        "SourceCity": d.get("SourceCity", ""),
        "DestinationCity": d.get("DestinationCity", ""),
    }

    # 6) (Optional) Persist payload for debug parity
    try:
        out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "responses")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{PERNR}_reimbursement_submit_payload.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        logger.info("Saved reimbursement payload → %s", out_path)
    except Exception as e:
        logger.warning("Could not write reimbursement payload to disk: %s", e)

    # 7) POST to SAP
    headers = {
        "Accept": "application/json",
        "X-Requested-With": "X",
    }
    if EMP_API_KEY:
        headers["Authorization"] = EMP_API_KEY

    auth = HTTPBasicAuth(ES_USERNAME, ES_PASSWORD) if (ES_USERNAME or ES_PASSWORD) else None

    try:
        resp = requests.post(ES_CREATE_EXP_URL, auth=auth, json=payload, headers=headers, timeout=(500, 1000))
        logger.info("ES_CREATE_EXP → status=%s", resp.status_code)
    except requests.exceptions.RequestException as e:
        reason = f"ES_CREATE_EXP request failed: {e}"
        logger.error(reason)
        return {"status_code": 500, "error": reason}

    # --- 8) Parse and handle SAP business-level response ---------------------
    try:
        resp_payload = resp.json()
    except ValueError:
        logger.warning("SAP response not JSON; skipping payload parsing.")
        return None

    # Clean metadata if you already have a helper
    try:
        cleaned = remove_metadata(resp_payload)
    except Exception:
        cleaned = resp_payload

    # Store in Redis for traceability
    try:
        redis_mgr.save_json(
            data=cleaned,
            user_id=PERNR,
            session_id=session_id,
            data_type="reimbursement_submit_response",
        )
        logger.info("Saved reimbursement_submit_response to Redis for PERNR=%s", PERNR)
    except Exception as e:
        logger.warning(f"Could not store reimbursement_submit_response in Redis: {e}")

    # Detect application-level SAP errors even if status=200
    try:
        d = cleaned.get("d", {})
        nav_da = (d.get("NAV_CRE_DA") or {}).get("results", [])
        nav_exp = (d.get("NAV_CRE_EXPDATA") or {}).get("results", [])
        potential_errors = []

        # Typical SAP OData error patterns
        for block in nav_da + nav_exp:
            typ = block.get("Type") or block.get("TYPE")
            msg = block.get("Message") or block.get("MESSAGE")
            if typ in ("E", "A") and msg:
                potential_errors.append(f"{typ}: {msg}")

        if potential_errors:
            err_text = " | ".join(potential_errors)
            logger.error("SAP business error detected: %s", err_text)
            return {"status_code": resp.status_code, "error": err_text}

    except Exception as e:
        logger.warning(f"Business-error scan failed: {e}")

    # --- Final success -------------------------------------------------------
    logger.info("🎉 reimbursement_submit succeeded (HTTP %s, no business errors)", resp.status_code)
    return None

