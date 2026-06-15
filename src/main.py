# Marwa Chatbot — Intelligent Appointment & Scheduling Assistant
#
# FastAPI service that powers the Telegram bot + web widget for
# Marwa Auto Repairs. Handles conversational booking, status checks,
# rescheduling, cancellations, and automated reminders.
#
# Architecture:
#   Customer (Telegram / Web Widget)
#       │
#       ▼
#   FastAPI Service (this file)
#       ├── Intent Classifier (Ollama LLM)
#       ├── Slot Filling Engine
#       ├── Scheduling Engine (conflict detection, slot availability)
#       └── Reminder Engine (cron-triggered)
#       │
#       ▼
#   Supabase (marwa-shop project: icffarzfmegvhhpecoyr)

import os
import sys
import json
import logging
import re
from datetime import date, time, datetime, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from supabase import create_client, Client

# ── Config ──────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://icffarzfmegvhhpecoyr.supabase.co")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "sb_publishable_030nwMaLSosXW0B8nRlUMQ_xye82rNV")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://redveil-mac.local:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.6:latest")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
SHOP_OWNER_ID = os.getenv("SHOP_OWNER_ID", "")  # auth.uid() of the shop owner

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("marwa-chatbot")

# ── Supabase Client ─────────────────────────────────────────────────
supabase: Client = None
supabase_admin: Client = None  # service_role client for admin operations


def get_supabase() -> Client:
    if supabase is None:
        raise HTTPException(500, "Supabase not initialized")
    return supabase


def get_supabase_admin() -> Client:
    if supabase_admin is None:
        raise HTTPException(500, "Supabase admin client not initialized (SERVICE_ROLE_KEY missing)")
    return supabase_admin


# ── Models ──────────────────────────────────────────────────────────

class Intent(str, Enum):
    BOOK = "book_appointment"
    CHECK_STATUS = "check_status"
    RESCHEDULE = "reschedule"
    CANCEL = "cancel"
    ASK_QUESTION = "ask_question"
    GREETING = "greeting"
    UNKNOWN = "unknown"


class IntentResult(BaseModel):
    intent: Intent
    confidence: float = 0.0
    entities: Dict[str, Any] = Field(default_factory=dict)
    raw_response: str = ""


class ChatRequest(BaseModel):
    message: str
    customer_id: Optional[str] = None  # Supabase customer UUID if known
    telegram_id: Optional[str] = None  # Telegram chat_id
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str
    intent: Intent
    action_taken: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


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


# ── Intent Classification ───────────────────────────────────────────

INTENT_PROMPT = """You are an intent classifier for an auto repair shop chatbot.
Analyze the customer message and output ONLY a JSON object with this exact structure:
{"intent": "<intent_name>", "confidence": <0.0-1.0>, "entities": {}}

Intents:
- book_appointment: Customer wants to schedule a service/repair
- check_status: Customer asks about their appointment or car status
- reschedule: Customer wants to change their appointment time
- cancel: Customer wants to cancel their appointment
- ask_question: Customer asks about services, pricing, hours, etc.
- greeting: Just saying hello, no action needed
- unknown: Cannot determine intent

For book_appointment, extract entities if present:
  service_type: oil change, brake repair, engine diagnostics, tire services, ac repair, custom exhaust, general repair
  vehicle: year/make/model if mentioned (e.g., "2020 Honda Civic")
  preferred_date: date if mentioned (today, tomorrow, Monday, specific date)
  preferred_time: time if mentioned (morning, afternoon, 2pm, specific time)
  customer_name: if they introduce themselves
  customer_phone: if they provide a phone number

For check_status/reschedule/cancel, extract:
  customer_name: who they are
  appointment_reference: any reference number or date they mention

Message: {message}

JSON only, no other text:"""


async def classify_intent(
    message: str,
    conversation_history: List[Dict[str, str]] = None
) -> IntentResult:
    """Use Ollama to classify the customer's intent and extract entities."""
    # Build context from recent history
    context = ""
    if conversation_history:
        recent = conversation_history[-4:]  # last 4 messages
        context = "\n".join(
            f"{'Customer' if m['role'] == 'user' else 'Bot'}: {m['content']}"
            for m in recent
        )

    prompt = INTENT_PROMPT.format(message=message)
    if context:
        prompt = f"Recent conversation:\n{context}\n\n{prompt}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": 256},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("response", "").strip()

        # Extract JSON from response (Ollama sometimes wraps in markdown)
        json_match = re.search(r'\{[\s\S]*\}', raw)
        if json_match:
            parsed = json.loads(json_match.group(0))
            return IntentResult(
                intent=Intent(parsed.get("intent", "unknown")),
                confidence=parsed.get("confidence", 0.0),
                entities=parsed.get("entities", {}),
                raw_response=raw,
            )
        else:
            # Fallback: keyword-based classification
            return keyword_classify(message)

    except Exception as e:
        logger.warning(f"Ollama intent classification failed: {e}. Falling back to keyword classifier.")
        return keyword_classify(message)


