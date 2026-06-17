"""
Marwa Chatbot — Intent Handlers

Handler functions for each intent: booking, status check, reschedule,
cancel, and general questions. Shared by the FastAPI routes and the
Telegram bot so routing logic is defined once.
"""

import logging
from datetime import date, timedelta
from typing import Dict, Any

from .models import Intent, ChatResponse, BookingRequest
from .scheduling import (
    get_available_slots,
    create_booking,
    get_customer_appointments,
    cancel_appointment,
)
from .knowledge import (
    PRICING_MESSAGE,
    HOURS_MESSAGE,
    LOCATION_MESSAGE,
    WARRANTY_MESSAGE,
    FALLBACK_MESSAGE,
    STATUS_EMOJI,
    SHOP_PHONE,
)

logger = logging.getLogger("marwa-chatbot.handlers")


# ── Booking Handler ───────────────────────────────────────────────────

async def handle_booking_intent(
    chat_id: str,
    name: str,
    message: str,
    entities: dict,
    owner_id: str,
) -> ChatResponse:
    """Handle the booking flow — check info and ask for missing pieces."""
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
            booking_date = date.today() + timedelta(days=1)

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
                        reply=(
                            f"{booking_date.isoformat()} is fully booked. "
                            f"The next available day is "
                            f"{next_date.isoformat()} with slots at "
                            f"{', '.join(s.time for s in next_available[:3])}. "
                            f"Would you like one of those?"
                        ),
                        intent=Intent.BOOK,
                        data={
                            "available_slots": [
                                s.model_dump()
                                for s in next_available[:5]
                            ],
                            "date": next_date.isoformat(),
                        },
                    )
                next_date += timedelta(days=1)

            return ChatResponse(
                reply=(
                    f"Sorry, {booking_date.isoformat()} and the next 7 "
                    f"days are fully booked. Please call the shop at "
                    f"{SHOP_PHONE} to find a slot."
                ),
                intent=Intent.BOOK,
            )

        # We have slots — confirm booking
        chosen_time = (
            pref_time
            if pref_time
            and any(s.time == pref_time for s in available)
            else available[0].time
        )

        # We need phone number — ask if not provided
        phone = entities.get("customer_phone")
        if not phone:
            return ChatResponse(
                reply=(
                    f"Great! I have slots available on "
                    f"{booking_date.isoformat()}. "
                    f"What's your phone number so I can book this?"
                ),
                intent=Intent.BOOK,
                data={
                    "pending_booking": {
                        "date": booking_date.isoformat(),
                        "service": service,
                        "vehicle": vehicle,
                    }
                },
            )

        # Create the booking
        result = await create_booking(
            BookingRequest(
                customer_name=name,
                customer_phone=phone,
                vehicle_make=(
                    vehicle.split()[1]
                    if vehicle and len(vehicle.split()) >= 2
                    else None
                ),
                vehicle_model=(
                    vehicle.split()[2]
                    if vehicle and len(vehicle.split()) >= 3
                    else None
                ),
                vehicle_year=(
                    vehicle.split()[0]
                    if vehicle and vehicle.split()[0].isdigit()
                    else None
                ),
                service_type=service,
                preferred_date=booking_date.isoformat(),
                preferred_time=chosen_time,
                telegram_id=chat_id,
            ),
            owner_id,
        )

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
        reply=(
            f"I'd love to book that for you! Could you tell me "
            f"{questions}? For example: "
            f"\"Oil change this Friday morning\"."
        ),
        intent=Intent.BOOK,
        data={"missing_info": missing},
    )


# ── Status Check Handler ──────────────────────────────────────────────

async def handle_status_check(
    chat_id: str, name: str, message: str, owner_id: str
) -> ChatResponse:
    """Check appointment status for a customer."""
    # Try to find customer by telegram_id first
    appointments = await get_customer_appointments(chat_id, owner_id)

    if not appointments:
        # Try name search
        appointments = await get_customer_appointments(name, owner_id)

    if not appointments:
        return ChatResponse(
            reply=(
                "I couldn't find any appointments under your name or "
                "phone number. Can you tell me the name or phone number "
                "you used when booking?"
            ),
            intent=Intent.CHECK_STATUS,
        )

    # Format response
    lines = ["Here are your appointments:"]
    for appt in appointments[:3]:
        cust = appt.get("customers", {}) or {}
        wo = appt.get("work_orders", {}) or {}
        service = (
            (wo.get("issues") or [{}])[0].get("category", "service")
            if wo.get("issues")
            else "service"
        )
        emoji = STATUS_EMOJI.get(appt["status"], "❓")

        lines.append(
            f"{emoji} {appt['scheduled_date']} at "
            f"{appt['scheduled_time']} — "
            f"{service.title()} "
            f"(WO: {wo.get('number', 'N/A')}) — "
            f"Status: {appt['status'].replace('_', ' ').title()}"
        )

    return ChatResponse(
        reply="\n".join(lines),
        intent=Intent.CHECK_STATUS,
        data={"appointments": appointments},
    )


