# ── Standard Library ──────────────────────────────────────────────────────────
import os
os.environ["OTEL_SDK_DISABLED"] = "true"
import asyncio
import base64
import copy
import hashlib
import json
import logging
import time
import traceback
import urllib.parse
import uuid
import msal
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File, Form, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from travel_assist_agentic_bot.voice_websocket_handler import handle_voice_websocket
from fastapi.responses import JSONResponse, StreamingResponse
from sse_starlette.sse import EventSourceResponse
from pathlib import Path
from typing import Any, Dict, List
from copy import deepcopy
from fastapi import WebSocket
# ── Third-Party ───────────────────────────────────────────────────────────────
import jwt
from dotenv import load_dotenv
from fastapi import Response
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from jwt import ExpiredSignatureError, DecodeError, InvalidTokenError, exceptions as jwt_exceptions
from pydantic import ValidationError
from requests import request
from starlette.concurrency import run_in_threadpool
from starlette.status import HTTP_400_BAD_REQUEST
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from base64 import b64decode
from Crypto.Cipher import AES

# ── Local / Application Modules ──────────────────────────────────────────────
from login_bootstap.get_emp_trips_list import get_emp_trips_list
from login_bootstap.get_emp_trip_expenses_list import get_emp_trip_expenses_list
from login_bootstap.get_es_header_api import get_es_header
from login_bootstap.get_es_mode_elig_or_not import check_mode_eligibility
from travel_assist_agentic_bot.voice_websocket_handler import handle_voice_websocket
import jwt

from google.genai import types
from travel_assist_agentic_bot.runtime import get_runner
from travel_assist_agentic_bot.services.session_service import (
    apply_state_delta,
    diff_state,
    ensure_session,
    get_session_service,
    get_session_state,
    merge_nested_travel_state,
)
from travel_assist_agentic_bot.config2 import APP_NAME, DEFAULT_TRAVEL_STATE
from travel_assist_agentic_bot.schemas import (
    ChatEnvelope,
    FlightDetails,
    GetReimbursement,
    Message,
    UploadAck,
)

from travel_assist_agentic_bot.services.redis_manager import RedisJSONManager
from travel_assist_agentic_bot.services.session_cleanup import (
    clear_user_session_in_redis,
    clear_user_response_jsons,
)

from travel_assist_agentic_bot.services.permanent_store import save_trip_chat, fetch_trip_chat
from travel_assist_agentic_bot.services.chat_extract import extract_pairs_from_events
from utils import decode_jwt, extract_user_id, create_refresh_token, fetch_recent_history, categorize_trips

from sqlalchemy import create_engine, text as sq_text

from fastapi import WebSocketDisconnect, Request, Body
from sse_starlette.sse import EventSourceResponse
# from travel_assist_agentic_bot.streaming import (
#     start_live_session, sse_event_stream, get_live_queue_if_connected,
#     close_live_session, is_live_connected
# )
from google.genai import types as genai_types
import base64, json

runner = get_runner()
session_service = get_session_service()
load_dotenv()

# ──────────────────────────────────────────────────────────────────────────────
# App & Config
# ──────────────────────────────────────────────────────────────────────────────
app = FastAPI(title="Travel Portal Backend", version="1.0.0")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
)
# Silence noisy libraries
logging.getLogger("google.adk").setLevel(logging.ERROR)
logging.getLogger("google.adk.flows").setLevel(logging.ERROR)
logging.getLogger("google.adk.models").setLevel(logging.ERROR)
logging.getLogger("google.adk.runners").setLevel(logging.ERROR)
logging.getLogger("google.genai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

# Keep your app logs visible
logging.getLogger("travel_portal").setLevel(logging.INFO)
logging.getLogger("travel_assist_agentic_bot").setLevel(logging.INFO)
logger = logging.getLogger("travel_portal")
logger.info("FastAPI app initialized")

# Add after app = FastAPI(...)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://mgcdvulnabotravelclrun01-167627519943.asia-south1.run.app",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],  # frontend URL
    allow_credentials=True,
    allow_methods=["*"],   # or restrict: ["GET", "POST"]
    allow_headers=["*"],   # or restrict as needed
)
logger.info("CORS middleware configured for frontend origin")

# Outbound (minted) JWT settings
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120
logger.debug(f"JWT settings -> ALG: {ALGORITHM}, EXP_MIN: {ACCESS_TOKEN_EXPIRE_MINUTES}")

# Inbound decrypt (exact Java pipeline key)
# AES_SECRET_KEY = b"MySecretKey12345"  # 16-byte AES-128 key
AES_SECRET_KEY = os.getenv("AES_SECRET_KEY", "").encode()
logger.debug(f"AES secret key length: {len(AES_SECRET_KEY)}")

# Date window for previous trips/expenses (default: last 365 days)
DEFAULT_DAYS_LOOKBACK = 365
logger.debug(f"DEFAULT_DAYS_LOOKBACK set to {DEFAULT_DAYS_LOOKBACK}")

# Simple in-memory token store (stub)
_TOKENS: Dict[str, Dict[str, Any]] = {}
logger.debug("Initialized in-memory token store _TOKENS")

redis_mgr = RedisJSONManager()

# ─────────────────────────────
# Azure AD / MSAL config
# ─────────────────────────────
AZURE_AD_CLIENT_ID = os.getenv("AZURE_AD_CLIENT_ID")        # your app's clientId
AZURE_AD_CLIENT_SECRET = os.getenv("AZURE_AD_CLIENT_SECRET")# your app's clientSecret
AZURE_AD_TENANT_ID = os.getenv("AZURE_AD_TENANT_ID")        # e.g. 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'

flight_timeout = int(os.getenv("FLIGHT_DATA_TIMEOUT_SECONDS", "15"))
flight_poll_interval = float(os.getenv("FLIGHT_DATA_POLL_INTERVAL", "1.0"))


# This MUST match exactly what you configured in Azure AD
# REDIRECT_URI = "https://mgcdvulnabotravelclrun01-167627519943.asia-south1.run.app/login"
REDIRECT_URI = "http://localhost:8000/login"

AUTHORITY = f"https://login.microsoftonline.com/{AZURE_AD_TENANT_ID}"

# Adjust scopes as per your scenario (Microsoft Graph / custom API / etc.)
SCOPES = ['offline_access', 'profile', 'openid']

def _is_valid_trip_id(s: str) -> bool:
    return isinstance(s, str) and s.isdigit() and len(s) == 10 and s != "0000000000"


