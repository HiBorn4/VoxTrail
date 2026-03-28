# schemas.py
from __future__ import annotations
import os
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator, field_validator


# ---------- Primitive blocks (always present) ----------

class Message(BaseModel):
    user_query: str = ""
    bot_response: str = ""


class TravelDetails(BaseModel):
    """
    Travel details for trip creation.
    All fields use empty string defaults for optional values.
    """
    travel_purpose: str = ""
    origin_city: str = ""
    origin_code: str = ""
    country_beg: str = ""
    destination_city: str = ""
    destination_code: str = ""
    country_end: str = ""
    start_date: str = ""
    end_date: str = ""
    start_time: str = ""
    end_time: str = ""
    journey_type: str = ""
    travel_mode: str = ""
    travel_mode_code: str = ""
    travel_class_text: str = ""
    travel_class: str = ""
    booking_method: str = ""
    booking_method_code: str = ""
    cost_center: str = ""
    project_wbs: str = ""
    travel_advance: str = ""
    additional_advance: str = ""
    reimburse_percentage: str = ""
    comment: str = ""


class FlightDetails(BaseModel):
    """
    Flight block used for BOTH directions.
    - stage: "", "flight_selection", "flight_booking", "submitted"
    - nav_preffered/nav_getsearch: provider-shaped flight dicts (lean or full)
    """
    stage: str = ""
    # Keep legacy spelling for wire format; you can still access as `flight_details.nav_preferred` in code.
    nav_preferred: Optional[List[Dict[str, Any]]] = Field(default_factory=list, alias="nav_preffered")
    nav_getsearch: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    options_ready: bool = False
    class Config:
        populate_by_name = True  # allow using the python name when constructing


class GetReimbursement(BaseModel):
    """
    Minimal client-visible state for the reimbursement flow; OCR/trip payloads live in Redis and are never carried here.

    Fields:
      stage: workflow stage: "", "request_upload", "review", "submitted", "reimbursement_submitted".
      correlation_id: optional correlation/reference string from FE or backends.
      files: upload placeholders (paths or simple dicts) used only for UI/collection; not the OCR result.
      analyze_results: deprecated (kept for backward-compat); always cleared by higher-level state enforcement.
      claim_da: DA amount to claim (string, e.g., "3000.00").
      claim_id: claim identifier returned by SAP (if available).
    """
    stage: str = Field(
        default="",
        description='Allowed: "", "request_upload", "review", "submitted", "reimbursement_submitted".',
    )
    correlation_id: str = ""
    files: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Upload placeholders only; structure: {'path': str, 'name'?: str, 'size'?: int, 'mimetype'?: str}.",
    )
    analyze_results: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Deprecated; do not use. OCR/trip data is stored in Redis.",
    )
    claim_da: str = Field(default="", description="DA amount to claim, e.g., '3000.00'.")
    claim_id: str = Field(default="", description="Claim identifier from SAP after submission, if any.")

    @field_validator("stage", mode="before")
    @classmethod
    def _normalize_stage(cls, v: Any) -> str:
        allowed = {"", "request_upload", "review", "submitted", "reimbursement_submitted"}
        return v if isinstance(v, str) and v in allowed else ""

    @field_validator("files", mode="before")
    @classmethod
    def _coerce_files(cls, v: Any) -> List[Dict[str, Any]]:
        """
        Accepts:
          - list of strings (paths)
          - list of dicts with {'path': str, ...}
          - list of objects having a `.path` attribute
          - nested lists (flattened one level)
        Returns a list of dicts with at least {'path': <normalized str>, 'name': <basename>}.
        """
        out: List[Dict[str, Any]] = []

        def _push(path: str, meta: Dict[str, Any] | None = None) -> None:
            p = str(path).replace("\\", "/")
            item: Dict[str, Any] = {"path": p}
            if isinstance(meta, dict):
                for k in ("name", "size", "mimetype"):
                    if k in meta:
                        item[k] = meta[k]
            if "name" not in item:
                item["name"] = os.path.basename(p)
            out.append(item)

        if v is None:
            return []

        items = v if isinstance(v, list) else [v]
        for it in items:
            # Flatten one level of nesting for backward compatibility
            if isinstance(it, list):
                for sub in it:
                    if isinstance(sub, str):
                        _push(sub)
                    elif isinstance(sub, dict) and isinstance(sub.get("path"), str):
                        _push(sub["path"], sub)
                    else:
                        p = getattr(sub, "path", None)
                        if isinstance(p, str):
                            _push(p)
                continue

            if isinstance(it, str):
                _push(it)
                continue

            if isinstance(it, dict) and isinstance(it.get("path"), str):
                _push(it["path"], it)
                continue

            p = getattr(it, "path", None)
            if isinstance(p, str):
                _push(p)

        return out


# ---------- Top-level envelope (ALWAYS present in request AND response) ----------

Intent = Literal["message", "flight", "reimbursement"]

class ChatEnvelope(BaseModel):
    """
    Single JSON shape for /chat/message (request + response).

    MUST always include:
      - user_token_id, session_id, trip_id, intent
      - message, flight_details, get_reimbursement, travel_details

    Notes:
      - Reimbursement OCR/trip payloads are never carried in the envelope; they live in Redis.
      - `trip_id` is treated as REINR for the reimbursement flow.
    """
    user_token_id: str = ""   # backend token from /login
    session_id: str = ""      # ADK session id
    trip_id: str = "0000000000"
    intent: Intent = "message"

    message: Message = Field(default_factory=Message)
    travel_details: TravelDetails = Field(default=[])  # ✅ ADDED
    flight_details: FlightDetails = Field(default_factory=FlightDetails)
    get_reimbursement: GetReimbursement = Field(default_factory=GetReimbursement)

    # ---------------- Invariant enforcement from the contract ----------------
    @model_validator(mode="after")
    def _enforce_contract(self) -> "ChatEnvelope":
        intent = self.intent or "message"

        # Normalize Nones to default empty values (defensive)
        if self.message is None:
            self.message = Message()
        if self.flight_details is None:
            self.flight_details = FlightDetails()
        if self.get_reimbursement is None:
            self.get_reimbursement = GetReimbursement()
        # travel_details can be None (optional)

        # Allowed stages (per intent)
        flight_allowed = {"flight_selection", "flight_booking", "submitted", ""}
        reimb_allowed = {"request_upload", "review", "submitted", "reimbursement_submitted", ""}

        if intent == "message":
            # Clear tool-specific blocks
            self.flight_details.stage = ""
            self.flight_details.nav_preferred = []   # alias field (legacy)
            self.flight_details.nav_getsearch = []
            self.get_reimbursement.stage = ""
            self.get_reimbursement.analyze_results = []
            self.get_reimbursement.files = []
            self.get_reimbursement.claim_da = ""
            self.get_reimbursement.claim_id = ""
            # travel_details persists across message intents

        elif intent == "flight":
            # Enforce flight stages
            if self.flight_details.stage not in flight_allowed:
                self.flight_details.stage = ""
            # Reset reimbursement state entirely for flight intent
            self.get_reimbursement = GetReimbursement()

            # Relaxed booking stage: nav_getsearch should be empty but don't error if present
            if self.flight_details.stage == "flight_booking" and self.flight_details.nav_getsearch:
                self.flight_details.nav_getsearch = []
            # travel_details persists in flight intent

        elif intent == "reimbursement":
            # Enforce reimbursement stages
            if self.get_reimbursement.stage not in reimb_allowed:
                self.get_reimbursement.stage = ""

            # Default entry stage if unset
            if self.get_reimbursement.stage == "":
                self.get_reimbursement.stage = "request_upload"

            # Reimbursement flow is independent of flight; clear flight state
            self.flight_details = FlightDetails()

            # Never carry OCR/trip payloads in the envelope
            self.get_reimbursement.analyze_results = []
            self.get_reimbursement.files = self.get_reimbursement.files or []
            self.get_reimbursement.claim_da = (self.get_reimbursement.claim_da or "").strip()

            # Ensure we have a REINR (trip_id) before allowing review/submitted
            reinr = (self.trip_id or "").strip()
            if self.get_reimbursement.stage in {"review", "submitted"} and not reinr:
                # Route back so agent can prompt for trip number
                self.get_reimbursement.stage = "request_upload"

            # Clear stale claim_id unless final state
            if self.get_reimbursement.stage != "reimbursement_submitted":
                self.get_reimbursement.claim_id = ""
            # travel_details can coexist with reimbursement

        else:
            # Fallback to message intent
            self.intent = "message"
            self.flight_details = FlightDetails()
            self.get_reimbursement = GetReimbursement()

        return self

    # Convenience: when sending back to FE, use legacy key aliases (e.g., nav_preffered)
    def to_wire(self) -> Dict[str, Any]:
        """Serialize using legacy key aliases (e.g., nav_preffered)."""
        return self.model_dump(by_alias=True)

# ---------- Upload API models ----------

class SavedFile(BaseModel):
    """
    Normalized server-side representation of an uploaded file.
    This is what /chat/upload/ returns and what FE can pass into
    ChatEnvelope.get_reimbursement.files (compatible with List[Dict[str, Any]]).
    """
    path: str                                   # absolute/normalized path on server
    stored_as: str                              # final filename on disk
    original_filename: str                      # client-provided name
    size: int                                   # bytes
    content_type: Optional[str] = None          # e.g., 'application/pdf', 'image/jpeg'
    sha256: Optional[str] = None                # integrity / dedup checks
    extra: Dict[str, Any] = Field(default_factory=dict)


class UploadAck(BaseModel):
    """
    JSON response schema for POST /chat/upload/.
    """
    session_id: str
    user_token_id: str
    pernr: str
    saved_files: List[SavedFile] = Field(default_factory=list)
    message: str = "Files uploaded successfully. Use these 'path' values in get_reimbursement.files for /chat/message."


# ---- (Optional) For API docs only: multipart form meta for the upload request ----
# FastAPI reads multipart form fields via function parameters (Form/File),
# not from a Pydantic body model. This class can be referenced in your docs.
class UploadRequestMeta(BaseModel):
    """
    Metadata fields expected in multipart form for /chat/upload/.
    NOTE: Files themselves are received as List[UploadFile] at the route,
    so they are *not* represented here.
    """
    session_id: str
    user_token_id: str
    # pernr: Optional[str] = None  # if you decide to send PERNR explicitly


__all__ = [
    "Message",
    "TravelDetails",
    "FlightDetails",
    "GetReimbursement",
    "ChatEnvelope",
    "SavedFile",
    "UploadAck",
    "UploadRequestMeta",
]