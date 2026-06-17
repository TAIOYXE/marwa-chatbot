# PROJECT STATUS
**Project:** Marwa Chatbot — Intelligent Appointment & Scheduling Assistant
**Last Scanned:** 2026-06-16 10:30 CST
**Stack:** Python 3.10+ / FastAPI + Uvicorn / Supabase (Python client) / Ollama (qwen3.6) / python-telegram-bot / React (sibling marwa-app)
**Architecture:** Modular FastAPI service (12 source modules) + standalone Telegram polling bot; React ChatWidget in sibling `marwa-app` repo
**Overall Stage:** IN PROGRESS
**Completion Estimate:** 75% — Core logic modularized and tested (88 tests passing), Supabase mismatch fixed, CORS/auth/logging middleware added, Dockerfile + CI in place. Remaining: rate limiting, multi-turn conversation state, non-Telegram reminder channels, DB migration independence.
**Can it run right now?** NO — Requires `SUPABASE_SERVICE_ROLE_KEY`, `TELEGRAM_BOT_TOKEN`, `SHOP_OWNER_ID` env vars (all placeholder), Ollama running locally with `qwen3.6:latest`, and migration `0006_chatbot_scheduling.sql` applied to the target Supabase project. However, the service starts gracefully with missing env vars and reports status via `/health`.

---

## SUMMARY
Marwa Chatbot is an AI-powered appointment scheduling assistant for Marwa Auto Repairs. The codebase has been refactored from a single 1157-line god file into 12 focused modules under `src/` (config, db, models, knowledge, classifier, scheduling, reminders, telegram, handlers, routes, main). All critical bugs from the initial scan are fixed: Supabase URL now consistently points to `gzozhaofzbfdlzysercx` (marwaautorepair), the real anon key was removed from `.env.example`, CORS is configurable via `CORS_ORIGINS` env var, `/reminders/send` requires `X-API-Key` header, Telegram webhook validates secret token, and request logging middleware is active. 88 unit tests pass covering the classifier, knowledge base, models, and scheduling engine. A Dockerfile and GitHub Actions CI workflow are in place. The `DEFAULT_HOURS` off-by-one bug (Monday showing as closed) was discovered and fixed during test development.

---

## WHAT'S DONE
- Modular package structure: 12 focused modules under `src/` (`src/__init__.py`, `config.py`, `db.py`, `models.py`, `knowledge.py`, `classifier.py`, `scheduling.py`, `reminders.py`, `telegram.py`, `handlers.py`, `routes.py`, `main.py`)
- Configuration centralized in `src/config.py` with env var reads, sensible defaults, and `check_required()` validation
- Supabase client management in `src/db.py` — init, accessors, availability check — shared by FastAPI and Telegram bot
- All Pydantic models and Intent enum in `src/models.py`
- Shop knowledge base (pricing, hours, location, warranty, greetings, status emoji) in `src/knowledge.py` — single source of truth, configurable via env vars for phone/address
- Intent classification: Ollama LLM + keyword regex fallback in `src/classifier.py`
- Scheduling engine: slot generation, booking CRUD, reschedule, cancel in `src/scheduling.py`
- Reminder engine: 24h + 1h reminders with Telegram delivery in `src/reminders.py`
- Telegram integration: message sending, webhook validation, webhook processing in `src/telegram.py`
- Intent handlers: booking flow, status check, reschedule, cancel, questions in `src/handlers.py` — shared by routes and Telegram bot
- API routes: all 9 endpoints with auth guards in `src/routes.py`
- Thin app factory: lifespan, CORS, logging middleware, route mounting in `src/main.py` (~80 lines)
- CORS origins from `CORS_ORIGINS` env var (default: `http://localhost:5173,http://localhost:3000`) — `src/main.py:88-95`
- Admin API key auth on `/reminders/send` via `X-API-Key` header — `src/routes.py:44-50`
- Request logging middleware with UUID request ID, method, path, status, duration — `src/main.py:97-109`
- Telegram webhook secret token validation — `src/telegram.py:48-52`, `src/routes.py:195-196`
- `DEFAULT_HOURS` off-by-one bug fixed — keys now correctly match `date.weekday()` (0=Monday) — `src/scheduling.py:30-38`
- Supabase URL mismatch fixed — all references now consistently point to `gzozhaofzbfdlzysercx` (marwaautorepair) — `src/config.py:16-18`
- Real Supabase anon key removed from `.env.example` — replaced with placeholder
- New env vars documented: `CORS_ORIGINS`, `ADMIN_API_KEY`, `TELEGRAM_WEBHOOK_SECRET` — `.env.example:25-33`
- `telegram_bot.py` refactored: imports from `src.*` modules, no dead imports, no duplicated knowledge base strings, uses shared handlers — `telegram_bot.py:22-40`
- 88 unit tests passing: classifier (42), knowledge (17), models (17), scheduling (12) — `tests/`
- Dockerfile: multi-stage Python 3.12-slim, non-root user, health check — `Dockerfile`
- CI workflow: pytest on Python 3.10/3.11/3.12 + Docker build — `.github/workflows/test.yml`
- React ChatWidget in sibling marwa-app (unchanged) — `marwa-app/src/ChatWidget.jsx`
- Database migration in sibling marwa-app (unchanged) — `marwa-app/supabase/migrations/0006_chatbot_scheduling.sql`

