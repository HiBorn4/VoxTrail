# travel_assist_agentic_bot/tools/function_tools.py

from __future__ import annotations
import os
import os
import asyncio
from google.adk.tools import FunctionTool, ToolContext
from typing import Any, Dict, List, Literal, Optional
import logging
from pathlib import Path
import json
from loguru import logger
import threading

from google.adk.tools.preload_memory_tool import PreloadMemoryTool

# Import your existing business functions
from .function_tools.check_trip_validity import check_trip_validity
from .function_tools.post_es_get import post_es_get
from .function_tools.post_es_final import post_es_final
from .function_tools.cancel_trip import cancel_trip
from .function_tools.reimbursement_api import analyze_reimbursement_documents
from .function_tools.post_es_get_flight import post_es_get_flight          # ES_GET (flight search)
from .function_tools.post_es_reprice import post_es_reprice               # ES_REPRICE (re-price selected flights)
from .function_tools.post_es_final_flight import post_es_final_flight     # ES_FINAL (book flight + get REINR)
from .function_tools.trip_details_api import get_es_trip_det
from .function_tools.reimbursement_submit import reimbursement_submit
from travel_assist_agentic_bot.services.session_service import get_session_service

logger = logging.getLogger(__name__)


async def _to_async(func, *args, **kwargs):
    """
    Helper to run a sync function in a worker thread so the tool stays async.
    This lets ADK execute multiple tools in parallel when possible.
    """
    return await asyncio.to_thread(func, *args, **kwargs)

            
def _get_ids_from_tool_context(tool_context: ToolContext) -> tuple[str, str]:
    """Helper to extract user_id and session_id from ToolContext.state."""
    user_id = ""
    session_id = ""

    if tool_context and hasattr(tool_context, "state"):
        # Read values directly from ToolContext.state
        user_id = str(tool_context.state.get("app:user_id", ""))
        session_id = str(tool_context.state.get("app:session_id", ""))

        print(f"user_id: {user_id}")
        print(f"session_id: {session_id}")
        # print(f"All available state keys: {list(tool_context.state.keys())}")
    else:
        print("⚠️ No valid ToolContext or missing state object")

    return user_id, session_id



