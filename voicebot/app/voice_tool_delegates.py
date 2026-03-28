import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from travel_assist_agentic_bot.tools.function_tools.check_trip_validity import check_trip_validity
from login_bootstap.get_emp_trips_list import get_emp_trips_list
from login_bootstap.get_es_header_api import get_es_header
from travel_assist_agentic_bot.tools.function_tools.post_es_final import post_es_final
from travel_assist_agentic_bot.tools.function_tools.post_es_final_flight import post_es_final_flight
from travel_assist_agentic_bot.tools.function_tools.cancel_trip import cancel_trip
from travel_assist_agentic_bot.tools.function_tools.post_es_get_flight import post_es_get_flight
from travel_assist_agentic_bot.tools.function_tools.trip_details_api import get_es_trip_det
from travel_assist_agentic_bot.tools.function_tools.reimbursement_api import analyze_reimbursement_documents
from travel_assist_agentic_bot.tools.function_tools.reimbursement_submit import reimbursement_submit
from travel_assist_agentic_bot.services.redis_manager import RedisJSONManager
from travel_assist_agentic_bot.services.session_service import (
    get_session_service,
    get_session_state
)

logger = logging.getLogger(__name__)
redis_manager = RedisJSONManager()


async def get_emp_id_from_session(session_id: str, app_name: str = "travel-portal-voice") -> Optional[str]:
    """Get employee ID from session state"""
    try:
        session_service = get_session_service()
        state = await get_session_state(
            session_service,
            app_name=app_name,
            user_id=session_id,  # Use session_id as user_id fallback
            session_id=session_id
        )
        return state.get("emp_id") or state.get("user_id") or session_id
    except Exception as e:
        logger.error(f"Error getting emp_id from session: {e}")
        return session_id


def parse_relative_date(date_str: str) -> str:
    """Convert relative dates to YYYY-MM-DD format"""
    date_str_lower = date_str.lower().strip()
    today = datetime.now()
    
    if date_str_lower == "today":
        return today.strftime("%Y-%m-%d")
    elif date_str_lower == "tomorrow":
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    elif "next monday" in date_str_lower:
        days_ahead = 0 - today.weekday() + 7  # Next Monday
        return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    elif "in" in date_str_lower and "day" in date_str_lower:
        # Parse "in 3 days"
        try:
            num_days = int(''.join(filter(str.isdigit, date_str_lower)))
            return (today + timedelta(days=num_days)).strftime("%Y-%m-%d")
        except:
            pass
    
    # Try to parse as-is
    try:
        parsed = datetime.strptime(date_str, "%Y-%m-%d")
        return date_str
    except:
        pass
    
    return None