def find_non_serializable(obj, path="root"):
    """Recursively find non-JSON-serializable objects"""
    if isinstance(obj, dict):
        for key, value in obj.items():
            find_non_serializable(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            find_non_serializable(item, f"{path}[{i}]")
    elif isinstance(obj, type):
        logger.error(f"❌ Found type object at {path}: {obj}")
        raise TypeError(f"Type object found at {path}: {obj}")
    elif not isinstance(obj, (str, int, float, bool, type(None))):
        try:
            json.dumps(obj)
        except TypeError as e:
            logger.error(f"❌ Non-serializable object at {path}: {type(obj)} - {e}")
            raise
        
def create_access_token(data: dict):
    """Create a non-expiring backend token (HS256)."""
    logger.info("Creating access token (no expiry)")
    start_ts = time.perf_counter()

    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    iat = int(now.timestamp())
    to_encode.update({"iat": iat})  # no 'exp' added

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    logger.info(f"Access token created for sub={data.get('sub')}, iat={iat}, exp=None")
    logger.debug("create_access_token duration: %.3f ms", (time.perf_counter() - start_ts) * 1000)

    return encoded_jwt, iat, None



def add_usertoken(user_id: str, token: str, iat: int, exp: int):
    logger.info(f"Storing token in _TOKENS for user_id={user_id}")
    _TOKENS[user_id] = {"token": token, "iat": iat, "exp": exp}
    logger.debug(f"_TOKENS[{user_id}] now present with exp={exp}")


def _date_ymd(dt: datetime) -> str:
    s = dt.strftime("%Y%m%d")
    logger.debug(f"_date_ymd({dt.isoformat()}) -> {s}")
    return s


# ──────────────────────────────────────────────────────────────────────────────
# Decrypt helper (exactly mirroring your Java / jwt_test.py pipeline)
# base64url decode -> base64 decode -> AES-ECB decrypt -> PKCS7 unpad -> URL decode
# ──────────────────────────────────────────────────────────────────────────────
def _pkcs7_unpad(b: bytes) -> bytes:
    logger.debug(f"Entered _pkcs7_unpad with length={len(b)}")
    pad = b[-1]
    if pad < 1 or pad > 16 or any(x != pad for x in b[-pad:]):
        logger.error("Invalid PKCS7 padding detected")
        raise ValueError("Invalid PKCS7 padding")
    unpadded = b[:-pad]
    logger.debug(f"_pkcs7_unpad reduced length from {len(b)} to {len(unpadded)}")
    return unpadded


def decrypt_token(jwt_token_blob: str) -> str:
    logger.info("Starting decrypt_token pipeline")
    start_ts = time.perf_counter()
    # 1) Base64 URL decode outer layer
    decoded_bytes = base64.urlsafe_b64decode(jwt_token_blob + "===")
    logger.debug(f"After urlsafe_b64decode: {len(decoded_bytes)} bytes")

    # 2) bytes -> string (this should be base64 ciphertext)
    encrypted_b64_str = decoded_bytes.decode("utf-8")
    logger.debug("Converted decoded bytes to UTF-8 string (base64 ciphertext)")

    # 3) base64 decode again => ciphertext bytes
    encrypted_bytes = base64.b64decode(encrypted_b64_str)
    logger.debug(f"After base64.b64decode: {len(encrypted_bytes)} bytes")

    # 4) AES decrypt (ECB mode)
    cipher = Cipher(algorithms.AES(AES_SECRET_KEY), modes.ECB(), backend=default_backend())
    decryptor = cipher.decryptor()
    decrypted_bytes = decryptor.update(encrypted_bytes) + decryptor.finalize()
    logger.debug(f"AES-ECB decrypted to {len(decrypted_bytes)} bytes")

    # 5) PKCS7 unpad
    decrypted_bytes = _pkcs7_unpad(decrypted_bytes)

    # 6) URL decode -> final JWT string
    original_jwt = urllib.parse.unquote(decrypted_bytes.decode("utf-8"))
    logger.info("decrypt_token pipeline complete")
    logger.debug("decrypt_token duration: %.3f ms", (time.perf_counter() - start_ts) * 1000)
    return original_jwt



# def decrypt_token(jwt_token_blob: str) -> str:
#     SECRET_KEY = "MySecretKey12345"  # 16 chars for AES-128
#     IV = b"YOUR_16_BYTE_IV"          # Must match Java's IV
    
#     # Fix Base64 padding
#     padding_needed = len(jwt_token_blob) % 4
#     if padding_needed:
#         jwt_token_blob += "=" * (4 - padding_needed)
    
#     encrypted_bytes = b64decode(jwt_token_blob)
#     cipher = AES.new(SECRET_KEY.encode('utf-8'), AES.MODE_CBC, IV)
#     decrypted_bytes = cipher.decrypt(encrypted_bytes)
    
#     pad_len = decrypted_bytes[-1]
#     return decrypted_bytes[:-pad_len].decode('utf-8')


def _decode_payload_no_verify(jwt_token: str) -> dict:
    """Decode JWT payload WITHOUT verifying signature (to match previous behavior)."""
    logger.warning("Decoding JWT without signature verification (legacy behavior)")
    payload = jwt.decode(jwt_token, "", options={"verify_signature": False})
    logger.debug(f"Decoded payload (no verify): keys={list(payload.keys())}")
    return payload



def _fetch_flight_lists_from_cache(
    pernr: str,
    session_id: str,
    journey_type: str | None = None,
) -> Dict[str, Any]:
    """
    Load NAV_PREFERRED_FLIGHT and NAV_GETSEARCH arrays for either one-way or
    round-trip from Redis.
    """
    # 1. Entry Log: helpful to trace flow start
    logger.debug(
        "Attempting to fetch flight lists from cache",
        extra={
            "pernr": pernr,
            "session_id": session_id,
            "journey_type": journey_type,
        },
    )

    def _load_d(key: str) -> Any:
        try:
            return redis_mgr.get_json(pernr, session_id, key)
        except AttributeError:
            return redis_mgr.load_json(pernr, session_id, key)

    def _extract_list(node: Any) -> Any:
        """Returns split structure [[outgoing], [return]] or flat list as-is."""
        if isinstance(node, dict):
            results = node.get("results")
            if isinstance(results, list):
                # Check for split structure (List of Lists)
                if (len(results) == 2 and 
                    isinstance(results[0], list) and 
                    isinstance(results[1], list)):
                    return results  # [[...], [...]]
                else:
                    return results  # Legacy flat [...]
            return []
        return node if isinstance(node, list) else []

    # --- Decide primary / fallback keys based on journey_type -----------------
    norm_jt = (journey_type or "").strip().lower()
    
    if norm_jt in {"one way", "one-way", "oneway"}:
        primary_key = "es_get_flight_oneway"
        fallback_key = "es_get_flight_roundtrip"
    elif norm_jt in {"round trip", "round-trip", "roundtrip", "return"}:
        primary_key = "es_get_flight_roundtrip"
        fallback_key = "es_get_flight_oneway"
    else:
        primary_key = "es_get_flight_oneway"
        fallback_key = "es_get_flight_roundtrip"

    used_key = primary_key
    
    try:
        # 2. Fetch Logic
        d = _load_d(primary_key)
        
        if d is None:
            logger.warning(
                "Primary flight cache key miss. Attempting fallback.",
                extra={
                    "session_id": session_id,
                    "pernr": pernr,
                    "primary_key": primary_key,
                    "fallback_key": fallback_key,
                    "journey_type": journey_type,
                },
            )
            d = _load_d(fallback_key)
            used_key = fallback_key

        if d is None:
            logger.warning(
                "Flight cache miss: No data found for primary or fallback keys.",
                extra={
                    "session_id": session_id,
                    "pernr": pernr,
                    "keys_checked": [primary_key, fallback_key],
                },
            )
            return {"nav_preffered": [], "nav_getsearch": []}

        # 3. Extraction
        pref_list = _extract_list(d.get("NAV_PREFERRED_FLIGHT"))
        gs_list = _extract_list(d.get("NAV_GETSEARCH"))

        # 4. Normalization & Stats Calculation
        # Normalize Pref List
        if not isinstance(pref_list, list):
            pref_list = []
        
        # Analyze GetSearch Structure for Logging
        gs_metadata = {"type": "empty", "counts": "0"}
        
        if isinstance(gs_list, list):
            # Check if it is the Split Structure [[out], [ret]]
            if len(gs_list) == 2 and isinstance(gs_list[0], list) and isinstance(gs_list[1], list):
                gs_metadata = {
                    "type": "split_structure",
                    "counts": f"out={len(gs_list[0])}, ret={len(gs_list[1])}"
                }
            else:
                gs_metadata = {
                    "type": "flat_list",
                    "counts": f"total={len(gs_list)}"
                }
        else:
            logger.warning(
                "Invalid NAV_GETSEARCH type detected. Normalizing to empty list.",
                extra={"session_id": session_id, "actual_type": type(gs_list).__name__}
            )
            gs_list = []

        # 5. Final Success Log
        logger.info(
            "Flight lists fetched successfully.",
            extra={
                "session_id": session_id,
                "pernr": pernr,
                "journey_type": journey_type,
                "source_redis_key": used_key,
                "preferred_count": len(pref_list),
                "getsearch_structure": gs_metadata["type"],
                "getsearch_counts": gs_metadata["counts"],
            },
        )
        
        return {"nav_preffered": pref_list, "nav_getsearch": gs_list}

    except Exception as e:
        logger.exception(
            "Critical error fetching flight lists from cache.",
            extra={
                "session_id": session_id,
                "pernr": pernr,
                "journey_type": journey_type,
                "attempted_key": used_key,
            },
        )
        return {"nav_preffered": [], "nav_getsearch": []}


def _attach_prefetched_flights_to_envelope(
    agent_env: ChatEnvelope,
    user_id: str,
    session_id: str,
    existing_state: Dict[str, Any],
    max_wait_seconds: int = 30,  # Increased from 15
    poll_interval: float = 1.0,
) -> ChatEnvelope:
    """
    Backend waits silently until flight data is available.
    Agent sends response ONLY when data is ready.
    """
    
    # 1. Validation & Early Exits
    if agent_env.intent != "flight":
        # Usually too verbose for info, debug is fine
        logger.debug("Skipping flight attachment: Intent is not 'flight'", extra={"intent": agent_env.intent})
        return agent_env

    stage = (agent_env.flight_details.stage or "").strip()
    if stage != "flight_selection":
        logger.debug("Skipping flight attachment: Stage is not 'flight_selection'", extra={"stage": stage})
        return agent_env

    # Check if data already attached
    fd_wire = agent_env.flight_details.model_dump(by_alias=True) or {}
    current_pref = fd_wire.get("nav_preffered") or []
    current_gs = fd_wire.get("nav_getsearch") or []
    
    if current_pref or current_gs:
        logger.info(
            "Skipping flight attachment: Flight data already present in envelope",
            extra={
                "user_id": user_id, 
                "session_id": session_id,
                "pref_count": len(current_pref),
                "gs_count": len(current_gs)
            }
        )
        return agent_env

    # 2. Context Extraction
    journey_type = None
    try:
        td = getattr(agent_env, "travel_details", None)
        if td is not None:
            journey_type = getattr(td, "journey_type", None)
    except Exception:
        pass
    
    if not journey_type:
        journey_type = (
            (existing_state or {}).get("travel_details", {}) or {}
        ).get("journey_type")

    # ========================================================================
    # SILENT POLLING - Only respond when data is ready
    # ========================================================================
    start_time = time.time()
    poll_count = 0
    
    logger.info(
        "🔍 Starting silent flight data polling (User wait invisible)",
        extra={
            "user_id": user_id,
            "session_id": session_id,
            "journey_type": journey_type,
            "max_wait_seconds": max_wait_seconds,
            "poll_interval": poll_interval,
        }
    )
    
    while (time.time() - start_time) < max_wait_seconds:
        poll_count += 1
        
        # Fetch from Redis
        cached = _fetch_flight_lists_from_cache(
            pernr=user_id,
            session_id=session_id,
            journey_type=journey_type,
        )
        pref = cached.get("nav_preffered") or []
        gs = cached.get("nav_getsearch") or []
        
        if pref or gs:
            # --- Analyze Structure for Logging ---
            gs_desc = f"flat_list(len={len(gs)})"
            if len(gs) == 2 and isinstance(gs[0], list) and isinstance(gs[1], list):
                 gs_desc = f"split_structure(out={len(gs[0])}, ret={len(gs[1])})"

            # --- SUCCESS: Data ready, attach and return ---
            agent_env.flight_details.nav_preferred = pref
            agent_env.flight_details.nav_getsearch = gs
            
            elapsed = time.time() - start_time
            logger.info(
                "✅ Flight data successfully attached after silent wait",
                extra={
                    "user_id": user_id,
                    "session_id": session_id,
                    "wait_time_seconds": round(elapsed, 2),
                    "poll_count": poll_count,
                    "nav_preferred_count": len(pref),
                    "nav_getsearch_structure": gs_desc,
                },
            )
            
            # Agent sends success message
            msg = agent_env.message or Message()
            if not msg.bot_response:
                # Dynamic response based on results
                count_desc = str(len(pref)) if pref else "several"
                msg.bot_response = (
                    f"Great! I've found {count_desc} flight options for you. "
                    f"Please review and select your preferred flights."
                )
            agent_env.message = msg
            
            return agent_env
        
        # Wait before next poll
        if (time.time() - start_time) < max_wait_seconds:
            time.sleep(poll_interval)
            
            # Log periodic heartbeat (every 5 polls) to track long waits
            if poll_count % 5 == 0:
                logger.info(
                    f"⏳ Still polling for flight data... (elapsed: {time.time() - start_time:.1f}s)",
                    extra={
                        "user_id": user_id,
                        "session_id": session_id,
                        "poll_count": poll_count
                    }
                )
    
    # ========================================================================
    # TIMEOUT: Give up after max_wait_seconds
    # ========================================================================
    elapsed = time.time() - start_time
    logger.error(
        "❌ Flight data timeout: API failed to populate Redis within limit",
        extra={
            "user_id": user_id,
            "session_id": session_id,
            "timeout_threshold": max_wait_seconds,
            "actual_elapsed": round(elapsed, 2),
            "total_polls": poll_count,
        },
    )
    
    # This is a real error - flight API failed or is extremely slow
    msg = agent_env.message or Message()
    if not msg.bot_response:
        msg.bot_response = (
            "I apologize, but the flight booking system is currently experiencing delays. "
            "This could take a few more minutes.\n\n"
            "Would you like to:\n"
            "1. Choose a different travel mode (Train, Bus, Car)\n"
            "2. Wait and I'll check again (you can ask 'show flights' in a moment)\n"
            "3. Book this trip later when the system is faster"
        )
    agent_env.message = msg
    
    # Keep stage as flight_selection for potential retry
    return agent_env



async def _fetch_user_data(pernr: str, session_id) -> Dict[str, Any]:
    """Run SAP calls (header, trips, expenses, mode eligibility) in parallel and return results."""
    logger.info(f"Fetching user data for pernr={pernr}")
    wall_start = time.perf_counter()
    today = datetime.now()
    start = today - timedelta(days=DEFAULT_DAYS_LOOKBACK)
    end = today + timedelta(days=30)
    startdate, enddate = _date_ymd(start), _date_ymd(end)
    logger.debug(f"Computed data window startdate={startdate}, enddate={enddate}")

    async def call_es_header(session_id):
        logger.debug("call_es_header invoked")
        if get_es_header:
            try:
                t0 = time.perf_counter()
                res = await run_in_threadpool(get_es_header, pernr)
                
                # Json store
                
                # Save the es_header_min
                success = redis_mgr.save_json(
                    data=res,
                    user_id=pernr,
                    session_id=session_id,
                    data_type="header"
                )
                

                logger.info(f"✅ Saved header and header_min for user {pernr} to Redis")
                logger.info("ES_HEADER call succeeded")
                logger.debug("ES_HEADER duration: %.3f ms", (time.perf_counter() - t0) * 1000)
                return res
            except Exception as e:
                logging.warning(f"ES_HEADER failed: {e}")
                logger.exception("ES_HEADER exception details")
        else:
            logger.warning("get_es_header is None; skipping ES header call")
        return None

    async def call_trips():
        logger.debug("call_trips invoked")
        try:
            t0 = time.perf_counter()
            res = await run_in_threadpool(
                get_emp_trips_list,
                emp_id=pernr,
                startdate=startdate,
                enddate=enddate,
                user_id=pernr,
                filter_status="",
                trip_number="",
            )
            
            # Trip list 
            
            success = redis_mgr.save_json(
                    data=res,
                    user_id=pernr,
                    session_id=session_id,
                    data_type="emp_trip_list"
                )
            
            
            logger.info("TRIPS list call succeeded")
            logger.debug("TRIPS list duration: %.3f ms", (time.perf_counter() - t0) * 1000)
            return res
        except Exception as e:
            logging.warning(f"TRIPS list failed: {e}")
            logger.exception("TRIPS list exception details")
            return {"params": {}, "count": 0, "trips": []}

    async def call_expenses():
        logger.debug("call_expenses invoked")
        try:
            t0 = time.perf_counter()
            res = await run_in_threadpool(
                get_emp_trip_expenses_list,
                emp_id=pernr,
                startdate=startdate,
                enddate=enddate,
                user_id=pernr,
                trip_number="",
            )
            
            success = redis_mgr.save_json(
                    data=res,
                    user_id=pernr,
                    session_id=session_id,
                    data_type="emp_trip_expenses_list"
                )
            
            logger.info("TRIP EXPENSES list call succeeded")
            logger.debug("TRIP EXPENSES duration: %.3f ms", (time.perf_counter() - t0) * 1000)
            return res
        except Exception as e:
            logging.warning(f"TRIP EXPENSES list failed: {e}")
            logger.exception("TRIP EXPENSES list exception details")
            return {"params": {}, "count": 0, "expenses": []}

    async def call_mode_elig():
        logger.debug("call_mode_elig invoked")
        if check_mode_eligibility:
            try:
                t0 = time.perf_counter()
                res = await run_in_threadpool(check_mode_eligibility, pernr)
                logger.info("MODE ELIG call succeeded")
                logger.debug("MODE ELIG duration: %.3f ms", (time.perf_counter() - t0) * 1000)
                return res
            except Exception as e:
                logging.warning(f"MODE ELIG failed: {e}")
                logger.exception("MODE ELIG exception details")
        else:
            logger.warning("check_mode_eligibility is None; skipping mode eligibility call")
        return None

    es_header_task = asyncio.create_task(call_es_header(session_id))
    trips_task = asyncio.create_task(call_trips())
    expenses_task = asyncio.create_task(call_expenses())
    mode_elig_task = asyncio.create_task(call_mode_elig())
    logger.debug("All SAP tasks scheduled; awaiting gather()")

    es_header_res, trips_res, expenses_res, mode_elig_res = await asyncio.gather(
        es_header_task, trips_task, expenses_task, mode_elig_task
    )
    logger.info("All SAP calls completed")
    logger.debug(
        "Result sizes -> header:%s, trips_count:%s, expenses_count:%s, mode_elig:%s",
        "present" if es_header_res is not None else "None",
        (trips_res or {}).get("count") if isinstance(trips_res, dict) else "N/A",
        (expenses_res or {}).get("count") if isinstance(expenses_res, dict) else "N/A",
        "present" if mode_elig_res is not None else "None",
    )

    logger.debug("Also printed es_header_res to stdout per original code")

    # os.makedirs("responses", exist_ok=True)
    logger.debug("Ensured 'responses' directory exists")

    try:
        # Define the responses directory using os.path
        responses_dir = os.path.join("travel_assist_agentic_bot", "responses")
        
        # Header file creation removed as requested
        
        # Write trips file
        trips_file = os.path.join(responses_dir, f"{pernr}_trips.json")
        with open(trips_file, "w", encoding="utf-8") as f:
            json.dump(trips_res, f, ensure_ascii=False, indent=2)
        logger.debug(f"Wrote {trips_file}")

        # Write expenses file
        expenses_file = os.path.join(responses_dir, f"{pernr}_expenses.json")
        with open(expenses_file, "w", encoding="utf-8") as f:
            json.dump(expenses_res, f, ensure_ascii=False, indent=2)
        logger.debug(f"Wrote {expenses_file}")

        # Write mode eligible file
        mode_eligible_file = os.path.join(responses_dir, f"{pernr}_modeEligible.json")
        with open(mode_eligible_file, "w", encoding="utf-8") as f:
            json.dump(mode_elig_res, f, ensure_ascii=False, indent=2)
        logger.debug(f"Wrote {mode_eligible_file}")
        
    except Exception as e:
        logging.error(f"Failed to write response JSONs: {e}")
        logger.exception("Error while writing response JSON files")

    logger.debug("Assembling final SAP response dict for pernr=%s", pernr)

    # Categorize trips based on approval and expense status
    categorized_trips = {}
    try:
        trips_data = trips_res or {"params": {}, "count": 0, "trips": []}
        expenses_data = expenses_res or {"params": {}, "count": 0, "expenses": []}
        categorized_trips = categorize_trips(trips_data, expenses_data)
        logger.info(f"Successfully categorized trips for pernr={pernr}")
    except Exception as e:
        logger.exception(f"Failed to categorize trips for pernr={pernr}: {e}")
        # Initialize empty categories on error
        categorized_trips = {
            "Trip Pending Approval": [],
            "Trip Approved": [],
            "Trip Not Approved": [],
            "Expense Not Submitted": [],
            "Expense Saved (Draft)": [],
            "Expense Pending Approval": [],
            "Expense Approved": []
        }

    
    out = {
        "window": {"startdate": startdate, "enddate": enddate},
        "header": es_header_res,
        "trips": trips_res or {"params": {}, "count": 0, "trips": []},
        "expenses": expenses_res or {"params": {}, "count": 0, "expenses": []},
        "categorized_trips": categorized_trips,
        "modeEligible": mode_elig_res,
    }
    logger.info("User data fetch complete for pernr=%s in %.3f ms", pernr, (time.perf_counter() - wall_start) * 1000)
    return out

def _derive_pernr_from_token(user_token_id: str) -> str:
    """Try to get PERNR from JWT; fall back to user_id; else 'unknown'."""
    try:
        payload = jwt.decode(user_token_id, SECRET_KEY, algorithms=[ALGORITHM])
        pernr = str(payload.get("pernr") or payload.get("employee_id") or "").strip()
        if pernr:
            return pernr
        user_id = str(payload.get("sub") or payload.get("user") or payload.get("user_id") or "").strip()
        return user_id or "unknown"
    except Exception:
        return "unknown"

def _sha256_of_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()

# ──────────────────────────────────────────────────────────────────────────────
# 1) /login — decrypt → decode → mint token → REDIRECT with ?user={user_id_token}
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/sso")
async def sso_login():
    logger.info(
        f"Starting SSO login with "
        f"client_id={AZURE_AD_CLIENT_ID}, "
        f"authority={AUTHORITY}, "
        f"redirect_uri={REDIRECT_URI}"
    )

    if not AZURE_AD_CLIENT_ID or not AUTHORITY or not REDIRECT_URI:
        logger.error("Missing Azure AD configuration (client_id/authority/redirect_uri)")
        raise HTTPException(
            status_code=500,
            detail="Azure AD is not configured correctly on the backend.",
        )

    msal_app = msal.ConfidentialClientApplication(
        client_id=AZURE_AD_CLIENT_ID,
        authority=AUTHORITY,
        client_credential=AZURE_AD_CLIENT_SECRET,
    )

    state = str(uuid.uuid4())

    auth_url = msal_app.get_authorization_request_url(
        scopes=["User.Read"],
        redirect_uri=REDIRECT_URI,
        state=state,
        response_type="code",
        prompt="select_account",
    )

    logger.info(f"Azure AD auth URL = {auth_url}")

    return RedirectResponse(url=auth_url, status_code=302)


@app.get("/login")
async def login(jwt_token: str = Query(...)):
    logger.info("Received /login request")
    if not jwt_token:
        logger.warning("No JWT token provided in request")
        raise HTTPException(status_code=400, detail="Token not provided")

    try:
        logger.info("Entered /login JWT processing")

        # --- 1. Decrypt token ---
        try:
            logger.debug(f"Raw incoming jwt_token length: {len(jwt_token)}")
            jwt_token = decrypt_token(jwt_token)
            logger.info("Successfully decrypted incoming token.")
        except Exception as ex:
            logger.exception(f"Token decrypt failed: {ex}")
            raise HTTPException(status_code=400, detail="Malformed token provided")

        # --- 2. Validate JWT structure ---
        if jwt_token.count(".") != 2:
            logger.error("Malformed JWT token after decrypt")
            raise HTTPException(status_code=400, detail="Malformed token provided")

        # --- 3. Decode payload ---
        payload = _decode_payload_no_verify(jwt_token)
        logger.info(f"/login decoded payload: {payload}")

        # --- 4. Extract user id ---
        user_id = payload.get("user") or payload.get("sub") or payload.get("user_mail")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in token")

        # --- 5. Mint backend token ---
        new_token, iat, exp = create_access_token({"sub": str(user_id)})
        add_usertoken(str(user_id), new_token, iat, exp)
        logger.info(f"Minted new_token for user={user_id}: {new_token}")

        # --- 6. Prepare initial state with validation ---
        try:
            logger.debug("DEFAULT_TRAVEL_STATE type: %s", type(DEFAULT_TRAVEL_STATE))
            logger.debug("DEFAULT_TRAVEL_STATE keys: %s", list(DEFAULT_TRAVEL_STATE.keys()) if isinstance(DEFAULT_TRAVEL_STATE, dict) else "N/A")
            
            # Parse string to dict if needed
            if isinstance(DEFAULT_TRAVEL_STATE, str):
                logger.info("DEFAULT_TRAVEL_STATE is a string, parsing to JSON")
                try:
                    initial_state = json.loads(DEFAULT_TRAVEL_STATE)
                    logger.info("✅ Successfully parsed DEFAULT_TRAVEL_STATE to dict")
                except json.JSONDecodeError as json_err:
                    logger.error("❌ Failed to parse DEFAULT_TRAVEL_STATE JSON: %s", json_err)
                    logger.error("Problematic string (first 200 chars): %s", DEFAULT_TRAVEL_STATE[:200])
                    raise HTTPException(status_code=500, detail=f"Invalid state template JSON: {json_err}")
            else:
                logger.info("DEFAULT_TRAVEL_STATE is already a dict, creating deep copy")
                initial_state = copy.deepcopy(DEFAULT_TRAVEL_STATE)
                logger.debug("Deep copy created successfully")
            
            # Validate JSON serializability BEFORE passing to session service
            logger.debug("Validating initial_state is JSON serializable")
            try:
                find_non_serializable(initial_state)
                logger.info("✅ State structure validation passed")
            except TypeError as type_err:
                logger.error("❌ initial_state contains non-JSON-serializable data: %s", type_err)
                logger.error("Problematic state structure: %s", initial_state)
                raise HTTPException(
                    status_code=500, 
                    detail=f"State template contains non-serializable data: {type_err}"
                )
            
            # Final JSON serialization test
            logger.debug("Testing JSON serialization")
            try:
                json_test = json.dumps(initial_state)
                logger.info("✅ initial_state is JSON serializable (%d bytes)", len(json_test))
                logger.debug("State structure preview: %s", json.dumps(initial_state, indent=2)[:500])
            except (TypeError, ValueError) as json_err:
                logger.error("❌ JSON serialization failed: %s", json_err)
                raise HTTPException(
                    status_code=500,
                    detail=f"State is not JSON serializable: {json_err}"
                )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("❌ Unexpected error preparing initial state")
            raise HTTPException(status_code=500, detail=f"Failed to prepare session state: {str(e)}")

        # --- 7. Create ADK session ---
        try:
            logger.info("Calling session_service.create_session | app_name=%s user_id=%s", APP_NAME, user_id)
            
            session = await session_service.create_session(
                app_name=APP_NAME,
                user_id=str(user_id),
                state=initial_state,
            )
            
            session_id = getattr(session, "id", None) or (
                session.get("id") if isinstance(session, dict) else None
            )
            
            if session_id:
                logger.info(
                    "✅ ADK session created successfully | session_id=%s user_id=%s",
                    session_id,
                    user_id,
                )
            else:
                logger.error("❌ Session created but session_id is None | user_id=%s", user_id)
                raise HTTPException(status_code=500, detail="Session created but ID is missing")

            # Stamp identifiers (need session_id, so do it after creation)
            logger.debug("Applying state delta to stamp identifiers")
            await apply_state_delta(
                session_service,
                session,
                {
                    "app:user_id": str(user_id),
                    "app:session_id": str(session_id),
                    "app:app_name": APP_NAME,  # optional, handy in tools
                    # Ensure conversation scaffolding is present (idempotent if already there)
                    "intent": initial_state.get("intent", "message"),
                    "trip_id": initial_state.get("trip_id", "0000000000"),
                    "travel_details": initial_state.get("travel_details", {}),
                    "flight_details": initial_state.get("flight_details", {}),
                    "get_reimbursement": initial_state.get("get_reimbursement", {}),
                    "message": initial_state.get("message", {"user_query": "", "bot_response": ""}),
                },
                author="system",
            )
            logger.info("✅ State delta applied successfully")

        except HTTPException:
            raise
        except Exception as e:
            logger.exception("❌ Failed to create ADK session during /login | user_id=%s", user_id)
            logger.error("Exception type: %s | message: %s", type(e).__name__, str(e))
            raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")

        # --- 8. Redirect to your FE with tokens ---
        redirect_url = (
            "https://mgcdvulnabotravelclrun01-167627519943.asia-south1.run.app/login"
            f"?user={new_token}&session_id={session_id}"
        )
        logger.info(f"Redirecting user {user_id} to: {redirect_url}")
        return RedirectResponse(url=redirect_url)

    except jwt_exceptions.ExpiredSignatureError:
        logger.error("JWT token expired")
        raise HTTPException(status_code=401, detail="Token expired")
    except (jwt_exceptions.DecodeError, jwt_exceptions.InvalidTokenError) as jwt_err:
        logger.error("JWT validation error: %s", jwt_err)
        raise HTTPException(status_code=401, detail="Invalid token")
    except HTTPException:
        raise
    except Exception as e:
        logger.critical(f"Unexpected error in /login: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/login_after_sso")
async def login(
    request: Request,                                  # 👈 add this
    code: str = Query(...),
    state: str | None = Query(None),
):
    """
    Azure AD redirect URI handler.
    """
    # Log RAW URL from Azure AD
    full_url = str(request.url)
    logger.info(f"[RAW LOGIN URL FROM AZURE] {full_url}")

    logger.info("Received /login SSO callback from Azure AD")
    try:
        # --- 1. Exchange auth code for AAD tokens ---
        logger.info("Exchanging auth code for tokens via create_refresh_token()")
        logger.info(f"auth_code: {code}")
        logger.info(f"state   : {state}")

        access_token, refresh_token, user_token = create_refresh_token(code)

        if not access_token:
            logger.error("create_refresh_token() did not return an access_token")
            raise HTTPException(
                status_code=401,
                detail="Failed to acquire tokens from Azure AD",
            )

        logger.info("Successfully acquired access_token from Azure AD")

        # --- 2. Decode access_token (JWT) ---
        try:
            decoded = decode_jwt(access_token)
            payload = decoded.get("payload", {})
            logger.info(f"/login decoded AAD JWT payload: {payload}")
        except Exception as ex:
            logger.exception(f"Failed to decode AAD JWT: {ex}")
            raise HTTPException(status_code=400, detail="Malformed JWT received from Azure AD")

        # --- 3. Extract user id (PERNR) from JWT payload ---
        user_id = extract_user_id(payload)
        if not user_id:
            logger.error("Could not derive user_id (PERNR) from JWT 'upn'/'unique_name'")
            raise HTTPException(status_code=401, detail="Unable to derive user_id from token")

        logger.info(f"User authenticated via Azure AD → PERNR={user_id}, oid={user_token}")

        # --- 4. Mint backend app token (your own JWT) ---
        new_token, iat, exp = create_access_token({"sub": str(user_id)})
        add_usertoken(str(user_id), new_token, iat, exp)
        logger.info(f"Minted backend JWT for user={user_id}: {new_token}")

        # --- 5. Create ADK session ---
        try:
            base_state = deepcopy(DEFAULT_TRAVEL_STATE)

            session = await session_service.create_session(
                app_name=APP_NAME,
                user_id=str(user_id),
                state=base_state,
            )
            session_id = getattr(session, "id", None) or (
                session.get("id") if isinstance(session, dict) else None
            )
            logger.info(f"Created ADK session for user={user_id}: {session_id}")

            # Stamp identifiers and scaffolding into state
            await apply_state_delta(
                session_service,
                session,
                {
                    "app:user_id": str(user_id),
                    "app:session_id": str(session_id),
                    "app:app_name": APP_NAME,
                    "intent": base_state.get("intent", "message"),
                    "trip_id": base_state.get("trip_id", "0000000000"),
                    "travel_details": base_state.get("travel_details", {}),
                    "flight_details": base_state.get("flight_details", {}),
                    "get_reimbursement": base_state.get("get_reimbursement", {}),
                    "message": base_state.get(
                        "message", {"user_query": "", "bot_response": ""}
                    ),
                },
                author="system",
            )

        except Exception:
            logger.exception("Failed to create ADK session during /login")
            raise HTTPException(status_code=500, detail="Failed to create session")

        # --- 6. Redirect to your FE with backend token + session_id ---
        redirect_url = (
            "https://mgcdvulnabotravelclrun01-167627519943.asia-south1.run.app/login"
            f"?user={new_token}&session_id={session_id}"
        )
        logger.info(f"Redirecting user {user_id} to: {redirect_url}")
        return RedirectResponse(url=redirect_url)

    except jwt_exceptions.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except (jwt_exceptions.DecodeError, jwt_exceptions.InvalidTokenError):
        raise HTTPException(status_code=401, detail="Invalid token")
    except HTTPException:
        # already logged above
        raise
    except Exception as e:
        logger.critical(f"Unexpected error in /login: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")



# ──────────────────────────────────────────────────────────────────────────────
# 2) /getdetails — decrypt → decode → user → SAP calls → JSON response
#     “we receive the same json that we receive in the first API”
#     Interpreted as: same input token flow; we return the JSON that earlier /login returned.
# ──────────────────────────────────────────────────────────────────────────────
@app.get("/getdetails")
async def get_details(jwt_token: str = Query(...), session_id: str = Query(...)):
    logger.info("Received /getdetails request")
    if not jwt_token:
        logging.warning("No JWT token provided in request")
        raise HTTPException(status_code=400, detail="Token not provided")

    try:
        logging.info("Entered /getdetails JWT processing")
        logger.debug(f"Backend token length received: {len(jwt_token)}")

        # ✅ Decode JWT directly with secret + algorithm (no decryption)
        try:
            payload = jwt.decode(jwt_token, SECRET_KEY, algorithms=[ALGORITHM])
            logger.info("Backend token verified successfully")
        except jwt_exceptions.ExpiredSignatureError:
            logger.warning("Expired backend token on /getdetails")
            raise HTTPException(status_code=401, detail="Token expired")
        except (jwt_exceptions.DecodeError, jwt_exceptions.InvalidTokenError):
            logger.warning("Invalid backend token on /getdetails")
            raise HTTPException(status_code=401, detail="Invalid token")

        logging.info(f"/getdetails decoded payload: {payload}")
        logger.debug(f"/getdetails payload keys: {list(payload.keys())}")

        # Extract user id + metadata
        user_id = payload.get("user") or payload.get("sub") or payload.get("user_mail")
        logger.debug(f"Extracted user_id={user_id}")
        if not user_id:
            logger.error("User ID not found in backend token payload")
            raise HTTPException(status_code=400, detail="User ID not found in token")

        user_mail = payload.get("user_mail", "")
        display_name = payload.get("displayname", "")
        logger.debug(f"User meta -> mail: {user_mail}, display_name: {display_name}")

        # Mint backend token & store (so FE can use it)
        user_id_token, iat, exp = create_access_token({"sub": str(user_id)})
        add_usertoken(str(user_id), user_id_token, iat, exp)
        logger.debug(f"Minted and stored new backend token for user_id={user_id}")

        # Fetch SAP data
        pernr = str(user_id)
        logger.info(f"Invoking _fetch_user_data for pernr={pernr}")
        sap = await _fetch_user_data(pernr, session_id)
        logger.info(f"_fetch_user_data returned for pernr={pernr}")

        # Build JSON response (same fields as you previously returned)
        out = {
            "pernr": pernr,
            "trips": sap["trips"],
            "expenses": sap["expenses"],
            "categorized_trips": sap.get("categorized_trips", {}),  # Add categorized trips
            "header": sap["header"],            # include if you want it visible
            "modeEligible": sap["modeEligible"],# include if you want it visible
            "token": user_id_token,                 # newly minted backend token
            "window": sap["window"],
            "user": {"id": pernr, "mail": user_mail, "name": display_name},
        }
        logger.debug(f"/getdetails response assembled with keys: {list(out.keys())}")
        return JSONResponse(status_code=200, content=out)

    except jwt_exceptions.ExpiredSignatureError:
        logger.warning("ExpiredSignatureError bubbled up in /getdetails")
        raise HTTPException(status_code=401, detail="Token expired")
    except (jwt_exceptions.DecodeError, jwt_exceptions.InvalidTokenError):
        logger.warning("Decode/InvalidTokenError bubbled up in /getdetails")
        raise HTTPException(status_code=401, detail="Invalid token")
    except HTTPException as e:
        logger.debug(f"/getdetails raising HTTPException: {e.status_code} {e.detail}")
        raise
    except Exception as e:
        logging.critical(f"Unexpected error in /getdetails: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/chat/message", response_model=ChatEnvelope)
async def chat_message(req: ChatEnvelope):
    """
    Accepts the canonical ChatEnvelope, forwards it to the agent,
    and returns the same envelope shape with bot_response and stages updated.
    """
    logger.info(
        "Received chat message request | session_id=%s intent=%s",
        req.session_id,
        req.intent,
    )

    # ----------------------------
    # Auth: decode backend token from user_token_id
    # ----------------------------
    try:
        logger.debug("Decoding JWT for user_token_id")
        payload = jwt.decode(req.user_token_id, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = str(
            payload.get("sub")
            or payload.get("user")
            or payload.get("user_id")
        )
        logger.info("JWT decoded successfully | user_id=%s", user_id)
        if not user_id:
            logger.warning("JWT payload did not contain user_id")
            raise ValueError("user_id missing in token payload")
    except Exception:
        logger.exception("JWT decode/validation failed")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # ----------------------------
    # Create / reuse ADK session
    # ----------------------------
    session_id = (req.session_id or "").strip()
    if not session_id:
        logger.info(
            "No session_id provided — creating a new session | user_id=%s",
            user_id,
        )
        try:
            # Convert string to dict if DEFAULT_TRAVEL_STATE is a string
            logger.debug("Checking DEFAULT_TRAVEL_STATE type: %s", type(DEFAULT_TRAVEL_STATE))
            
            if isinstance(DEFAULT_TRAVEL_STATE, str):
                logger.info("DEFAULT_TRAVEL_STATE is a string, parsing to JSON")
                try:
                    initial_state = json.loads(DEFAULT_TRAVEL_STATE)
                    logger.info("✅ Successfully parsed DEFAULT_TRAVEL_STATE to dict")
                except json.JSONDecodeError as json_err:
                    logger.error("❌ Failed to parse DEFAULT_TRAVEL_STATE JSON: %s", json_err)
                    logger.error("Problematic string (first 200 chars): %s", DEFAULT_TRAVEL_STATE[:200])
                    raise
            else:
                logger.info("DEFAULT_TRAVEL_STATE is already a dict, creating deep copy")
                initial_state = copy.deepcopy(DEFAULT_TRAVEL_STATE)
                logger.debug("Deep copy created successfully")
            
            # Verify the state is JSON serializable before passing to session service
            logger.debug("Validating initial_state is JSON serializable")
            try:
                json.dumps(initial_state)
                logger.info("✅ initial_state is JSON serializable")
            except TypeError as type_err:
                logger.error("❌ initial_state contains non-JSON-serializable data: %s", type_err)
                logger.error("Problematic state structure: %s", initial_state)
                raise HTTPException(
                    status_code=500, 
                    detail=f"State template contains non-serializable data: {type_err}"
                )
            
            logger.info("Calling session_service.create_session | app_name=%s user_id=%s", APP_NAME, user_id)
            session = await session_service.create_session(
                app_name=APP_NAME,
                user_id=user_id,
                state=initial_state,
            )
            
            session_id = getattr(session, "id", None) or (
                session.get("id") if isinstance(session, dict) else None
            )
            
            if session_id:
                logger.info(
                    "✅ New session created successfully | session_id=%s user_id=%s",
                    session_id,
                    user_id,
                )
            else:
                logger.error("❌ Session created but session_id is None | user_id=%s", user_id)
                raise HTTPException(status_code=500, detail="Session created but ID is missing")
                
        except json.JSONDecodeError as e:
            logger.exception("❌ JSON parsing error for DEFAULT_TRAVEL_STATE")
            raise HTTPException(status_code=500, detail=f"Invalid state template JSON: {e}")
        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            logger.exception("❌ Unexpected error creating new session | user_id=%s", user_id)
            logger.error("Exception type: %s", type(e).__name__)
            logger.error("Exception message: %s", str(e))
            raise HTTPException(status_code=500, detail=f"Could not create session: {str(e)}")
    else:
        logger.debug(
            "Using existing session | session_id=%s user_id=%s",
            session_id,
            user_id,
        )

    # ----------------------------
    # Load existing session state (for seeding & snapshot)
    # ----------------------------
    try:
        logger.debug(
            "Fetching existing session state | session_id=%s user_id=%s",
            session_id,
            user_id,
        )
        existing_state = await get_session_state(
            session_service,
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )
        logger.info(
            "Loaded existing session state | session_id=%s",
            session_id,
        )
    except Exception:
        logger.exception(
            "Failed to load existing session state — using defaults | session_id=%s user_id=%s",
            session_id,
            user_id,
        )
        existing_state = DEFAULT_TRAVEL_STATE.copy()

    # ----------------------------
    # Normalize incoming envelope against our schema
    # ----------------------------
    intent = (req.intent or existing_state.get("intent") or "message").strip()
    trip_id = (req.trip_id or existing_state.get("trip_id") or "0000000000").strip()

    outgoing_env = ChatEnvelope(
        user_token_id=req.user_token_id or "",
        session_id=session_id,
        trip_id=trip_id,
        intent=intent,
        message=req.message or Message(),
        flight_details=req.flight_details or FlightDetails(),
        get_reimbursement=req.get_reimbursement or GetReimbursement(),
    )

    logger.debug(
        "Prepared outgoing envelope for agent | intent=%s flight_stage=%s reimb_stage=%s",
        outgoing_env.intent,
        outgoing_env.flight_details.stage,
        outgoing_env.get_reimbursement.stage,
    )

    # ─────────────────────────────────────────────────────────────
    # Persist FE-provided preferred flights when we enter flight_booking
    # ─────────────────────────────────────────────────────────────
    try:
        if (
            outgoing_env.intent == "flight"
            and (outgoing_env.flight_details.stage or "").strip() == "flight_booking"
        ):
            # Read either the model field (nav_preffered) or the wire alias (nav_preffered)
            preferred_list = (
                getattr(outgoing_env.flight_details, "nav_preffered", None)
                or (outgoing_env.flight_details.model_dump(by_alias=True) or {}).get(
                    "nav_preffered"
                )
                or []
            )
            if isinstance(preferred_list, list) and preferred_list:
                redis_mgr.save_json(
                    data=preferred_list,
                    user_id=user_id,                # PERNR from JWT
                    session_id=session_id,
                    data_type="preffered_flights",   # exact key name requested
                )
                logger.info(
                    "Saved preffered_flights to Redis | session_id=%s user_id=%s count=%d",
                    session_id,
                    user_id,
                    len(preferred_list),
                )
            else:
                logger.debug(
                    "No nav_preferredflights present in FE payload to persist | session_id=%s user_id=%s",
                    session_id,
                    user_id,
                )
    except Exception:
        logger.exception(
            "Failed to persist preffered_flights from FE payload | session_id=%s user_id=%s",
            session_id,
            user_id,
        )

    # ─────────────────────────────────────────────────────────────
    # Redact flight lists before sending to the agent
    # (keep only the stage; no flight objects leave the server)
    # ─────────────────────────────────────────────────────────────
    env_for_agent = outgoing_env.model_copy(deep=True)  # pydantic v2 deep copy
    if (
        env_for_agent.intent == "flight"
        and (env_for_agent.flight_details.stage or "").strip() in {"flight_selection", "flight_booking"}
    ):
        logger.debug(
            "Redacting flight details before sending to agent | session_id=%s stage=%s",
            session_id,
            env_for_agent.flight_details.stage,
        )
        env_for_agent.flight_details = FlightDetails(stage=env_for_agent.flight_details.stage)

    # ----------------------------
    # Send to agent (as JSON)
    # ----------------------------
    outgoing_json = json.dumps(env_for_agent.to_wire(), ensure_ascii=False)
    user_content = types.Content(role="user", parts=[types.Part(text=outgoing_json)])

    final_text_parts: List[str] = []
    try:
        logger.info(
            "Invoking agent runner | user_id=%s session_id=%s intent=%s",
            user_id,
            session_id,
            env_for_agent.intent,
        )
        
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=user_content,
        ):
            content = getattr(event, "content", None)
            parts = getattr(content, "parts", []) if content else []
            for p in parts or []:
                if getattr(p, "text", None):
                    final_text_parts.append(p.text)
            if getattr(event, "turn_complete", False):
                logger.debug(
                    "Agent turn_complete received | session_id=%s",
                    session_id,
                )
                break
        logger.info(
            "Agent runner completed | session_id=%s collected_parts=%d",
            session_id,
            len(final_text_parts),
        )
    except Exception as e:
        logger.exception(
            "Runner.run_async failed | session_id=%s user_id=%s error=%s",
            session_id,
            user_id,
            e,
        )
        raise HTTPException(status_code=500, detail=f"Agent run failed: {e}")

    # ----------------------------
    # Parse agent response as ChatEnvelope and persist minimal state
    # ----------------------------
    agent_response = "".join(final_text_parts).strip()
    cleaned = agent_response.replace("```json", "").replace("```", "").strip()
    logger.debug(
        "Raw agent response received | session_id=%s length=%d",
        session_id,
        len(agent_response),
    )

# Try to parse the agent response into ChatEnvelope
    try:
        agent_env = ChatEnvelope.model_validate_json(cleaned)

        logger.info(
            "Agent response parsed into ChatEnvelope | session_id=%s intent=%s trip_id=%s",
            session_id,
            agent_env.intent,
            agent_env.trip_id,
        )

        # Log full agent_env and existing_state
        logger.info("=" * 80)
        logger.info("📦 FULL AGENT RESPONSE (agent_env):")
        logger.info("=" * 80)
        logger.info(json.dumps(agent_env.model_dump(), indent=2, default=str))
        logger.info("=" * 80)
        logger.info("")
        logger.info("=" * 80)
        logger.info("💾 FULL SESSION STATE (existing_state):")
        logger.info("=" * 80)
        logger.info(json.dumps(existing_state, indent=2, default=str))
        logger.info("=" * 80)

        logger.info(
            "Agent response parsed into ChatEnvelope | session_id=%s intent=%s trip_id=%s",
            session_id,
            agent_env.intent,
            agent_env.trip_id,
        )
 
        # ─────────────────────────────────────────────────────────────
        # Attach prefetched flight options ONLY when:
        #   - intent == "flight"
        #   - stage == "flight_selection"
        #
        # ES_GET flight was already triggered (once) in check_trip_validity_tool.
        # This helper MUST ONLY READ from Redis and MUST NOT call SAP again.
        # ─────────────────────────────────────────────────────────────
        try:
            if (
                agent_env.intent == "flight"
                and agent_env.flight_details is not None
                and (agent_env.flight_details.stage or "") == "flight_selection"
            ):
                logger.info(
                    "Attaching prefetched flights from Redis | user_id=%s session_id=%s",
                    user_id,
                    session_id,
                )

                # Log all input parameters
                logger.info("📋 Function inputs: agent_env.intent=%s, agent_env.travel_details=%s, user_id=%s, session_id=%s, existing_state.keys=%s, max_wait=%s, poll_interval=%s",
                    getattr(agent_env, 'intent', None),
                    agent_env.travel_details.model_dump() if hasattr(agent_env, 'travel_details') and agent_env.travel_details else None,
                    user_id,
                    session_id,
                    list(existing_state.keys()) if existing_state else None,
                    flight_timeout,
                    flight_poll_interval
                )

                agent_env = _attach_prefetched_flights_to_envelope(
                    agent_env=agent_env,
                    user_id=user_id,
                    session_id=session_id,
                    existing_state=existing_state,
                    max_wait_seconds=flight_timeout,
                    poll_interval=flight_poll_interval,
                )
            else:
                logger.debug(
                    "Skipping flight attachment (intent=%s, stage=%s) | session_id=%s",
                    agent_env.intent,
                    getattr(agent_env.flight_details, "stage", ""),
                    session_id,
                )
        except Exception:
            # Never break main flow if flight attachment fails
            logger.exception(
                "Failed to attach prefetched flights from Redis | user_id=%s session_id=%s",
                user_id,
                session_id,
            )

    except Exception:
        # Agent returned non-JSON or wrong shape → fall back to plain text
        logger.exception(
            "Agent did not return a valid ChatEnvelope; falling back to text | session_id=%s",
            session_id,
        )
        fallback_env = ChatEnvelope(
            user_token_id=req.user_token_id,
            session_id=session_id,
            trip_id=trip_id,
            intent=intent,
            message=Message(
                user_query=req.message.user_query if req.message else "",
                bot_response=agent_response
                or "Sorry, I couldn't parse the response.",
            ),
            flight_details=FlightDetails(),
            get_reimbursement=GetReimbursement(),
        )
        return fallback_env

    # 2) Best-effort: permanent chat snapshot logic (must NEVER break main flow)
    try:
        logger.info(
            "▶ Entering permanent chat snapshot logic | session_id=%s prev_trip_id_raw=%s",
            session_id,
            (existing_state or {}).get("trip_id", "0000000000"),
        )

        prev_trip_id = (existing_state or {}).get("trip_id", "0000000000")
        new_trip_id = (agent_env.trip_id or "").strip()
        
        logger.info(
            "🔍 Trip ID check | prev_trip_id=%s new_trip_id=%s",
            prev_trip_id,
            new_trip_id,
        )

        # Only proceed when valid & changed
        if _is_valid_trip_id(new_trip_id) and new_trip_id != prev_trip_id:
            logger.info(
                "🆕 New valid trip_id detected → begin snapshot | user_id=%s session_id=%s trip_id=%s",
                user_id,
                session_id,
                new_trip_id,
            )

            # ------------------------------------------------------------------
            # 1) Preferred method: fetch events using session_service
            # ------------------------------------------------------------------
            raw_event_rows = []
            try:
                logger.info(
                    "📥 Fetching events via session_service.get_session | app_name=%s user_id=%s session_id=%s",
                    APP_NAME,
                    user_id,
                    session_id,
                )

                sess = await session_service.get_session(
                    app_name=APP_NAME, user_id=user_id, session_id=session_id
                )
                events = getattr(sess, "events", None)

                if not events:
                    logger.warning(
                        "⚠ No events returned from session_service | user_id=%s session_id=%s",
                        user_id,
                        session_id,
                    )
                else:
                    logger.info(
                        "📦 Events received from ADK session table | user_id=%s session_id=%s event_count=%d",
                        user_id,
                        session_id,
                        len(events),
                    )

                for idx, ev in enumerate(events or []):
                    try:
                        # Try to normalize event content
                        try:
                            content_json = ev.content.to_json()  # some ADK builds support this
                        except Exception:
                            content_json = None

                        if not content_json:
                            parts = getattr(ev.content, "parts", None)
                            if parts:
                                try:
                                    content_json = json.dumps(
                                        {
                                            "parts": [
                                                {"text": getattr(parts[0], "text", "")}
                                            ]
                                        }
                                    )
                                except Exception:
                                    content_json = getattr(ev, "content", None)
                            else:
                                content_json = getattr(ev, "content", None)

                        row = {
                            "timestamp": getattr(ev, "timestamp", None),
                            "author": getattr(ev, "author", ""),
                            "content": (
                                content_json
                                if isinstance(content_json, str)
                                else json.dumps(content_json or "")
                            ),
                        }
                        raw_event_rows.append(row)

                        logger.debug(
                            "📄 Event normalized | index=%d author=%s timestamp=%s",
                            idx,
                            row["author"],
                            row["timestamp"],
                        )

                    except Exception:
                        logger.exception(
                            "Failed to normalize event | event_index=%d",
                            idx,
                        )

            except Exception:
                # ------------------------------------------------------------------
                # 2) Fallback: query database manually
                # ------------------------------------------------------------------
                logger.exception(
                    "❌ session_service.get_session failed — falling back to events table | user_id=%s session_id=%s",
                    user_id,
                    session_id,
                )
                try:
                    adk_db_url = os.getenv(
                        "SESSION_DB_URL",
                        "sqlite:///./agent_sessions.db",
                    )
                    logger.info(
                        "📚 Querying ADK events table directly | db_url=%s user_id=%s session_id=%s",
                        adk_db_url,
                        user_id,
                        session_id,
                    )

                    eng = create_engine(adk_db_url, future=True)
                    with eng.begin() as conn:
                        result = conn.execute(
                            sq_text(
                                """
                                SELECT timestamp, author, content
                                FROM events
                                WHERE app_name = :app
                                  AND user_id  = :uid
                                  AND session_id = :sid
                                  AND author IN ('user','OrchestratorAgent')
                                ORDER BY timestamp ASC, id ASC
                                """
                            ),
                            {
                                "app": APP_NAME,
                                "uid": user_id,
                                "sid": session_id,
                            },
                        )
                        raw_event_rows = [dict(row._mapping) for row in result]

                    logger.info(
                        "📦 Fallback DB events loaded | user_id=%s session_id=%s count=%d",
                        user_id,
                        session_id,
                        len(raw_event_rows),
                    )
                except Exception:
                    logger.exception(
                        "❌ Failed to read events from fallback DB | user_id=%s session_id=%s",
                        user_id,
                        session_id,
                    )
                    raw_event_rows = []

            # ------------------------------------------------------------------
            # 3) Convert raw events → user/bot pairs
            # ------------------------------------------------------------------
            try:
                logger.info(
                    "🔧 Extracting message pairs from events | user_id=%s session_id=%s raw_event_count=%d",
                    user_id,
                    session_id,
                    len(raw_event_rows),
                )

                pairs = extract_pairs_from_events(raw_event_rows)

                logger.info(
                    "📑 extract_pairs_from_events output | user_id=%s session_id=%s pair_count=%d",
                    user_id,
                    session_id,
                    len(pairs),
                )
            except Exception:
                logger.exception(
                    "❌ Failed during extract_pairs_from_events | user_id=%s session_id=%s",
                    user_id,
                    session_id,
                )
                pairs = []

            # ------------------------------------------------------------------
            # 4) Persist to permanent store
            # ------------------------------------------------------------------
            try:
                logger.info(
                    "💾 Saving permanent chat history | user_id=%s trip_id=%s rows_in_snapshot=%d",
                    user_id,
                    new_trip_id,
                    len(pairs),
                )

                saved = save_trip_chat(
                    user_id=user_id,
                    trip_id=new_trip_id,
                    chat_rows=pairs,
                )

                logger.info(
                    "✅ Permanent chat history saved successfully | user_id=%s trip_id=%s rows_saved=%d",
                    user_id,
                    new_trip_id,
                    saved,
                )
            except Exception:
                logger.exception(
                    "❌ Failed to persist permanent chat snapshot | user_id=%s trip_id=%s",
                    user_id,
                    new_trip_id,
                )

    except Exception:
        # Snapshot errors should NEVER break the main response
        logger.exception(
            "💥 Unexpected error in trip history snapshot block | user_id=%s session_id=%s",
            user_id,
            session_id,
        )

    # 3) Build final response envelope (always)
    response_env = ChatEnvelope(
        user_token_id=req.user_token_id,
        session_id=session_id,
        trip_id=(agent_env.trip_id or trip_id),
        intent=agent_env.intent,
        message=agent_env.message,
        flight_details=agent_env.flight_details,
        get_reimbursement=agent_env.get_reimbursement,
    )
    logger.info(
        "Returning ChatEnvelope response | user_id=%s session_id=%s intent=%s trip_id=%s",
        user_id,
        session_id,
        response_env.intent,
        response_env.trip_id,
    )
    return response_env






@app.post("/chat/upload/", response_model=UploadAck)
async def upload_reimbursement_files(
    session_id: str = Form(...),
    user_token_id: str = Form(...),
    files: List[UploadFile] = File(...),
):
    """
    Accepts multipart/form-data with files and saves them to:
      travel_assist_agentic_bot/responses/reimburse_files/{PERNR}_{session_id}/{filename}

    Overwrites if a file already exists. Returns paths relative to the project like:
      travel_assist_agentic_bot/responses/reimburse_files/25017514_<session>/bill1.jpg
    """
    logger.info("Upload request received", extra={"session_id": session_id})

    if not files:
        logger.warning("No files provided in upload request", extra={"session_id": session_id})
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="No files provided")

    # Resolve PERNR from token (your existing helper)
    pernr_code = _derive_pernr_from_token(user_token_id)
    logger.info("Derived PERNR from token", extra={"session_id": session_id, "pernr": pernr_code})

    # Base dir: travel_assist_agentic_bot/responses/reimburse_files/{PERNR}_{session_id}
    base_dir = Path("travel_assist_agentic_bot") / "responses" / "reimburse_files" / f"{pernr_code}_{session_id}"
    try:
        base_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.exception("Failed to ensure base directory", extra={"base_dir": str(base_dir)})
        raise HTTPException(status_code=500, detail=f"Failed to prepare upload folder: {e}")

    saved: List[Dict[str, Any]] = []

    for up in files:
        original = up.filename or "upload.bin"
        stem = Path(original).stem
        ext = Path(original).suffix or ".bin"

        # Filenames are stored AS-IS (sanitized only minimally)
        out_name = f"{stem}{ext}"
        out_path = base_dir / out_name

        if out_path.exists():
            logger.info(
                "Overwriting existing file",
                extra={"session_id": session_id, "pernr": pernr_code, "existing": str(out_path)},
            )

        try:
            blob = await up.read()
        except Exception as e:
            logger.exception("Failed reading upload from client", extra={"filename": original})
            raise HTTPException(status_code=500, detail=f"Failed to read uploaded file: {original}: {e}")

        try:
            with open(out_path, "wb") as f:
                f.write(blob)
        except Exception as e:
            logger.exception("Failed writing file", extra={"path": str(out_path)})
            raise HTTPException(status_code=500, detail=f"Failed to save file {out_name}: {e}")

        size = len(blob)

        # Build the relative path under reimburse_files/{PERNR}_{session_id}/{filename}
        rel_path = (Path("travel_assist_agentic_bot") / "responses" / "reimburse_files" / f"{pernr_code}_{session_id}" / out_name)
        rel_path_str = rel_path.as_posix()  # keep forward slashes for consistency

        logger.info(
            "File saved",
            extra={
                "session_id": session_id,
                "pernr": pernr_code,
                "stored_as": out_name,
                "size_bytes": size,
                "content_type": up.content_type,
                "relative_path": rel_path_str,
            },
        )

        # ⬇️ Return structure UNCHANGED
        saved.append({
            "path": rel_path_str,                       # unchanged key
            "stored_as": out_name,                      # unchanged key
            "original_filename": original,              # unchanged key
            "size": size,                               
            "content_type": up.content_type or "application/octet-stream",
            "sha256": _sha256_of_bytes(blob),          # your existing helper
        })

    logger.info(
        "Upload completed",
        extra={"session_id": session_id, "pernr": pernr_code, "total_files": len(saved), "folder": str(base_dir)},
    )

    # ⬇️ Response shape UNCHANGED
    return {
        "session_id": session_id,
        "user_token_id": user_token_id,
        "pernr": pernr_code,
        "saved_files": saved,
        "message": (
            "Files uploaded successfully. Use these 'path' values in "
            "get_reimbursement.files for /chat/message."
        ),
    }



