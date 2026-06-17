"""
Marwa Chatbot — Knowledge Base

Shop information: pricing, hours, location, warranty, and FAQ responses.
All hardcoded strings live here so they can be updated in one place.
Imports config for overridable values like phone and address.
"""

from .config import SHOP_PHONE, SHOP_ADDRESS, SHOP_NAME


# ── Service Pricing ───────────────────────────────────────────────────

PRICING = {
    "oil change": "from $49.99",
    "brake repair": "from $149.99",
    "engine diagnostics": "$89.99",
    "tire services": "from $25/tire",
    "ac repair": "from $129.99",
    "custom exhaust": "from $299.99",
}

PRICING_MESSAGE = (
    "Our pricing varies by service:\n"
    "• Oil Change: from $49.99\n"
    "• Brake Repair: from $149.99\n"
    "• Engine Diagnostics: $89.99\n"
    "• Tire Services: from $25/tire\n"
    "• AC Repair: from $129.99\n"
    "• Custom Exhaust: from $299.99\n\n"
    "All services include a free multi-point inspection. Want to book one?"
)


# ── Shop Hours ─────────────────────────────────────────────────────────

HOURS_MESSAGE = (
    "Our shop hours:\n"
    "• Monday–Friday: 8:00 AM – 5:00 PM\n"
    "• Saturday: 9:00 AM – 3:00 PM\n"
    "• Sunday: Closed\n\n"
    "Would you like to book an appointment?"
)

HOURS_MARKDOWN = (
    "🕐 *Marwa Auto Repairs Hours*\n\n"
    "• Monday–Friday: 8:00 AM – 5:00 PM\n"
    "• Saturday: 9:00 AM – 3:00 PM\n"
    "• Sunday: Closed\n\n"
    "Want to book? Just tell me when!"
)


# ── Location ──────────────────────────────────────────────────────────

LOCATION_MESSAGE = (
    f"We're at {SHOP_ADDRESS}. "
    "You can drop by during business hours or book an appointment here!"
)


# ── Warranty ───────────────────────────────────────────────────────────

WARRANTY_MESSAGE = (
    "All our repairs come with a 12-month/20,000 km warranty "
    "on parts and labor. We stand behind our work!"
)


# ── Fallback / Unknown ─────────────────────────────────────────────────

FALLBACK_MESSAGE = (
    "Good question! For specific details, you can call the shop at "
    f"{SHOP_PHONE} or I can help you book an appointment. "
    "What service are you interested in?"
)

UNKNOWN_MESSAGE = (
    "I'm not sure what you need. I can help with:\n"
    "• Booking an appointment — just tell me what service and vehicle\n"
    "• Checking your appointment status\n"
    "• Questions about our services and pricing\n\n"
    "Try rephrasing or call the shop directly at "
    f"{SHOP_PHONE}."
)

UNKNOWN_MESSAGE_SHORT = (
    "I'm not sure what you need. Try saying something like "
    "\"I need an oil change for my Honda Civic\" or "
    "\"Check my appointment status\"."
)


# ── Greeting ───────────────────────────────────────────────────────────

GREETING_MESSAGE = (
    "Hello! 👋 I'm the Marwa Auto Repairs assistant. "
    "I can help you book appointments, check your vehicle status, "
    "or answer questions. What can I do for you?"
)

GREETING_MESSAGE_NAMED = (
    "Hello {name}! 👋 I'm the Marwa Auto Repairs assistant.\n"
    "I can help you:\n"
    "• Book an appointment (e.g., \"I need an oil change for my 2020 Honda Civic\")\n"
    "• Check your appointment status\n"
    "• Reschedule or cancel\n"
    "• Answer questions about our services\n\n"
    "What can I do for you today?"
)

GREETING_MESSAGE_TELEGRAM = (
    "Hello {name}! 👋 How can I help with your vehicle today?\n"
    "You can book an appointment, check your status, or ask about our services."
)


# ── Status Emoji Map ───────────────────────────────────────────────────

STATUS_EMOJI = {
    "scheduled": "📅",
    "confirmed": "✅",
    "in_progress": "🔧",
    "completed": "🏁",
    "cancelled": "❌",
    "no_show": "⚠️",
}


# ── Service Keyword Map (for classifier) ──────────────────────────────

SERVICE_KEYWORDS = {
    "oil": "oil change",
    "brake": "brake repair",
    "diagnostic": "engine diagnostics",
    "tire": "tire services",
    "ac": "ac repair",
    "air conditioning": "ac repair",
    "exhaust": "custom exhaust",
    "repair": "general repair",
    "service": "general service",
    "maintenance": "general service",
    "tune": "general service",
    "fix": "general repair",
}
