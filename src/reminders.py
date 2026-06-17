"""
Marwa Chatbot — Reminder Engine

Sends 24h and 1h reminders for upcoming appointments via Telegram
(and other channels in the future). Called by cron jobs via the
/reminders/send endpoint.
"""

import logging
from datetime import date, time, datetime, timedelta

from .db import get_supabase_admin
from .telegram import send_telegram_message

logger = logging.getLogger("marwa-chatbot.reminders")


async def send_reminders(owner_id: str, channel: str = "telegram") -> dict:
    """Send reminders for upcoming appointments. Called by cron job."""
    admin = get_supabase_admin()
    now = datetime.now()
    today = now.date()
    tomorrow = today + timedelta(days=1)

    results = {"24h_sent": 0, "1h_sent": 0, "errors": 0}

    # ── 24h reminders: appointments tomorrow ───────────────────────
    resp = (
        admin.table("appointments")
        .select(
            "id,customer_id,scheduled_date,scheduled_time,status,"
            "customers(name,phone,telegram_id),work_orders(number,issues)"
        )
        .eq("owner_id", owner_id)
        .eq("scheduled_date", tomorrow.isoformat())
        .eq("reminder_24h_sent", False)
        .not_.in_("status", ["cancelled", "no_show", "completed"])
        .execute()
    )

    for appt in resp.data or []:
        try:
            customer = appt.get("customers", {}) or {}
            wo = appt.get("work_orders", {}) or {}
            service = (
                (wo.get("issues") or [{}])[0].get("category", "service")
                if wo.get("issues")
                else "service"
            )

            message = (
                f"🔧 Reminder: Your {service} appointment at "
                f"Marwa Auto Repairs is tomorrow "
                f"({tomorrow.isoformat()}) at {appt['scheduled_time']}.\n"
                f"Work Order: {wo.get('number', 'N/A')}\n"
                f"Need to reschedule? Just reply to this message."
            )

            if channel == "telegram" and customer.get("telegram_id"):
                await send_telegram_message(
                    customer["telegram_id"], message
                )

            # Log reminder
            admin.table("reminder_log").insert(
                {
                    "owner_id": owner_id,
                    "appointment_id": appt["id"],
                    "customer_id": appt["customer_id"],
                    "channel": channel,
                    "reminder_type": "24h",
                    "message_text": message,
                    "status": "sent",
                }
            ).execute()

            # Mark as sent
            (
                admin.table("appointments")
                .update({"reminder_24h_sent": True})
                .eq("id", appt["id"])
                .execute()
            )
            results["24h_sent"] += 1
            logger.info(f"24h reminder sent for appointment {appt['id']}")

        except Exception as e:
            logger.error(
                f"Failed to send 24h reminder for {appt['id']}: {e}"
            )
            results["errors"] += 1

    # ── 1h reminders: appointments today within 45-90 min ──────────
    resp = (
        admin.table("appointments")
        .select(
            "id,customer_id,scheduled_date,scheduled_time,status,"
            "customers(name,phone,telegram_id),work_orders(number,issues)"
        )
        .eq("owner_id", owner_id)
        .eq("scheduled_date", today.isoformat())
        .eq("reminder_1h_sent", False)
        .not_.in_("status", ["cancelled", "no_show", "completed"])
        .execute()
    )

    for appt in resp.data or []:
        try:
            appt_time = time.fromisoformat(
                str(appt["scheduled_time"])[:5]
            )
            appt_dt = datetime.combine(today, appt_time)
            time_until = (appt_dt - now).total_seconds() / 60

            # Send if appointment is 45-90 minutes away
            if 45 <= time_until <= 90:
                customer = appt.get("customers", {}) or {}
                wo = appt.get("work_orders", {}) or {}
                service = (
                    (wo.get("issues") or [{}])[0].get(
                        "category", "service"
                    )
                    if wo.get("issues")
                    else "service"
                )

                message = (
                    f"⏰ Your {service} appointment at Marwa Auto Repairs "
                    f"is in about 1 hour ({appt['scheduled_time']}).\n"
                    f"Work Order: {wo.get('number', 'N/A')}\n"
                    f"We're at 123 Mechanic Lane. See you soon!"
                )

                if channel == "telegram" and customer.get("telegram_id"):
                    await send_telegram_message(
                        customer["telegram_id"], message
                    )

                admin.table("reminder_log").insert(
                    {
                        "owner_id": owner_id,
                        "appointment_id": appt["id"],
                        "customer_id": appt["customer_id"],
                        "channel": channel,
                        "reminder_type": "1h",
                        "message_text": message,
                        "status": "sent",
                    }
                ).execute()

                (
                    admin.table("appointments")
                    .update({"reminder_1h_sent": True})
                    .eq("id", appt["id"])
                    .execute()
                )
                results["1h_sent"] += 1
                logger.info(
                    f"1h reminder sent for appointment {appt['id']}"
                )

        except Exception as e:
            logger.error(
                f"Failed to send 1h reminder for {appt['id']}: {e}"
            )
            results["errors"] += 1

    return results
