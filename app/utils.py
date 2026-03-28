import base64
import json
from typing import Dict, Any, List, Optional
import msal
import os 
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
)

logger = logging.getLogger("travel_portal")
logger.info("FastAPI app initialized")

CLIENT_ID = os.getenv("AZURE_AD_CLIENT_ID")
CLIENT_SECRET = os.getenv("AZURE_AD_CLIENT_SECRET")
TENANT_ID = os.getenv("AZURE_AD_TENANT_ID")
REDIRECT_URI= "https://travel-assist-bot-backend-167627519943.asia-south1.run.app/login"
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"

def _pad_base64(b64_string: str) -> str:
    """Pad Base64 string with '=' so it can be decoded."""
    return b64_string + '=' * (-len(b64_string) % 4)


def decode_jwt(token: str) -> Dict[str, Any]:
    """
    Decode a JWT token's header and payload WITHOUT verifying signature.

    Returns:
        {
            "header": { ... },
            "payload": { ... }
        }

    Raises:
        ValueError if token is not in JWT format or decoding fails.
    """
    if token.count(".") != 2:
        raise ValueError("Not a valid JWT format (must contain exactly two '.')")

    header_b64, payload_b64, _ = token.split(".")

    try:
        header_json = base64.urlsafe_b64decode(_pad_base64(header_b64)).decode()
        payload_json = base64.urlsafe_b64decode(_pad_base64(payload_b64)).decode()

        return {
            "header": json.loads(header_json),
            "payload": json.loads(payload_json),
        }
    except Exception as e:
        raise ValueError(f"Failed to decode JWT: {e}")


def extract_user_id(payload: Dict[str, Any]) -> Optional[str]:
    """
    Extract PERNR/user_id from a JWT payload using 'upn' or 'unique_name'.

    Assumes values like:
        "upn": "25017514@mahindra.com"
        "unique_name": "25017514@mahindra.com"

    Returns:
        user_id (e.g., "25017514") or None if not found.
    """
    upn = payload.get("upn") or payload.get("unique_name")
    if not upn or "@" not in upn:
        return None
    return upn.split("@")[0]



def create_refresh_token(auth_code):
    app = msal.ConfidentialClientApplication(
        client_id=CLIENT_ID,
        client_credential=CLIENT_SECRET,
        authority=AUTHORITY
    )    
    # Exchange code for tokens
    result = app.acquire_token_by_authorization_code(
        code=auth_code,
        scopes=["User.Read"],
        redirect_uri=REDIRECT_URI
    )

    if "access_token" in result and "refresh_token" in result:
        # Use a unique identifier from the id_token if available
        user_token = result.get("id_token_claims", {}).get("oid", "unknown_user")
        logger.info("Tokens acquired successfully.")
        return result["access_token"], result["refresh_token"], user_token
    else:
        logger.error("Failed to acquire tokens.")
        logger.error(result.get("error_description"))
        return None, None, None
    
    
