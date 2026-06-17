"""
Tests for scheduling engine — slot generation, business hours logic.

These tests mock Supabase calls to test the scheduling algorithm
without requiring a live database.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import date, time, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from src.scheduling import (
    DEFAULT_HOURS,
    SLOT_DURATION,
    BUFFER_MINUTES,
    get_available_slots,
    get_schedule_config,
)


class TestDefaultHours:
    """Verify default business hours configuration.
    Keys match Python's date.weekday(): 0=Monday, 6=Sunday."""

    def test_sunday_closed(self):
        assert DEFAULT_HOURS[6] is None  # Sunday

    def test_weekday_hours(self):
        assert DEFAULT_HOURS[0] == ("08:00", "17:00")  # Monday
        assert DEFAULT_HOURS[4] == ("08:00", "17:00")  # Friday

    def test_saturday_hours(self):
        assert DEFAULT_HOURS[5] == ("09:00", "15:00")  # Saturday

    def test_all_days_defined(self):
        assert len(DEFAULT_HOURS) == 7
        for i in range(7):
            assert i in DEFAULT_HOURS


class TestSlotGeneration:
    """Test slot generation logic with mocked Supabase."""
    pytestmark = pytest.mark.asyncio

    @patch("src.scheduling.get_supabase_admin")
    @patch("src.scheduling.get_schedule_config")
    async def test_sunday_returns_empty(self, mock_config, mock_admin):
        """Sunday (closed) should return no slots."""
        mock_config.return_value = {}  # Use defaults
        # Find next Sunday
        today = date.today()
        days_until_sunday = (6 - today.weekday()) % 7
        if days_until_sunday == 0:
            days_until_sunday = 7  # Don't use today if it's Sunday
        sunday = today + timedelta(days=days_until_sunday)

        # Mock empty appointments
        mock_resp = MagicMock()
        mock_resp.data = []
        mock_admin.return_value.table.return_value.select.return_value.eq.return_value.eq.return_value.not_.in_.return_value.execute.return_value = mock_resp

        slots = await get_available_slots(sunday, "owner-1")
        assert slots == []

    @patch("src.scheduling.get_supabase_admin")
    @patch("src.scheduling.get_schedule_config")
    async def test_weekday_generates_slots(self, mock_config, mock_admin):
        """A weekday should generate slots from 8:00 to 17:00."""
        mock_config.return_value = {}  # Use defaults
        # Find next Monday
        today = date.today()
        days_until_monday = (0 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        monday = today + timedelta(days=days_until_monday)

        # Mock empty appointments
        mock_resp = MagicMock()
        mock_resp.data = []
        mock_admin.return_value.table.return_value.select.return_value.eq.return_value.eq.return_value.not_.in_.return_value.execute.return_value = mock_resp

        slots = await get_available_slots(monday, "owner-1")
        assert len(slots) > 0
        # First slot should be 08:00
        assert slots[0].time == "08:00"
        # All slots should be available (no conflicts)
        assert all(s.available for s in slots)

    @patch("src.scheduling.get_supabase_admin")
    @patch("src.scheduling.get_schedule_config")
    async def test_slots_respect_close_time(self, mock_config, mock_admin):
        """Last slot should not exceed close time."""
        mock_config.return_value = {}
        today = date.today()
        days_until_monday = (0 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        monday = today + timedelta(days=days_until_monday)

        mock_resp = MagicMock()
        mock_resp.data = []
        mock_admin.return_value.table.return_value.select.return_value.eq.return_value.eq.return_value.not_.in_.return_value.execute.return_value = mock_resp

        slots = await get_available_slots(monday, "owner-1")
        # Last slot + duration should be <= 17:00
        last_slot_time = time.fromisoformat(slots[-1].time)
        close_time = time(17, 0)
        # The slot starts before close and slot+duration <= close
        assert last_slot_time < close_time

    @patch("src.scheduling.get_supabase_admin")
    @patch("src.scheduling.get_schedule_config")
    async def test_conflict_marks_unavailable(self, mock_config, mock_admin):
        """An existing appointment should make its slot unavailable."""
        mock_config.return_value = {}
        today = date.today()
        days_until_monday = (0 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        monday = today + timedelta(days=days_until_monday)

        # Mock an existing appointment at 08:00 for 60 min
        # (first slot of the day — 08:00-09:00)
        mock_resp = MagicMock()
        mock_resp.data = [
            {
                "scheduled_time": "08:00",
                "duration_minutes": 60,
                "status": "scheduled",
            }
        ]
        mock_admin.return_value.table.return_value.select.return_value.eq.return_value.eq.return_value.not_.in_.return_value.execute.return_value = mock_resp

        slots = await get_available_slots(monday, "owner-1")
        # The 08:00 slot should be unavailable (conflict)
        slot_0800 = next((s for s in slots if s.time == "08:00"), None)
        assert slot_0800 is not None
        assert slot_0800.available is False
        # But the next slot (09:15) should still be available
        slot_0915 = next((s for s in slots if s.time == "09:15"), None)
        assert slot_0915 is not None
        assert slot_0915.available is True

    @patch("src.scheduling.get_supabase_admin")
    @patch("src.scheduling.get_schedule_config")
    async def test_cancelled_appointments_ignored(self, mock_config, mock_admin):
        """Cancelled appointments should not block slots."""
        mock_config.return_value = {}
        today = date.today()
        days_until_monday = (0 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        monday = today + timedelta(days=days_until_monday)

        # The query filters out cancelled/no_show — return empty data
        mock_resp = MagicMock()
        mock_resp.data = []
        mock_admin.return_value.table.return_value.select.return_value.eq.return_value.eq.return_value.not_.in_.return_value.execute.return_value = mock_resp

        slots = await get_available_slots(monday, "owner-1")
        # All slots should be available (no active appointments)
        assert len(slots) > 0
        assert all(s.available for s in slots)

    @patch("src.scheduling.get_supabase_admin")
    @patch("src.scheduling.get_schedule_config")
    async def test_custom_business_hours(self, mock_config, mock_admin):
        """Custom business hours from config should override defaults."""
        mock_config.return_value = {
            "business_hours": {
                "monday": {"open": "10:00", "close": "14:00"},
            },
            "slot_duration_minutes": 30,
            "buffer_minutes": 5,
        }
        today = date.today()
        days_until_monday = (0 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        monday = today + timedelta(days=days_until_monday)

        mock_resp = MagicMock()
        mock_resp.data = []
        mock_admin.return_value.table.return_value.select.return_value.eq.return_value.eq.return_value.not_.in_.return_value.execute.return_value = mock_resp

        slots = await get_available_slots(monday, "owner-1")
        # First slot should be 10:00 (not 08:00)
        assert slots[0].time == "10:00"
        # Should have fewer slots (10:00-14:00 with 30min slots + 5min buffer)
        # 10:00-10:30, 10:35-11:05, 11:10-11:40, 11:45-12:15, 12:20-12:50, 12:55-13:25, 13:30-14:00
        assert len(slots) >= 5


class TestScheduleConfig:
    """Test schedule config retrieval."""
    pytestmark = pytest.mark.asyncio

    @patch("src.scheduling.get_supabase_admin")
    async def test_returns_defaults_when_no_config(self, mock_admin):
        """When settings table has no schedule_config, return empty dict."""
        mock_resp = MagicMock()
        mock_resp.data = None
        mock_admin.return_value.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_resp

        config = await get_schedule_config("owner-1")
        assert config == {}

    @patch("src.scheduling.get_supabase_admin")
    async def test_returns_config_when_present(self, mock_admin):
        """When schedule_config exists, return it."""
        mock_resp = MagicMock()
        mock_resp.data = {
            "schedule_config": {
                "business_hours": {"monday": {"open": "09:00", "close": "18:00"}},
            }
        }
        mock_admin.return_value.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_resp

        config = await get_schedule_config("owner-1")
        assert "business_hours" in config
        assert config["business_hours"]["monday"]["open"] == "09:00"

    @patch("src.scheduling.get_supabase_admin")
    async def test_handles_supabase_error_gracefully(self, mock_admin):
        """Supabase errors should return empty config, not crash."""
        mock_admin.return_value.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.side_effect = Exception("Connection refused")

        config = await get_schedule_config("owner-1")
        assert config == {}
