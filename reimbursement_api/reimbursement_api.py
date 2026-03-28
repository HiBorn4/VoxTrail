"""
tool_analyze_api.py
Requires:
    pip install requests python-dotenv httpx

.env:
    SECRET_KEY=your_api_key_here
"""

from __future__ import annotations

import os
import mimetypes
from typing import Iterable, List, Dict, Any, Optional, Tuple, Union
from pathlib import Path
from loguru import logger
import requests
from dotenv import load_dotenv
from ...services.redis_manager import RedisJSONManager
# Optional async/parallel support
import httpx


# Load environment variables early so functions can read SECRET_KEY
load_dotenv()

DEFAULT_ANALYZE_API_URL = "https://trip-reimburse-cf-01-167627519943.asia-south1.run.app/analyze"
DEFAULT_TIMEOUT_SECONDS = 120  # internal default; not exposed as a parameter

# Initialize Redis manager once at the beginning
redis_mgr = RedisJSONManager()

def _detect_mime(path: Path) -> str:
    """Best-effort MIME detection for images & pdfs."""
    # Fallback for common cases if mimetypes returns None
    mt, _ = mimetypes.guess_type(path.name)
    if mt:
        return mt
    if path.suffix.lower() == ".pdf":
        return "application/pdf"
    return "application/octet-stream"


def _prep_files(paths: Iterable[Path]) -> Tuple[List[Tuple[str, Tuple[str, Any, str]]], List[Any]]:
    """
    Build the requests-compatible 'files' payload and keep open file handles.

    Returns:
        (files_payload, open_handles)
        files_payload: list for requests.post(..., files=files_payload)
        open_handles: list of open file objects we must close later
    """
    files_payload: List[Tuple[str, Tuple[str, Any, str]]] = []
    open_handles: List[Any] = []
    for p in paths:
        f = open(p, "rb")
        open_handles.append(f)
        files_payload.append(("files", (p.name, f, _detect_mime(p))))
    return files_payload, open_handles


def _coerce_to_paths(items: Iterable[Union[str, Dict[str, Any], Any]]) -> List[Path]:
    out: List[Path] = []
    for it in items or []:
        # NEW: already a Path
        if isinstance(it, Path):
            out.append(it)
            continue
        # strings
        if isinstance(it, str):
            out.append(Path(it.replace("\\", "/")))
            continue
        # dict with path-ish keys
        if isinstance(it, dict):
            for k in ("path", "filepath", "saved_path"):
                v = it.get(k)
                if isinstance(v, str):
                    out.append(Path(v.replace("\\", "/")))
                    break
            continue
        # objects with .path
        p = getattr(it, "path", None)
        if isinstance(p, str):
            out.append(Path(p.replace("\\", "/")))
    return out