async def fetch_recent_history(
    session_service,
    app_name: str,
    user_id: str,
    session_id: str,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Fetch recent conversation history from the session.
    
    Returns a list of messages in format:
    [
        {"role": "user", "message": "...", "timestamp": 123456789},
        {"role": "assistant", "message": "...", "timestamp": 123456790},
        ...
    ]
    
    Args:
        session_service: ADK DatabaseSessionService instance
        app_name: Application name (e.g., "travel-portal")
        user_id: User identifier (PERNR)
        session_id: Session identifier
        limit: Maximum number of messages to return (default: 20)
    
    Returns:
        List of message dictionaries, empty list on error
    """
    logger.info(
        "Fetching conversation history | user_id=%s session_id=%s limit=%d",
        user_id,
        session_id,
        limit
    )
    
    try:
        # Fetch session with events
        session = await session_service.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id
        )
        
        events = getattr(session, "events", None)
        
        if not events:
            logger.warning(
                "No events found in session | user_id=%s session_id=%s",
                user_id,
                session_id
            )
            return []
        
        logger.info(
            "Retrieved %d events from session | user_id=%s session_id=%s",
            len(events),
            user_id,
            session_id
        )
        
        # Extract messages from events
        messages = []
        
        for event in events:
            try:
                author = getattr(event, "author", "")
                timestamp = getattr(event, "timestamp", None)
                content = getattr(event, "content", None)
                
                # Skip system events or events without content
                if not content or author not in ("user", "OrchestratorAgent"):
                    continue
                
                # Extract text from content
                message_text = ""
                
                # Try different methods to get text from content
                parts = getattr(content, "parts", None)
                if parts and len(parts) > 0:
                    # Get text from first part
                    first_part = parts[0]
                    message_text = getattr(first_part, "text", "")
                
                # If still no text, try to_json method
                if not message_text:
                    try:
                        content_json = content.to_json() if hasattr(content, "to_json") else None
                        if content_json:
                            content_dict = json.loads(content_json) if isinstance(content_json, str) else content_json
                            parts_list = content_dict.get("parts", [])
                            if parts_list and len(parts_list) > 0:
                                message_text = parts_list[0].get("text", "")
                    except Exception:
                        pass
                
                # Skip if we couldn't extract any text
                if not message_text:
                    continue
                
                # Try to parse as ChatEnvelope JSON to extract bot_response
                if author == "OrchestratorAgent":
                    try:
                        # Agent responses are ChatEnvelope JSON strings
                        envelope_data = json.loads(message_text)
                        bot_response = envelope_data.get("message", {}).get("bot_response", "")
                        if bot_response:
                            message_text = bot_response
                    except (json.JSONDecodeError, AttributeError, KeyError):
                        # If parsing fails, use the raw text
                        pass
                elif author == "user":
                    try:
                        # User messages are also ChatEnvelope JSON strings
                        envelope_data = json.loads(message_text)
                        user_query = envelope_data.get("message", {}).get("user_query", "")
                        if user_query:
                            message_text = user_query
                    except (json.JSONDecodeError, AttributeError, KeyError):
                        # If parsing fails, use the raw text
                        pass
                
                # Determine role
                role = "assistant" if author == "OrchestratorAgent" else "user"
                
                # Add to messages list
                messages.append({
                    "role": role,
                    "message": message_text,
                    "timestamp": timestamp
                })
                
            except Exception as e:
                logger.warning(
                    "Failed to process event | error=%s",
                    str(e)
                )
                continue
        
        # Get last N messages (limit)
        recent_messages = messages[-limit:] if len(messages) > limit else messages
        
        logger.info(
            "Extracted %d messages from %d events (limit=%d) | user_id=%s session_id=%s",
            len(recent_messages),
            len(events),
            limit,
            user_id,
            session_id
        )
        
        return recent_messages
        
    except Exception as e:
        logger.exception(
            "Failed to fetch conversation history | user_id=%s session_id=%s error=%s",
            user_id,
            session_id,
            str(e)
        )
        return []
    
    


def categorize_trips(trips_data: Dict[str, Any], expenses_data: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Categorize trips based on APPROVALSTATUS and expense status.
    
    Business Rules:
    - Every trip goes into exactly ONE trip status category (Pending/Approved/Not Approved)
    - Expense categories are separate and based on expense records
    - "Expense Not Submitted" only includes APPROVED trips without expenses
    - Rejected/Cancelled trips cannot have expenses, so they never appear in expense categories
    
    Args:
        trips_data: Response from get_emp_trips_list containing trip records
        expenses_data: Response from get_emp_trip_expenses_list containing expense records
    
    Returns:
        Dictionary with categorized trips:
        {
            "Trip Pending Approval": [...],
            "Trip Approved": [...],
            "Trip Not Approved": [...],
            "Expense Not Submitted": [...],
            "Expense Saved (Draft)": [...],
            "Expense Pending Approval": [...],
            "Expense Approved": [...]
        }
    """
    logger.info("Starting trip categorization")
    
    # Initialize category buckets
    categorized = {
        "Trip Pending Approval": [],
        "Trip Approved": [],
        "Trip Not Approved": [],
        "Expense Not Submitted": [],
        "Expense Saved (Draft)": [],
        "Expense Pending Approval": [],
        "Expense Approved": []
    }
    
    # Extract trip and expense lists
    trips = trips_data.get("trips", [])
    expenses = expenses_data.get("expenses", [])
    
    # Create expense lookup by TRIP_NUMBER for quick access
    expense_map = {}
    for expense in expenses:
        trip_num = expense.get("TRIP_NUMBER", "")
        if trip_num:
            expense_map[trip_num] = expense
    
    logger.info(f"Processing {len(trips)} trips and {len(expenses)} expense records")
    
    # PART 1: Categorize by Trip Approval Status
    for trip in trips:
        trip_number = trip.get("TRIP_NUMBER", "")
        approval_status = trip.get("APPROVALSTATUS", "").strip()
        
        # Create enriched trip object with expense info if available
        enriched_trip = trip.copy()
        matching_expense = expense_map.get(trip_number)
        if matching_expense:
            enriched_trip["expense_details"] = matching_expense
        
        # Categorize based on APPROVALSTATUS
        if approval_status == "Pending Approval":
            categorized["Trip Pending Approval"].append(enriched_trip)
            logger.debug(f"Trip {trip_number}: Pending Approval")
        elif approval_status == "Trip Approved":
            categorized["Trip Approved"].append(enriched_trip)
            logger.debug(f"Trip {trip_number}: Approved")
        elif approval_status in ["Trip Rejected", "Trip Cancelled"]:
            categorized["Trip Not Approved"].append(enriched_trip)
            logger.debug(f"Trip {trip_number}: Not Approved ({approval_status})")
    
    # PART 2: Categorize by Expense Status
    # Only process trips that are NOT rejected/cancelled
    for trip in trips:
        trip_number = trip.get("TRIP_NUMBER", "")
        approval_status = trip.get("APPROVALSTATUS", "").strip()
        
        # CRITICAL: Skip rejected/cancelled trips - they cannot have expenses
        if approval_status in ["Trip Rejected", "Trip Cancelled"]:
            logger.debug(f"Trip {trip_number}: Skipping expense categorization (trip rejected/cancelled)")
            continue
        
        # Create enriched trip object
        enriched_trip = trip.copy()
        matching_expense = expense_map.get(trip_number)
        if matching_expense:
            enriched_trip["expense_details"] = matching_expense
        
        # Check if expense exists
        if not matching_expense:
            # No expense record exists - only add if trip is approved
            if approval_status == "Trip Approved":
                categorized["Expense Not Submitted"].append(enriched_trip)
                logger.debug(f"Trip {trip_number}: Expense Not Submitted (approved trip, no expense)")
        else:
            # Expense exists - categorize based on expense status
            expense_created_date = matching_expense.get("TRVL_EXPENSE_CREATED_DATE", "").strip()
            expense_status = matching_expense.get("EXPENSE_STATUS", "").strip()
            
            if expense_created_date == "Expense Saved":
                # Draft expense exists but not submitted
                categorized["Expense Saved (Draft)"].append(enriched_trip)
                logger.debug(f"Trip {trip_number}: Expense Saved (Draft)")
            elif expense_created_date and expense_created_date != "":
                # Expense has been created with a date
                if expense_status == "Trip Approved":
                    categorized["Expense Approved"].append(enriched_trip)
                    logger.debug(f"Trip {trip_number}: Expense Approved")
                else:
                    categorized["Expense Pending Approval"].append(enriched_trip)
                    logger.debug(f"Trip {trip_number}: Expense Pending Approval")
            else:
                # Edge case: expense record exists but no creation date
                # Only add to "Not Submitted" if trip is approved
                if approval_status == "Trip Approved":
                    categorized["Expense Not Submitted"].append(enriched_trip)
                    logger.debug(f"Trip {trip_number}: Expense Not Submitted (no date)")
    
    # Log summary
    logger.info("Categorization complete:")
    for category, items in categorized.items():
        logger.info(f"  {category}: {len(items)} trips")
    
    return categorized