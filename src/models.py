"""
Marwa Chatbot — Pydantic Models & Enums

Request/response schemas and the Intent enumeration used across all modules.
"""

from typing import Optional, Dict, Any, List
from enum import Enum

from pydantic import BaseModel, Field


# ── Intent ─────────────────────────────────────────────────────────────

class Intent(str, Enum):
    BOOK = "book_appointment"
    CHECK_STATUS = "check_status"
    RESCHEDULE = "reschedule"
    CANCEL = "cancel"
    ASK_QUESTION = "ask_question"
    GREETING = "greeting"
    UNKNOWN = "unknown"


# ── Classification ────────────────────────────────────────────────────

class IntentResult(BaseModel):
    intent: Intent
    confidence: float = 0.0
    entities: Dict[str, Any] = Field(default_factory=dict)
    raw_response: str = ""


# ── Chat ──────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    customer_id: Optional[str] = None
    telegram_id: Optional[str] = None
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str
    intent: Intent
    action_taken: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


# ── Scheduling ────────────────────────────────────────────────────────

class AvailableSlot(BaseModel):
    time: str  # HH:MM
    available: bool


class BookingRequest(BaseModel):
    customer_name: str
    customer_phone: str
    customer_email: Optional[str] = None
    vehicle_year: Optional[str] = None
    vehicle_make: Optional[str] = None
    vehicle_model: Optional[str] = None
    service_type: str
    preferred_date: str  # YYYY-MM-DD
    preferred_time: Optional[str] = None  # HH:MM or "morning"/"afternoon"
    notes: Optional[str] = None
    telegram_id: Optional[str] = None


class BookingResult(BaseModel):
    success: bool
    appointment_id: Optional[str] = None
    work_order_id: Optional[str] = None
    scheduled_date: Optional[str] = None
    scheduled_time: Optional[str] = None
    message: str
