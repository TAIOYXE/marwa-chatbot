"""
Marwa Chatbot — API Routes

All FastAPI route definitions. The routes are thin — they validate input,
check auth where needed, and delegate to handler/service functions.
"""

import logging
from datetime import date, timedelta

import httpx
from fastapi import APIRouter, Request, HTTPException, Header, Depends
from fastapi.responses import JSONResponse

from .config import (
    OLLAMA_BASE_URL,
    TELEGRAM_BOT_TOKEN,
    SHOP_OWNER_ID,
    ADMIN_API_KEY,
)
from .db import supabase, supabase_admin, is_admin_available
from .models import (
    Intent,
    ChatRequest,
    ChatResponse,
    BookingRequest,
    BookingResult,
)
from .classifier import classify_intent
from .scheduling import (
    get_available_slots,
    create_booking,
    get_customer_appointments,
    reschedule_appointment,
    cancel_appointment,
)
from .reminders import send_reminders
from .telegram import (
    send_telegram_message,
    process_telegram_webhook,
    validate_webhook_secret,
)
from .handlers import (
    handle_booking_intent,
    handle_status_check,
    handle_reschedule_intent,
    handle_cancel_intent,
    handle_question,
)
from .knowledge import GREETING_MESSAGE, UNKNOWN_MESSAGE_SHORT

logger = logging.getLogger("marwa-chatbot.routes")

router = APIRouter()


# ── Auth Helpers ──────────────────────────────────────────────────────

def _require_shop_owner():
    """Raise if SHOP_OWNER_ID is not configured."""
    if not SHOP_OWNER_ID:
        raise HTTPException(500, "SHOP_OWNER_ID not configured")


def _require_admin_key(x_api_key: str | None = Header(None)):
    """Validate admin API key if configured. Fails if key is set but
    request doesn't match. Passes if ADMIN_API_KEY is not configured
    (development mode)."""
    if ADMIN_API_KEY:
        if not x_api_key or x_api_key != ADMIN_API_KEY:
            raise HTTPException(401, "Invalid or missing admin API key")
    # If ADMIN_API_KEY is not set, allow all (development fallback)


# ── Health ────────────────────────────────────────────────────────────

@router.get("/health")
async def health_check():
    """Health check endpoint — verifies connectivity to all services."""
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


# ── Chat ──────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Main chat endpoint — process a customer message and respond."""
    _require_shop_owner()

    # Classify intent
    intent_result = await classify_intent(
        req.message, req.conversation_history
    )

    # Route based on intent
    if intent_result.intent == Intent.GREETING:
        return ChatResponse(
            reply=GREETING_MESSAGE, intent=Intent.GREETING
        )

    elif intent_result.intent == Intent.BOOK:
        entities = intent_result.entities
        name = entities.get("customer_name", "Customer")
        return await handle_booking_intent(
            req.telegram_id or "web",
            name,
            req.message,
            entities,
            SHOP_OWNER_ID,
        )

    elif intent_result.intent == Intent.CHECK_STATUS:
        identifier = req.telegram_id or req.customer_id or ""
        return await handle_status_check(
            identifier, "", req.message, SHOP_OWNER_ID
        )

    elif intent_result.intent == Intent.RESCHEDULE:
        identifier = req.telegram_id or req.customer_id or ""
        return await handle_reschedule_intent(
            identifier, req.message, SHOP_OWNER_ID
        )

    elif intent_result.intent == Intent.CANCEL:
        identifier = req.telegram_id or req.customer_id or ""
        return await handle_cancel_intent(
            identifier, req.message, SHOP_OWNER_ID
        )

    elif intent_result.intent == Intent.ASK_QUESTION:
        return await handle_question(req.message)

    else:
        return ChatResponse(
            reply=UNKNOWN_MESSAGE_SHORT, intent=Intent.UNKNOWN
        )


# ── Schedule ──────────────────────────────────────────────────────────

@router.get("/schedule")
async def get_schedule(d: str = None, days: int = 7):
    """Get available slots for a date range."""
    _require_shop_owner()

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


# ── Booking ───────────────────────────────────────────────────────────

@router.post("/booking", response_model=BookingResult)
async def create_booking_endpoint(req: BookingRequest):
    """Direct booking endpoint (for web widget)."""
    _require_shop_owner()
    return await create_booking(req, SHOP_OWNER_ID)


# ── Appointments ──────────────────────────────────────────────────────

@router.get("/appointments/{identifier}")
async def get_appointments(identifier: str):
    """Get appointments for a customer (by telegram_id, phone, or name)."""
    _require_shop_owner()
    return await get_customer_appointments(identifier, SHOP_OWNER_ID)


@router.post("/appointments/{appointment_id}/reschedule")
async def reschedule_endpoint(
    appointment_id: str, new_date: str, new_time: str
):
    """Reschedule an appointment."""
    _require_shop_owner()
    result = await reschedule_appointment(
        appointment_id, new_date, new_time, SHOP_OWNER_ID
    )
    if not result:
        raise HTTPException(404, "Appointment not found")
    return result


@router.post("/appointments/{appointment_id}/cancel")
async def cancel_endpoint(appointment_id: str):
    """Cancel an appointment."""
    _require_shop_owner()
    result = await cancel_appointment(appointment_id, SHOP_OWNER_ID)
    if not result:
        raise HTTPException(404, "Appointment not found")
    return result


# ── Reminders (Admin) ─────────────────────────────────────────────────

@router.post("/reminders/send")
async def trigger_reminders(
    channel: str = "telegram",
    x_api_key: str | None = Header(None),
):
    """Trigger reminder sending (called by cron). Requires admin API key
    if ADMIN_API_KEY is configured."""
    _require_shop_owner()
    _require_admin_key(x_api_key)
    return await send_reminders(SHOP_OWNER_ID, channel)


# ── Telegram Webhook ─────────────────────────────────────────────────

@router.post("/telegram/webhook")
async def telegram_webhook(req: Request):
    """Telegram Bot webhook endpoint."""
    _require_shop_owner()

    # Validate webhook secret if configured
    if not validate_webhook_secret(dict(req.headers)):
        raise HTTPException(403, "Invalid webhook secret token")

    try:
        update = await req.json()
        response = await process_telegram_webhook(update, SHOP_OWNER_ID)

        # Send reply back to Telegram
        chat_id = str(
            update.get("message", {}).get("chat", {}).get("id", "")
        )
        if chat_id and response.reply:
            await send_telegram_message(chat_id, response.reply)

        return JSONResponse({"status": "ok"})
    except Exception as e:
        logger.error(f"Telegram webhook error: {e}")
        return JSONResponse(
            {"status": "error", "message": str(e)}, status_code=500
        )
