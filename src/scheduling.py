"""
Marwa Chatbot — Scheduling Engine

Slot availability, conflict detection, booking creation (customer →
vehicle → work order → appointment), reschedule, cancel, and
customer appointment lookup.
"""

import logging
from datetime import date, time, datetime, timedelta
from typing import List

from .config import SHOP_OWNER_ID
from .db import get_supabase_admin
from .models import AvailableSlot, BookingRequest, BookingResult

logger = logging.getLogger("marwa-chatbot.scheduling")

# ── Default Business Hours ────────────────────────────────────────────
# Overridden by settings.schedule_config in Supabase

# Keys match Python's date.weekday(): 0=Monday, 6=Sunday
DEFAULT_HOURS = {
    0: ("08:00", "17:00"),         # Monday
    1: ("08:00", "17:00"),         # Tuesday
    2: ("08:00", "17:00"),         # Wednesday
    3: ("08:00", "17:00"),         # Thursday
    4: ("08:00", "17:00"),         # Friday
    5: ("09:00", "15:00"),         # Saturday
    6: None,                       # Sunday - closed
}

SLOT_DURATION = 60       # minutes
BUFFER_MINUTES = 15
MAX_DAILY_APPOINTMENTS = 8


# ── Schedule Config ───────────────────────────────────────────────────

async def get_schedule_config(owner_id: str) -> dict:
    """Get schedule configuration from settings, with defaults."""
    try:
        admin = get_supabase_admin()
        resp = (
            admin.table("settings")
            .select("schedule_config")
            .eq("owner_id", owner_id)
            .maybe_single()
            .execute()
        )
        if resp.data and resp.data.get("schedule_config"):
            return resp.data["schedule_config"]
    except Exception as e:
        logger.warning(f"Could not load schedule config: {e}")
    return {}


# ── Slot Availability ─────────────────────────────────────────────────

async def get_available_slots(
    check_date: date, owner_id: str
) -> List[AvailableSlot]:
    """Get available time slots for a given date."""
    config = await get_schedule_config(owner_id)
    dow = check_date.weekday()  # 0=Monday, 6=Sunday

    # Get business hours for this day
    biz_hours = config.get("business_hours", {})
    day_names = [
        "monday", "tuesday", "wednesday", "thursday",
        "friday", "saturday", "sunday",
    ]
    day_name = day_names[dow]

    day_config = biz_hours.get(day_name) or (
        {"open": DEFAULT_HOURS[dow][0], "close": DEFAULT_HOURS[dow][1]}
        if DEFAULT_HOURS[dow]
        else None
    )

    if day_config is None:
        return []  # Closed

    open_time = time.fromisoformat(day_config["open"])
    close_time = time.fromisoformat(day_config["close"])
    slot_duration = config.get("slot_duration_minutes", SLOT_DURATION)
    buffer = config.get("buffer_minutes", BUFFER_MINUTES)

    # Get existing appointments for this date
    admin = get_supabase_admin()
    resp = (
        admin.table("appointments")
        .select("scheduled_time,duration_minutes,status")
        .eq("owner_id", owner_id)
        .eq("scheduled_date", check_date.isoformat())
        .not_.in_("status", ["cancelled", "no_show"])
        .execute()
    )

    existing = resp.data or []

    slots = []
    current = datetime.combine(check_date, open_time)
    end = datetime.combine(check_date, close_time)

    while current + timedelta(minutes=slot_duration) <= end:
        slot_end = current + timedelta(minutes=slot_duration)
        slot_time_str = current.time().isoformat(timespec="minutes")

        # Check conflicts
        conflict = False
        for appt in existing:
            appt_start = datetime.combine(
                check_date,
                time.fromisoformat(str(appt["scheduled_time"])[:5]),
            )
            appt_end = appt_start + timedelta(
                minutes=appt.get("duration_minutes", 60)
            )
            if current < appt_end and slot_end > appt_start:
                conflict = True
                break

        slots.append(
            AvailableSlot(time=slot_time_str, available=not conflict)
        )
        current = slot_end + timedelta(minutes=buffer)

    return slots


# ── Booking ────────────────────────────────────────────────────────────