@app.post("/logout")
async def logout(jwt_token: str = Query(...), session_id: str = Query(...)):
    """
    Frontend sends backend jwt_token (the one we minted) and a session_id.
    We verify token, extract user_id, and then:
      1) Delete ONLY Redis keys under travel_data:{user_id}:{session_id}:*
      2) Delete ONLY top-level JSON files in 'responses/' that start with '{user_id}_'
    """
    logger.info("Received /logout request")
    if not jwt_token or not session_id:
        raise HTTPException(status_code=400, detail="jwt_token and session_id are required")

    # ---- Verify + decode backend token ----
    try:
        payload = jwt.decode(jwt_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = str(payload.get("sub") or payload.get("user") or payload.get("user_id") or "").strip()
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID missing in token")
        logger.info("Logout for user_id=%s, session_id=%s", user_id, session_id)
    except jwt_exceptions.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except (jwt_exceptions.DecodeError, jwt_exceptions.InvalidTokenError):
        raise HTTPException(status_code=401, detail="Invalid token")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected JWT decode error in /logout")
        raise HTTPException(status_code=500, detail=f"JWT processing failed: {e}")

    # ---- Redis cleanup (only this user's session keys) ----
    try:
        # Reuse the same connection params / prefix you use elsewhere
        deleted_redis = clear_user_session_in_redis(
            user_id=user_id,
            session_id=session_id,
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "0")),
            password=os.getenv("REDIS_PASSWORD", None),
            key_prefix=os.getenv("REDIS_KEY_PREFIX", "travel_data"),
        )
    except Exception:
        logger.exception("Redis cleanup threw an exception in /logout")
        deleted_redis = 0

    # ---- Responses JSON cleanup (only files starting with '{user_id}_') ----
    try:
        deleted_files_count, deleted_files = clear_user_response_jsons(
            user_id=user_id,
            responses_dir=os.path.join("travel_assist_agentic_bot", "responses"),
        )
    except Exception:
        logger.exception("File cleanup threw an exception in /logout")
        deleted_files_count, deleted_files = 0, []

    # Optionally: drop in-memory token
    try:
        if user_id in _TOKENS:
            _TOKENS.pop(user_id, None)
    except Exception:
        logger.exception("Failed to remove user token from in-memory store during /logout")

    # Done
    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "user_id": user_id,
            "session_id": session_id,
            "redis_keys_deleted": deleted_redis,
            "json_files_deleted": deleted_files_count,
            "deleted_file_paths": deleted_files,  # useful while testing; remove in prod if noisy
            "message": "User session cache and JSON files cleared.",
        },
    )

