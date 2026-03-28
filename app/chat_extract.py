# travel_assist_agentic_bot/services/chat_extract.py

import json
import re
from datetime import datetime
from typing import List, Dict, Any, Tuple

# ---------------------------------------------------------------------------
# Constants & helpers
# ---------------------------------------------------------------------------

FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", flags=re.DOTALL)

# All agent authors that can carry final bot responses in parts[*].text
BOT_AUTHORS = {
    "OrchestratorAgent",
    "TravelRequestBookingAgent",
    "ReimbursementAgent",
    "RedisDataAgent",
}


def _parse_timestamp(value: Any) -> float:
    """Normalize various timestamp formats to a float epoch seconds."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except Exception:
        try:
            return datetime.fromisoformat(str(value)).timestamp()
        except Exception:
            return 0.0


def _strip_fences(s: str) -> str:
    """Remove ```json fences around a string, if present."""
    return FENCE_RE.sub("", (s or "").strip())


def _safe_json_load(s: str) -> Any:
    """json.loads with failure → None."""
    try:
        return json.loads(s)
    except Exception:
        return None


def _candidate_plain_text(s: str) -> bool:
    """
    Treat as plain text only if it looks like a small sentence, not a big JSON blob.
    """
    if not s:
        return False
    if "{" in s or "}" in s or "[" in s or "]" in s:
        return False
    return len(s.strip()) <= 300 and (" " in s or "." in s)


# ---------------------------------------------------------------------------
# parts[*] and content parsing
# ---------------------------------------------------------------------------

def _extract_text_snippets_from_parts_obj(parts_obj: List[dict]) -> List[str]:
    """
    Given ADK/GenAI content.parts, return text-like snippets.

    In your data:
      { "parts": [ { "text": "<ChatEnvelope JSON string>" } ], "role": "user|model" }

    We also handle function_response.result just in case.
    """
    out: List[str] = []
    for p in parts_obj or []:
        if not isinstance(p, dict):
            continue

        # 1) direct text
        txt = p.get("text")
        if isinstance(txt, str) and txt.strip():
            out.append(txt.strip())
            continue

        # 2) function_response.response.result (sometimes text or an envelope)
        fr = p.get("function_response")
        if isinstance(fr, dict):
            resp = fr.get("response")
            if isinstance(resp, dict):
                res = resp.get("result")
                if isinstance(res, str) and res.strip():
                    out.append(res.strip())
            # non-string result → ignore

        # 3) function_call → ignore

    return out


def _extract_texts_from_content(cell: str) -> List[str]:
    """
    Normalize the 'content' column to a list of candidate text snippets.

    Handles:
      - '{"parts":[...],"role":"user|model"}' → returns every parts[*].text / result
      - dict/list → keep as single JSON string
      - plain string → keep
    """
    out: List[str] = []
    if not cell:
        return out
    cell = cell.strip()
    if not cell:
        return out

    obj = _safe_json_load(cell)

    # ADK-style object: { "parts": [...], "role": "user|model" }
    if isinstance(obj, dict) and "parts" in obj:
        out.extend(_extract_text_snippets_from_parts_obj(obj.get("parts") or []))
        return out

    # Already structured (dict/list) – maybe a raw envelope
    if isinstance(obj, (dict, list)):
        out.append(cell)
        return out

    # Plain string
    out.append(cell)
    return out


# ---------------------------------------------------------------------------
# Inner ChatEnvelope parsing
# ---------------------------------------------------------------------------

def _unwrap_envelope(s: str) -> Dict[str, Any]:
    """
    Try to parse a ChatEnvelope from a string that may be fenced or plain JSON.
    """
    cleaned = _strip_fences(s)
    obj = _safe_json_load(cleaned)
    return obj if isinstance(obj, dict) else {}


def _extract_user_bot_from_snippet(s: str) -> Tuple[str, str]:
    """
    Given one snippet (usually parts[*].text), try to extract:

      user_query, bot_response

    from the inner ChatEnvelope:

      {
        "message": {
          "user_query": "...",
          "bot_response": "..."
        },
        ...
      }
    """
    env = _unwrap_envelope(s)
    if not env:
        return "", ""
    msg = env.get("message") or {}
    uq = msg.get("user_query") or ""
    br = msg.get("bot_response") or ""
    return (
        uq.strip() if isinstance(uq, str) else "",
        br.strip() if isinstance(br, str) else "",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_pairs_from_events(rows: List[dict]) -> List[Dict[str, Any]]:
    """
    Input rows (from master/events DB):
        [{"timestamp": "...", "author": "...", "content": "..."}]

    Output conversation (chronological, normalized):

        [
          {"at": float_ts, "author": "user",              "text": "..."},
          {"at": float_ts, "author": "OrchestratorAgent", "text": "..."},
          ...
        ]

    Rules:
      - For *every* event, for each envelope we find:
          * If envelope.message.user_query → add a 'user' row.
          * If envelope.message.bot_response → add an 'OrchestratorAgent' row.
      - Outer author is only used to decide whether we should trust the
        bot_response (we require author in BOT_AUTHORS).
      - If there is no envelope at all, we fall back to small plain text.
    """
    out: List[Dict[str, Any]] = []

    for r in rows:
        raw_author = (r.get("author") or "").strip()
        ts = _parse_timestamp(r.get("timestamp"))
        snippets = _extract_texts_from_content(r.get("content") or "")

        is_bot_event = raw_author in BOT_AUTHORS
        is_user_event = raw_author == "user"

        for snip in snippets:
            uq, br = _extract_user_bot_from_snippet(snip)

            # --- user side ---
            if uq:
                # We *always* trust user_query as something the user said.
                out.append(
                    {
                        "at": ts,
                        "author": "user",
                        "text": uq,
                    }
                )
            elif is_user_event and _candidate_plain_text(snip):
                # Fallback: plain text user message
                out.append(
                    {
                        "at": ts,
                        "author": "user",
                        "text": snip.strip(),
                    }
                )

            # --- bot side ---
            if br and is_bot_event:
                out.append(
                    {
                        "at": ts,
                        "author": "OrchestratorAgent",
                        "text": br,
                    }
                )
            elif is_bot_event and not br and _candidate_plain_text(snip):
                # Rare fallback: plain text bot message without envelope
                out.append(
                    {
                        "at": ts,
                        "author": "OrchestratorAgent",
                        "text": snip.strip(),
                    }
                )

    # Keep chronological ordering (stable sort keeps insertion order for same ts)
    out.sort(key=lambda r: r["at"])
    return out
