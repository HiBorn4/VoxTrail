from loguru import logger
import os
from dotenv import load_dotenv
import requests
from requests.auth import HTTPBasicAuth

load_dotenv()

ES_USERNAME = os.getenv("SAP_BASIC_USER", "")
ES_PASSWORD = os.getenv("SAP_BASIC_PASS", "")

def cancel_trip(trip_json: dict):
    """
    Calls SAP ES_TRIP_CANCEL endpoint to cancel a trip.

    Expects:
        {
            "employee_id": "<8-digit ID>",
            "trip_id": "<Trip number>"
        }

    Returns:
        (True, dict) on success else (False, reason)
    """

    pernr = trip_json.get("employee_id", "")
    tripno = trip_json.get("trip_id", "")
    comments = "Trip cancellation requested by user"
    # https://emssq.mahindra.com/sap/opu/odata/sap/ZHR_DOMESTIC_TRAVEL_SRV/ES_TRIP_CANCEL
    base_url = "https://emssq.mahindra.com/sap/opu/odata/sap/ZHR_DOMESTIC_TRAVEL_SRV"
    endpoint = f"/ES_TRIP_CANCEL(PERNR='{pernr}',TRIPNO='{tripno}',COMMENTS='{comments}')"
    url = base_url + endpoint

    logger.info("📡 Initiating trip cancellation request")
    logger.info(f"➡️ Employee PERNR: {pernr}")
    logger.info(f"➡️ Trip Number: {tripno}")
    logger.info(f"➡️ Endpoint: {endpoint}")
    logger.info(f"➡️ Full URL: {url}")

    headers = {
        "Accept": "application/json",
        "X-Requested-With": "X"
    }

    try:
        auth = HTTPBasicAuth(ES_USERNAME, ES_PASSWORD) if (ES_USERNAME or ES_PASSWORD) else None
        logger.debug(f"Using authentication: {'Yes' if auth else 'No'}")

        resp = requests.get(url, headers=headers, auth=auth, timeout=10)
        logger.info(f"🔁 API Response Status: {resp.status_code}")

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Trip cancel request failed for PERNR={pernr}, TRIPNO={tripno}: {e}")
        return False, f"Request failed: {e}"

    if resp.status_code == 200:
        try:
            data = resp.json().get("d", {})
            result = {
                "MESSAGE_TYPE": data.get("MESSAGE_TYPE", ""),
                "MESSAGE": data.get("MESSAGE", "")
            }
            logger.success(f"✅ Trip cancellation successful: {result}")
            return True, result
        except Exception as e:
            logger.error(f"⚠️ Invalid JSON response for PERNR={pernr}, TRIPNO={tripno}: {e}")
            return False, f"Invalid JSON response: {e}"
    else:
        reason = f"Request failed with status code {resp.status_code}"
        logger.error(f"❌ Trip cancellation failed for PERNR={pernr}, TRIPNO={tripno}: {reason}")
        return False, reason