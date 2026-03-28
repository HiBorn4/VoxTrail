# travel_assist_agentic_bot/services/permanent_store.py
from __future__ import annotations
import os
import json
import hashlib
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy import (
    create_engine, MetaData, Table, Column, Integer, String, Text,
    Float, DateTime, UniqueConstraint
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

PERM_DB_URL = os.getenv("PERM_DB_URL", "sqlite:///./permanent_store.db")

_metadata = MetaData()
_engine: Engine | None = None

trip_chats = Table(
    "trip_chats", _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String(64), nullable=False, index=True),
    Column("trip_id", String(16), nullable=False, index=True),
    Column("timestamp", Float, nullable=False, index=True),
    Column("author", String(64), nullable=False),
    Column("message_text", Text, nullable=False),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
    UniqueConstraint("user_id", "trip_id", "timestamp", "author", "message_text",
                     name="uq_trip_chat_row"),
)

def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(PERM_DB_URL, future=True)
        _metadata.create_all(_engine)
    return _engine

def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def save_trip_chat(*, user_id: str, trip_id: str,
                   chat_rows: List[Dict[str, Any]]) -> int:
    """
    Persist chat_rows: [{"at": float, "author": "user|OrchestratorAgent", "text": str}]
    Returns count of inserted rows.
    """
    if not (user_id and trip_id and chat_rows):
        return 0
    eng = _get_engine()
    inserted = 0
    with eng.begin() as conn:
        for row in chat_rows:
            try:
                conn.execute(
                    trip_chats.insert().values(
                        user_id=user_id,
                        trip_id=trip_id,
                        timestamp=float(row["at"]),
                        author=row["author"],
                        message_text=row["text"],
                        created_at=datetime.utcnow(),
                    )
                )
                inserted += 1
            except IntegrityError:
                pass
    return inserted

def fetch_trip_chat(user_id: str, trip_id: str) -> List[Dict[str, Any]]:
    """Retrieve chat history ordered by time for a given user+trip."""
    eng = _get_engine()
    with eng.begin() as conn:
        res = conn.execute(
            trip_chats.select()
            .where(trip_chats.c.user_id == user_id, trip_chats.c.trip_id == trip_id)
            .order_by(trip_chats.c.timestamp.asc(), trip_chats.c.id.asc())
        )
        rows = res.fetchall()
    return [
        {
            "timestamp": r.timestamp,
            "author": r.author,
            "message_text": r.message_text,
        }
        for r in rows
    ]
