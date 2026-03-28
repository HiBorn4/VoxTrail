# sap_csrf.py
from typing import Any, Dict, Optional
from fastapi import HTTPException
import requests
import os
from travel_assist_agentic_bot.services import RedisJSONManager


SAP_BASE_URL = "https://emss.mahindra.com/sap/opu/odata/sap/ZHR_DOMESTIC_TRAVEL_SRV/"
redis_mgr = RedisJSONManager()

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


def get_csrf_token(BEARER_TOKEN: str):
    url = SAP_BASE_URL  # Always call the root service to fetch token

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {BEARER_TOKEN}",
        "X-CSRF-Token": "Fetch",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=20)
    except requests.exceptions.RequestException as e:
        raise Exception(f"CSRF token fetch failed: {e}")

    if resp.status_code != 200:
        raise Exception(
            f"Failed to fetch CSRF token, HTTP {resp.status_code}: {resp.text}"
        )

    csrf_token = resp.headers.get("X-CSRF-Token")
    cookies = resp.cookies.get_dict()  # SAP session cookies

    if not csrf_token:
        raise Exception("CSRF token missing in response headers")

    return {
        "csrf_token": csrf_token,
        "cookies": cookies,
    }


__all__ = ["get_csrf_token"]
