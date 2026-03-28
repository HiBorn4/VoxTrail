# check_trip_validity.py
from loguru import logger
import os
from dotenv import load_dotenv
import requests
from requests.auth import HTTPBasicAuth

load_dotenv()

# --- ENV VARS (as requested) ---
ES_USERNAME  = os.getenv("SAP_BASIC_USER", "")
ES_PASSWORD  = os.getenv("SAP_BASIC_PASS", "")
SAP_CLIENT   = os.getenv("SAP_CLIENT", "")
SAP_COOKIE   = os.getenv("COOKIE", "")
SAP_BASE_URL = "https://emssq.mahindra.com"

# I want to travel from mumbai to banglore from 5th March 2026 9am, 10th March 9pm, its a R&D Project
# by flight, round trip and company booked
def _to_hhmmss(t: str) -> str:
    """
    Accepts 'HH:MM' | 'HHMM' | 'HHMMSS' (or None) and returns HHMMSS.
    """
    if t is None:
        return ""
    t = str(t).strip().replace(":", "")
    if len(t) == 4:
        return t + "00"
    if len(t) == 6:
        return t
    return t.zfill(6)[:6]


def check_trip_validity(
    pernr, dept_date, arr_date, dept_time, arr_time, action="", tripno="0000000000"
):
    """
    Calls ES_TRIPVALD and returns a dict response:
    {
        "status": "success" | "error",
        "status_code": int,
        "remarks": str
    }
    """

    SAP_BASE_URL_LOCAL = f"{SAP_BASE_URL}/sap/opu/odata/sap/ZHR_DOMESTIC_TRAVEL_SRV"

    dept_time6 = _to_hhmmss(dept_time)
    arr_time6 = _to_hhmmss(arr_time)

    base = f"{SAP_BASE_URL_LOCAL}/ES_TRIPVALD"
    entity = (
        f"(PERNR='{pernr}',DEPT_DATE='{dept_date}',ARR_DATE='{arr_date}',"
        f"DEPT_TIME='{dept_time6}',ARR_TIME='{arr_time6}',ACTION='{action}',TRIPNO='{tripno}')"
    )

    qs = "$format=json"
    if SAP_CLIENT:
        qs += f"&sap-client={SAP_CLIENT}"

    url = f"{base}{entity}?{qs}"

    headers = {
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    }
    if SAP_COOKIE:
        headers["Cookie"] = SAP_COOKIE

    auth = (
        HTTPBasicAuth(ES_USERNAME, ES_PASSWORD)
        if (ES_USERNAME and ES_PASSWORD)
        else None
    )

    logger.info("📡 Calling trip validation:")

    try:
        resp = requests.get(
            url, headers=headers, auth=auth, timeout=20, allow_redirects=True
        )
    except requests.RequestException as e:
        logger.error("Trip validation request failed: %s", e)
        return {
            "status": "error",
            "status_code": 500,
            "error_message": f"Request failed: {e}",
        }

    ct = (resp.headers.get("Content-Type") or "").lower()
    preview = (resp.text or "")[:400].replace("\n", " ")

    if resp.history:
        chain = " → ".join(str(r.status_code) for r in resp.history)
        logger.warning("Redirect chain detected: %s", chain)

    if not resp.ok:
        logger.error(
            "Trip validation HTTP %s, ct=%s, body≈ %s",
            resp.status_code,
            ct,
            preview,
        )
        return {
            "status": "error",
            "status_code": resp.status_code,
            "error_message": f"HTTP {resp.status_code} from ES_TRIPVALD",
        }

    if "text/html" in ct:
        logger.error(
            "Received HTML (likely SAP logon/SSO). Ensure MYSAPSSO2 cookie and/or valid Basic Auth."
        )
        return {
            "status": "error",
            "status_code": resp.status_code,
            "error_message": "Auth required: send MYSAPSSO2 cookie and/or valid Basic Auth.",
        }

    try:
        body = resp.json()
    except ValueError:
        logger.error("Non-JSON response, ct=%s, body≈ %s", ct, preview)
        return {
            "status": "error",
            "status_code": resp.status_code,
            "error_message": "Non-JSON response from ES_TRIPVALD.",
        }

    d = body.get("d", body) if isinstance(body, dict) else {}
    status = d.get("STATUS", "")
    remarks = d.get("REMARKS", "") or d.get("MESSAGE", "")

    if status == "S":
        return {
            "status": "success",
            "status_code": resp.status_code,
            "remarks": remarks or "Trip validation succeeded.",
        }
    if status != "S":
        return {
            "status": "error",
            "status_code": resp.status_code,
            "error_message": remarks or "Trip validation failed.",
        }

    logger.warning("Trip validation unknown status: %s / %s", status, remarks)
    return {
        "status": "error",
        "status_code": resp.status_code,
        "error_message": f"UNKNOWN STATUS: {status}, REMARKS: {remarks or 'No message'}",
    }

