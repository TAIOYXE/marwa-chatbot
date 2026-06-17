"""
Tests for intent classification — keyword fallback (pure function, no I/O).
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.classifier import keyword_classify
from src.models import Intent


class TestKeywordClassifier:
    """Unit tests for keyword_classify() — the rule-based fallback."""

    def test_greeting_hi(self):
        result = keyword_classify("hi")
        assert result.intent == Intent.GREETING
        assert result.confidence == 0.9

    def test_greeting_hello(self):
        result = keyword_classify("hello")
        assert result.intent == Intent.GREETING
        assert result.confidence == 0.9

    def test_greeting_hey(self):
        result = keyword_classify("hey")
        assert result.intent == Intent.GREETING

    def test_greeting_good_morning(self):
        result = keyword_classify("good morning")
        assert result.intent == Intent.GREETING

    def test_greeting_with_name_not_greeting(self):
        # "hi there how are you" is >3 words, should NOT be greeting
        result = keyword_classify("hi there how are you")
        assert result.intent != Intent.GREETING

    def test_greeting_short_only(self):
        # Long message starting with hi should not be greeting
        result = keyword_classify("hi I need an oil change for my car please")
        assert result.intent != Intent.GREETING

    def test_book_oil_change(self):
        result = keyword_classify("I need an oil change")
        assert result.intent == Intent.BOOK
        assert result.entities.get("service_type") == "oil change"

    def test_book_brake_repair(self):
        result = keyword_classify("I need brake repair for my car")
        assert result.intent == Intent.BOOK
        assert result.entities.get("service_type") == "brake repair"

    def test_book_with_vehicle(self):
        result = keyword_classify(
            "I need an oil change for my 2020 Honda Civic"
        )
        assert result.intent == Intent.BOOK
        assert result.entities.get("service_type") == "oil change"
        assert result.entities.get("vehicle") == "2020 Honda Civic"

    def test_book_with_today(self):
        result = keyword_classify("book an oil change today")
        assert result.intent == Intent.BOOK
        assert "preferred_date" in result.entities

    def test_book_with_tomorrow(self):
        result = keyword_classify("schedule brake service tomorrow")
        assert result.intent == Intent.BOOK
        assert "preferred_date" in result.entities

    def test_book_tire_services(self):
        # "I need tire service" matches the booking pattern
        result = keyword_classify("I need tire service")
        assert result.intent == Intent.BOOK
        assert result.entities.get("service_type") == "tire services"

    def test_book_ac_repair(self):
        # "I need ac repair" matches the booking pattern
        result = keyword_classify("I need ac repair")
        assert result.intent == Intent.BOOK
        assert result.entities.get("service_type") == "ac repair"

    def test_book_exhaust(self):
        # "I need custom exhaust" matches the booking pattern
        result = keyword_classify("I need custom exhaust work")
        assert result.intent == Intent.BOOK
        assert result.entities.get("service_type") == "custom exhaust"

    def test_book_diagnostic(self):
        # "I need diagnostic" matches (singular keyword)
        result = keyword_classify("I need a diagnostic check")
        assert result.intent == Intent.BOOK
        assert result.entities.get("service_type") == "engine diagnostics"

    def test_book_loose_phrasing_falls_to_unknown(self):
        # These phrasings don't match keyword patterns — Ollama handles them.
        # Keyword fallback is deliberately conservative.
        assert keyword_classify("my ac is broken").intent == Intent.UNKNOWN
        assert keyword_classify("I want a custom exhaust").intent == Intent.UNKNOWN
        assert keyword_classify("I need new tires").intent == Intent.UNKNOWN

    def test_book_general_repair(self):
        result = keyword_classify("my car needs a fix")
        assert result.intent == Intent.BOOK
        assert result.entities.get("service_type") == "general repair"

    def test_book_schedule_appointment(self):
        result = keyword_classify("I want to schedule an appointment")
        assert result.intent == Intent.BOOK

    def test_book_make_appointment(self):
        result = keyword_classify("I'd like to make an appointment for service")
        assert result.intent == Intent.BOOK

    def test_cancel_appointment(self):
        result = keyword_classify("cancel my appointment")
        assert result.intent == Intent.CANCEL
        assert result.confidence == 0.8

    def test_cancel_cant_make_it(self):
        result = keyword_classify("I can't make it tomorrow")
        assert result.intent == Intent.CANCEL

    def test_cancel_wont_make(self):
        result = keyword_classify("I won't be able to make it")
        assert result.intent == Intent.CANCEL

    def test_cancel_need_cancel(self):
        result = keyword_classify("I need to cancel")
        assert result.intent == Intent.CANCEL

    def test_reschedule_change_time(self):
        result = keyword_classify("I need to change my appointment time")
        assert result.intent == Intent.RESCHEDULE

    def test_reschedule_move_appointment(self):
        result = keyword_classify("can I move my appointment to Friday")
        assert result.intent == Intent.RESCHEDULE

    def test_reschedule_different_day(self):
        result = keyword_classify("I need a different day")
        assert result.intent == Intent.RESCHEDULE

    def test_reschedule_keyword(self):
        result = keyword_classify("reschedule my appointment please")
        assert result.intent == Intent.RESCHEDULE

    def test_status_check_appointment(self):
        result = keyword_classify("check my appointment status")
        assert result.intent == Intent.CHECK_STATUS

    def test_status_how_is_my_car(self):
        result = keyword_classify("how is my car doing")
        assert result.intent == Intent.CHECK_STATUS

    def test_status_is_my_car_ready(self):
        result = keyword_classify("is my car ready")
        assert result.intent == Intent.CHECK_STATUS

    def test_status_update(self):
        result = keyword_classify("status update please")
        assert result.intent == Intent.CHECK_STATUS

    def test_question_pricing(self):
        result = keyword_classify("how much is an oil change")
        assert result.intent == Intent.ASK_QUESTION

    def test_question_hours(self):
        result = keyword_classify("what are your hours")
        assert result.intent == Intent.ASK_QUESTION

    def test_question_location(self):
        # "where" alone doesn't match keyword patterns — needs "address" or "location"
        result = keyword_classify("what is your address")
        assert result.intent == Intent.ASK_QUESTION

    def test_question_where_falls_to_unknown(self):
        # "where are you located" doesn't match keyword patterns (no "address"/"location")
        # Ollama handles this; keyword fallback is conservative
        result = keyword_classify("where are you located")
        assert result.intent == Intent.UNKNOWN

    def test_question_do_you(self):
        result = keyword_classify("do you do tire rotations")
        assert result.intent == Intent.ASK_QUESTION

    def test_unknown_gibberish(self):
        result = keyword_classify("asdfghjkl")
        assert result.intent == Intent.UNKNOWN
        assert result.confidence == 0.0

    def test_unknown_empty(self):
        result = keyword_classify("")
        assert result.intent == Intent.UNKNOWN

    def test_priority_cancel_over_book(self):
        # "cancel" should match CANCEL even though "appointment" is in booking patterns
        result = keyword_classify("cancel my appointment for brake repair")
        assert result.intent == Intent.CANCEL

    def test_priority_reschedule_over_book(self):
        result = keyword_classify("reschedule my oil change appointment")
        assert result.intent == Intent.RESCHEDULE

    def test_priority_status_over_book(self):
        result = keyword_classify("status of my brake repair appointment")
        assert result.intent == Intent.CHECK_STATUS

    def test_case_insensitivity(self):
        result = keyword_classify("I NEED AN OIL CHANGE FOR MY 2020 HONDA CIVIC")
        assert result.intent == Intent.BOOK
        assert result.entities.get("service_type") == "oil change"
        assert result.entities.get("vehicle") == "2020 Honda Civic"