async def delegate_flight_search(
    origin: str,
    destination: str,
    departure_date: str,
    trip_type: str,
    return_date: Optional[str] = None,
    class_preference: Optional[str] = None,
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delegate flight search to existing trip validation and flight search logic
    NOW SYNCHRONOUS - waits for results before responding to prevent audio overlap
    """
    try:
        # Parse relative dates
        departure_date = parse_relative_date(departure_date) or departure_date
        if return_date:
            return_date = parse_relative_date(return_date) or return_date
        
        # Validate dates
        try:
            dep_date = datetime.strptime(departure_date, "%Y-%m-%d")
            if dep_date.date() < datetime.now().date():
                return {
                    "success": False,
                    "error": "departure_date_past",
                    "message": "The departure date is in the past. Please provide a future date.",
                    "voice_response": "The departure date you mentioned is in the past. Could you provide a future date?"
                }
        except:
            return {
                "success": False,
                "error": "invalid_date_format",
                "message": "Invalid date format. Please use YYYY-MM-DD.",
                "voice_response": "I couldn't understand the date format. Could you provide the date as year, month, day?"
            }
        
        # Validate origin != destination
        if origin.lower() == destination.lower():
            return {
                "success": False,
                "error": "same_origin_destination",
                "message": "Origin and destination cannot be the same.",
                "voice_response": "Your departure and arrival cities are the same. Could you check your destination?"
            }
        
        # Call existing trip validation
        validation_result = await check_trip_validity(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            trip_type=trip_type
        )
        
        if not validation_result.get("valid"):
            return {
                "success": False,
                "error": "validation_failed",
                "message": validation_result.get("error", "Trip validation failed"),
                "voice_response": f"I encountered an issue: {validation_result.get('error', 'The trip details are invalid')}"
            }
        
        # Get employee ID for flight search
        emp_id = await get_emp_id_from_session(session_id)

        # SYNCHRONOUS: Actually search for flights before responding
        # This prevents audio overlap - agent waits for results
        logger.info(f"Searching flights for {origin} to {destination} on {departure_date}")

        # Build travel details payload for flight search
        travel_details = {
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date,
            "return_date": return_date,
            "trip_type": trip_type,
            "class": class_preference or "economy"
        }

        # Call the actual flight search API
        flight_response = post_es_get_flight(
            travel=travel_details,
            PERNR=emp_id,
            session_id=session_id
        )

        if not flight_response.get("success"):
            logger.error(f"Flight search failed: {flight_response.get('error')}")
            return {
                "success": False,
                "error": "flight_search_failed",
                "message": flight_response.get("error", "Flight search failed"),
                "voice_response": "I couldn't find any flights at the moment. Could you try different dates or destinations?"
            }

        # Extract and store flights - the API already stores in Redis
        if trip_type == "oneway":
            flights = flight_response.get("outbound_flights", [])
            flight_count = len(flights)

            if flight_count == 0:
                voice_response = f"I couldn't find any available flights from {origin} to {destination} on {departure_date}."
            elif flight_count == 1:
                voice_response = f"I found 1 flight from {origin} to {destination} on {departure_date}. Would you like to hear the details?"
            else:
                voice_response = f"I found {flight_count} flights from {origin} to {destination} on {departure_date}. Would you like me to list them?"

        else:  # round-trip
            outbound = flight_response.get("outbound_flights", [])
            inbound = flight_response.get("return_flights", [])

            outbound_count = len(outbound)
            inbound_count = len(inbound)

            if outbound_count == 0 or inbound_count == 0:
                voice_response = f"I couldn't find complete round-trip options for those dates."
            else:
                voice_response = f"I found {outbound_count} outbound flights and {inbound_count} return flights from {origin} to {destination}. "
                if return_date:
                    voice_response += f"Departing {departure_date}, returning {return_date}. "
                voice_response += "Would you like to hear the options?"

        logger.info(f"Flight search completed: {flight_count if trip_type == 'oneway' else f'{outbound_count} out, {inbound_count} in'} flights")
        
        return {
            "success": True,
            "validation": validation_result,
            "message": "Flights found successfully",
            "voice_response": voice_response,
            "trip_details": {
                "origin": origin,
                "destination": destination,
                "departure_date": departure_date,
                "return_date": return_date,
                "trip_type": trip_type,
                "class": class_preference or "economy",
                "flight_count": flight_count if trip_type == 'oneway' else {"outbound": outbound_count, "inbound": inbound_count}
            }
        }
        
    except Exception as e:
        logger.error(f"Error in delegate_flight_search: {e}", exc_info=True)
        return {
            "success": False,
            "error": "internal_error",
            "message": str(e),
            "voice_response": "I encountered a technical issue while searching for flights. Could you try again?"
        }


async def prefetch_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: Optional[str],
    trip_type: str,
    session_id: Optional[str]
):
    """
    Background task to pre-load flight results
    Integrates with your existing parallel flight search
    """
    try:
        # Get employee ID for ES header call
        emp_id = await get_emp_id_from_session(session_id)
        
        # Get ES header - note: takes PERNR as parameter
        header_response = get_es_header(PERNR=emp_id)
        
        if not header_response.get("success"):
            logger.error(f"ES header failed: {header_response.get('error')}")
            return
        
        # Store flight results in Redis
        if trip_type == "oneway":
            # Store one-way flights
            flights = header_response.get("outbound_flights", [])
            await redis_manager.set_key(
                f"es_get_flight_oneway:{session_id}",
                {"flights": flights},
                ttl=1800  # 30 minutes
            )
        else:
            # Store round-trip flights
            outbound = header_response.get("outbound_flights", [])
            inbound = header_response.get("inbound_flights", [])
            await redis_manager.set_key(
                f"es_get_flight_roundtrip:{session_id}",
                {"outbound": outbound, "inbound": inbound},
                ttl=1800
            )
        
        logger.info(f"Pre-fetched flights for session {session_id}")
        
    except Exception as e:
        logger.error(f"Error prefetching flights: {e}", exc_info=True)


async def delegate_booking_confirmation(
    flight_id: str,
    trip_details: Dict[str, Any],
    user_confirmation: bool,
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delegate booking confirmation to existing booking agent
    """
    try:
        if not user_confirmation:
            return {
                "success": False,
                "error": "user_not_confirmed",
                "message": "User must confirm booking",
                "voice_response": "I need your confirmation before proceeding. Would you like to book this flight?"
            }
        
        # Get employee ID from session
        emp_id = await get_emp_id_from_session(session_id)
        if not emp_id:
            return {
                "success": False,
                "error": "session_not_found",
                "voice_response": "I couldn't find your session. Please try reconnecting."
            }
        
        # Prepare travel dict for booking
        travel_dict = dict(trip_details)
        travel_dict["flight_id"] = flight_id
        
        # Execute booking via existing SAP integration
        trip_type = trip_details.get("trip_type", "oneway")
        
        if trip_type == "oneway":
            booking_result = post_es_final(
                travel=travel_dict,
                PERNR=emp_id,
                session_id=session_id
            )
        else:
            booking_result = post_es_final_flight(
                travel=travel_dict,
                PERNR=emp_id,
                session_id=session_id
            )
        
        if booking_result.get("success"):
            trip_id = booking_result.get("trip_id")
            return {
                "success": True,
                "trip_id": trip_id,
                "message": f"Booking confirmed. Trip ID: {trip_id}",
                "voice_response": f"Your booking is confirmed! Your trip ID is {trip_id}. You'll receive a confirmation email shortly."
            }
        else:
            return {
                "success": False,
                "error": booking_result.get("error"),
                "voice_response": f"I couldn't complete the booking. {booking_result.get('error', 'Please try again.')}"
            }
            
    except Exception as e:
        logger.error(f"Error in delegate_booking_confirmation: {e}", exc_info=True)
        return {
            "success": False,
            "error": "internal_error",
            "voice_response": "I encountered an issue while confirming your booking. Please try again."
        }


async def delegate_trip_listing(
    filter: str = "upcoming",
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delegate trip listing to existing trips API
    """
    try:
        # Get employee ID from session
        emp_id = await get_emp_id_from_session(session_id)
        if not emp_id:
            return {
                "success": False,
                "error": "session_not_found",
                "voice_response": "I couldn't find your session."
            }
        
        # Call get_emp_trips_list (synchronous function)
        trips = get_emp_trips_list(PERNR=emp_id)
        
        if not trips or len(trips) == 0:
            return {
                "success": True,
                "trips": [],
                "message": "No trips found",
                "voice_response": f"You don't have any {filter} trips."
            }
        
        # Format for voice response
        trip_count = len(trips)
        voice_summary = f"You have {trip_count} {filter} trip{'s' if trip_count > 1 else ''}. "
        
        if trip_count <= 3:
            # List all trips
            for i, trip in enumerate(trips[:3]):
                voice_summary += f"Trip {i+1}: {trip.get('origin')} to {trip.get('destination')} on {trip.get('departure_date')}. "
        else:
            # Summarize
            voice_summary += f"Your next trip is {trips[0].get('origin')} to {trips[0].get('destination')} on {trips[0].get('departure_date')}. Would you like to hear more?"
        
        return {
            "success": True,
            "trips": trips,
            "count": trip_count,
            "voice_response": voice_summary
        }
        
    except Exception as e:
        logger.error(f"Error in delegate_trip_listing: {e}", exc_info=True)
        return {
            "success": False,
            "error": "internal_error",
            "voice_response": "I couldn't retrieve your trips. Please try again."
        }


async def delegate_reimbursement_query(
    trip_id: Optional[str] = None,
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delegate reimbursement query - not supported via voice (requires document upload)
    """
    try:
        # The analyze_reimbursement_documents function requires document uploads
        # This is not suitable for voice interaction
        return {
            "success": False,
            "error": "not_supported_via_voice",
            "voice_response": "Reimbursement submissions require document uploads, which aren't available via voice. Please use the web interface to submit your reimbursement request."
        }
        
    except Exception as e:
        logger.error(f"Error in delegate_reimbursement_query: {e}", exc_info=True)
        return {
            "success": False,
            "error": "internal_error",
            "voice_response": "I couldn't retrieve your reimbursement details."
        }


async def delegate_trip_cancellation(
    trip_id: str,
    user_confirmation: bool,
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delegate trip cancellation to existing cancellation API
    """
    try:
        if not user_confirmation:
            return {
                "success": False,
                "error": "user_not_confirmed",
                "voice_response": "I need your confirmation before canceling the trip. Are you sure you want to cancel?"
            }
        
        # Get employee ID from session
        emp_id = await get_emp_id_from_session(session_id)
        if not emp_id:
            return {
                "success": False,
                "error": "session_not_found",
                "voice_response": "I couldn't find your session."
            }
        
        # Build trip_json for cancel_trip function
        trip_json = {
            "trip_id": trip_id,
            "PERNR": emp_id
        }
        
        # Call cancel_trip (synchronous function)
        cancellation_result = cancel_trip(trip_json)
        
        if cancellation_result.get("success"):
            return {
                "success": True,
                "message": "Trip cancelled successfully",
                "voice_response": f"Your trip {trip_id} has been cancelled successfully."
            }
        else:
            return {
                "success": False,
                "error": cancellation_result.get("error"),
                "voice_response": f"I couldn't cancel the trip. {cancellation_result.get('error', 'Please try again.')}"
            }
            
    except Exception as e:
        logger.error(f"Error in delegate_trip_cancellation: {e}", exc_info=True)
        return {
            "success": False,
            "error": "internal_error",
            "voice_response": "I encountered an issue while canceling your trip."
        }


async def request_user_confirmation(
    action: str,
    details: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Format confirmation request for user
    """
    if action == "book_flight":
        voice_response = f"Let me confirm: You want to book a flight from {details.get('origin')} to {details.get('destination')} "
        voice_response += f"on {details.get('departure_date')}"
        if details.get("return_date"):
            voice_response += f", returning on {details.get('return_date')}"
        voice_response += f" in {details.get('class', 'economy')} class. Is this correct?"
        
    elif action == "cancel_trip":
        voice_response = f"Are you sure you want to cancel trip {details.get('trip_id')}? This action cannot be undone."
        
    else:
        voice_response = f"Please confirm: {action}"
    
    return {
        "action": action,
        "details": details,
        "voice_response": voice_response,
        "requires_confirmation": True
    }


async def handle_missing_parameter(
    parameter_name: str,
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generate clarification question for missing parameter
    """
    prompts = {
        "origin": "Where are you flying from?",
        "destination": "Where would you like to go?",
        "departure_date": "When would you like to depart?",
        "return_date": "When would you like to return?",
        "trip_type": "Is this a one-way or round-trip flight?",
        "class_preference": "Which cabin class would you prefer: economy, business, or first class?",
        "trip_id": "Which trip ID are you referring to?"
    }

    voice_response = prompts.get(
        parameter_name,
        f"Could you provide the {parameter_name.replace('_', ' ')}?"
    )

    return {
        "missing_parameter": parameter_name,
        "voice_response": voice_response,
        "context": context or {}
    }


async def delegate_trip_details(
    trip_id: str,
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delegate trip details retrieval to existing API
    """
    try:
        # Get employee ID from session
        emp_id = await get_emp_id_from_session(session_id)
        if not emp_id:
            return {
                "success": False,
                "error": "session_not_found",
                "voice_response": "I couldn't find your session."
            }

        # Call get_es_trip_det (synchronous function) - requires session_id parameter
        trip_result = get_es_trip_det(PERNR=emp_id, REINR=trip_id, session_id=session_id)

        if not trip_result or not trip_result.get("ok"):
            return {
                "success": False,
                "error": "trip_not_found",
                "voice_response": f"I couldn't find details for trip {trip_id}."
            }

        # Format for voice response - the data structure is under 'd' key
        details = trip_result.get("d", {})
        origin = details.get("ORIGIN", "unknown")
        destination = details.get("DESTINATION", "unknown")
        departure_date = details.get("DEPT_DATE", "unknown")
        status = details.get("STATUS", "unknown")

        voice_response = f"Trip {trip_id} is from {origin} to {destination} on {departure_date}. Status: {status}."

        return {
            "success": True,
            "trip_details": details,
            "voice_response": voice_response
        }

    except Exception as e:
        logger.error(f"Error in delegate_trip_details: {e}", exc_info=True)
        return {
            "success": False,
            "error": "internal_error",
            "voice_response": "I encountered an issue while retrieving trip details."
        }


async def delegate_reimbursement_analysis(
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delegate reimbursement document analysis - requires prior document upload
    """
    try:
        # Get employee ID from session
        emp_id = await get_emp_id_from_session(session_id)
        if not emp_id:
            return {
                "success": False,
                "error": "session_not_found",
                "voice_response": "I couldn't find your session."
            }

        # Get uploaded file paths from responses folder
        import os
        from pathlib import Path
        responses_dir = Path("responses") / "reimburse_files" / f"{emp_id}_{session_id}"

        if not responses_dir.exists():
            return {
                "success": False,
                "error": "no_files_uploaded",
                "voice_response": "I couldn't find any uploaded documents. Please upload your reimbursement documents using the web interface first."
            }

        file_paths = list(responses_dir.glob("*"))
        if not file_paths:
            return {
                "success": False,
                "error": "no_files_uploaded",
                "voice_response": "I couldn't find any uploaded documents. Please upload your reimbursement documents using the web interface first."
            }

        # Call analyze_reimbursement_documents (synchronous function)
        analysis_result = analyze_reimbursement_documents(
            file_paths=file_paths,
            user_id=emp_id,
            session_id=session_id
        )

        if analysis_result.get("status") != "success":
            return {
                "success": False,
                "error": "analysis_failed",
                "voice_response": "I encountered an error while analyzing your documents. Please try again."
            }

        # Load results from Redis to format response
        ocr_data = await redis_manager.get_key(f"reimbursement_analyze:{emp_id}:{session_id}")

        if not ocr_data:
            return {
                "success": False,
                "error": "analysis_failed",
                "voice_response": "I couldn't retrieve the analysis results. Please try again."
            }

        # Format for voice response
        items_count = len(ocr_data.get("items", []))
        total_amount = ocr_data.get("total_amount", 0)

        voice_response = f"I've analyzed your documents and found {items_count} expense item{'s' if items_count != 1 else ''} totaling {total_amount} rupees. Would you like to submit this reimbursement?"

        return {
            "success": True,
            "analysis": ocr_data,
            "voice_response": voice_response
        }

    except Exception as e:
        logger.error(f"Error in delegate_reimbursement_analysis: {e}", exc_info=True)
        return {
            "success": False,
            "error": "internal_error",
            "voice_response": "I encountered an issue while analyzing your documents."
        }


async def delegate_reimbursement_submission(
    trip_id: str,
    user_confirmation: bool,
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delegate reimbursement submission to existing API
    """
    try:
        if not user_confirmation:
            return {
                "success": False,
                "error": "user_not_confirmed",
                "voice_response": "I need your confirmation before submitting the reimbursement. Would you like to proceed?"
            }

        # Get employee ID from session
        emp_id = await get_emp_id_from_session(session_id)
        if not emp_id:
            return {
                "success": False,
                "error": "session_not_found",
                "voice_response": "I couldn't find your session."
            }

        # Call reimbursement_submit (synchronous function) with correct parameters
        from datetime import datetime
        claimda = datetime.now().strftime("%Y-%m-%d")

        submit_result = reimbursement_submit(
            PERNR=emp_id,
            REINR=trip_id,
            session_id=session_id,
            claimda=claimda
        )

        # Check if submission was successful (None means success)
        if submit_result is None:
            return {
                "success": True,
                "message": "Reimbursement submitted successfully",
                "voice_response": f"Your reimbursement for trip {trip_id} has been submitted successfully."
            }
        else:
            error_msg = submit_result.get("error", "Unknown error")
            return {
                "success": False,
                "error": error_msg,
                "voice_response": f"I couldn't submit the reimbursement. {error_msg}"
            }

    except Exception as e:
        logger.error(f"Error in delegate_reimbursement_submission: {e}", exc_info=True)
        return {
            "success": False,
            "error": "internal_error",
            "voice_response": "I encountered an issue while submitting your reimbursement."
        }