async def create_booking(
    req: BookingRequest, owner_id: str
) -> BookingResult:
    """Create a customer, vehicle, work order, and appointment."""
    admin = get_supabase_admin()

    try:
        # 1. Find or create customer
        customer_id = None
        if req.telegram_id:
            resp = (
                admin.table("customers")
                .select("id")
                .eq("telegram_id", req.telegram_id)
                .maybe_single()
                .execute()
            )
            if resp.data:
                customer_id = resp.data["id"]

        if not customer_id:
            # Search by phone
            resp = (
                admin.table("customers")
                .select("id")
                .eq("phone", req.customer_phone)
                .maybe_single()
                .execute()
            )
            if resp.data:
                customer_id = resp.data["id"]
                # Update telegram_id if provided
                if req.telegram_id:
                    (
                        admin.table("customers")
                        .update({"telegram_id": req.telegram_id})
                        .eq("id", customer_id)
                        .execute()
                    )

        if not customer_id:
            # Create new customer
            cust_data = {
                "owner_id": owner_id,
                "name": req.customer_name,
                "phone": req.customer_phone,
                "email": req.customer_email or "",
                "telegram_id": req.telegram_id,
            }
            resp = admin.table("customers").insert(cust_data).execute()
            customer_id = resp.data[0]["id"]
            logger.info(
                f"Created new customer: {customer_id} ({req.customer_name})"
            )

        # 2. Find or create vehicle
        vehicle_id = None
        if req.vehicle_make:
            resp = (
                admin.table("vehicles")
                .select("id")
                .eq("customer_id", customer_id)
                .eq("make", req.vehicle_make)
                .eq("model", req.vehicle_model or "")
                .maybe_single()
                .execute()
            )
            if resp.data:
                vehicle_id = resp.data["id"]

        if not vehicle_id and req.vehicle_make:
            veh_data = {
                "owner_id": owner_id,
                "customer_id": customer_id,
                "year": req.vehicle_year or "",
                "make": req.vehicle_make,
                "model": req.vehicle_model or "",
            }
            resp = admin.table("vehicles").insert(veh_data).execute()
            vehicle_id = resp.data[0]["id"]
            logger.info(f"Created new vehicle: {vehicle_id}")

        # 3. Create work order (Intake status)
        now = datetime.now()
        wo_number = (
            f"WO-{now.strftime('%y%m%d')}-{now.strftime('%H%M%S')}"
        )
        wo_data = {
            "owner_id": owner_id,
            "number": wo_number,
            "customer_id": customer_id,
            "vehicle_id": vehicle_id,
            "status": "Intake",
            "date": date.today().isoformat(),
            "issues": [
                {
                    "category": req.service_type,
                    "description": req.notes or "",
                }
            ],
            "assigned_tech": "Unassigned",
            "priority": "Standard",
        }
        resp = admin.table("work_orders").insert(wo_data).execute()
        work_order_id = resp.data[0]["id"]
        logger.info(f"Created work order: {work_order_id} ({wo_number})")

        # 4. Parse preferred time
        scheduled_time = req.preferred_time or "09:00"
        if scheduled_time in ("morning", "am"):
            scheduled_time = "09:00"
        elif scheduled_time in ("afternoon", "pm"):
            scheduled_time = "13:00"

        # 5. Create appointment
        appt_data = {
            "owner_id": owner_id,
            "work_order_id": work_order_id,
            "customer_id": customer_id,
            "scheduled_date": req.preferred_date,
            "scheduled_time": scheduled_time,
            "duration_minutes": 60,
            "status": "scheduled",
            "notes": req.notes,
        }
        resp = admin.table("appointments").insert(appt_data).execute()
        appointment_id = resp.data[0]["id"]
        logger.info(f"Created appointment: {appointment_id}")

        # 6. Link appointment to work order
        (
            admin.table("work_orders")
            .update({"appointment_id": appointment_id})
            .eq("id", work_order_id)
            .execute()
        )

        return BookingResult(
            success=True,
            appointment_id=appointment_id,
            work_order_id=work_order_id,
            scheduled_date=req.preferred_date,
            scheduled_time=scheduled_time,
            message=(
                f"Appointment booked! {req.service_type.title()} on "
                f"{req.preferred_date} at {scheduled_time}. "
                f"Your work order is {wo_number}."
            ),
        )

    except Exception as e:
        logger.error(f"Booking failed: {e}")
        return BookingResult(
            success=False,
            message=(
                "Sorry, I couldn't complete your booking. "
                "Please call the shop directly. "
                f"Error: {str(e)}"
            ),
        )


# ── Customer Appointments ─────────────────────────────────────────────

async def get_customer_appointments(
    customer_identifier: str, owner_id: str
) -> List[dict]:
    """Get appointments for a customer by name, phone, or telegram_id."""
    admin = get_supabase_admin()

    # Try telegram_id first, then phone, then name
    resp = (
        admin.table("customers")
        .select("id")
        .or_(
            f"telegram_id.eq.{customer_identifier},"
            f"phone.eq.{customer_identifier},"
            f"name.ilike.%{customer_identifier}%"
        )
        .execute()
    )

    if not resp.data:
        return []

    customer_ids = [c["id"] for c in resp.data]

    resp = (
        admin.table("appointments")
        .select(
            "id,scheduled_date,scheduled_time,status,duration_minutes,"
            "notes,work_order_id,"
            "work_orders(number,status,issues),customers(name,phone)"
        )
        .eq("owner_id", owner_id)
        .in_("customer_id", customer_ids)
        .order("scheduled_date", desc=True)
        .limit(5)
        .execute()
    )

    return resp.data or []


# ── Reschedule ─────────────────────────────────────────────────────────

async def reschedule_appointment(
    appointment_id: str, new_date: str, new_time: str, owner_id: str
) -> dict | None:
    """Reschedule an existing appointment."""
    admin = get_supabase_admin()
    resp = (
        admin.table("appointments")
        .update(
            {
                "scheduled_date": new_date,
                "scheduled_time": new_time,
                "status": "scheduled",
                "reminder_24h_sent": False,
                "reminder_1h_sent": False,
            }
        )
        .eq("id", appointment_id)
        .eq("owner_id", owner_id)
        .execute()
    )
    return resp.data[0] if resp.data else None


# ── Cancel ─────────────────────────────────────────────────────────────

async def cancel_appointment(
    appointment_id: str, owner_id: str
) -> dict | None:
    """Cancel an appointment."""
    admin = get_supabase_admin()
    resp = (
        admin.table("appointments")
        .update({"status": "cancelled"})
        .eq("id", appointment_id)
        .eq("owner_id", owner_id)
        .execute()
    )
    return resp.data[0] if resp.data else None