---

## IN PROGRESS
- **Slot filling conversation flow**: The booking handler asks for missing info but multi-turn state is not persisted — each request is stateless. `src/handlers.py:30-140` shows the logic; missing a session/state mechanism.
- **Reminder cron integration**: Reminder logic exists and the `/reminders/send` endpoint is wired with auth, but the README references "OpenClaw cron jobs" that are external. The `scripts/` directory is empty.

---

## NOT STARTED
- **Rate limiting**: No rate limiting on any endpoint.
- **Input sanitization**: No sanitization of user input beyond Pydantic type coercion.
- **SMS/Email/WhatsApp reminder channels**: Reminder engine and `reminder_log` schema support multiple channels, but only Telegram is implemented (`src/reminders.py:55-56`, `src/reminders.py:107-108`).
- **Conversation session persistence**: Multi-turn booking state is lost between requests.
- **DB migration independence**: The migration lives in sibling `marwa-app/supabase/migrations/`. This repo has no way to apply it independently.
- **`scripts/` directory**: Exists but is empty.
- **Scheduling Postgres function usage**: The migration defines `get_available_slots()` and `get_schedule()` as DB functions, but Python implements its own slot calculation. The DB functions are unused by the service.

---

## BUGS & BROKEN
| Severity | Issue | Location | Fix Direction |
|----------|-------|----------|---------------|
| MEDIUM | `get_schedule_config()` queries `settings` table by `owner_id` — assumes the `settings` table exists with that column. If absent, fails at runtime. | `src/scheduling.py:44-56` | Verify the `settings` table schema in the target Supabase project, or add a migration that creates it if absent. |
| LOW | `reschedule_appointment` and `cancel_appointment` return `None` when no row updated; endpoint treats both "not found" and "wrong owner" as 404 instead of distinguishing 403. | `src/scheduling.py:218-240`, `src/routes.py:170-186` | Check `resp.data` explicitly; return 403 when row exists but owner mismatch. |
| LOW | `/appointments/{id}/reschedule` accepts `new_date` and `new_time` as query parameters (non-standard for POST). | `src/routes.py:165` | Change to accept a Pydantic request body model. |

---

## SECURITY FLAGS
| Severity | Issue | Location | Fix Direction |
|----------|-------|----------|---------------|
| MEDIUM | `/booking` endpoint has no authentication — anonymous web widget bookings are intentional per the migration's anon insert policy, but there's no abuse prevention (rate limiting, CAPTCHA). | `src/routes.py:148-152` | Add rate limiting per IP or a lightweight proof-of-work. |
| LOW | No HTTPS enforcement — the service binds to `0.0.0.0:8000` with plain HTTP. In production this should be behind a reverse proxy with TLS termination. | `src/main.py:119` | Document the need for a reverse proxy (nginx/Caddy) in README. |