@app.get("/chat/history")
async def get_chat_history(
    jwt_token: str = Query(..., description="Backend JWT token"),
    session_id: str = Query(..., description="ADK session identifier"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of messages to return (1-100)")
):
    """
    Fetch conversation history for a given session.
    
    Query Parameters:
    - jwt_token: Backend JWT token (from /login)
    - session_id: ADK session identifier
    - limit: Number of recent messages to return (default: 20, max: 100)
    
    Returns:
    {
        "session_id": "abc-123",
        "user_id": "25017514",
        "count": 10,
        "chat_history": [
            {"role": "user", "message": "...", "timestamp": ...},
            {"role": "assistant", "message": "...", "timestamp": ...},
            ...
        ]
    }
    """
    logger.info("Received /chat/history request | session_id=%s", session_id)
    
    # Validate JWT token
    try:
        payload = jwt.decode(jwt_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = str(payload.get("sub") or payload.get("user") or payload.get("user_id") or "").strip()
        if not user_id:
            logger.warning("JWT payload missing user_id")
            raise HTTPException(status_code=400, detail="User ID missing in token")
        logger.info("Token validated | user_id=%s session_id=%s", user_id, session_id)
    except jwt_exceptions.ExpiredSignatureError:
        logger.warning("Expired token in /chat/history")
        raise HTTPException(status_code=401, detail="Token expired")
    except (jwt_exceptions.DecodeError, jwt_exceptions.InvalidTokenError):
        logger.warning("Invalid token in /chat/history")
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        logger.exception("JWT decode error in /chat/history")
        raise HTTPException(status_code=500, detail=f"Token validation failed: {e}")
    
    # Fetch chat history
    try:
        logger.info(
            "Fetching chat history | user_id=%s session_id=%s limit=%d",
            user_id,
            session_id,
            limit
        )
        
        chat_history = await fetch_recent_history(
            session_service=session_service,
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
            limit=limit
        )
        
        logger.info(
            "Chat history fetched successfully | user_id=%s session_id=%s count=%d",
            user_id,
            session_id,
            len(chat_history)
        )
        
        return JSONResponse(
            status_code=200,
            content={
                "session_id": session_id,
                "user_id": user_id,
                "count": len(chat_history),
                "chat_history": chat_history
            }
        )
        
    except Exception as e:
        logger.exception(
            "Error fetching chat history | user_id=%s session_id=%s error=%s",
            user_id,
            session_id,
            str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch chat history: {str(e)}"
        )
        

@app.get("/trips/{trip_id}/chat")
async def get_trip_chat(trip_id: str, user_id: str = Query(...)):
    try:
        chat = fetch_trip_chat(user_id=user_id, trip_id=trip_id)
        return JSONResponse(
            status_code=200,
            content={"user_id": user_id, "trip_id": trip_id, "count": len(chat), "chat": chat},
        )
    except Exception as e:
        logger.exception("Error fetching chat history")
        raise HTTPException(status_code=500, detail=str(e))
    

@app.websocket("/ws/voice/{session_id}")
async def voice_websocket_endpoint(websocket: WebSocket, session_id: str):
    """Voice WebSocket endpoint for real-time audio streaming"""
    
    # Extract query params
    user_id = websocket.query_params.get("user_id")
    app_name = websocket.query_params.get("app_name", "travel-portal-voice")
    
    await handle_voice_websocket(  
        websocket,
        session_id,
        user_id=user_id,
        app_name=app_name
    )


# OPTIONAL: Add voice health check endpoint
@app.get("/api/voice/health")
async def voice_health_check():
    """Check if voice service is available"""
    try:
        # Add any voice-specific health checks here
        return {
            "status": "healthy",
            "voice_enabled": True,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }






