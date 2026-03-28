from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional

from dotenv import load_dotenv
import requests
from requests.auth import HTTPBasicAuth
from loguru import logger

from .post_es_get import remove_metadata
from ...services.redis_manager import RedisJSONManager

load_dotenv()

ES_USERNAME = os.getenv("SAP_BASIC_USER")
ES_PASSWORD = os.getenv("SAP_BASIC_PASS")
EMP_API_KEY = os.getenv("AUTHORIZATION")
SAP_BASE_URL = os.getenv("SAP_BASE_URL")

# Prepare responses directory (mirrors post_es_reprice.py behavior)
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
responses_dir = os.path.join(base_dir, "responses")
os.makedirs(responses_dir, exist_ok=True)

# Single Redis manager instance
redis_mgr = RedisJSONManager()


def get_es_trip_det(PERNR: str, REINR: str, session_id: str) -> Dict[str, Optional[Any]]:
    """
    Fetch trip details from SAP OData (ES_TRIP_DET), strip __metadata, and store in Redis.

    Parameters
    ----------
    PERNR : str
        Employee personnel number (e.g., "25017514").
    REINR : str
        Trip request number / Trip ID (e.g., "2200119544").
    session_id : str
        Current chat/session identifier used for Redis scoping.

    Returns
    -------
    dict
        Normalized result object (same shape as post_es_reprice.py):
        {
          "ok": bool,            # True if HTTP 200; else False
          "reason": str | None   # None on success; error/diagnostic text on failure
        }

    Side Effects
    ------------
    - Writes raw-cleaned response to: responses/{PERNR}_es_trip_det_response.json
    - Saves cleaned response in Redis under key:
        user_id=PERNR, session_id=session_id, data_type="es_trip_det"

    Notes
    -----
    - Authorization headers mirror post_es_reprice.py (EMP_API_KEY as 'Authorization').
    - Basic auth is applied if ES_USERNAME/ES_PASSWORD are set.
    - OData expansions match the example URL you provided.
    """
    # Compose OData URL with expansions
    url = (
        f"{SAP_BASE_URL}/sap/opu/odata/sap/ZZHR_TRAVEL_EXP_SRV/ES_TRIP_DET(REINR='{REINR}',PERNR='{PERNR}')"
        "?$expand=NAV_TRIP_ACC,NAV_TRIP_DA,NAV_TRIP_APPROVER,"
        "NAV_TRIP_HOTELDA,NAV_TRIP_OWN_STAY&$format=json"
    )

    headers = {
        "Accept": "application/json",
        "X-Requested-With": "X",
    }
    # Mirror post_es_reprice.py header usage if EMP_API_KEY provided
    if EMP_API_KEY:
        headers["Authorization"] = EMP_API_KEY

    auth = HTTPBasicAuth(ES_USERNAME, ES_PASSWORD) if (ES_USERNAME or ES_PASSWORD) else None

    logger.info("📡 Calling ES_TRIP_DET API", extra={"pernr": PERNR, "reinr": REINR})

    try:
        resp = requests.get(url, headers=headers, auth=auth, timeout=120)
    except requests.exceptions.RequestException as e:
        logger.error(f"ES_TRIP_DET request failed: {e}")
        return {"ok": False, "reason": f"ES_TRIP_DET request failed: {e}"}

    if resp.status_code != 200:
        reason = f"ES_TRIP_DET failed status {resp.status_code}: {resp.text[:400]}"
        logger.error(reason)
        return {"ok": False, "reason": reason}

    # Parse & clean
    # Parse & clean
    try:
        raw = resp.json()
    except ValueError:
        logger.error("ES_TRIP_DET returned invalid JSON.")
        return {
            "ok": False,
            "reason": "Invalid JSON response from ES_TRIP_DET.",
            "data": None,
        }

    try:
        cleaned = remove_metadata(raw)  # same utility used by post_es_reprice.py
    except Exception as e:
        logger.warning(f"remove_metadata failed; storing raw JSON. Error: {e}")
        cleaned = raw

    # Persist cleaned response in Redis with a distinct data_type
    try:
        saved = redis_mgr.save_json(
            data=cleaned,
            user_id=PERNR,
            session_id=session_id,
            data_type="es_trip_det",
        )
        if saved:
            logger.info(f"✅ Saved ES_TRIP_DET (cleaned) to Redis for PERNR={PERNR}")
        else:
            logger.warning("Redis save_json returned False for ES_TRIP_DET.")
    except Exception as e:
        logger.error(f"Failed to save ES_TRIP_DET to Redis: {e}")

    # Optional backup to disk (like post_es_reprice.py)
    try:
        out_path = os.path.join(responses_dir, f"{PERNR}_es_trip_det_response.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved cleaned ES_TRIP_DET response → {out_path}")
    except Exception as e:
        logger.warning(f"Could not write ES_TRIP_DET response to disk: {e}")

    logger.info("ES_TRIP_DET fetched, stored, and returned successfully.")
    return {
        "ok": True,
        "reason": None,
        "data": cleaned,  # ⬅️ cleaned ES_TRIP_DET JSON for direct use by caller
    }

