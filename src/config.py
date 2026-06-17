"""
Marwa Chatbot — Configuration

All environment variable reads in one place. Sensible defaults for development;
required values fail with clear error messages when accessed.
"""

import os
import logging

logger = logging.getLogger("marwa-chatbot.config")

# ── Supabase ──────────────────────────────────────────────────────────
# Project: marwaautorepair (gzozhaofzbfdlzysercx)
SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    "https://gzozhaofzbfdlzysercx.supabase.co",
)
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# ── Ollama (local LLM) ────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.6:latest")

# ── Telegram ───────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")

# ── Shop Owner ─────────────────────────────────────────────────────────
SHOP_OWNER_ID = os.getenv("SHOP_OWNER_ID", "")

# ── CORS ───────────────────────────────────────────────────────────────
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:3000",
)

# ── Admin API Key ──────────────────────────────────────────────────────
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")

# ── Shop Info (overrideable via env) ───────────────────────────────────
SHOP_PHONE = os.getenv("SHOP_PHONE", "(555) 123-4567")
SHOP_ADDRESS = os.getenv("SHOP_ADDRESS", "123 Mechanic Lane, Saskatoon")
SHOP_NAME = os.getenv("SHOP_NAME", "Marwa Auto Repairs")


def check_required() -> list[str]:
    """Return list of missing required config vars. Empty list = all good."""
    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_SERVICE_ROLE_KEY:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if not SHOP_OWNER_ID:
        missing.append("SHOP_OWNER_ID")
    return missing
