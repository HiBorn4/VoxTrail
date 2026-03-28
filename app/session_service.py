# travel_assist_agentic_bot/services/session_service.py
"""
Session service utilities for Google ADK, using a DB-backed SessionService
and Event-based state updates (state_delta).

Requires:
    pip install "google-adk[database]"

References:
- Sessions & State docs
- Event injection via actions.state_delta
- DatabaseSessionService (SQLite) patterns
"""

from __future__ import annotations
from typing import Any, Dict, Optional
import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from google.adk.sessions import DatabaseSessionService, Session
from google.adk.events import Event, EventActions
import uuid

# def generate_session_id() -> str:
#     """Generate a unique session ID"""
#     return str(uuid.uuid4())
log = logging.getLogger("travel_portal")

# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_session_service(db_url: str = "sqlite:///./agent_sessions.db") -> DatabaseSessionService:
    """
    Create a DatabaseSessionService instance (SQLite by default).
    Externalize db_url via env if needed.
    """
    return DatabaseSessionService(db_url=db_url)

# ---------------------------------------------------------------------------
# Session helpers (READ / CREATE)
# ---------------------------------------------------------------------------

# def create_session(emp_id: str, session_id: Optional[str] = None) -> Dict[str, Any]:
#     """
#     Create new session with voice support
#     """
#     if not session_id:
#         session_id = generate_session_id()
    
#     session = {
#         "session_id": session_id,
#         "emp_id": emp_id,
#         "created_at": datetime.now().isoformat(),
#         "updated_at": datetime.now().isoformat(),
#         "metadata": {
#             "voice_enabled": False,  # NEW: Track voice state
#             "voice_started_at": None,  # NEW: Voice session start
#             "voice_ended_at": None,  # NEW: Voice session end
#         },
#         "conversation_history": [],
#         # ... rest of your existing session fields
#     }
    
#     return session

async def ensure_session(
    session_service: DatabaseSessionService,
    *,
    app_name: str,
    user_id: str,
    session_id: Optional[str] = None,
    initial_state: Optional[Dict[str, Any]] = None,
) -> Session:
    """
    Create or fetch a session using the canonical ADK signature:
      get_session(app_name=..., user_id=..., session_id=...)

    If session_id is missing or session doesn't exist, a new one is created with optional initial_state.
    """
    # Try to get existing session if session_id provided
    if session_id:
        try:
            session = await session_service.get_session(
                app_name=app_name, user_id=user_id, session_id=session_id
            )
            if session:
                return session
        except Exception as e:
            log.debug(f"Session {session_id} not found, creating new one: {e}")
    
    # Create new session if not found or no session_id provided
    session = await session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        state=initial_state or {},
    )
    log.info(f"Created new session: {session.id} for user: {user_id}")
    return session

async def get_session_state(
    session_service: DatabaseSessionService,
    *,
    app_name: str,
    user_id: str,
    session_id: str,
) -> Dict[str, Any]:
    """
    Read session.state as a dict (never None). Uses keyworded signature expected by ADK.
    """
    sess = await session_service.get_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )
    return dict(getattr(sess, "state", {}) or {})

# ---------------------------------------------------------------------------
# Session helpers (WRITE via Event.state_delta)
# ---------------------------------------------------------------------------

async def apply_state_delta(
    session_service: DatabaseSessionService,
    session: Session,
    state_delta: Dict[str, Any],
    *,
    author: str = "system",
    invocation_id: Optional[str] = None,
) -> None:
    """
    Persist partial state changes by appending an Event with actions.state_delta.
    This is the ADK-recommended write path (there is no update_session).
    """
    if not state_delta:
        return

    evt = Event(
        invocation_id=invocation_id or f"state_update_{int(time.time())}",
        author=author,
        actions=EventActions(state_delta=state_delta),
        timestamp=time.time(),
    )
    await session_service.append_event(session, evt)

async def replace_full_state(
    session_service: DatabaseSessionService,
    session: Session,
    new_state: Dict[str, Any],
    *,
    author: str = "system",
) -> None:
    """
    Replace the entire state by emitting a state_delta that overwrites keys.
    Prefer apply_state_delta() where possible; full replacement is rarely needed.
    """
    await apply_state_delta(session_service, session, state_delta=new_state, author=author)


