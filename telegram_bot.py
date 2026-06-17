#!/usr/bin/env python3
"""
Marwa Chatbot — Telegram Bot Runner (Polling Mode)

Uses python-telegram-bot for polling-based Telegram integration.
Run this if you don't want to set up a webhook (no public URL needed).

Usage:
    TELEGRAM_BOT_TOKEN="your_token" SHOP_OWNER_ID="uuid" python telegram_bot.py

The bot uses the same intent classification, scheduling engine, and
handlers as the FastAPI service, imported from the src/ package.
"""

import os
import sys
import logging

# Ensure src/ is on the path when run directly
sys.path.insert(0, os.path.dirname(__file__))

from src.config import (
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
    TELEGRAM_BOT_TOKEN,
    SHOP_OWNER_ID,
)
from src.db import init_supabase_admin
from src.classifier import classify_intent
from src.handlers import (
    handle_booking_intent,
    handle_status_check,
    handle_reschedule_intent,
    handle_cancel_intent,
    handle_question,
)
from src.knowledge import (
    HOURS_MARKDOWN,
    PRICING_MESSAGE,
    GREETING_MESSAGE_TELEGRAM,
)

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("marwa-telegram-bot")

# ── Initialize Supabase ────────────────────────────────────────────────
if SUPABASE_SERVICE_ROLE_KEY:
    init_supabase_admin()
    logger.info("Supabase admin client initialized")
else:
    logger.warning(
        "SUPABASE_SERVICE_ROLE_KEY not set — admin operations will fail"
    )

OWNER_ID = os.getenv("SHOP_OWNER_ID", SHOP_OWNER_ID)


# ── Command Handlers ──────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message on /start."""
    user = update.effective_user
    await update.message.reply_text(
        f"Hello {user.first_name}! 👋 I'm the Marwa Auto Repairs "
        f"assistant.\n\n"
        f"I can help you:\n"
        f"• Book an appointment — just tell me what service and vehicle\n"
        f"  (e.g., \"I need an oil change for my 2020 Honda Civic\")\n"
        f"• Check your appointment status — "
        f"\"What's my appointment status?\"\n"
        f"• Reschedule or cancel — \"I need to reschedule\"\n"
        f"• Ask about services, pricing, or hours\n\n"
        f"What can I do for you today?"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help message on /help."""
    await update.message.reply_text(
        "📋 *Marwa Auto Repairs — Chatbot Help*\n\n"
        "*Booking:* Just tell me what you need!\n"
        "• \"I need an oil change tomorrow morning\"\n"
        "• \"Brake repair for my 2019 Ford F-150 on Friday\"\n\n"
        "*Checking:* \n"
        "• \"What's my appointment status?\"\n"
        "• \"Is my car ready?\"\n\n"
        "*Changing:* \n"
        "• \"Reschedule my appointment to Monday\"\n"
        "• \"Cancel my appointment\"\n\n"
        "*Commands:*\n"
        "/start — Welcome message\n"
        "/help — This help\n"
        "/status — Check your appointments\n"
        "/hours — Shop hours\n"
        "/pricing — Service pricing\n"
        "/cancel — Cancel an appointment",
        parse_mode="Markdown",
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check appointment status via /status command."""
    chat_id = str(update.effective_chat.id)
    response = await handle_status_check(chat_id, "", "", OWNER_ID)
    await update.message.reply_text(response.reply)


async def hours_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show shop hours."""
    await update.message.reply_text(
        HOURS_MARKDOWN, parse_mode="Markdown"
    )


async def pricing_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Show pricing."""
    await update.message.reply_text(
        f"💰 *Service Pricing*\n\n{PRICING_MESSAGE}",
        parse_mode="Markdown",
    )


async def cancel_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Cancel an appointment via /cancel."""
    chat_id = str(update.effective_chat.id)
    response = await handle_cancel_intent(chat_id, "", OWNER_ID)
    await update.message.reply_text(response.reply)


# ── Message Handler ───────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process all non-command messages."""
    text = update.message.text.strip()
    chat_id = str(update.effective_chat.id)
    user_name = update.effective_user.first_name

    # Classify intent
    intent_result = await classify_intent(text)

    logger.info(
        f"Intent: {intent_result.intent.value} "
        f"(confidence: {intent_result.confidence:.2f}) "
        f"— \"{text[:80]}\""
    )

    # Route
    if intent_result.intent.value == "greeting":
        await update.message.reply_text(
            GREETING_MESSAGE_TELEGRAM.format(name=user_name)
        )

    elif intent_result.intent.value == "book_appointment":
        entities = intent_result.entities
        response = await handle_booking_intent(
            chat_id, user_name, text, entities, OWNER_ID
        )
        await update.message.reply_text(response.reply)

    elif intent_result.intent.value == "check_status":
        response = await handle_status_check(
            chat_id, user_name, text, OWNER_ID
        )
        await update.message.reply_text(response.reply)

    elif intent_result.intent.value == "reschedule":
        response = await handle_reschedule_intent(
            chat_id, text, OWNER_ID
        )
        await update.message.reply_text(response.reply)

    elif intent_result.intent.value == "cancel":
        response = await handle_cancel_intent(chat_id, text, OWNER_ID)
        await update.message.reply_text(response.reply)

    elif intent_result.intent.value == "ask_question":
        response = await handle_question(text)
        await update.message.reply_text(response.reply)

    else:
        await update.message.reply_text(
            "I'm not sure what you need. Try:\n"
            "• \"I need an oil change for my Honda Civic\"\n"
            "• \"Check my appointment status\"\n"
            "• \"What are your hours?\"\n\n"
            "Or type /help for more options."
        )


# ── Main ──────────────────────────────────────────────────────────────

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN)
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        sys.exit(1)

    if not OWNER_ID:
        logger.error("SHOP_OWNER_ID not set!")
        sys.exit(1)

    app = Application.builder().token(token).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("hours", hours_command))
    app.add_handler(CommandHandler("pricing", pricing_command))
    app.add_handler(CommandHandler("cancel", cancel_command))

    # Messages
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    logger.info("Starting Marwa Telegram Bot (polling mode)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