def keyword_classify(message: str) -> IntentResult:
    """Fallback rule-based intent classifier when Ollama is unavailable."""
    msg = message.lower().strip()

    # CANCEL — check first (before booking, which also matches "appointment")
    if re.search(r'\b(cancel|can\'t make it|won\'t.*make|need.*cancel)\b', msg):
        return IntentResult(intent=Intent.CANCEL, confidence=0.8)

    # RESCHEDULE — check before booking
    if re.search(r'\b(reschedule|change.*(appointment|time|date)|move.*(appointment|time)|different.*(day|time))\b', msg):
        return IntentResult(intent=Intent.RESCHEDULE, confidence=0.8)

    # STATUS — check before booking
    if re.search(r'\b(status|update|check.*(appointment|car|vehicle|repair|status)|how.*(my|the).*(car|vehicle|repair|appointment|going)|is.*(my|the).*(car|ready|done|fixed))\b', msg):
        return IntentResult(intent=Intent.CHECK_STATUS, confidence=0.8)

    # GREETING — short messages that are just hellos (allow "hi there", "hello!", etc.)
    if re.search(r'^(hi|hello|hey|good morning|good afternoon|sup|yo)\b', msg) and len(msg.split()) <= 3:
        return IntentResult(intent=Intent.GREETING, confidence=0.9)

    # BOOKING patterns
    book_patterns = [
        r'\b(book|schedule|set up|make.*appointment|need.*(oil|brake|repair|service|fix|tire|ac|exhaust|diagnostic|check.*up|maintenance))\b',
        r'\b(want.*(to.*get|to.*have).*(oil|brake|repair|service|fix|tire|ac|exhaust))\b',
        r'\b(can i.*(bring|drop|come).*(car|vehicle|truck))\b',
        r'\b(i need.*(oil change|brake|repair|service|tune.up|maintenance))\b',
        r'\b(i\'d like.*(to.*(book|schedule|get|have)).*(oil|brake|repair|service))\b',
    ]
    for pattern in book_patterns:
        if re.search(pattern, msg):
            entities = {}
            # Extract service type
            service_map = {
                "oil": "oil change", "brake": "brake repair",
                "diagnostic": "engine diagnostics", "tire": "tire services",
                "ac": "ac repair", "air conditioning": "ac repair",
                "exhaust": "custom exhaust", "repair": "general repair",
                "service": "general service", "maintenance": "general service",
                "tune": "general service", "fix": "general repair",
            }
            for keyword, service in service_map.items():
                if keyword in msg:
                    entities["service_type"] = service
                    break

            # Extract vehicle
            vehicle_match = re.search(r'(\d{4})\s+([a-z]+)\s+([a-z]+)', msg)
            if vehicle_match:
                entities["vehicle"] = f"{vehicle_match.group(1)} {vehicle_match.group(2).title()} {vehicle_match.group(3).title()}"

            # Extract date hints
            if "today" in msg:
                entities["preferred_date"] = date.today().isoformat()
            elif "tomorrow" in msg:
                entities["preferred_date"] = (date.today() + timedelta(days=1)).isoformat()

            return IntentResult(intent=Intent.BOOK, confidence=0.7, entities=entities)

    # QUESTION patterns
    if re.search(r'\b(how much|price|cost|hours|open|location|address|what.*(do|is|are)|do you|can you)\b', msg):
        return IntentResult(intent=Intent.ASK_QUESTION, confidence=0.6)

    return IntentResult(intent=Intent.UNKNOWN, confidence=0.0)


# ── Scheduling Engine ───────────────────────────────────────────────

# Default business hours (overridden by settings.schedule_config)
DEFAULT_HOURS = {
    0: None,  # Sunday - closed
    1: ("08:00", "17:00"),  # Monday
    2: ("08:00", "17:00"),  # Tuesday
    3: ("08:00", "17:00"),  # Wednesday
    4: ("08:00", "17:00"),  # Thursday
    5: ("08:00", "17:00"),  # Friday
    6: ("09:00", "15:00"),  # Saturday
}

SLOT_DURATION = 60  # minutes
BUFFER_MINUTES = 15
MAX_DAILY_APPOINTMENTS = 8


async def get_schedule_config(owner_id: str) -> dict:
    """Get schedule configuration from settings, with defaults."""
    try:
        admin = get_supabase_admin()
        resp = admin.table("settings").select("schedule_config").eq("owner_id", owner_id).maybe_single().execute()
        if resp.data and resp.data.get("schedule_config"):
            return resp.data["schedule_config"]
    except Exception as e:
        logger.warning(f"Could not load schedule config: {e}")
    return {}