# -------------------------
# check_trip_validity_tool
# -------------------------
def check_trip_validity_tool(
    travel_purpose: str,
    travel_mode: str,
    travel_mode_code: str,
    origin_city: str,
    destination_city: str,
    start_date: str,
    end_date: str,
    start_time: str,
    end_time: str,
    country_beg: Optional[str],
    country_end: Optional[str],
    tool_context: ToolContext,
) -> Dict[str, Any]:
    """
    Validate a flight trip using basic trip fields and, on success, asynchronously
    prefetch ES_GET flight options (one-way + round-trip).
    
    ----------------------------------------------------------------------
    INPUT PARAMETERS
    ----------------------------------------------------------------------
    travel_purpose : str
        Reason for travel. Used in ES_GET flight payload.
    
    travel_mode : str
        Travel mode string. For this tool it SHOULD be "Flight".
        (The agent must always pass "Flight" here.)
    
    travel_mode_code : str
        Travel mode code. For this tool it SHOULD be "F".
        (The agent must always pass "F" here.)
    
    origin_city : str
        Start city.
    
    destination_city : str
        End city.
    
    start_date : str
        Outbound (departure) date in `YYYYMMDD` format.
    
    end_date : str
        Return (arrival) date in `YYYYMMDD` format.
    
    start_time : str
        Outbound (departure) time in `HHMM` (24-hour) format.
    
    end_time : str
        Return (arrival) time in `HHMM` (24-hour) format.
    
    country_beg : Optional[str]
        2-letter ISO country code for origin (e.g., "IN").
        If falsy or empty, it defaults to "IN".
    
    country_end : Optional[str]
        2-letter ISO country code for destination (e.g., "IN").
        If falsy or empty, it defaults to "IN".
    
    tool_context : ToolContext
        ADK tool context used to:
        - Read `app:user_id` / `app:session_id` for SAP + Redis keys.
        - Store temporary flags & results in `tool_context.state`.
    
    ----------------------------------------------------------------------
    RESPONSE SCHEMA
    ----------------------------------------------------------------------
    Returns a dict:
    
        {
          "status": "success" | "error",
          "status_code": int,
          "remarks": str
        }
    
    - status: high-level status of validation.
    - status_code: SAP HTTP status code if available, else 200/400.
    - remarks: SAP message text or a fallback explanation.
    
    Side effects (on success):
    - Writes `tool_context.state["temp:trip_validity"] = {"valid": bool, "remarks": str}`
    - Starts a background thread that calls `post_es_get_flight(...)` exactly
      once per session and stores flight options in Redis.
    """

    # ------------------------------------------------------------------
    # 0) Log all incoming parameters and basic validation
    # ------------------------------------------------------------------
    logger.info(
        "check_trip_validity_tool called with: "
        "travel_purpose=%r, travel_mode=%r, travel_mode_code=%r, "
        "origin_city=%r, destination_city=%r, "
        "start_date=%r, end_date=%r, start_time=%r, end_time=%r, "
        "country_beg=%r, country_end=%r",
        travel_purpose,
        travel_mode,
        travel_mode_code,
        origin_city,
        destination_city,
        start_date,
        end_date,
        start_time,
        end_time,
        country_beg,
        country_end,
    )

    # Required fields for validation + ES_TRIPVALD
    required_values = {
        "start_date": start_date,
        "end_date": end_date,
        "start_time": start_time,
        "end_time": end_time,
        "origin_city": origin_city,
        "destination_city": destination_city,
    }
    missing = [k for k, v in required_values.items() if not str(v or "").strip()]

    if missing:
        msg = "check_trip_validity_tool missing required fields: " + ", ".join(missing)
        logger.warning(msg)
        raise ValueError(msg)

    # Normalize dates/times for validation call
    dept_date: str = str(start_date)
    arr_date: str = str(end_date)
    dept_time: str = str(start_time)
    arr_time: str = str(end_time)

    # Normalize countries (default to "IN")
    country_beg_norm = (country_beg or "IN").strip()
    country_end_norm = (country_end or "IN").strip()

    # ------------------------------------------------------------------
    # 1) Resolve pernr (employee id) and session from ToolContext
    # ------------------------------------------------------------------
    pernr: str = ""
    session_id: str = ""

    if tool_context is not None:
        try:
            user_id, session_id = _get_ids_from_tool_context(tool_context)
            pernr = str(user_id or "")
        except Exception as e:
            logger.warning(
                "check_trip_validity_tool: could not resolve ids from ToolContext: %s",
                e,
            )

    if not pernr:
        msg = (
            "check_trip_validity_tool could not resolve 'pernr' from ToolContext "
            "(expected in app:user_id or similar)."
        )
        logger.error(msg)
        raise ValueError(msg)

    logger.info(
        "check_trip_validity_tool resolved pernr=%s, session_id=%s",
        pernr,
        session_id,
    )

    # ------------------------------------------------------------------
    # 2) Call trip validation API (synchronous, but cheap)
    # ------------------------------------------------------------------
    try:
        raw: Dict[str, Any] = check_trip_validity(
            pernr, dept_date, arr_date, dept_time, arr_time
        )
        logger.info("Trip validation API returned raw response: %s", raw)
    except Exception as e:
        logger.exception("Trip validation raised an exception")
        remarks = f"Trip validation error: {e}"
        if tool_context is not None:
            tool_context.state["temp:trip_validity"] = {"valid": False, "remarks": remarks}
        return {"status": "error", "status_code": None, "remarks": remarks}

    if not isinstance(raw, dict):
        logger.error("Unexpected trip validation return type: %s", type(raw).__name__)
        remarks = "Trip validation returned an unexpected format."
        if tool_context is not None:
            tool_context.state["temp:trip_validity"] = {"valid": False, "remarks": remarks}
        return {"status": "error", "status_code": None, "remarks": remarks}

    status = str(raw.get("status", "")).lower()
    status_code = raw.get("status_code")
    remarks = raw.get("remarks") or raw.get("error_message") or ""

    valid: bool = (status == "success")
    remarks = remarks or ("Trip validation succeeded." if valid else "Trip validation failed.")

    # Scratch space for downstream tools
    if tool_context is not None:
        tool_context.state["temp:trip_validity"] = {"valid": valid, "remarks": remarks}

    # ------------------------------------------------------------------
    # 3) Log outcome clearly
    # ------------------------------------------------------------------
    if valid:
        logger.info(
            "Trip validation succeeded [pernr=%s, dept_date=%s, arr_date=%s] → %s",
            pernr,
            dept_date,
            arr_date,
            remarks,
        )
    else:
        logger.warning(
            "Trip validation failed [pernr=%s, dept_date=%s, arr_date=%s] → %s",
            pernr,
            dept_date,
            arr_date,
            remarks,
        )

    # ------------------------------------------------------------------
    # 4) On success: fire flight prefetch in background (only once, only for Flight)
    # ------------------------------------------------------------------
    if valid and tool_context is not None:
        try:
            state = tool_context.state
            
            # # ------------------------------------------------------------------
            # # Save travel_details to tool_context.state
            # # ------------------------------------------------------------------
            # travel_details_to_save = {
            #     "travel_purpose": travel_purpose,
            #     "origin_city": origin_city,
            #     "origin_code": "",
            #     "country_beg": country_beg_norm,
            #     "destination_city": destination_city,
            #     "destination_code": "",
            #     "country_end": country_end_norm,
            #     "start_date": start_date,
            #     "end_date": end_date,
            #     "start_time": start_time,
            #     "end_time": end_time,
            #     "journey_type": "",
            #     "travel_mode": travel_mode,
            #     "travel_mode_code": travel_mode_code,
            #     "travel_class_text": "",
            #     "travel_class": "",
            #     "booking_method": "",
            #     "booking_method_code": "",
            #     "cost_center": "",
            #     "project_wbs": "",
            #     "travel_advance": "0.00",
            #     "additional_advance": "0.00",
            #     "reimburse_percentage": "100.00",
            #     "comment": ""
            # }
            
            # state["travel_details"] = travel_details_to_save
            # logger.info(
            #     "💾 Saved travel_details to tool_context.state | pernr=%s session_id=%s",
            #     pernr,
            #     session_id
            # )


            # Do not prefetch if this is not a Flight (defensive)
            if travel_mode.lower() != "flight" or travel_mode_code.upper() != "F":
                logger.info(
                    "Trip valid but travel_mode is not Flight (mode=%r, code=%r). "
                    "Skipping ES_GET flight prefetch [pernr=%s].",
                    travel_mode,
                    travel_mode_code,
                    pernr,
                )
            else:
                # Never start flight prefetch more than once per session
                if state.get("temp:flight_prefetch_started"):
                    logger.info(
                        "Skipping ES_GET flight prefetch; already started earlier [pernr=%s]",
                        pernr,
                    )
                else:
                    # Mark as started BEFORE starting thread (to avoid race)
                    state["temp:flight_prefetch_started"] = True

                    if not session_id:
                        # As a fallback, try again from context if needed
                        try:
                            _, session_id = _get_ids_from_tool_context(tool_context)
                        except Exception:
                            session_id = ""

                    if not session_id:
                        logger.warning(
                            "Skipping flight prefetch: missing session_id "
                            "[pernr=%s, session_id=%s]",
                            pernr,
                            session_id,
                        )
                    else:
                        # Build minimal travel_details payload for ES_GET flight
                        travel_details: Dict[str, Any] = {
                            "travel_purpose": travel_purpose,
                            "origin_city": origin_city,
                            "destination_city": destination_city,
                            "start_date": start_date,
                            "end_date": end_date,
                            "start_time": start_time,
                            "end_time": end_time,
                            "country_beg": country_beg_norm,
                            "country_end": country_end_norm,
                            "travel_mode": travel_mode,
                            "travel_mode_code": travel_mode_code,
                        }

                        logger.info(
                            "Scheduling ES_GET flight prefetch in background "
                            "[pernr=%s, session_id=%s] with travel_details=%s",
                            pernr,
                            session_id,
                            travel_details,
                        )

                        # Optionally stash this minimal structure for other tools
                        state["temp:travel_details"] = dict(travel_details)

                        def _run_flight_prefetch() -> None:
                            """
                            Fire-and-forget ES_GET flight search.

                            Runs in a separate daemon thread.
                            NEVER blocks check_trip_validity_tool's main flow.
                            """
                            try:
                                logger.info(
                                    "▶ Flight prefetch thread started [pernr=%s, session_id=%s] "
                                    "with travel_details=%s",
                                    pernr,
                                    session_id,
                                    travel_details,
                                )
                                travel_payload = dict(travel_details)
                                result = post_es_get_flight(travel_payload, pernr, session_id)
                                s = str(result.get("status", "")).lower()
                                sc = result.get("status_code")

                                if s in {"success", "ok"} and sc in {200, 201}:
                                    logger.info(
                                        "✅ Flight prefetch completed [pernr=%s, session_id=%s] "
                                        "status=%s status_code=%s result=%s",
                                        pernr,
                                        session_id,
                                        s,
                                        sc,
                                        result,
                                    )
                                    state["temp:flight_prefetch_result"] = {
                                        "status": "success",
                                        "status_code": sc,
                                        "message": "Flight API succeeded",
                                    }
                                else:
                                    logger.warning(
                                        "❌ Flight prefetch failed [pernr=%s, session_id=%s] "
                                        "status=%s status_code=%s result=%s",
                                        pernr,
                                        session_id,
                                        s,
                                        sc,
                                        result,
                                    )
                                    state["temp:flight_prefetch_result"] = {
                                        "status": "error",
                                        "status_code": sc or 500,
                                        "message": "Flight API failed",
                                    }

                            except Exception as e:
                                logger.exception(
                                    "❌ Flight prefetch raised exception [pernr=%s, session_id=%s]: %s",
                                    pernr,
                                    session_id,
                                    e,
                                )
                                state["temp:flight_prefetch_result"] = {
                                    "status": "error",
                                    "status_code": 500,
                                    "message": "Flight API failed",
                                }

                        # Fire-and-forget background thread (non-blocking)
                        try:
                            t = threading.Thread(
                                target=_run_flight_prefetch,
                                daemon=True,
                                name=f"es_get_flight_prefetch_{pernr}_{session_id}",
                            )
                            t.start()
                            logger.info(
                                "Background thread for ES_GET flight prefetch started "
                                "[pernr=%s, session_id=%s]",
                                pernr,
                                session_id,
                            )
                        except Exception as e:
                            logger.exception(
                                "Failed to start background thread for flight prefetch: %s",
                                e,
                            )

        except Exception as e:
            # Prefetch failures MUST NOT break validation response
            logger.exception(
                "Unexpected error while scheduling flight prefetch after validation: %s",
                e,
            )


    # ------------------------------------------------------------------
    # 5) Normalized return (FAST path back to main flow)
    # ------------------------------------------------------------------
    return {
        "status": "success" if valid else "error",
        "status_code": status_code if isinstance(status_code, int) else (200 if valid else 400),
        "remarks": remarks,
    }


    

