# travel_assist_agentic_bot/services/session_cleanup.py
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Tuple

import redis  # redis-py

logger = logging.getLogger(__name__)

def clear_user_session_in_redis(
    user_id: str,
    session_id: str,
    *,
    host: str = os.getenv("REDIS_HOST", "localhost"),
    port: int = int(os.getenv("REDIS_PORT", "6379")),
    db: int = int(os.getenv("REDIS_DB", "0")),
    password: str | None = os.getenv("REDIS_PASSWORD", None),
    key_prefix: str = os.getenv("REDIS_KEY_PREFIX", "travel_data"),
) -> int:
    """
    Delete ONLY keys for the given user_id + session_id:
    Pattern -> {key_prefix}:{user_id}:{session_id}:*

    Returns number of keys deleted.
    """
    pattern = f"{key_prefix}:{user_id}:{session_id}:*"
    r = redis.Redis(host=host, port=port, db=db, password=password, decode_responses=True)

    total_deleted = 0
    try:
        # Efficiently scan and delete
        cursor = 0
        while True:
            cursor, keys = r.scan(cursor=cursor, match=pattern, count=500)
            for chunk_start in range(0, len(keys), 500):
                chunk = keys[chunk_start:chunk_start + 500]
                if chunk:
                    total_deleted += r.delete(*chunk)
            if cursor == 0:
                break

        logger.info(
            "Redis cleanup done",
            extra={"user_id": user_id, "session_id": session_id, "deleted": total_deleted, "pattern": pattern},
        )
    except Exception:
        logger.exception("Failed during Redis cleanup for user_id=%s session_id=%s", user_id, session_id)

    return total_deleted


def clear_user_response_jsons(
    user_id: str,
    *,
    responses_dir: str = str(Path("travel_assist_agentic_bot") / "responses"),
) -> Tuple[int, list[str]]:
    """
    Delete ONLY *.json files inside `responses_dir` that start with '{user_id}_'.
    Does NOT touch subfolders (e.g., reimburse_files/) or non-JSON files.

    Returns (deleted_count, deleted_paths)
    """
    base = Path(responses_dir)
    deleted = []

    try:
        if not base.exists():
            logger.info("Responses directory does not exist: %s", responses_dir)
            return 0, []

        for p in base.glob(f"{user_id}_*.json"):
            try:
                p.unlink(missing_ok=True)
                deleted.append(str(p))
            except Exception:
                logger.exception("Failed deleting JSON file: %s", p)

        logger.info(
            "Responses *.json cleanup done",
            extra={"user_id": user_id, "responses_dir": responses_dir, "deleted_count": len(deleted)},
        )
    except Exception:
        logger.exception("Failed during responses JSON cleanup for user_id=%s", user_id)

    return len(deleted), deleted