async def get_available_slots(check_date: date, owner_id: str) -> List[AvailableSlot]:
    """Get available time slots for a given date."""
    config = await get_schedule_config(owner_id)
    dow = check_date.weekday()  # 0=Monday, 6=Sunday

    # Get business hours for this day
    biz_hours = config.get("business_hours", {})
    day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    day_name = day_names[dow]

    day_config = biz_hours.get(day_name) or (
        {"open": DEFAULT_HOURS[dow][0], "close": DEFAULT_HOURS[dow][1]}
        if DEFAULT_HOURS[dow] else None
    )

    if day_config is None:
        return []  # Closed

    open_time = time.fromisoformat(day_config["open"])
    close_time = time.fromisoformat(day_config["close"])
    slot_duration = config.get("slot_duration_minutes", SLOT_DURATION)
    buffer = config.get("buffer_minutes", BUFFER_MINUTES)

    # Get existing appointments for this date
    admin = get_supabase_admin()
    resp = admin.table("appointments").select("scheduled_time,duration_minutes,status") \
        .eq("owner_id", owner_id) \
        .eq("scheduled_date", check_date.isoformat()) \
        .not_.in_("status", ["cancelled", "no_show"]) \
        .execute()

    existing = resp.data or []

    slots = []
    current = datetime.combine(check_date, open_time)
    end = datetime.combine(check_date, close_time)

    while current + timedelta(minutes=slot_duration) <= end:
        slot_end = current + timedelta(minutes=slot_duration)
        slot_time_str = current.time().isoformat(timespec="minutes")

        # Check conflicts
        conflict = False
        for appt in existing:
            appt_start = datetime.combine(
                check_date,
                time.fromisoformat(str(appt["scheduled_time"])[:5])
            )
            appt_end = appt_start + timedelta(minutes=appt.get("duration_minutes", 60))
            if current < appt_end and slot_end > appt_start:
                conflict = True
                break

        slots.append(AvailableSlot(time=slot_time_str, available=not conflict))
        current = slot_end + timedelta(minutes=buffer)

    return slots


async def create_booking(req: BookingRequest, owner_id: str) -> BookingResult:
    """Create a customer, vehicle, work order, and appointment in one transaction."""
    admin = get_supabase_admin()

    try:
        # 1. Find or create customer
        customer_id = None
        if req.telegram_id:
            resp = admin.table("customers").select("id").eq("telegram_id", req.telegram_id).maybe_single().execute()
            if resp.data:
                customer_id = resp.data["id"]

        if not customer_id:
            # Search by phone
            resp = admin.table("customers").select("id").eq("phone", req.customer_phone).maybe_single().execute()
            if resp.data:
                customer_id = resp.data["id"]
                # Update telegram_id if provided
                if req.telegram_id:
                    admin.table("customers").update({"telegram_id": req.telegram_id}).eq("id", customer_id).execute()

        if not customer_id:
            # Create new customer
            cust_data = {
                "owner_id": owner_id,
                "name": req.customer_name,
                "phone": req.customer_phone,
                "email": req.customer_email or "",
                "telegram_id": req.telegram_id,
            }
            resp = admin.table("customers").insert(cust_data).execute()
            customer_id = resp.data[0]["id"]
            logger.info(f"Created new customer: {customer_id} ({req.customer_name})")

        # 2. Find or create vehicle
        vehicle_id = None
        if req.vehicle_make:
            resp = admin.table("vehicles").select("id").eq("customer_id", customer_id) \
                .eq("make", req.vehicle_make).eq("model", req.vehicle_model or "") \
                .maybe_single().execute()
            if resp.data:
                vehicle_id = resp.data["id"]

        if not vehicle_id and req.vehicle_make:
            veh_data = {
                "owner_id": owner_id,
                "customer_id": customer_id,
                "year": req.vehicle_year or "",
                "make": req.vehicle_make,
                "model": req.vehicle_model or "",
            }
            resp = admin.table("vehicles").insert(veh_data).execute()
            vehicle_id = resp.data[0]["id"]
            logger.info(f"Created new vehicle: {vehicle_id}")

        # 3. Create work order (Intake status)
        wo_number = f"WO-{datetime.now().strftime('%y%m%d')}-{datetime.now().strftime('%H%M%S')}"
        wo_data = {
            "owner_id": owner_id,
            "number": wo_number,
            "customer_id": customer_id,
            "vehicle_id": vehicle_id,
            "status": "Intake",
            "date": date.today().isoformat(),
            "issues": [{"category": req.service_type, "description": req.notes or ""}],
            "assigned_tech": "Unassigned",
            "priority": "Standard",
        }
        resp = admin.table("work_orders").insert(wo_data).execute()
        work_order_id = resp.data[0]["id"]
        logger.info(f"Created work order: {work_order_id} ({wo_number})")

        # 4. Parse preferred time
        scheduled_time = req.preferred_time or "09:00"
        if scheduled_time in ("morning", "am"):
            scheduled_time = "09:00"
        elif scheduled_time in ("afternoon", "pm"):
            scheduled_time = "13:00"

        # 5. Create appointment
        appt_data = {
            "owner_id": owner_id,
            "work_order_id": work_order_id,
            "customer_id": customer_id,
            "scheduled_date": req.preferred_date,
            "scheduled_time": scheduled_time,
            "duration_minutes": 60,
            "status": "scheduled",
            "notes": req.notes,
        }
        resp = admin.table("appointments").insert(appt_data).execute()
        appointment_id = resp.data[0]["id"]
        logger.info(f"Created appointment: {appointment_id}")

        # 6. Link appointment to work order
        admin.table("work_orders").update({"appointment_id": appointment_id}).eq("id", work_order_id).execute()

        return BookingResult(
            success=True,
            appointment_id=appointment_id,
            work_order_id=work_order_id,
            scheduled_date=req.preferred_date,
            scheduled_time=scheduled_time,
            message=f"Appointment booked! {req.service_type.title()} on {req.preferred_date} at {scheduled_time}. Your work order is {wo_number}.",
        )

    except Exception as e:
        logger.error(f"Booking failed: {e}")
        return BookingResult(success=False, message=f"Sorry, I couldn't complete your booking. Please call the shop directly. Error: {str(e)}")