async def post_es_get_tool(
    travel_purpose: str,
    origin_city: str,
    destination_city: str,
    start_date: str,
    end_date: str,
    start_time: str,
    end_time: str,
    journey_type: str,
    travel_mode: str,
    travel_mode_code: str,
    travel_class_text: str,
    travel_class: str,
    booking_method: str,
    booking_method_code: str,
    country_beg: Optional[str],
    country_end: Optional[str],
    tool_context: ToolContext,
) -> Dict[str, Any]:
    """
    Create a non-flight travel request draft in ES (ZHR_DOMESTIC_TRAVEL_SRV → ES_GET).

    This wrapper takes normalized scalar fields, builds the ES_GET travel_details payload,
    calls the underlying `post_es_get(...)`, and persists minimal scratch state.

    Parameters
    ----------
    travel_purpose : str
        Reason for travel (maps to REASON in ES_GET).
    origin_city : str
        Start city.
    destination_city : str
        End city.
    start_date : str
        Outbound (departure) date in YYYYMMDD.
    end_date : str
        Return (arrival) date in YYYYMMDD.
    start_time : str
        Outbound (departure) time in HHMM (24h).
    end_time : str
        Return (arrival) time in HHMM (24h).
    journey_type : str
        One-Way | Round-Trip
    travel_mode : str
        Travel mode string: "Bus" | "Own Car" | "Co.Arranged car" | "Train".
    travel_mode_code : str
        Travel mode code: "B" | "O" | "A" | "T".
    travel_class_text : str
        Human-readable class.
    travel_class : str
        Class code.
    booking_method : str
        "Company Booked" | "Self Booked" | "Others".
    booking_method_code : str
        "3" | "1" | "4".
    country_beg : Optional[str]
        Origin country code (defaults to "IN" if falsy).
    country_end : Optional[str]
        Destination country code (defaults to "IN" if falsy).
    tool_context : ToolContext
        ADK tool context used to resolve `pernr` / `session_id` and persist temp state.

    Returns
    -------
    dict
        {
          "ok": bool,
          "reason": str | None
        }
    """

    logger.info(
        "post_es_get_tool called with: "
        "travel_purpose=%r, origin_city=%r, destination_city=%r, "
        "start_date=%r, end_date=%r, start_time=%r, end_time=%r, journey_type=%r, "
        "travel_mode=%r, travel_mode_code=%r, travel_class_text=%r, "
        "travel_class=%r, booking_method=%r, booking_method_code=%r, "
        "country_beg=%r, country_end=%r",
        travel_purpose,
        origin_city,
        destination_city,
        start_date,
        end_date,
        start_time,
        end_time,
        journey_type,
        travel_mode,
        travel_mode_code,
        travel_class_text,
        travel_class,
        booking_method,
        booking_method_code,
        country_beg,
        country_end,
    )

    required_values = {
        "travel_purpose": travel_purpose,
        "origin_city": origin_city,
        "destination_city": destination_city,
        "start_date": start_date,
        "end_date": end_date,
        "start_time": start_time,
        "end_time": end_time,
        "travel_mode": travel_mode,
        "travel_mode_code": travel_mode_code,
        "travel_class_text": travel_class_text,
        "travel_class": travel_class,
        "booking_method": booking_method,
        "booking_method_code": booking_method_code,
    }
    missing = [k for k, v in required_values.items() if not str(v or "").strip()]
    if missing:
        msg = "post_es_get_tool missing required fields: " + ", ".join(missing)
        logger.warning(msg)
        raise ValueError(msg)

    country_beg_norm = country_beg or "IN"
    country_end_norm = country_end or "IN"

    pernr = ""
    session_id = ""
    if tool_context:
        try:
            user_id, session_id = _get_ids_from_tool_context(tool_context)
            pernr = str(user_id or "")
        except Exception as e:
            logger.warning("Could not resolve ids from ToolContext: %s", e)

    if not pernr:
        msg = "post_es_get_tool cannot resolve PERNR (app:user_id missing)"
        logger.error(msg)
        raise ValueError(msg)

    travel_details = {
        "travel_purpose": travel_purpose,
        "origin_city": origin_city,
        "destination_city": destination_city,
        "start_date": start_date,
        "end_date": end_date,
        "start_time": start_time,
        "end_time": end_time,
        "journey_type": journey_type,
        "country_beg": country_beg_norm,
        "country_end": country_end_norm,
        "origin_code": "",
        "destination_code": "",
        "travel_mode": travel_mode,
        "travel_mode_code": travel_mode_code,
        "travel_class_text": travel_class_text,
        "travel_class": travel_class,
        "booking_method": booking_method,
        "booking_method_code": booking_method_code,
        "booking_method_text": booking_method,
    }

    logger.info("travel_details payload prepared: %s", travel_details)

    # 🔥 async-safe call
    try:
        raw = await _to_async(post_es_get, travel_details, pernr, session_id)
        logger.info("post_es_get raw response: %s", raw)
    except Exception as e:
        logger.exception("post_es_get raised an exception")
        result = {"ok": False, "reason": f"post_es_get error: {e}"}
        if tool_context:
            tool_context.state["temp:post_es_get"] = result
        return result

    # Normalize result
    if not isinstance(raw, dict):
        result = {"ok": False, "reason": "post_es_get returned invalid structure"}
    else:
        ok = bool(raw.get("ok"))
        reason = raw.get("reason") or None
        result = {"ok": ok, "reason": reason}

    if tool_context:
        tool_context.state["temp:post_es_get"] = result
        if result["ok"]:
            tool_context.state["temp:travel_details"] = dict(travel_details)

    return result