async def update_session_metadata(
    session_service: DatabaseSessionService,
    *,
    app_name: str,
    user_id: str,
    session_id: str,
    metadata: Dict[str, Any],
) -> Session:
    """
    Update session metadata with voice-specific fields using ADK's state_delta pattern.
    
    Args:
        session_service: DatabaseSessionService instance
        app_name: Application name
        user_id: User/employee ID
        session_id: Session identifier
        metadata: Dictionary of metadata to update
            - voice_enabled: bool
            - voice_started_at: timestamp
            - voice_ended_at: timestamp
    
    Returns:
        Updated Session object
    """
    try:
        # Get existing session using ADK signature
        session = await session_service.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id
        )
        
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        # Get current state
        current_state = dict(getattr(session, "state", {}) or {})
        
        # Merge metadata into state
        current_metadata = current_state.get("metadata", {})
        current_metadata.update(metadata)
        current_metadata["updated_at"] = datetime.now().isoformat()
        
        # Create state delta
        state_delta = {"metadata": current_metadata}
        
        # Apply state delta using ADK's event-based update
        await apply_state_delta(
            session_service,
            session,
            state_delta=state_delta,
            author="voice_system",
            invocation_id=f"voice_metadata_{int(time.time())}"
        )
        
        return session
        
    except Exception as e:
        log.error(f"Error updating session metadata: {e}")
        raise
# ---------------------------------------------------------------------------
# Business utility: merge nested travel state (idempotent)
# ---------------------------------------------------------------------------

def merge_nested_travel_state(
    existing_state: Dict[str, Any],
    parsed_agent_json: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Merge model output into session state with simple rules:

      Expected agent JSON keys:
        - "intent": "message" | "flight" | "reimbursement"
        - "travel_details": { ... }  -> merged into state["travel_details"]
        - "flight_stage": "flight_selection" | "flight_booking"
        - "reimbursement_stage": "request_upload" | "review" | "submitted" | "reimbursement_submitted"
        - "trip_id": str

      Rules:
        - Only non-empty values overwrite.
        - travel_details merges shallowly.
        - When intent == "flight": set/keep flight_stage (omit when unknown).
        - When intent == "reimbursement": set/keep reimbursement_stage (omit when unknown).
        - When intent == "message": clear both stages (omit keys entirely).
        - NEVER store "" for stage fields (omit unknowns).
    """
    state = dict(existing_state or {})
    td = dict(state.get("travel_details") or {})

    # intent
    intent = (parsed_agent_json.get("intent") or "").strip()
    if intent:
        state["intent"] = intent

    # travel_details
    updates = parsed_agent_json.get("travel_details") or {}
    if isinstance(updates, dict) and updates:
        for k, v in updates.items():
            if v is None:
                continue
            if isinstance(v, str) and not v.strip():
                continue
            td[k] = v
        state["travel_details"] = td

    # stages (omit empty values)
    current_intent = state.get("intent", "")
    if current_intent == "flight":
        new_stage = (parsed_agent_json.get("flight_stage") or "").strip()
        if new_stage:
            state["flight_stage"] = new_stage
        else:
            state.pop("flight_stage", None)
        # don’t touch reimbursement_stage
    elif current_intent == "reimbursement":
        new_stage = (
            parsed_agent_json.get("reimbursement_stage")
            or parsed_agent_json.get("stage")
            or ""
        ).strip()
        if new_stage:
            state["reimbursement_stage"] = new_stage
        else:
            state.pop("reimbursement_stage", None)
        # don’t touch flight_stage
    else:
        # message / unknown
        state.pop("flight_stage", None)
        state.pop("reimbursement_stage", None)

    # trip_id
    trip_id = (parsed_agent_json.get("trip_id") or "").strip()
    if trip_id:
        state["trip_id"] = trip_id

    return state

# ---------------------------------------------------------------------------
# Convenience: compute a minimal delta (so we only write what's changed)
# ---------------------------------------------------------------------------

def diff_state(prev: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a shallow diff: keys whose values differ or are newly added.
    Deletes are not handled here (keep state additive).
    """
    delta: Dict[str, Any] = {}
    for k, v in new.items():
        if prev.get(k) != v:
            delta[k] = v
    return delta
