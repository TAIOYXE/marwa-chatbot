"""
Tests for knowledge base — shop info strings and constants.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.knowledge import (
    PRICING_MESSAGE,
    HOURS_MESSAGE,
    HOURS_MARKDOWN,
    LOCATION_MESSAGE,
    WARRANTY_MESSAGE,
    FALLBACK_MESSAGE,
    UNKNOWN_MESSAGE,
    UNKNOWN_MESSAGE_SHORT,
    GREETING_MESSAGE,
    GREETING_MESSAGE_NAMED,
    GREETING_MESSAGE_TELEGRAM,
    STATUS_EMOJI,
    SERVICE_KEYWORDS,
    PRICING,
    SHOP_PHONE,
    SHOP_ADDRESS,
    SHOP_NAME,
)


class TestKnowledgeBase:
    """Verify all knowledge base strings are non-empty and well-formed."""

    def test_pricing_message_not_empty(self):
        assert len(PRICING_MESSAGE) > 50
        assert "Oil Change" in PRICING_MESSAGE
        assert "Brake Repair" in PRICING_MESSAGE

    def test_pricing_dict_coverage(self):
        assert "oil change" in PRICING
        assert "brake repair" in PRICING
        assert "engine diagnostics" in PRICING
        assert "tire services" in PRICING
        assert "ac repair" in PRICING
        assert "custom exhaust" in PRICING

    def test_hours_message_not_empty(self):
        assert len(HOURS_MESSAGE) > 30
        assert "Monday" in HOURS_MESSAGE
        assert "Sunday" in HOURS_MESSAGE

    def test_hours_markdown_has_formatting(self):
        assert "*" in HOURS_MARKDOWN
        assert "Monday" in HOURS_MARKDOWN

    def test_location_uses_config_address(self):
        assert SHOP_ADDRESS in LOCATION_MESSAGE

    def test_warranty_message_not_empty(self):
        assert "12-month" in WARRANTY_MESSAGE
        assert "20,000 km" in WARRANTY_MESSAGE

    def test_fallback_uses_phone(self):
        assert SHOP_PHONE in FALLBACK_MESSAGE

    def test_unknown_uses_phone(self):
        assert SHOP_PHONE in UNKNOWN_MESSAGE

    def test_greeting_not_empty(self):
        assert len(GREETING_MESSAGE) > 20
        assert "Marwa" in GREETING_MESSAGE

    def test_greeting_named_has_placeholder(self):
        assert "{name}" in GREETING_MESSAGE_NAMED

    def test_greeting_named_format(self):
        formatted = GREETING_MESSAGE_NAMED.format(name="TestUser")
        assert "TestUser" in formatted
        assert "{name}" not in formatted

    def test_greeting_telegram_has_placeholder(self):
        assert "{name}" in GREETING_MESSAGE_TELEGRAM

    def test_status_emoji_all_statuses(self):
        assert STATUS_EMOJI["scheduled"] == "📅"
        assert STATUS_EMOJI["confirmed"] == "✅"
        assert STATUS_EMOJI["in_progress"] == "🔧"
        assert STATUS_EMOJI["completed"] == "🏁"
        assert STATUS_EMOJI["cancelled"] == "❌"
        assert STATUS_EMOJI["no_show"] == "⚠️"

    def test_service_keywords_mapping(self):
        assert SERVICE_KEYWORDS["oil"] == "oil change"
        assert SERVICE_KEYWORDS["brake"] == "brake repair"
        assert SERVICE_KEYWORDS["tire"] == "tire services"
        assert SERVICE_KEYWORDS["ac"] == "ac repair"
        assert SERVICE_KEYWORDS["air conditioning"] == "ac repair"
        assert SERVICE_KEYWORDS["exhaust"] == "custom exhaust"
        assert SERVICE_KEYWORDS["diagnostic"] == "engine diagnostics"

    def test_shop_config_values(self):
        assert len(SHOP_PHONE) > 5
        assert len(SHOP_ADDRESS) > 5
        assert "Marwa" in SHOP_NAME