# -------------------------
# post_es_final_tool (non-flight ES_FINAL)
# -------------------------
async def post_es_final_tool(
    travel_purpose: str,
    origin_city: str,
    destination_city: str,
    start_date: str,
    end_date: str,
    start_time: str,
    end_time: str,
    travel_mode: str,
    travel_mode_code: str,
    travel_class_text: str,
    travel_class: str,
    booking_method: str,
    booking_method_code: str,
    country_beg: Optional[str],
    country_end: Optional[str],
    journey_type: str,
    project_wbs: str,
    travel_advance: float,
    additional_advance: float,
    reimburse_percentage: float,
    comment: str,
    tool_context: ToolContext,
) -> Dict[str, Any]:
    """
    Finalize and submit a non-flight travel request via ES_FINAL and return the SAP trip ID.

    This tool-level wrapper exposes only scalar inputs (no `travel` dict), builds a normalized
    `travel` payload, resolves PERNR / session_id from the ToolContext, and calls the
    underlying `post_es_final(...)` function. It handles both One Way and Round Trip journeys
    based on `journey_type`.

    Parameters
    ----------
    travel_purpose : str
        Reason for travel (maps to REASON in ES_FINAL).
    origin_city : str
        Departure city name.
    destination_city : str
        Arrival city name.
    start_date : str
        Outbound travel date in YYYYMMDD format.
    end_date : str
        Return travel date in YYYYMMDD format. For one-way trips,
        this is usually the same as `start_date`.
    start_time : str
        Outbound time in HHMM (or compatible) format.
    end_time : str
        Return time in HHMM (or compatible) format.
    travel_mode : str
        Human-readable travel mode label
        Used mainly for UX and logging; ES uses the code.
    travel_mode_code : str
        SAP mode code
    travel_class_text : str
        Human-readable class label
    travel_class : str
        SAP travel class code
    booking_method : str
        Booking method text
    booking_method_code : str
        SAP booking method code corresponding to `booking_method`
    country_beg : Optional[str]
        Origin country code (2-letter ISO). If falsy, defaults to "IN".
    country_end : Optional[str]
        Destination country code (2-letter ISO). If falsy, defaults to "IN".
    journey_type : str
        Journey type preference: "One Way" or "Round Trip". Controls whether ES_FINAL
        builds a single-leg or two-leg NAV_FIN_TO_IT payload.
    project_wbs : str
        Project WBS element (POSNR) used for cost assignment in NAV_FIN_COST.
    travel_advance : float
        Travel advance amount requested (TRAVADV). Defaults to 0.00 if not provided.
    additional_advance : float
        Additional advance amount (ADDADV). Defaults to 0.00 if not provided.
    reimburse_percentage : float
        Reimbursement percentage for the trip (PERCENT in NAV_FIN_COST). Typically 100.0.
    comment : str
        Free-text comment or justification for the trip (COMMENT field in ES_FINAL).
    tool_context : ToolContext
        ADK tool context. Used to:
          - Resolve `(user_id, session_id)` → PERNR via `_get_ids_from_tool_context`.
          - Persist intermediate state in:
              * `tool_context.state["temp:post_es_final"]`
              * `tool_context.state["temp:travel"]` (normalized travel payload).

    Returns
    -------
    Dict[str, Any]
        Normalized ES_FINAL result object with the schema:

        {
          "success": bool,                 # True if ES_FINAL HTTP call succeeded (2xx)
          "trip_id": str | None,           # SAP trip number (REINR) if available
          "error": str | None,             # Error message on failure; None on success
          "status_code": int | None,       # HTTP status code from ES_FINAL
          "raw_response": dict | str | None
              # Parsed SAP JSON response if available; otherwise truncated raw text
        }

        Additionally, a compact status is stored in the ToolContext:

        - tool_context.state["temp:post_es_final"] = {
              "ok": bool,                  # Mirrors `success`
              "reason": str                # Error message or "OK"
          }

        and the normalized scalar travel payload is persisted at:

        - tool_context.state["temp:travel"]  # For downstream tools/agents.
    """

    logger.info(
        "post_es_final_tool called with: "
        "travel_purpose=%r, origin_city=%r, destination_city=%r, "
        "start_date=%r, end_date=%r, start_time=%r, end_time=%r, "
        "travel_mode=%r, travel_mode_code=%r, travel_class_text=%r, "
        "travel_class=%r, booking_method=%r, booking_method_code=%r, "
        "country_beg=%r, country_end=%r, journey_type=%r, "
        "project_wbs=%r, travel_advance=%r, additional_advance=%r, "
        "reimburse_percentage=%r",
        travel_purpose,
        origin_city,
        destination_city,
        start_date,
        end_date,
        start_time,
        end_time,
        travel_mode,
        travel_mode_code,
        travel_class_text,
        travel_class,
        booking_method,
        booking_method_code,
        country_beg,
        country_end,
        journey_type,
        project_wbs,
        travel_advance,
        additional_advance,
        reimburse_percentage,
    )

    # ----------------------------
    # Basic validation
    # ----------------------------
    required_values = {
        "travel_purpose": travel_purpose,
        "origin_city": origin_city,
        "destination_city": destination_city,
        "start_date": start_date,
        "end_date": end_date,
        "start_time": start_time,
        "end_time": end_time,
        "travel_mode": travel_mode,
        "travel_mode_code": travel_mode_code,
        "travel_class_text": travel_class_text,
        "travel_class": travel_class,
        "booking_method": booking_method,
        "booking_method_code": booking_method_code,
        "journey_type": journey_type,
        "project_wbs": project_wbs,
    }
    missing = [k for k, v in required_values.items() if not str(v or "").strip()]
    if missing:
        msg = "post_es_final_tool missing required fields: " + ", ".join(missing)
        logger.warning(msg)
        raise ValueError(msg)

    country_beg_norm = (country_beg or "IN").strip() or "IN"
    country_end_norm = (country_end or "IN").strip() or "IN"
    journey_type_norm = (journey_type or "").strip()

    # ----------------------------
    # Resolve PERNR & session_id from ToolContext
    # ----------------------------
    try:
        user_id, session_id = _get_ids_from_tool_context(tool_context)
        pernr = str(user_id or "").strip()
        logger.info("Resolved PERNR and session_id in post_es_final_tool: %s, %s", pernr, session_id)
    except Exception as e:
        logger.exception("Could not resolve PERNR/session_id from ToolContext: %s", e)
        raise ValueError("post_es_final_tool cannot resolve PERNR/session_id from ToolContext") from e

    if not pernr:
        msg = "post_es_final_tool cannot resolve PERNR (app:user_id missing)"
        logger.error(msg)
        raise ValueError(msg)

    # ----------------------------
    # Build normalized travel dict for ES_FINAL
    # ----------------------------
    travel: Dict[str, Any] = {
        "travel_purpose": travel_purpose,
        "origin_city": origin_city,
        "destination_city": destination_city,
        "start_date": start_date,
        "end_date": end_date,
        "start_time": start_time,
        "end_time": end_time,
        "country_beg": country_beg_norm,
        "country_end": country_end_norm,
        "origin_code": "",              # ES_FINAL reads codes from ES_GET response
        "destination_code": "",
        "travel_mode": travel_mode,
        "travel_mode_code": travel_mode_code,
        "travel_class_text": travel_class_text,
        "travel_class": travel_class,
        "booking_method": booking_method,
        "booking_method_code": booking_method_code,
        "booking_method_text": booking_method,
        "journey_type": journey_type_norm,
        "project_wbs": project_wbs,
        "travel_advance": float(travel_advance or 0.0),
        "additional_advance": float(additional_advance or 0.0),
        "reimburse_percentage": float(reimburse_percentage or 100.0),
        "comment": comment or "",
    }

    logger.info("post_es_final_tool travel payload prepared: %s", travel)

    # ----------------------------
    # Call underlying ES_FINAL business function
    # ----------------------------
    try:
        raw: Dict[str, Any] = await _to_async(post_es_final, travel, pernr, session_id)
        logger.info("post_es_final raw response for pernr=%s: %s", pernr, raw)
    except Exception as e:
        logger.exception("post_es_final raised an exception for pernr=%s", pernr)
        result = {
            "success": False,
            "trip_id": None,
            "error": f"post_es_final error: {e}",
            "status_code": None,
            "raw_response": None,
        }
        if tool_context is not None:
            tool_context.state["temp:post_es_final"] = {"ok": False, "reason": result["error"]}
        return result

    # ----------------------------
    # Normalize result
    # ----------------------------
    if not isinstance(raw, dict):
        logger.error("Unexpected post_es_final return type for pernr=%s: %s", pernr, type(raw).__name__)
        result = {
            "success": False,
            "trip_id": None,
            "error": "post_es_final returned an unexpected format.",
            "status_code": None,
            "raw_response": raw,
        }
    else:
        success = bool(raw.get("success", False))
        trip_id = raw.get("trip_id")
        error = raw.get("error")
        status_code = raw.get("status_code")
        raw_response = raw.get("raw_response")

        result = {
            "success": success,
            "trip_id": trip_id if trip_id else None,
            "error": str(error) if error else None,
            "status_code": status_code if isinstance(status_code, int) else (200 if success else 400),
            "raw_response": raw_response,
        }

        if success:
            if trip_id:
                logger.info("post_es_final succeeded for pernr=%s → trip_id=%s", pernr, trip_id)

                # ---------------------------------------------------
                # NEW: Write trip_id into ADK session.state directly
                # (So auto_save_to_memory_callback can pick it up)
                # ---------------------------------------------------
                try:
                    session_state = getattr(tool_context, "session_state", {}) if tool_context else {}
                    old_trip = session_state.get("trip_id")

                    if trip_id != "0000000000" and trip_id and trip_id != old_trip:
                        new_state = dict(session_state)
                        new_state["trip_id"] = trip_id
                        tool_context.session_state = new_state

                        logger.info(
                            "🔐 Stored trip_id into session.state | old=%s new=%s pernr=%s session=%s",
                            old_trip,
                            trip_id,
                            pernr,
                            getattr(tool_context, "session_id", None),
                        )
                    else:
                        logger.info(
                            "ℹ Session trip_id unchanged | existing=%s incoming=%s pernr=%s",
                            old_trip,
                            trip_id,
                            pernr,
                        )

                except Exception as e:
                    logger.exception(
                        "❌ Failed writing trip_id to session.state in post_es_final_tool | pernr=%s session=%s error=%s",
                        pernr,
                        getattr(tool_context, "session_id", None),
                        e,
                    )
                # ---------------------------------------------------

            else:
                logger.warning("post_es_final succeeded for pernr=%s but no trip_id returned", pernr)
        else:
            logger.warning("post_es_final failed for pernr=%s → %s", pernr, error)


        # ----------------------------
        # Persist scratch state
        # ----------------------------
        if tool_context is not None:
            # -------------------------------------------------------------------
            # FIX: Explicitly store the trip_id in the temp:post_es_final state
            # -------------------------------------------------------------------
            tool_context.state["temp:post_es_final"] = {
                "ok": result["success"],
                "reason": result["error"] or "OK",
                "trip_id": result.get("trip_id"), # <-- ADD THIS LINE
            }
            # Also persist travel for downstream tools if needed
            try:
                tool_context.state["temp:travel"] = dict(travel)
            except Exception:
                logger.exception("Failed to persist temp:travel in ToolContext.state")

            if result.get("trip_id"):
                logger.info("Stored trip_id=%s in temp:post_es_final for pernr=%s", result["trip_id"], pernr)

        return result