**Previously flagged — now resolved:**
- ~~Real Supabase anon key in `.env.example`~~ → Replaced with placeholder
- ~~CORS allows all origins~~ → Now reads `CORS_ORIGINS` env var
- ~~`/reminders/send` no auth~~ → Requires `X-API-Key` header (when `ADMIN_API_KEY` is set)
- ~~Hardcoded Supabase anon key in `main.py`~~ → Removed; reads from env only
- ~~Telegram webhook no secret token~~ → Validates `X-Telegram-Bot-Api-Secret-Token` header
- ~~Supabase URL mismatch~~ → All references now consistently `gzozhaofzbfdlzysercx`

---

## TECH DEBT & SMELLS
- **Duplicate slot calculation**: The migration defines `get_available_slots()` as a Postgres function (`0006_chatbot_scheduling.sql:143-226`) but Python reimplements it in-app (`src/scheduling.py:60-115`). The DB function is never called.
- **No database migration in this repo**: The migration lives in sibling `marwa-app/supabase/migrations/`. This repo has no independent migration mechanism.
- **No type hints on some functions**: `get_customer_appointments` returns `List[dict]`, `reschedule_appointment`/`cancel_appointment` return `dict | None`.
- **`telegram_bot.py` duplicates intent routing**: The message handler mirrors the routing in `src/routes.py` and `src/telegram.py`. Could be further DRYed by having the bot call the service via HTTP or use `process_telegram_webhook`.

**Previously flagged — now resolved:**
- ~~God file (1157-line `main.py`)~~ → Split into 12 modules
- ~~Duplicate knowledge base~~ → Centralized in `src/knowledge.py`
- ~~Hardcoded phone/address~~ → Configurable via `SHOP_PHONE`/`SHOP_ADDRESS` env vars
- ~~No request logging middleware~~ → Added with UUID request IDs
- ~~`telegram_bot.py` dead imports~~ → Cleaned up
- ~~`DEFAULT_HOURS` off-by-one (Monday=closed)~~ → Fixed

---

## BLOCKERS
1. **Missing `SUPABASE_SERVICE_ROLE_KEY`**: All admin operations (booking, scheduling, reminders) require this key. Without it, the service starts but admin operations fail with clear error messages.
2. **Ollama dependency**: Intent classification requires Ollama running locally with `qwen3.6:latest` model. Without it, the system falls back to keyword classification — functional but degraded.
3. **Database migration**: Migration `0006_chatbot_scheduling.sql` must be applied to the `gzozhaofzbfdlzysercx` Supabase project before the service can operate.

---

## NEXT ACTIONS (Priority Order)
1. **Add rate limiting** — At minimum on `/booking` and `/chat` endpoints. Use slowapi or a simple middleware.
2. **Implement conversation session persistence** — Store pending booking state (Redis or Supabase) so multi-turn booking flows work across requests.
3. **Add DB migration to this repo** — Copy `0006_chatbot_scheduling.sql` into a `migrations/` directory so the repo is self-contained.
4. **Verify `settings` table schema** — Confirm the target Supabase project has the `settings` table with `owner_id` column, or add a migration.
5. **Add SMS/Email reminder channels** — Implement Twilio/SendGrid integrations for customers without Telegram.
6. **Add integration tests** — Test `/health` and `/chat` endpoints against a running service.
7. **Pin dependency versions** — Replace `>=` with specific minor versions in `requirements.txt` for reproducible builds.

---