async def get_customer_appointments(customer_identifier: str, owner_id: str) -> List[dict]:
    """Get appointments for a customer by name, phone, or telegram_id."""
    admin = get_supabase_admin()

    # Try telegram_id first, then phone, then name
    resp = admin.table("customers").select("id").or_(
        f"telegram_id.eq.{customer_identifier},phone.eq.{customer_identifier},name.ilike.%{customer_identifier}%"
    ).execute()

    if not resp.data:
        return []

    customer_ids = [c["id"] for c in resp.data]

    resp = admin.table("appointments").select(
        "id,scheduled_date,scheduled_time,status,duration_minutes,notes,work_order_id,"
        "work_orders(number,status,issues),customers(name,phone)"
    ).eq("owner_id", owner_id).in_("customer_id", customer_ids) \
        .order("scheduled_date", desc=True).limit(5).execute()

    return resp.data or []


async def reschedule_appointment(appointment_id: str, new_date: str, new_time: str, owner_id: str) -> dict:
    """Reschedule an existing appointment."""
    admin = get_supabase_admin()
    resp = admin.table("appointments").update({
        "scheduled_date": new_date,
        "scheduled_time": new_time,
        "status": "scheduled",
        "reminder_24h_sent": False,
        "reminder_1h_sent": False,
    }).eq("id", appointment_id).eq("owner_id", owner_id).execute()
    return resp.data[0] if resp.data else None


async def cancel_appointment(appointment_id: str, owner_id: str) -> dict:
    """Cancel an appointment."""
    admin = get_supabase_admin()
    resp = admin.table("appointments").update({
        "status": "cancelled"
    }).eq("id", appointment_id).eq("owner_id", owner_id).execute()
    return resp.data[0] if resp.data else None


# ── Reminder Engine ─────────────────────────────────────────────────

async def send_reminders(owner_id: str, channel: str = "telegram") -> dict:
    """Send reminders for upcoming appointments. Called by cron job."""
    admin = get_supabase_admin()
    now = datetime.now()
    today = now.date()
    tomorrow = today + timedelta(days=1)

    results = {"24h_sent": 0, "1h_sent": 0, "errors": 0}

    # 24h reminders: appointments tomorrow that haven't been reminded
    resp = admin.table("appointments").select(
        "id,customer_id,scheduled_date,scheduled_time,status,"
        "customers(name,phone,telegram_id),work_orders(number,issues)"
    ).eq("owner_id", owner_id) \
        .eq("scheduled_date", tomorrow.isoformat()) \
        .eq("reminder_24h_sent", False) \
        .not_.in_("status", ["cancelled", "no_show", "completed"]) \
        .execute()

    for appt in (resp.data or []):
        try:
            customer = appt.get("customers", {}) or {}
            wo = appt.get("work_orders", {}) or {}
            service = (wo.get("issues") or [{}])[0].get("category", "service") if wo.get("issues") else "service"

            message = (
                f"🔧 Reminder: Your {service} appointment at Marwa Auto Repairs "
                f"is tomorrow ({tomorrow.isoformat()}) at {appt['scheduled_time']}.\n"
                f"Work Order: {wo.get('number', 'N/A')}\n"
                f"Need to reschedule? Just reply to this message."
            )

            if channel == "telegram" and customer.get("telegram_id"):
                await send_telegram_message(customer["telegram_id"], message)

            # Log reminder
            admin.table("reminder_log").insert({
                "owner_id": owner_id,
                "appointment_id": appt["id"],
                "customer_id": appt["customer_id"],
                "channel": channel,
                "reminder_type": "24h",
                "message_text": message,
                "status": "sent",
            }).execute()

            # Mark as sent
            admin.table("appointments").update({"reminder_24h_sent": True}).eq("id", appt["id"]).execute()
            results["24h_sent"] += 1
            logger.info(f"24h reminder sent for appointment {appt['id']}")

        except Exception as e:
            logger.error(f"Failed to send 24h reminder for {appt['id']}: {e}")
            results["errors"] += 1

    # 1h reminders: appointments today starting within 60-90 minutes
    resp = admin.table("appointments").select(
        "id,customer_id,scheduled_date,scheduled_time,status,"
        "customers(name,phone,telegram_id),work_orders(number,issues)"
    ).eq("owner_id", owner_id) \
        .eq("scheduled_date", today.isoformat()) \
        .eq("reminder_1h_sent", False) \
        .not_.in_("status", ["cancelled", "no_show", "completed"]) \
        .execute()

    for appt in (resp.data or []):
        try:
            appt_time = time.fromisoformat(str(appt["scheduled_time"])[:5])
            appt_dt = datetime.combine(today, appt_time)
            time_until = (appt_dt - now).total_seconds() / 60

            # Send if appointment is 45-90 minutes away
            if 45 <= time_until <= 90:
                customer = appt.get("customers", {}) or {}
                wo = appt.get("work_orders", {}) or {}
                service = (wo.get("issues") or [{}])[0].get("category", "service") if wo.get("issues") else "service"

                message = (
                    f"⏰ Your {service} appointment at Marwa Auto Repairs "
                    f"is in about 1 hour ({appt['scheduled_time']}).\n"
                    f"Work Order: {wo.get('number', 'N/A')}\n"
                    f"We're at 123 Mechanic Lane. See you soon!"
                )

                if channel == "telegram" and customer.get("telegram_id"):
                    await send_telegram_message(customer["telegram_id"], message)

                admin.table("reminder_log").insert({
                    "owner_id": owner_id,
                    "appointment_id": appt["id"],
                    "customer_id": appt["customer_id"],
                    "channel": channel,
                    "reminder_type": "1h",
                    "message_text": message,
                    "status": "sent",
                }).execute()

                admin.table("appointments").update({"reminder_1h_sent": True}).eq("id", appt["id"]).execute()
                results["1h_sent"] += 1
                logger.info(f"1h reminder sent for appointment {appt['id']}")

        except Exception as e:
            logger.error(f"Failed to send 1h reminder for {appt['id']}: {e}")
            results["errors"] += 1

    return results