# -------------------------
# NEW: post_es_get_final_tool (Flight Search)
# -------------------------
async def post_es_get_flight_tool(
    pernr: str,
    travel: Dict[str, Any],
    tool_context: ToolContext,
) -> Dict[str, Any]:
    """
    Search available flights using ES_GET (flight) based on the user's trip preferences.

    Purpose
    -------
    - Builds the ES_GET flight payload from the given `travel` dict (origin/destination, dates, times,
    class, booking method, etc.) and posts it to the SAP backend.
    - Extracts and persists lean flight listings (`nav_preffered`, `nav_getsearch`) for later selection.

    Parameters
    ----------
    pernr : str
        Personnel number / employee identifier for the logged-in user.

    travel_details : dict
        Travel details extracted from the current session state's JSON.
        This dict represents the normalized fields needed to construct the ES_GET (flight) payload. 
        Expected keys and types:
            {
            "travel_purpose": str,           # Reason for travel 
            "origin_city": str,              # Start city 
            "origin_code": str,              # Origin airport/station code 
            "country_beg": str,              # 2-letter ISO country code 
            "destination_city": str,         # End city 
            "destination_code": str,         # Destination airport/station code 
            "country_end": str,              # 2-letter ISO country code 
            "start_date": str,               # YYYYMMDD format 
            "end_date": str,                 # YYYYMMDD format 
            "start_time": str,               # HHMM format 
            "end_time": str,                 # HHMM format 
            "journey_type": str,             # "One Way" | "Round Trip"
            "travel_mode": str,              # Always "Flight" for this tool
            "travel_mode_code": str,         # "F" (code for Flight)
            "travel_class_text": str,        # "Economy Class"
            "travel_class": str,             # "EC"
            "booking_method": str,           # "Company Booked" | "Self Booked" | "Others"
            "booking_method_code": str,      # "3" | "1" | "4"
            "project_wbs": str,              # Work Breakdown Structure element
            "travel_advance": float,         # Requested advance (default: 0.00)
            "additional_advance": float,     # Additional advance (default: 0.00)
            "reimburse_percentage": int      # % reimbursement (default: 100),
            "comment" : ""                   # String: Any additional comments.
            }

        Notes:
        - Mandatory flight fields: origin_city/origin_code, destination_city/destination_code,
        start_date, end_date, start_time, end_time, travel_class, and booking_method.
        - This tool specifically requires `travel_mode_code="F"` (Flight).

    tool_context : ToolContext
        Injected by ADK. Used to pass data between tools for the current invocation via temp state.
        - Reads: "temp:travel" / "temp:travel_details" if `travel` is None
        - Writes: "temp:travel", "temp:post_es_get_final"

    Returns (normalized)
    --------------------
    dict
        {
        "success": bool,                  # True if API call succeeded (HTTP 200/201), else False
        "trip_id": str | None,            # SAP trip number (REINR) if available (ES_GET does not create trips, so None)
        "error": str | None,              # Diagnostic error message on failure, None on success
        "status_code": int | None,        # HTTP status code if available
        "raw_response": dict | str | None # Parsed SAP JSON if available, else raw body (may be None)
        }
    """

    # Resolve IDs
    try:
        user_id, session_id = _get_ids_from_tool_context(tool_context)
    except Exception as e:
        logger.exception("Failed to read user/session ids from ToolContext")
        return {
            "success": False,
            "trip_id": None,
            "error": f"ToolContext id resolution failed: {e}",
            "status_code": None,
            "raw_response": None,
        }

    # Resolve travel from temp state if not provided
    if travel is None and tool_context is not None:
        try:
            travel = (
                tool_context.state.get("temp:travel")
                or tool_context.state.get("temp:travel_details")
                or {}
            )
            logger.info("Using travel from temp state for ES_GET flight: %s", travel)
        except Exception as e:
            logger.warning("Could not resolve travel from ToolContext: %s", e)
            travel = travel or {}

    logger.info("travel details before calling the API")
    logger.info(f"{travel}")
    # Call underlying implementation (sync) via adapter and normalize
    try:
        raw = await _to_async(post_es_get_flight, travel, pernr, session_id)
        logger.info("post_es_get_flight returned: %s", type(raw).__name__)
    except Exception as e:
        logger.exception("post_es_get_flight raised an exception")
        return {
            "success": False,
            "trip_id": None,
            "error": f"post_es_get_flight error: {e}",
            "status_code": None,
            "raw_response": None,
        }

    # Validate expected shape
    if not isinstance(raw, dict):
        logger.error("Unexpected post_es_get_flight return type: %s", type(raw).__name__)
        return {
            "success": False,
            "trip_id": None,
            "error": "post_es_get_flight returned an unexpected format",
            "status_code": None,
            "raw_response": None,
        }

    status_code = raw.get("status_code")
    status = raw.get("status")
    error = raw.get("error")

    if error:
        tool_context.state["temp:flight_search_error"] = {
            "message": error,
            "code": raw.get("validation_type") or "NO_FLIGHTS",
            "chk": raw.get("validation_chk") or "E",
        }

    # Determine success (ES_GET success path saves lean results to Redis; no REINR expected here)
    is_success = bool(status in {"success", "ok"} and status_code in {200, 201} and not error)

    # Optionally persist minimal temp state (non-fatal)
    try:
        if tool_context is not None:
            tool_context.state["temp:post_es_get_final"] = {
                "ok": is_success,
                "reason": None if is_success else (str(error) if error else "ES_GET failed"),
            }
            if travel:
                tool_context.state["temp:travel"] = travel
    except Exception as e:
        logger.warning("Failed to update ToolContext temp state: %s", e)

    # Normalize final return
    if is_success:
        return {
            "success": True,
            "trip_id": None,            # ES_GET does not create a trip
            "error": None,
            "status_code": status_code,
            "raw_response": None,       # Underlying function doesn't return SAP JSON here
        }

    # Error path
    return {
        "success": False,
        "trip_id": None,
        "error": str(error) if error else "ES_GET flight search failed",
        "status_code": status_code if isinstance(status_code, int) else None,
        "raw_response": None,
    }



# -------------------------
# Combined: post_es_final_flight_tool
# (Runs ES_REPRICE first, then ES_FINAL flight booking)
# -------------------------

