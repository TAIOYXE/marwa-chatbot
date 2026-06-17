"""
Tests for Pydantic models — validation, defaults, serialization.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pydantic import ValidationError

from src.models import (
    Intent,
    IntentResult,
    ChatRequest,
    ChatResponse,
    AvailableSlot,
    BookingRequest,
    BookingResult,
)


class TestIntentEnum:
    def test_all_intents_present(self):
        assert Intent.BOOK == "book_appointment"
        assert Intent.CHECK_STATUS == "check_status"
        assert Intent.RESCHEDULE == "reschedule"
        assert Intent.CANCEL == "cancel"
        assert Intent.ASK_QUESTION == "ask_question"
        assert Intent.GREETING == "greeting"
        assert Intent.UNKNOWN == "unknown"

    def test_from_string(self):
        assert Intent("book_appointment") == Intent.BOOK
        assert Intent("greeting") == Intent.GREETING

    def test_invalid_intent_raises(self):
        with pytest.raises(ValueError):
            Intent("nonexistent")


class TestIntentResult:
    def test_defaults(self):
        result = IntentResult(intent=Intent.UNKNOWN)
        assert result.confidence == 0.0
        assert result.entities == {}
        assert result.raw_response == ""

    def test_with_entities(self):
        result = IntentResult(
            intent=Intent.BOOK,
            confidence=0.9,
            entities={"service_type": "oil change"},
        )
        assert result.entities["service_type"] == "oil change"

    def test_serialization(self):
        result = IntentResult(intent=Intent.GREETING, confidence=0.95)
        d = result.model_dump()
        assert d["intent"] == "greeting"
        assert d["confidence"] == 0.95


class TestChatRequest:
    def test_minimal(self):
        req = ChatRequest(message="hello")
        assert req.message == "hello"
        assert req.customer_id is None
        assert req.telegram_id is None
        assert req.conversation_history == []

    def test_full(self):
        req = ChatRequest(
            message="book oil change",
            customer_id="cust-123",
            telegram_id="tg-456",
            conversation_history=[
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "Hello!"},
            ],
        )
        assert len(req.conversation_history) == 2

    def test_message_required(self):
        with pytest.raises(ValidationError):
            ChatRequest()


class TestChatResponse:
    def test_minimal(self):
        resp = ChatResponse(reply="Hello!", intent=Intent.GREETING)
        assert resp.reply == "Hello!"
        assert resp.action_taken is None
        assert resp.data is None

    def test_with_action(self):
        resp = ChatResponse(
            reply="Booked!",
            intent=Intent.BOOK,
            action_taken="booking_created",
            data={"appointment_id": "123"},
        )
        assert resp.action_taken == "booking_created"
        assert resp.data["appointment_id"] == "123"


class TestAvailableSlot:
    def test_available(self):
        slot = AvailableSlot(time="09:00", available=True)
        assert slot.time == "09:00"
        assert slot.available is True

    def test_unavailable(self):
        slot = AvailableSlot(time="10:00", available=False)
        assert slot.available is False


class TestBookingRequest:
    def test_minimal(self):
        req = BookingRequest(
            customer_name="John Doe",
            customer_phone="555-1234",
            service_type="oil change",
            preferred_date="2026-06-20",
        )
        assert req.customer_name == "John Doe"
        assert req.vehicle_make is None

    def test_full(self):
        req = BookingRequest(
            customer_name="Jane",
            customer_phone="555-5678",
            customer_email="jane@example.com",
            vehicle_year="2020",
            vehicle_make="Honda",
            vehicle_model="Civic",
            service_type="brake repair",
            preferred_date="2026-06-21",
            preferred_time="14:00",
            notes="Front brakes squeaking",
            telegram_id="tg-789",
        )
        assert req.vehicle_make == "Honda"
        assert req.preferred_time == "14:00"

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            BookingRequest(
                customer_name="John",
                # missing customer_phone
                service_type="oil change",
                preferred_date="2026-06-20",
            )


class TestBookingResult:
    def test_success(self):
        result = BookingResult(
            success=True,
            appointment_id="appt-1",
            work_order_id="wo-1",
            scheduled_date="2026-06-20",
            scheduled_time="09:00",
            message="Booked!",
        )
        assert result.success is True
        assert result.appointment_id == "appt-1"

    def test_failure(self):
        result = BookingResult(
            success=False,
            message="Booking failed",
        )
        assert result.success is False
        assert result.appointment_id is None