# ── Telegram Integration ─────────────────────────────────────────────

async def send_telegram_message(chat_id: str, text: str) -> bool:
    """Send a message via Telegram Bot API."""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set, cannot send Telegram message")
        return False

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            )
            resp.raise_for_status()
            return True
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        return False


async def process_telegram_webhook(update: dict, owner_id: str) -> ChatResponse:
    """Process an incoming Telegram message and return a response."""
    message = update.get("message", {})
    text = message.get("text", "").strip()
    chat_id = str(message.get("chat", {}).get("id", ""))
    user_first_name = message.get("from", {}).get("first_name", "")

    if not text:
        return ChatResponse(reply="I didn't catch that. How can I help with your vehicle?", intent=Intent.UNKNOWN)

    # Classify intent
    intent_result = await classify_intent(text)

    # Route to handler
    if intent_result.intent == Intent.GREETING:
        reply = (
            f"Hello {user_first_name}! 👋 I'm the Marwa Auto Repairs assistant.\n"
            f"I can help you:\n"
            f"• Book an appointment (e.g., \"I need an oil change for my 2020 Honda Civic\")\n"
            f"• Check your appointment status\n"
            f"• Reschedule or cancel\n"
            f"• Answer questions about our services\n\n"
            f"What can I do for you today?"
        )
        return ChatResponse(reply=reply, intent=Intent.GREETING)

    elif intent_result.intent == Intent.BOOK:
        entities = intent_result.entities
        return await handle_booking_intent(chat_id, user_first_name, text, entities, owner_id)

    elif intent_result.intent == Intent.CHECK_STATUS:
        return await handle_status_check(chat_id, user_first_name, text, owner_id)

    elif intent_result.intent == Intent.RESCHEDULE:
        return await handle_reschedule_intent(chat_id, text, owner_id)

    elif intent_result.intent == Intent.CANCEL:
        return await handle_cancel_intent(chat_id, text, owner_id)

    elif intent_result.intent == Intent.ASK_QUESTION:
        return await handle_question(text)

    else:
        reply = (
            "I'm not sure what you need. I can help with:\n"
            "• Booking an appointment — just tell me what service and vehicle\n"
            "• Checking your appointment status\n"
            "• Questions about our services and pricing\n\n"
            "Try rephrasing or call the shop directly at (555) 123-4567."
        )
        return ChatResponse(reply=reply, intent=Intent.UNKNOWN)