async def post_es_final_flight_tool(
    travel_purpose: str,
    origin_city: str,
    destination_city: str,
    start_date: str,
    end_date: str,
    start_time: str,
    end_time: str,
    journey_type: str,
    travel_mode: str,
    travel_mode_code: str,
    travel_class_text: str,
    travel_class: str,
    booking_method: str,
    booking_method_code: str,
    project_wbs: Optional[str],
    comment: Optional[str],
    tool_context: ToolContext,
) -> Dict[str, Any]:
    """
    Book a flight trip in ES by performing ES_REPRICE + ES_FINAL in one tool call.

    This tool is the *only* flight-booking tool the agent needs to call.
    It performs the following steps:

      1. Uses `tool_context` to resolve PERNR (employee id) and session_id.
      2. Calls `post_es_reprice(PERNR, session_id)` to reprice the user's
         preferred flight(s) (stored in Redis under `preffered_flights`).
         - This loads data from Redis and persists the cleaned ES_REPRICE
           response back to Redis as `es_reprice`.
      3. If ES_REPRICE succeeds, calls
         `post_es_final_flight(travel, PERNR, session_id)` to send the
         ES_FINAL (flight) booking request.
         - `post_es_final_flight` loads all required data from Redis:
             * Employee header        → `header`
             * Flight search details  → `es_get_flight_oneway or es_get_flight_roundtrip`
             * ES_REPRICE response    → `es_reprice`
           and builds the final payload for ES_FINAL (one-way or round-trip
           is inferred from these structures).
      4. Returns the same normalized schema as `post_es_final_flight`.

    The scalar parameters are provided for consistency with the rest of the
    tools (no `travel` dict). At the moment, only `project_wbs` and `comment`
    are used to enrich the NAV_FIN_COST and COMMENT fields in ES_FINAL,
    but the other fields are logged and may be used later if needed.

    ----------------------------------------------------------------------
    INPUT PARAMETERS
    ----------------------------------------------------------------------
    travel_purpose : str
        High-level purpose of travel.
        (The actual REASON used by ES_FINAL is already present in Redis
         via the ES_GET flight search payload.)

    origin_city : str
        Origin city. Used earlier in the flow to build
        ES_GET; here it is just logged for traceability.

    destination_city : str
        Destination city. Same as above.

    start_date : str
        Departure date in `YYYYMMDD`. Same as above (logged for traceability).

    end_date : str
        Return date in `YYYYMMDD`. Same as above (logged for traceability).

    start_time : str
        Departure time in `HHMM` 24h format. Same as above.

    end_time : str
        Return time in `HHMM` 24h format. Same as above.

    journey_type : str
        "One Way" | "Round Trip".
        The ES_FINAL flight payload infers actual structure
        (one-way vs round-trip) from ES_GET + ES_REPRICE data in Redis.

    travel_mode : str
        Travel mode string. For this tool it SHOULD be "Flight".
        (Used primarily for logging and validation.)

    travel_mode_code : str
        Travel mode code. For this tool it SHOULD be "F".

    travel_class_text : str
        Human-readable flight class.
        (Already captured earlier in ES_GET; here it is logged only.)

    travel_class : str
        Flight class code.

    booking_method : str
        "Company Booked" | "Self Booked" | "Others".
        (Already reflected via ES_GET + frontend; logged here.)

    booking_method_code : str
        "3" | "1" | "4".

    project_wbs : Optional[str]
        WBS element to be associated with this trip.
        This is passed into `post_es_final_flight` via the `travel` payload
        and becomes `POSNR` in `NAV_FIN_COST`.

    comment : Optional[str]
        Free-text comment / justification. Passed into `post_es_final_flight`
        and mapped to the ES_FINAL `COMMENT` field.

    tool_context : ToolContext
        ADK tool context used to:
          - Read `app:user_id` / `app:session_id` from `tool_context.state`.
          - Persist scratch results:
              * `temp:post_es_reprice`
              * `temp:post_es_final_flight`

    ----------------------------------------------------------------------
    OUTPUT SCHEMA
    ----------------------------------------------------------------------
    Returns a dict with the SAME schema as `post_es_final_flight`:

        {
          "success": bool,                  # True if ES_FINAL returned 200/201
          "trip_id": str | None,           # SAP trip number (REINR) if available
          "error": str | None,             # Error / warning message or None
          "status_code": int | None,       # HTTP status code from ES_FINAL
          "raw_response": dict | str | None  # Parsed JSON or truncated text
        }

    - If ES_REPRICE fails, this tool returns `success=False`, `trip_id=None`,
      and `error` describing the ES_REPRICE failure.
    - If ES_REPRICE succeeds but ES_FINAL fails, the error from
      `post_es_final_flight` is propagated.

    Side Effects:
    -------------
    - Always reads required inputs from Redis inside `post_es_reprice`
      and `post_es_final_flight`.
    - Saves ES_REPRICE response in Redis as `es_reprice`.
    - Saves REINR (trip_id) in Redis as `es_final_flight` (inside
      `post_es_final_flight`) if booking succeeds.
    - Writes compact summaries to:
        * tool_context.state["temp:post_es_reprice"]
        * tool_context.state["temp:post_es_final_flight"]
    """

    logger.info(
        "post_es_final_flight_tool called with: "
        "travel_purpose=%r, origin_city=%r, destination_city=%r, "
        "start_date=%r, end_date=%r, start_time=%r, end_time=%r, "
        "journey_type=%r, travel_mode=%r, travel_mode_code=%r, "
        "travel_class_text=%r, travel_class=%r, booking_method=%r, "
        "booking_method_code=%r, project_wbs=%r, comment=%r",
        travel_purpose,
        origin_city,
        destination_city,
        start_date,
        end_date,
        start_time,
        end_time,
        journey_type,
        travel_mode,
        travel_mode_code,
        travel_class_text,
        travel_class,
        booking_method,
        booking_method_code,
        project_wbs,
        comment,
    )

    # ------------------------------------------------------------------
    # 1) Resolve PERNR and session_id from ToolContext
    # ------------------------------------------------------------------
    pernr = ""
    session_id = ""
    if tool_context is not None:
        try:
            user_id, session_id = _get_ids_from_tool_context(tool_context)
            pernr = str(user_id or "")
        except Exception as e:
            logger.warning("post_es_final_flight_tool: could not resolve ids from ToolContext: %s", e)

    if not pernr:
        msg = (
            "post_es_final_flight_tool cannot resolve PERNR "
            "(expected in tool_context.state['app:user_id'])."
        )
        logger.error(msg)
        raise ValueError(msg)

    logger.info(
        "post_es_final_flight_tool resolved pernr=%s, session_id=%s, journey_type=%s",
        pernr,
        session_id,
        journey_type,  # ✅ Log journey_type for traceability
    )

    # ------------------------------------------------------------------
    # 2) Call ES_REPRICE first (required Redis data loader)
    # ------------------------------------------------------------------
    try:
        # ✅ FIXED: Pass journey_type as third parameter
        reprice_raw: Dict[str, Any] = await _to_async(
            post_es_reprice, 
            pernr, 
            session_id, 
            journey_type  # ✅ Now passing journey_type!
        )
        logger.info(
            "post_es_reprice raw result for pernr=%s, session_id=%s, journey_type=%s: %s",
            pernr,
            session_id,
            journey_type,
            reprice_raw,
        )
    except Exception as e:
        logger.exception("post_es_reprice raised an exception for pernr=%s", pernr)
        error_msg = f"post_es_reprice error: {e}"
        if tool_context is not None:
            tool_context.state["temp:post_es_reprice"] = {"ok": False, "reason": error_msg}
        return {
            "success": False,
            "trip_id": None,
            "error": error_msg,
            "status_code": None,
            "raw_response": None,
        }

    # Normalize ES_REPRICE output (expected: {"ok": bool, "reason": str | None})
    ok_reprice = bool(reprice_raw.get("ok"))
    reason_reprice = reprice_raw.get("reason") or None

    if tool_context is not None:
        tool_context.state["temp:post_es_reprice"] = {
            "ok": ok_reprice,
            "reason": reason_reprice or ("OK" if ok_reprice else "ES_REPRICE failed"),
        }

    if not ok_reprice:
        # Short-circuit: do NOT call ES_FINAL if repricing failed
        logger.warning(
            "ES_REPRICE failed for pernr=%s, session_id=%s, journey_type=%s → %s",
            pernr,
            session_id,
            journey_type,
            reason_reprice,
        )
        return {
            "success": False,
            "trip_id": None,
            "error": f"ES_REPRICE failed: {reason_reprice}",
            "status_code": None,
            "raw_response": None,
        }

    logger.info(
        "ES_REPRICE succeeded for pernr=%s, session_id=%s, journey_type=%s; proceeding to ES_FINAL flight.",
        pernr,
        session_id,
        journey_type,
    )

    # ------------------------------------------------------------------
    # 3) Call ES_FINAL (flight) using Redis-backed business function
    # ------------------------------------------------------------------
    travel_for_final: Dict[str, Any] = {
        "project_wbs": project_wbs or "",
        "comment": comment or "",
        "journey_type": journey_type or "", 
    }

    try:
        final_raw: Dict[str, Any] = await _to_async(
            post_es_final_flight, travel_for_final, pernr, session_id
        )
        logger.info(
            "post_es_final_flight raw response for pernr=%s, session_id=%s: %s",
            pernr,
            session_id,
            final_raw,
        )
    except Exception as e:
        logger.exception("post_es_final_flight raised an exception for pernr=%s", pernr)
        result = {
            "success": False,
            "trip_id": None,
            "error": f"post_es_final_flight error: {e}",
            "status_code": None,
            "raw_response": None,
        }
        if tool_context is not None:
            tool_context.state["temp:post_es_final_flight"] = {
                "ok": False,
                "reason": result["error"],
            }
        return result

    # ------------------------------------------------------------------
    # 4) Normalize ES_FINAL flight output (align with original schema)
    # ------------------------------------------------------------------
    if not isinstance(final_raw, dict):
        logger.error(
            "Unexpected post_es_final_flight return type for pernr=%s: %s",
            pernr,
            type(final_raw).__name__,
        )
        result = {
            "success": False,
            "trip_id": None,
            "error": "post_es_final_flight returned an unexpected format.",
            "status_code": None,
            "raw_response": final_raw,
        }
    else:
        success = bool(final_raw.get("success", False))
        trip_id = final_raw.get("trip_id")
        error = final_raw.get("error")
        status_code = final_raw.get("status_code")
        raw_response = final_raw.get("raw_response")

        result = {
            "success": success,
            "trip_id": trip_id if trip_id else None,
            "error": str(error) if error else None,
            "status_code": (
                status_code
                if isinstance(status_code, int)
                else (200 if success else 400)
            ),
            "raw_response": raw_response,
        }

        if success:
            if trip_id:
                logger.info(
                    "post_es_final_flight succeeded for pernr=%s → trip_id=%s",
                    pernr,
                    trip_id,
                )

                # ---------------------------------------------------
                # NEW: Write trip_id into ADK session.state directly
                # (So auto_save_to_memory_callback can pick it up)
                # ---------------------------------------------------
                try:
                    session_state = getattr(tool_context, "session_state", {}) if tool_context else {}
                    old_trip = session_state.get("trip_id")

                    if trip_id != "0000000000" and trip_id and trip_id != old_trip:
                        new_state = dict(session_state)
                        new_state["trip_id"] = trip_id
                        tool_context.session_state = new_state

                        logger.info(
                            "🔐 Stored trip_id into session.state (flight) | old=%s new=%s pernr=%s session=%s",
                            old_trip,
                            trip_id,
                            pernr,
                            getattr(tool_context, "session_id", None),
                        )
                    else:
                        logger.info(
                            "ℹ Session trip_id (flight) unchanged | existing=%s incoming=%s pernr=%s",
                            old_trip,
                            trip_id,
                            pernr,
                        )

                except Exception as e:
                    logger.exception(
                        "❌ Failed writing trip_id to session.state in post_es_final_flight_tool | pernr=%s session=%s error=%s",
                        pernr,
                        getattr(tool_context, "session_id", None),
                        e,
                    )
                # ---------------------------------------------------

            else:
                logger.warning(
                    "post_es_final_flight succeeded for pernr=%s but no trip_id returned",
                    pernr,
                )
        else:
            logger.warning(
                "post_es_final_flight failed for pernr=%s → %s",
                pernr,
                error,
            )

    # ------------------------------------------------------------------
    # 5) Persist compact ES_FINAL status into tool_context.state
    # ------------------------------------------------------------------
    if tool_context is not None:
        tool_context.state["temp:post_es_final_flight"] = {
            "ok": result["success"],
            "reason": result["error"] or "OK",
        }
        if result.get("trip_id"):
            logger.info(
                "Stored trip_id=%s in temp:post_es_final_flight for pernr=%s",
                result["trip_id"],
                pernr,
            )

    return result