def analyze_reimbursement_documents(
    file_paths: Iterable[Union[str, Dict[str, Any], Any]],
    user_id: str,
    session_id: str,
) -> Dict[str, Any]:
    """
    Analyze reimbursement documents and store ONLY in Redis; do not return the JSON payload.

    Inputs:
      - file_paths: Iterable of file paths / dicts / objects with .path
      - user_id (str): Required. Used as Redis user scope (e.g., PERNR).
      - session_id (str): Required. Used as Redis session scope.
      - data_type (str): Redis logical bucket (default: 'reimbursement_analyze').

    Output (no data returned):
      {
        "status": "success" | "error",
        "http_status": int,
        "error_message": str | None
      }
    """
    logger.info("🔍 Starting analyze_reimbursement_documents for user_id=%s session_id=%s", user_id, session_id)

    # ---- Mandatory Redis scoping ----
    if not user_id or not session_id:
        logger.error("❌ Missing required Redis scoping info: user_id=%s, session_id=%s", user_id, session_id)
        return {
            "status": "error",
            "http_status": 0,
            "error_message": "user_id and session_id are required to store results in Redis.",
        }

    api_key = os.getenv("JWT_SECRET_KEY")
    if not api_key:
        logger.error("❌ JWT_SECRET_KEY not found in environment.")
        return {
            "status": "error",
            "http_status": 0,
            "error_message": "JWT_SECRET_KEY not found in environment (.env).",
        }

    # Normalize to Paths
    logger.info("📁 Normalizing incoming file paths...")
    paths = _coerce_to_paths(file_paths)

    logger.info(f"📄 Total files received: {len(paths)}")

    for i, p in enumerate(paths, start=1):
        logger.info(f"   • [{i:02d}] {p} (exists={os.path.exists(p)})")

    # Validate
    if not paths:
        logger.error("❌ No valid file paths provided: %s", file_paths)
        return {
            "status": "error",
            "http_status": 0,
            "error_message": "No valid file paths provided.",
        }

    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        logger.warning("⚠️ Missing files: %s", missing)
        return {
            "status": "error",
            "http_status": 0,
            "error_message": f"Missing files: {missing}",
        }

    # Prepare upload payload
    logger.info("🧾 Preparing file payload for OCR API...")
    files_payload, open_handles = _prep_files(paths)
    logger.info("✅ Prepared %d files for upload.", len(files_payload))

    headers = {
        "X-API-KEY": api_key,
        "Accept": "application/json",
    }

    try:
        timeout = httpx.Timeout(DEFAULT_TIMEOUT_SECONDS)
        with httpx.Client(timeout=timeout) as client:
            logger.info("🚀 Sending POST request to OCR API: %s", DEFAULT_ANALYZE_API_URL)
            resp = client.post(
                DEFAULT_ANALYZE_API_URL,
                headers=headers,
                files=files_payload,
            )
            logger.info("📬 OCR API response status: %s", resp.status_code)
    except Exception as e:
        for f in open_handles:
            try:
                f.close()
            except Exception:
                pass
        logger.exception("❌ Request to OCR API failed: %s", e)
        return {
            "status": "error",
            "http_status": 0,
            "error_message": f"Request failed: {e}",
        }
    finally:
        for f in open_handles:
            try:
                f.close()
            except Exception:
                pass

    # Non-2xx => error (no storage)
    if not (200 <= resp.status_code < 300):
        logger.error("❌ Non-2xx response from OCR API (%s): %s", resp.status_code, resp.text[:300])
        return {
            "status": "error",
            "http_status": resp.status_code,
            "error_message": f"Non-2xx response ({resp.status_code}).",
        }

    try:
        data = resp.json()
        logger.info("✅ Successfully parsed OCR API JSON response.")
    except ValueError:
        logger.exception("❌ OCR API returned invalid JSON.")
        return {
            "status": "error",
            "http_status": resp.status_code,
            "error_message": "Invalid JSON response from server.",
            "data": None,   # ⬅️ added
        }

    # Store in Redis ONLY; do not return the data
    try:
        logger.info("💾 Saving OCR result to Redis under user_id=%s session_id=%s", user_id, session_id)
        saved_ok = redis_mgr.save_json(
            data=data,
            user_id=str(user_id),
            session_id=str(session_id),
            data_type="reimbursement_analyze",
        )
        if not saved_ok:
            logger.warning("⚠️ Redis save_json returned False.")
            return {
                "status": "error",
                "http_status": resp.status_code,
                "error_message": "Redis save_json returned False.",
                "data": None,   # ⬅️ added
            }
    except Exception as e:
        logger.exception("❌ Failed to save OCR result in Redis: %s", e)
        return {
            "status": "error",
            "http_status": resp.status_code,
            "error_message": f"Failed to store in Redis: {e}",
            "data": None,   # ⬅️ added
        }

    # Success
    logger.info(
        "🎉 analyze_reimbursement_documents completed successfully for user_id=%s session_id=%s",
        user_id, session_id
    )
    return {
        "status": "success",
        "http_status": resp.status_code,
        "error_message": None,
        "data": data,   # ⬅️ return cleaned OCR response to caller
    }