async def handle_booking_intent(
    chat_id: str, name: str, message: str, entities: dict, owner_id: str
) -> ChatResponse:
    """Handle the booking flow — check what info we have and ask for missing pieces."""
    service = entities.get("service_type")
    vehicle = entities.get("vehicle")
    pref_date = entities.get("preferred_date")
    pref_time = entities.get("preferred_time")

    # If we have enough info, try to book
    if service and pref_date:
        # Parse date
        try:
            booking_date = date.fromisoformat(pref_date)
        except ValueError:
            booking_date = date.today() + timedelta(days=1)  # default tomorrow

        # Check availability
        slots = await get_available_slots(booking_date, owner_id)
        available = [s for s in slots if s.available]

        if not available:
            # Find next available day
            next_date = booking_date + timedelta(days=1)
            for _ in range(7):
                next_slots = await get_available_slots(next_date, owner_id)
                next_available = [s for s in next_slots if s.available]
                if next_available:
                    return ChatResponse(
                        reply=f"{booking_date.isoformat()} is fully booked. The next available day is {next_date.isoformat()} with slots at {', '.join(s.time for s in next_available[:3])}. Would you like one of those?",
                        intent=Intent.BOOK,
                        data={"available_slots": [s.model_dump() for s in next_available[:5]], "date": next_date.isoformat()},
                    )
                next_date += timedelta(days=1)

            return ChatResponse(
                reply=f"Sorry, {booking_date.isoformat()} and the next 7 days are fully booked. Please call the shop at (555) 123-4567 to find a slot.",
                intent=Intent.BOOK,
            )

        # We have slots — confirm booking
        chosen_time = pref_time if pref_time and any(s.time == pref_time for s in available) else available[0].time

        # We need phone number — ask if not provided
        phone = entities.get("customer_phone")
        if not phone:
            return ChatResponse(
                reply=f"Great! I have slots available on {booking_date.isoformat()}. What's your phone number so I can book this?",
                intent=Intent.BOOK,
                data={"pending_booking": {"date": booking_date.isoformat(), "service": service, "vehicle": vehicle}},
            )

        # Create the booking
        result = await create_booking(BookingRequest(
            customer_name=name,
            customer_phone=phone,
            vehicle_make=vehicle.split()[1] if vehicle and len(vehicle.split()) >= 2 else None,
            vehicle_model=vehicle.split()[2] if vehicle and len(vehicle.split()) >= 3 else None,
            vehicle_year=vehicle.split()[0] if vehicle and vehicle.split()[0].isdigit() else None,
            service_type=service,
            preferred_date=booking_date.isoformat(),
            preferred_time=chosen_time,
            telegram_id=chat_id,
        ), owner_id)

        if result.success:
            return ChatResponse(
                reply=result.message,
                intent=Intent.BOOK,
                action_taken="booking_created",
                data=result.model_dump(),
            )
        else:
            return ChatResponse(reply=result.message, intent=Intent.BOOK)

    # Not enough info — ask for what's missing
    missing = []
    if not service:
        missing.append("what service you need")
    if not pref_date:
        missing.append("when you'd like to come in")

    questions = " and ".join(missing)
    return ChatResponse(
        reply=f"I'd love to book that for you! Could you tell me {questions}? For example: \"Oil change this Friday morning\".",
        intent=Intent.BOOK,
        data={"missing_info": missing},
    )


async def handle_status_check(chat_id: str, name: str, message: str, owner_id: str) -> ChatResponse:
    """Check appointment status for a customer."""
    # Try to find customer by telegram_id first
    appointments = await get_customer_appointments(chat_id, owner_id)

    if not appointments:
        # Try name search
        appointments = await get_customer_appointments(name, owner_id)

    if not appointments:
        return ChatResponse(
            reply="I couldn't find any appointments under your name or phone number. Can you tell me the name or phone number you used when booking?",
            intent=Intent.CHECK_STATUS,
        )

    # Format response
    lines = ["Here are your appointments:"]
    for appt in appointments[:3]:
        cust = appt.get("customers", {}) or {}
        wo = appt.get("work_orders", {}) or {}
        service = (wo.get("issues") or [{}])[0].get("category", "service") if wo.get("issues") else "service"
        status_emoji = {
            "scheduled": "📅", "confirmed": "✅", "in_progress": "🔧",
            "completed": "🏁", "cancelled": "❌", "no_show": "⚠️",
        }.get(appt["status"], "❓")

        lines.append(
            f"{status_emoji} {appt['scheduled_date']} at {appt['scheduled_time']} — "
            f"{service.title()} (WO: {wo.get('number', 'N/A')}) — Status: {appt['status'].replace('_', ' ').title()}"
        )

    return ChatResponse(
        reply="\n".join(lines),
        intent=Intent.CHECK_STATUS,
        data={"appointments": appointments},
    )


async def handle_reschedule_intent(chat_id: str, message: str, owner_id: str) -> ChatResponse:
    """Handle reschedule request."""
    appointments = await get_customer_appointments(chat_id, owner_id)

    if not appointments:
        return ChatResponse(
            reply="I need to find your appointment first. What name or phone number did you book under?",
            intent=Intent.RESCHEDULE,
        )

    active = [a for a in appointments if a["status"] in ("scheduled", "confirmed")]
    if not active:
        return ChatResponse(
            reply="You don't have any active appointments to reschedule. Would you like to book a new one?",
            intent=Intent.RESCHEDULE,
        )

    if len(active) == 1:
        appt = active[0]
        return ChatResponse(
            reply=f"Your current appointment is on {appt['scheduled_date']} at {appt['scheduled_time']}. What date and time would you prefer instead?",
            intent=Intent.RESCHEDULE,
            data={"appointment_id": appt["id"], "current_date": appt["scheduled_date"], "current_time": appt["scheduled_time"]},
        )
    else:
        lines = ["Which appointment would you like to reschedule?"]
        for i, appt in enumerate(active, 1):
            lines.append(f"{i}. {appt['scheduled_date']} at {appt['scheduled_time']} (ID: {appt['id'][:8]}...)")
        return ChatResponse(reply="\n".join(lines), intent=Intent.RESCHEDULE, data={"appointments": active})


