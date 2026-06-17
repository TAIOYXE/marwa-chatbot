"""
Marwa Chatbot — Telegram Integration

Telegram message sending and webhook processing.
Shared by the FastAPI service and the polling bot.
"""

import logging
from typing import Dict, Any

import httpx

from .config import TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET
from .models import Intent, IntentResult, ChatResponse
from .classifier import classify_intent
from .handlers import (
    handle_booking_intent,
    handle_status_check,
    handle_reschedule_intent,
    handle_cancel_intent,
    handle_question,
)
from .knowledge import GREETING_MESSAGE_NAMED, UNKNOWN_MESSAGE

logger = logging.getLogger("marwa-chatbot.telegram")


# ── Send Message ──────────────────────────────────────────────────────

async def send_telegram_message(chat_id: str, text: str) -> bool:
    """Send a message via Telegram Bot API."""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning(
            "TELEGRAM_BOT_TOKEN not set, cannot send Telegram message"
        )
        return False

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                },
            )
            resp.raise_for_status()
            return True
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        return False


# ── Webhook Validation ────────────────────────────────────────────────

def validate_webhook_secret(headers: Dict[str, str]) -> bool:
    """Validate Telegram webhook secret token if configured."""
    if not TELEGRAM_WEBHOOK_SECRET:
        return True  # Not configured — allow all (development mode)
    token = headers.get("x-telegram-bot-api-secret-token", "")
    return token == TELEGRAM_WEBHOOK_SECRET


# ── Webhook Processing ────────────────────────────────────────────────

async def process_telegram_webhook(
    update: dict, owner_id: str
) -> ChatResponse:
    """Process an incoming Telegram message and return a response."""
    message = update.get("message", {})
    text = message.get("text", "").strip()
    chat_id = str(message.get("chat", {}).get("id", ""))
    user_first_name = message.get("from", {}).get("first_name", "")

    if not text:
        return ChatResponse(
            reply=(
                "I didn't catch that. How can I help with your vehicle?"
            ),
            intent=Intent.UNKNOWN,
        )

    # Classify intent
    intent_result = await classify_intent(text)

    # Route to handler
    if intent_result.intent == Intent.GREETING:
        reply = GREETING_MESSAGE_NAMED.format(name=user_first_name)
        return ChatResponse(reply=reply, intent=Intent.GREETING)

    elif intent_result.intent == Intent.BOOK:
        entities = intent_result.entities
        return await handle_booking_intent(
            chat_id, user_first_name, text, entities, owner_id
        )

    elif intent_result.intent == Intent.CHECK_STATUS:
        return await handle_status_check(
            chat_id, user_first_name, text, owner_id
        )

    elif intent_result.intent == Intent.RESCHEDULE:
        return await handle_reschedule_intent(chat_id, text, owner_id)

    elif intent_result.intent == Intent.CANCEL:
        return await handle_cancel_intent(chat_id, text, owner_id)

    elif intent_result.intent == Intent.ASK_QUESTION:
        return await handle_question(text)

    else:
        return ChatResponse(reply=UNKNOWN_MESSAGE, intent=Intent.UNKNOWN)