# -------------------------
# cancel_trip_tool
# -------------------------

async def cancel_trip_tool(
    pernr: str,
    travel: Dict[str, Any],
    tool_context: Any,
) -> Dict[str, Any]:
    """
    Cancel an existing SAP travel trip for the given employee.

    Parameters:
        pernr (str): Employee personnel number (8-digit SAP ID).
        travel (dict): Travel details containing:
            - "trip_id": str → Trip number to cancel.
        tool_context (ToolContext): Execution context for temporary state persistence.

    Returns:
        dict: {
            "ok": bool,      # True if trip cancellation succeeded, else False
            "reason": str    # Descriptive success or failure message
        }

    Side Effects:
        Stores {"ok": bool, "reason": str} in tool_context.state["temp:cancel_trip"].
    """
    try:
        # Prepare input for cancel_trip()
        trip_json = {
            "employee_id": pernr,
            "trip_id": travel.get("trip_id", "")
        }
        
        logger.info(f"trip_json in cancel API :", trip_json)

        ok, result = await _to_async(cancel_trip, trip_json)

        reason = (
            result.get("MESSAGE", "")
            if ok and isinstance(result, dict)
            else str(result)
        )

    except Exception as e:
        ok = False
        reason = f"Exception during cancel_trip_tool: {e}"
        logger.error(reason)

    out = {"ok": ok, "reason": reason}

    if tool_context is not None:
        tool_context.state["temp:cancel_trip"] = out

    return out




# -------------------------
# analyze_reimbursement_documents_tool
# -------------------------

async def analyze_reimbursement_documents_tool(
    documents: List[Any],
    tool_context: ToolContext,    # ToolContext
) -> Dict[str, Any]:
    """
    Analyze reimbursement documents (PDFs, images) and extract structured fields.

    Purpose
    -------
    - Normalizes incoming document references (paths, dicts, or SavedFile objects).
    - Calls the Reimbursement OCR API to classify and extract fields for
      Travel, Food, and Hotel bills.
    - Supports multiple files in a single request.

    Parameters
    ----------
    documents : list[str | dict | SavedFile]
        One or more document references, in any of the following forms:
          - str : direct file path (must exist on disk).
          - dict : object with {"path": "<file path>"}.
          - SavedFile (pydantic model) or any object with a `.path` attribute.

        Each path must exist locally; missing paths are reported as error.

    tool_context : ToolContext, optional
        Injected automatically by ADK. Used to stash results in
        `tool_context.state["temp:analyze_results"]` for downstream tools.

    Returns (normalized)
    --------------------
    dict
        {
          "status": "success" | "error",   # Overall result of OCR request
          "http_status": int | None,       # HTTP status code from OCR API
          "data": dict | None,             # OCR API response JSON (when available)
          "error_message": str | None      # Diagnostic message if error
        }

    Description of `data`
    ---------------------
    When successful, `data` reflects the OCR service contract, e.g.:

    {
      "status": "ok" | "error",
      "session_id": str,
      "messages": list,
      "results": [
        {
          "file_id": str,
          "original_filename": str,
          "classification": "Travel" | "Food" | "Hotel",
          "status": "ok" | "error",
          "brand": dict | null,
          "pages": [
            {
              "page_id": str,
              "classification": str,
              "status": str,
              "data": {
                # Extracted fields depending on classification
              },
              "doc_code": str
            }
          ],
          "data": {
            # Hotel-level fields if applicable
          },
          "messages": list,
          "doc_code": str
        }
      ]
    }

    Temp State
    ----------
    - Writes the normalized output dictionary into
      `tool_context.state["temp:analyze_results"]` if tool_context is provided.
    - Downstream tools and stages can consume this directly.
    """
    # --- Resolve user_id & session_id (required for folder + Redis) -----------
    try:
        user_id, session_id = _get_ids_from_tool_context(tool_context)
    except Exception as e:
        out = {
            "status": "error",
            "http_status": 0,
            "error_message": f"ToolContext id resolution failed: {e}",
            "data": None,
        }
        tool_context.state["temp:analyze_results"] = out
        logger.exception("ToolContext id resolution failed in analyze_reimbursement_documents_tool")
        return out

    # --- Compute folder and collect files ------------------------------------
    # function_tools.py is likely under: travel_assist_agentic_bot/tools/...
    # repo_root -> travel_assist_agentic_bot
    repo_root = Path(__file__).resolve().parents[1]
    folder = (repo_root / "responses" / "reimburse_files" / f"{user_id}_{session_id}")

    if not folder.exists() or not folder.is_dir():
        msg = f"No upload folder found for user_id={user_id}, session_id={session_id}: {folder.as_posix()}"
        out = {
            "status": "error",
            "http_status": 0,
            "error_message": msg,
            "data": None,
        }
        tool_context.state["temp:analyze_results"] = out
        logger.warning("analyze_reimbursement_documents_tool: %s", msg)
        return out

    # Pick all regular files
    file_paths: List[Path] = [p for p in folder.iterdir() if p.is_file()]
    logger.info(
        "Reimbursement analyze: scanning folder %s → %d files",
        folder.as_posix(), len(file_paths)
    )
    for i, p in enumerate(sorted(file_paths), 1):
        logger.info(
            "   • [%02d] %s (exists=%s, size=%s bytes)",
            i, p.as_posix(), p.exists(), (p.stat().st_size if p.exists() else "NA")
        )

    if not file_paths:
        msg = f"No files found in {folder.as_posix()} for user_id={user_id}, session_id={session_id}"
        out = {
            "status": "error",
            "http_status": 0,
            "error_message": msg,
            "data": None,
        }
        tool_context.state["temp:analyze_results"] = out
        logger.warning("analyze_reimbursement_documents_tool: %s", msg)
        return out

    # --- Call core client: stores JSON in Redis; returns status + data --------
    try:
        result = await _to_async(
            analyze_reimbursement_documents,
            file_paths,            # absolute Paths collected above
            str(user_id),
            str(session_id),
        )
        logger.info("analyze_reimbursement_documents response: %s", result)
    except Exception as e:
        logger.exception("analyze_reimbursement_documents raised an exception")
        out = {
            "status": "error",
            "http_status": 0,
            "error_message": f"analyze_reimbursement_documents failed: {e}",
            "data": None,
        }
        tool_context.state["temp:analyze_results"] = out
        return out

    # --- Normalize/guard: expect status/http_status/error_message/data --------
    if not isinstance(result, dict):
        out = {
            "status": "error",
            "http_status": None,
            "error_message": "Unexpected response format from analyze_reimbursement_documents.",
            "data": None,
        }
    else:
        normalized_status = "success" if result.get("status") == "success" else "error"
        out = {
            "status": normalized_status,
            "http_status": result.get("http_status") if isinstance(result.get("http_status"), int) else None,
            "error_message": result.get("error_message"),
            "data": result.get("data") if normalized_status == "success" else None,
        }

        if out["status"] == "success":
            logger.info("analyze_reimbursement_documents succeeded [http_status=%s]", out["http_status"])
        else:
            logger.warning(
                "analyze_reimbursement_documents failed [http_status=%s] → %s",
                out["http_status"], out["error_message"]
            )

    # --- Temp state for chaining ---------------------------------------------
    tool_context.state["temp:analyze_results"] = out
    logger.info("Stored analyze status in temp:analyze_results")
    return out