async def handle_cancel_intent(chat_id: str, message: str, owner_id: str) -> ChatResponse:
    """Handle cancellation request."""
    appointments = await get_customer_appointments(chat_id, owner_id)

    if not appointments:
        return ChatResponse(
            reply="I need to find your appointment first. What name or phone number did you book under?",
            intent=Intent.CANCEL,
        )

    active = [a for a in appointments if a["status"] in ("scheduled", "confirmed")]
    if not active:
        return ChatResponse(
            reply="You don't have any active appointments to cancel.",
            intent=Intent.CANCEL,
        )

    if len(active) == 1:
        appt = active[0]
        result = await cancel_appointment(appt["id"], owner_id)
        if result:
            return ChatResponse(
                reply=f"Your appointment on {appt['scheduled_date']} at {appt['scheduled_time']} has been cancelled. Need to rebook? Just let me know.",
                intent=Intent.CANCEL,
                action_taken="cancelled",
            )
        else:
            return ChatResponse(reply="Sorry, I couldn't cancel that appointment. Please call the shop directly.", intent=Intent.CANCEL)
    else:
        lines = ["Which appointment would you like to cancel? Reply with the number:"]
        for i, appt in enumerate(active, 1):
            lines.append(f"{i}. {appt['scheduled_date']} at {appt['scheduled_time']}")
        return ChatResponse(reply="\n".join(lines), intent=Intent.CANCEL, data={"appointments": active})


async def handle_question(message: str) -> ChatResponse:
    """Handle general questions about the shop."""
    msg = message.lower()

    if "price" in msg or "cost" in msg or "how much" in msg:
        return ChatResponse(
            reply="Our pricing varies by service:\n"
                  "• Oil Change: from $49.99\n"
                  "• Brake Repair: from $149.99\n"
                  "• Engine Diagnostics: $89.99\n"
                  "• Tire Services: from $25/tire\n"
                  "• AC Repair: from $129.99\n"
                  "• Custom Exhaust: from $299.99\n\n"
                  "All services include a free multi-point inspection. Want to book one?",
            intent=Intent.ASK_QUESTION,
        )

    if "hour" in msg or "open" in msg or "close" in msg:
        return ChatResponse(
            reply="Our shop hours:\n"
                  "• Monday–Friday: 8:00 AM – 5:00 PM\n"
                  "• Saturday: 9:00 AM – 3:00 PM\n"
                  "• Sunday: Closed\n\n"
                  "Would you like to book an appointment?",
            intent=Intent.ASK_QUESTION,
        )

    if "location" in msg or "address" in msg or "where" in msg:
        return ChatResponse(
            reply="We're at 123 Mechanic Lane, Saskatoon. You can drop by during business hours or book an appointment here!",
            intent=Intent.ASK_QUESTION,
        )

    if "warranty" in msg:
        return ChatResponse(
            reply="All our repairs come with a 12-month/20,000 km warranty on parts and labor. We stand behind our work!",
            intent=Intent.ASK_QUESTION,
        )

    return ChatResponse(
        reply="Good question! For specific details, you can call the shop at (555) 123-4567 or I can help you book an appointment. What service are you interested in?",
        intent=Intent.ASK_QUESTION,
    )


# ── FastAPI Application ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global supabase, supabase_admin
    logger.info("Starting Marwa Chatbot service...")

    # Initialize Supabase clients
    supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

    if SUPABASE_SERVICE_ROLE_KEY:
        supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        logger.info("Supabase admin client initialized (service_role)")
    else:
        logger.warning("SUPABASE_SERVICE_ROLE_KEY not set — admin operations will fail")

    # Verify Ollama connectivity
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                logger.info(f"Ollama connected: {len(models)} models available")
            else:
                logger.warning(f"Ollama returned status {resp.status_code}")
    except Exception as e:
        logger.warning(f"Ollama not reachable at {OLLAMA_BASE_URL}: {e}. Will use keyword fallback.")

    yield

    logger.info("Shutting down Marwa Chatbot service...")


