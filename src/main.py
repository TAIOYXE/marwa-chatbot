"""
Marwa Chatbot — FastAPI Application Factory

Thin entry point that initializes services and mounts routes.
All business logic lives in sibling modules:
  config.py   — environment variables
  db.py       — Supabase client management
  models.py   — Pydantic schemas & enums
  knowledge.py— shop info (pricing, hours, etc.)
  classifier.py— intent classification (Ollama + keyword)
  scheduling.py— slot availability, booking CRUD
  reminders.py— 24h/1h reminder engine
  telegram.py — Telegram messaging & webhook processing
  handlers.py — intent handler functions
  routes.py   — API route definitions
"""

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import (
    OLLAMA_BASE_URL,
    CORS_ORIGINS,
    check_required,
)
from .db import init_supabase, init_supabase_admin
from .routes import router

logger = logging.getLogger("marwa-chatbot")

# ── Logging ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


# ── Lifespan ──────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialize Supabase clients, verify Ollama connectivity.
    Shutdown: clean up resources."""
    logger.info("Starting Marwa Chatbot service...")

    # Check required config
    missing = check_required()
    if missing:
        logger.warning(
            f"Missing required env vars: {', '.join(missing)}. "
            f"Some features will be unavailable."
        )

    # Initialize Supabase clients
    init_supabase()
    init_supabase_admin()

    # Verify Ollama connectivity
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                logger.info(
                    f"Ollama connected: {len(models)} models available"
                )
            else:
                logger.warning(
                    f"Ollama returned status {resp.status_code}"
                )
    except Exception as e:
        logger.warning(
            f"Ollama not reachable at {OLLAMA_BASE_URL}: {e}. "
            f"Will use keyword fallback."
        )

    yield

    logger.info("Shutting down Marwa Chatbot service...")


# ── App Factory ───────────────────────────────────────────────────────

def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="Marwa Chatbot API",
        description=(
            "Intelligent appointment scheduling chatbot "
            "for Marwa Auto Repairs"
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS — origins from env var, with safe development defaults
    origins = [
        o.strip()
        for o in CORS_ORIGINS.split(",")
        if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request logging middleware
    @app.middleware("http")
    async def log_requests(request, call_next):
        import time
        import uuid

        request_id = str(uuid.uuid4())[:8]
        start = time.time()

        response = await call_next(request)

        duration_ms = (time.time() - start) * 1000
        logger.info(
            f"[{request_id}] {request.method} {request.url.path} "
            f"→ {response.status_code} ({duration_ms:.0f}ms)"
        )

        response.headers["X-Request-ID"] = request_id
        return response

    # Mount routes
    app.include_router(router)

    return app


# ── Application Instance ──────────────────────────────────────────────

app = create_app()

# ── Entry Point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