# ── Reschedule Handler ─────────────────────────────────────────────────

async def handle_reschedule_intent(
    chat_id: str, message: str, owner_id: str
) -> ChatResponse:
    """Handle reschedule request."""
    appointments = await get_customer_appointments(chat_id, owner_id)

    if not appointments:
        return ChatResponse(
            reply=(
                "I need to find your appointment first. "
                "What name or phone number did you book under?"
            ),
            intent=Intent.RESCHEDULE,
        )

    active = [
        a
        for a in appointments
        if a["status"] in ("scheduled", "confirmed")
    ]
    if not active:
        return ChatResponse(
            reply=(
                "You don't have any active appointments to reschedule. "
                "Would you like to book a new one?"
            ),
            intent=Intent.RESCHEDULE,
        )

    if len(active) == 1:
        appt = active[0]
        return ChatResponse(
            reply=(
                f"Your current appointment is on "
                f"{appt['scheduled_date']} at {appt['scheduled_time']}. "
                f"What date and time would you prefer instead?"
            ),
            intent=Intent.RESCHEDULE,
            data={
                "appointment_id": appt["id"],
                "current_date": appt["scheduled_date"],
                "current_time": appt["scheduled_time"],
            },
        )
    else:
        lines = ["Which appointment would you like to reschedule?"]
        for i, appt in enumerate(active, 1):
            lines.append(
                f"{i}. {appt['scheduled_date']} at "
                f"{appt['scheduled_time']} "
                f"(ID: {appt['id'][:8]}...)"
            )
        return ChatResponse(
            reply="\n".join(lines),
            intent=Intent.RESCHEDULE,
            data={"appointments": active},
        )


# ── Cancel Handler ────────────────────────────────────────────────────

async def handle_cancel_intent(
    chat_id: str, message: str, owner_id: str
) -> ChatResponse:
    """Handle cancellation request."""
    appointments = await get_customer_appointments(chat_id, owner_id)

    if not appointments:
        return ChatResponse(
            reply=(
                "I need to find your appointment first. "
                "What name or phone number did you book under?"
            ),
            intent=Intent.CANCEL,
        )

    active = [
        a
        for a in appointments
        if a["status"] in ("scheduled", "confirmed")
    ]
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
                reply=(
                    f"Your appointment on {appt['scheduled_date']} at "
                    f"{appt['scheduled_time']} has been cancelled. "
                    f"Need to rebook? Just let me know."
                ),
                intent=Intent.CANCEL,
                action_taken="cancelled",
            )
        else:
            return ChatResponse(
                reply=(
                    "Sorry, I couldn't cancel that appointment. "
                    "Please call the shop directly."
                ),
                intent=Intent.CANCEL,
            )
    else:
        lines = [
            "Which appointment would you like to cancel? "
            "Reply with the number:"
        ]
        for i, appt in enumerate(active, 1):
            lines.append(
                f"{i}. {appt['scheduled_date']} at "
                f"{appt['scheduled_time']}"
            )
        return ChatResponse(
            reply="\n".join(lines),
            intent=Intent.CANCEL,
            data={"appointments": active},
        )


# ── Question Handler ──────────────────────────────────────────────────

async def handle_question(message: str) -> ChatResponse:
    """Handle general questions about the shop."""
    msg = message.lower()

    if "price" in msg or "cost" in msg or "how much" in msg:
        return ChatResponse(
            reply=PRICING_MESSAGE, intent=Intent.ASK_QUESTION
        )

    if "hour" in msg or "open" in msg or "close" in msg:
        return ChatResponse(
            reply=HOURS_MESSAGE, intent=Intent.ASK_QUESTION
        )

    if "location" in msg or "address" in msg or "where" in msg:
        return ChatResponse(
            reply=LOCATION_MESSAGE, intent=Intent.ASK_QUESTION
        )

    if "warranty" in msg:
        return ChatResponse(
            reply=WARRANTY_MESSAGE, intent=Intent.ASK_QUESTION
        )

    return ChatResponse(
        reply=FALLBACK_MESSAGE, intent=Intent.ASK_QUESTION
    )