app = FastAPI(
    title="Marwa Chatbot API",
    description="Intelligent appointment scheduling chatbot for Marwa Auto Repairs",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── API Routes ──────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    ollama_ok = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            ollama_ok = resp.status_code == 200
    except Exception:
        pass

    return {
        "status": "ok",
        "supabase": supabase is not None,
        "supabase_admin": supabase_admin is not None,
        "ollama": ollama_ok,
        "telegram_configured": bool(TELEGRAM_BOT_TOKEN),
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Main chat endpoint — process a customer message and return a response."""
    if not SHOP_OWNER_ID:
        raise HTTPException(500, "SHOP_OWNER_ID not configured")

    # Classify intent
    intent_result = await classify_intent(req.message, req.conversation_history)

    # Route based on intent
    if intent_result.intent == Intent.GREETING:
        return ChatResponse(
            reply="Hello! 👋 I'm the Marwa Auto Repairs assistant. I can help you book appointments, check your vehicle status, or answer questions. What can I do for you?",
            intent=Intent.GREETING,
        )

    elif intent_result.intent == Intent.BOOK:
        entities = intent_result.entities
        name = entities.get("customer_name", "Customer")
        return await handle_booking_intent(
            req.telegram_id or "web", name, req.message, entities, SHOP_OWNER_ID
        )

    elif intent_result.intent == Intent.CHECK_STATUS:
        identifier = req.telegram_id or req.customer_id or ""
        return await handle_status_check(identifier, "", req.message, SHOP_OWNER_ID)

    elif intent_result.intent == Intent.RESCHEDULE:
        identifier = req.telegram_id or req.customer_id or ""
        return await handle_reschedule_intent(identifier, req.message, SHOP_OWNER_ID)

    elif intent_result.intent == Intent.CANCEL:
        identifier = req.telegram_id or req.customer_id or ""
        return await handle_cancel_intent(identifier, req.message, SHOP_OWNER_ID)

    elif intent_result.intent == Intent.ASK_QUESTION:
        return await handle_question(req.message)

    else:
        return ChatResponse(
            reply="I'm not sure what you need. Try saying something like \"I need an oil change for my Honda Civic\" or \"Check my appointment status\".",
            intent=Intent.UNKNOWN,
        )


@app.get("/schedule")
async def get_schedule(d: str = None, days: int = 7):
    """Get available slots for a date range."""
    if not SHOP_OWNER_ID:
        raise HTTPException(500, "SHOP_OWNER_ID not configured")

    start = date.fromisoformat(d) if d else date.today()
    result = {}

    for i in range(days):
        check_date = start + timedelta(days=i)
        slots = await get_available_slots(check_date, SHOP_OWNER_ID)
        available = [s for s in slots if s.available]
        result[check_date.isoformat()] = {
            "day_name": check_date.strftime("%A"),
            "total_slots": len(slots),
            "available_slots": len(available),
            "slots": [s.model_dump() for s in slots],
        }

    return result


@app.post("/booking", response_model=BookingResult)
async def create_booking_endpoint(req: BookingRequest):
    """Direct booking endpoint (for web widget)."""
    if not SHOP_OWNER_ID:
        raise HTTPException(500, "SHOP_OWNER_ID not configured")
    return await create_booking(req, SHOP_OWNER_ID)


@app.get("/appointments/{identifier}")
async def get_appointments(identifier: str):
    """Get appointments for a customer (by telegram_id, phone, or name)."""
    if not SHOP_OWNER_ID:
        raise HTTPException(500, "SHOP_OWNER_ID not configured")
    return await get_customer_appointments(identifier, SHOP_OWNER_ID)


@app.post("/appointments/{appointment_id}/reschedule")
async def reschedule_endpoint(appointment_id: str, new_date: str, new_time: str):
    """Reschedule an appointment."""
    if not SHOP_OWNER_ID:
        raise HTTPException(500, "SHOP_OWNER_ID not configured")
    result = await reschedule_appointment(appointment_id, new_date, new_time, SHOP_OWNER_ID)
    if not result:
        raise HTTPException(404, "Appointment not found")
    return result


@app.post("/appointments/{appointment_id}/cancel")
async def cancel_endpoint(appointment_id: str):
    """Cancel an appointment."""
    if not SHOP_OWNER_ID:
        raise HTTPException(500, "SHOP_OWNER_ID not configured")
    result = await cancel_appointment(appointment_id, SHOP_OWNER_ID)
    if not result:
        raise HTTPException(404, "Appointment not found")
    return result


@app.post("/reminders/send")
async def trigger_reminders(channel: str = "telegram"):
    """Trigger reminder sending (called by cron)."""
    if not SHOP_OWNER_ID:
        raise HTTPException(500, "SHOP_OWNER_ID not configured")
    return await send_reminders(SHOP_OWNER_ID, channel)


# ── Telegram Webhook ─────────────────────────────────────────────────

@app.post("/telegram/webhook")
async def telegram_webhook(req: Request):
    """Telegram Bot webhook endpoint."""
    if not SHOP_OWNER_ID:
        raise HTTPException(500, "SHOP_OWNER_ID not configured")

    try:
        update = await req.json()
        response = await process_telegram_webhook(update, SHOP_OWNER_ID)

        # Send reply back to Telegram
        chat_id = str(update.get("message", {}).get("chat", {}).get("id", ""))
        if chat_id and response.reply:
            await send_telegram_message(chat_id, response.reply)

        return JSONResponse({"status": "ok"})
    except Exception as e:
        logger.error(f"Telegram webhook error: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ── Main ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