# -------------------------
# get_es_trip_det_tool
# -------------------------
async def get_es_trip_det_tool(
    pernr: str,
    reinr: str,
    tool_context: ToolContext,
) -> Dict[str, Any]:
    """
    Fetch and cache SAP trip details (ES_TRIP_DET).

    Parameters:
        pernr (str): Employee personnel number.
        reinr (str): SAP trip number.
        tool_context (ToolContext): Injected by ADK; used to read session_id and store temp state.

    Returns (normalized):
        dict: {
          "ok": bool,             # True on success; else False
          "reason": str | None,   # None on success; diagnostic reason on failure
          "data": dict | None     # Cleaned ES_TRIP_DET JSON on success; None on failure
        }
    """
    try:
        _user_id, session_id = _get_ids_from_tool_context(tool_context)
    except Exception as e:
        logger.exception("ToolContext id resolution failed in get_es_trip_det_tool")
        out = {
            "ok": False,
            "reason": f"ToolContext id resolution failed: {e}",
            "data": None,
        }
        tool_context.state["temp:es_trip_det"] = out
        return out

    try:
        raw = await _to_async(get_es_trip_det, pernr, reinr, session_id)
        logger.info("get_es_trip_det raw response: %s", raw)
    except Exception as e:
        logger.exception("get_es_trip_det raised an exception")
        out = {
            "ok": False,
            "reason": f"get_es_trip_det error: {e}",
            "data": None,
        }
        tool_context.state["temp:es_trip_det"] = out
        return out

    if not isinstance(raw, dict):
        out = {
            "ok": False,
            "reason": "Unexpected response format from get_es_trip_det.",
            "data": None,
        }
    else:
        out = {
            "ok": bool(raw.get("ok", False)),
            "reason": (raw.get("reason") if raw.get("reason") else None),
            # pass through cleaned ES_TRIP_DET payload from the underlying function
            "data": raw.get("data") if raw.get("ok") else None,
        }

    tool_context.state["temp:es_trip_det"] = out
    return out



# -------------------------
# reimbursement_submit_tool
# -------------------------
async def reimbursement_submit_tool(
    pernr: str,
    reinr: str,
    claimda: str,
    tool_context: ToolContext,
) -> Dict[str, Any]:
    """
    Submit reimbursement payload to SAP (ES_CREATE_EXP) and return status only.

    One-liner:
        Calls reimbursement_submit(...), which posts to SAP, stores the SAP response
        in Redis, and detects business errors; this wrapper normalizes the result.

    Inputs:
        pernr (str): Employee personnel number.
        reinr (str): Trip number.
        claimda (str): DA amount to claim.
        tool_context (ToolContext): Provides session_id and a place to stash temp state.

    Output (normalized; no payload):
        {
          "ok": bool,                  # True if HTTP 200/201 AND no SAP business error
          "reason": str | None,        # Error text when ok=False; else None
          "status_code": int | None    # HTTP code if available (200/201 on success)
        }
    """
    # Resolve ids from ToolContext (needed by reimbursement_submit to scope Redis writes)
    try:
        _user_id, session_id = _get_ids_from_tool_context(tool_context)
    except Exception as e:
        logger.exception("ToolContext id resolution failed in reimbursement_submit_tool")
        out = {"ok": False, "reason": f"ToolContext id resolution failed: {e}", "status_code": None}
        tool_context.state["temp:reimbursement_submit"] = out
        return out

    # Call the core submitter (returns None on success; dict with error on failure)
    try:
        raw = await _to_async(reimbursement_submit, pernr, reinr, session_id, claimda)
        logger.info("reimbursement_submit returned: %s", raw)
    except Exception as e:
        logger.exception("reimbursement_submit raised an exception")
        out = {"ok": False, "reason": f"reimbursement_submit error: {e}", "status_code": None}
        tool_context.state["temp:reimbursement_submit"] = out
        return out

    # Normalize result:
    # - None  => full success (HTTP 200/201 and no business errors)
    # - dict  => failure; expect {"status_code": int, "error": str}
    if raw is None:
        out = {"ok": True, "reason": None, "status_code": 200}
    elif isinstance(raw, dict):
        error_text = raw.get("error")
        status_code = raw.get("status_code")
        # If function returned a dict without "error", treat conservatively as failure with generic reason
        out = {
            "ok": False if error_text else False,
            "reason": str(error_text) if error_text else "Unknown error during reimbursement submit.",
            "status_code": status_code if isinstance(status_code, int) else None,
        }
    else:
        # Unexpected type; fail safe
        out = {"ok": False, "reason": "Unexpected response from reimbursement_submit.", "status_code": None}

    # Stash minimal status for downstream steps (payload already saved to Redis by core fn)
    tool_context.state["temp:reimbursement_submit"] = out
    return out


# -------------
# Expose tools
# -------------

TRIP_FUNCTION_TOOLS = [
    FunctionTool(check_trip_validity_tool),
    FunctionTool(post_es_get_tool),
    FunctionTool(post_es_final_tool),
    FunctionTool(cancel_trip_tool),
    FunctionTool(post_es_final_flight_tool),
    PreloadMemoryTool()
]


REIMBURSEMENT_FUNCTION_TOOLS = [
    FunctionTool(analyze_reimbursement_documents_tool),
    FunctionTool(get_es_trip_det_tool),       
    FunctionTool(reimbursement_submit_tool),
]


