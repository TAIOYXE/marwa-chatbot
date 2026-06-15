# Marwa Chatbot — Intelligent Appointment & Scheduling Assistant

AI-powered chatbot for Marwa Auto Repairs that manages appointments, work orders,
scheduling, and automated reminders via Telegram and an embedded web widget.

## Architecture

```
Customer ──┬── Telegram Bot (python-telegram-bot)
           │
           └── Web Chat Widget (React, embedded in marwa-app)
                    │
                    ▼
           FastAPI Service (src/main.py)
           ├── Intent Classifier (Ollama qwen3.6 + keyword fallback)
           ├── Slot Filling Engine
           ├── Scheduling Engine (conflict detection, slot availability)
           └── Reminder Engine (cron-triggered)
                    │
                    ▼
           Supabase (marwa-shop: icffarzfmegvhhpecoyr)
           ├── appointments (NEW — migration 0006)
           ├── work_orders (existing + appointment_id FK)
           ├── customers (existing + telegram_id)
           ├── reminder_log (NEW)
           └── settings.schedule_config (NEW)
```

## Quick Start

### 1. Database Migration

Run migration `0006_chatbot_scheduling.sql` on the marwa-shop Supabase project.
You need the `service_role` key.

**Option A — Supabase Dashboard:**
1. Go to https://supabase.com/dashboard/project/icffarzfmegvhhpecoyr
2. SQL Editor → paste contents of `supabase/migrations/0006_chatbot_scheduling.sql`
3. Run

**Option B — CLI (if linked):**
```bash
supabase link --project-ref icffarzfmegvhhpecoyr
supabase db push
```

### 2. Configure Environment

```bash
cd marwa-chatbot
cp .env.example .env
# Edit .env with real values:
#   SUPABASE_SERVICE_ROLE_KEY (from Supabase Dashboard → Project Settings → API)
#   TELEGRAM_BOT_TOKEN (from @BotFather)
#   SHOP_OWNER_ID (from Supabase Dashboard → Authentication → Users)
```

### 3. Install & Run

```bash
pip install -r requirements.txt

# Start the FastAPI service
python src/main.py

# OR start the Telegram bot (polling mode, no webhook needed)
python telegram_bot.py
```

### 4. Web Widget

The ChatWidget is already integrated into marwa-app (`src/ChatWidget.jsx`).
Set the chatbot URL in marwa-app's `.env`:
```
VITE_CHATBOT_URL=http://localhost:8000
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (Supabase, Ollama, Telegram status) |
| POST | `/chat` | Main chat endpoint — intent classification + response |
| GET | `/schedule?d=YYYY-MM-DD&days=7` | Get available slots for date range |
| POST | `/booking` | Direct booking (web widget) |
| GET | `/appointments/{identifier}` | Get customer appointments |
| POST | `/appointments/{id}/reschedule` | Reschedule appointment |
| POST | `/appointments/{id}/cancel` | Cancel appointment |
| POST | `/reminders/send?channel=telegram` | Trigger reminder sending |
| POST | `/telegram/webhook` | Telegram webhook receiver |

## Intents Handled

| Intent | Example | Action |
|--------|---------|--------|
| `book_appointment` | "I need an oil change for my 2020 Honda Civic tomorrow" | Creates customer, vehicle, work order, appointment |
| `check_status` | "What's my appointment status?" | Looks up appointments by customer |
| `reschedule` | "I need to reschedule my appointment to Friday" | Changes appointment date/time |
| `cancel` | "Cancel my appointment" | Sets appointment status to cancelled |
| `ask_question` | "How much is a brake job?" / "What are your hours?" | Answers from knowledge base |
| `greeting` | "Hi" / "Hello" | Welcome message with capabilities |

## Reminder Cron Jobs

Two OpenClaw cron jobs handle automated reminders:

- **marwa-reminders-24h**: Runs at 8am and 2pm CST daily — sends reminders for tomorrow's appointments
- **marwa-reminders-1h**: Runs every 30 min during business hours — sends reminders for appointments starting in ~1 hour

## Fallback Behavior

- **Ollama offline**: Falls back to keyword-based intent classification (rule-based regex)
- **Supabase admin client missing**: Admin operations (booking, scheduling) fail gracefully with clear error messages
- **Telegram token missing**: Telegram features disabled; web widget still works

## Files

```
marwa-chatbot/
├── src/main.py              # FastAPI service (all logic)
├── telegram_bot.py          # Telegram polling bot runner
├── requirements.txt         # Python dependencies
├── .env.example             # Environment template
└── README.md                # This file

marwa-app/
├── src/ChatWidget.jsx       # React web chat widget
└── supabase/migrations/
    └── 0006_chatbot_scheduling.sql  # DB migration
```
