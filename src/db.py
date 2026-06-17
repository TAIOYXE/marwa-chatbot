"""
Marwa Chatbot — Database Layer

Supabase client initialization and accessor functions.
Both the FastAPI service and Telegram bot use this module.
"""

import logging
from supabase import create_client, Client

from .config import SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY

logger = logging.getLogger("marwa-chatbot.db")

# ── Module-level client references ────────────────────────────────────
supabase: Client | None = None
supabase_admin: Client | None = None


def init_supabase() -> Client:
    """Initialize the anon-key Supabase client. Safe to call multiple times."""
    global supabase
    if supabase is None and SUPABASE_URL and SUPABASE_ANON_KEY:
        supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        logger.info("Supabase anon client initialized")
    return supabase


def init_supabase_admin() -> Client | None:
    """Initialize the service_role Supabase client. Returns None if key missing."""
    global supabase_admin
    if supabase_admin is None and SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        logger.info("Supabase admin client initialized (service_role)")
    elif not SUPABASE_SERVICE_ROLE_KEY:
        logger.warning("SUPABASE_SERVICE_ROLE_KEY not set — admin operations will fail")
    return supabase_admin


def get_supabase() -> Client:
    """Get the anon Supabase client. Raises if not initialized."""
    if supabase is None:
        raise RuntimeError("Supabase anon client not initialized")
    return supabase


def get_supabase_admin() -> Client:
    """Get the service_role Supabase client. Raises if not initialized."""
    if supabase_admin is None:
        raise RuntimeError(
            "Supabase admin client not initialized — SUPABASE_SERVICE_ROLE_KEY missing"
        )
    return supabase_admin


def is_admin_available() -> bool:
    """Check if admin client is available without raising."""
    return supabase_admin is not None