## ARCHITECTURE SNAPSHOT
```
src/
├── main.py              # App factory, lifespan, middleware, entry point
├── config.py            # Env var reads, defaults, validation
├── db.py                # Supabase client init & accessors
├── models.py            # Pydantic schemas & Intent enum
├── knowledge.py         # Shop info: pricing, hours, location, greetings
├── classifier.py        # Ollama LLM + keyword regex fallback
├── scheduling.py        # Slots, booking CRUD, reschedule, cancel
├── reminders.py         # 24h/1h reminder engine
├── telegram.py          # sendMessage, webhook validation & processing
├── handlers.py          # Intent handlers (shared by routes + bot)
└── routes.py            # All 9 API endpoints with auth guards

Entry Points:
  ├── FastAPI (src/main.py:119) — uvicorn on 0.0.0.0:8000
  │   ├── Middleware: CORS (from env) → Request Logging (UUID + duration)
  │   └── Routes (src/routes.py):
  │       ├── GET  /health
  │       ├── POST /chat
  │       ├── GET  /schedule
  │       ├── POST /booking
  │       ├── GET  /appointments/{identifier}
  │       ├── POST /appointments/{id}/reschedule
  │       ├── POST /appointments/{id}/cancel
  │       ├── POST /reminders/send       [X-API-Key auth]
  │       └── POST /telegram/webhook     [secret token validation]
  │
  ├── Telegram Polling Bot (telegram_bot.py)
  │   └── Uses src.handlers, src.classifier, src.knowledge
  │
  └── React ChatWidget (marwa-app/src/ChatWidget.jsx)
      └── POST {VITE_CHATBOT_URL}/chat

Data Layer:
  Supabase (postgrest) via src/db.py
  ├── supabase (anon key) — health checks
  └── supabase_admin (service_role) — all CRUD
      ├── customers, vehicles, work_orders, appointments, settings, reminder_log

External Services:
  ├── Ollama (local) — LLM intent classification
  └── Telegram Bot API — sendMessage, webhook
```

---

## DEPENDENCY HEALTH
| Dependency | Specified | Status |
|------------|-----------|--------|
| fastapi | >=0.110.0 | Current. |
| uvicorn[standard] | >=0.27.0 | Current. |
| httpx | >=0.27.0 | Current. |
| pydantic | >=2.6.0 | Current. |
| supabase | >=2.3.0 | Current. |
| python-telegram-bot | >=21.0 | Current. |
| pytest | >=8.0.0 | **Active** — 88 tests. |
| pytest-asyncio | >=0.23.0 | **Active** — 12 async tests. |

No version pins — all use `>=`. Recommend pinning minor versions for reproducibility.

---

## SCAN NOTES
- **`settings` table assumption**: `get_schedule_config()` queries `public.settings` by `owner_id`. The migration adds a `schedule_config` column but does not create the table. Not verified whether `settings` exists in the target Supabase project.
- **`update_updated_at_column()` trigger**: Referenced by migration — assumed to exist from a prior migration. Not verified.
- **Ollama model**: `qwen3.6:latest` is specified. Not verified if this model exists. System degrades gracefully to keyword classification.
- **OpenClaw cron jobs**: README describes external cron infrastructure. Not defined in this repo.
- **`DEFAULT_HOURS` bug discovered during testing**: The original mapping had keys shifted by one (0=Sunday instead of 0=Monday), causing Monday to appear closed and Sunday to show Saturday hours. Fixed in `src/scheduling.py:30-38`.

---

## UPDATE LOG
| Date | What Changed | Stage | Completion |
|------|-------------|-------|------------|
| 2026-06-16 09:45 | Initial forensic scan | IN PROGRESS | 55% |
| 2026-06-16 10:30 | Phase 1-5: Fixed Supabase mismatch, replaced anon key, modularized into 12 files, added CORS/auth/logging middleware, fixed DEFAULT_HOURS off-by-one bug, wrote 88 tests, added Dockerfile + CI workflow | IN PROGRESS | 75% |

---

## MAINTENANCE PROTOCOL
This file is the single source of truth and the FIRST file read at the start of every session.

After each build session:
1. Move completed items IN PROGRESS -> DONE (keep the evidence path).
2. Add newly discovered items to the correct section.
3. Re-run security + dependency checks if new code/deps were added.
4. Append a row to UPDATE LOG (date, change summary, new stage, new %).
5. Re-assess Overall Stage, Completion %, and "Can it run right now?"
6. Never delete the UPDATE LOG history — it's the project's memory.
