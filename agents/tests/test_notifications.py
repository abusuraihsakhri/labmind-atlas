import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["AUDIT_SECRET_KEY"] = "test-audit-secret-key-for-testing-only"
os.environ["TIER2_AUTH_SECRET"] = "test-tier2-secret"
os.environ["TIER3_AUTH_SECRET"] = "test-tier3-secret"
os.environ["SERVICE_AUTH_SECRET"] = "test-service-secret"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

from agents.notifications import send_email, send_sms, notify_critical_value


class TestNotifications:
    def test_email_skipped_without_config(self):
        result = send_email("test@example.com", "Test", "<p>Hello</p>")
        assert result is False

    def test_sms_skipped_without_config(self):
        result = send_sms("+1234567890", "Test message")
        assert result is False

    def test_notify_critical_value_no_config(self):
        notify_critical_value(
            clinician_email=None,
            clinician_phone=None,
            specimen_token="SPECIMEN_abc123",
            value_summary="Critical potassium",
            routed_at="2026-08-24T12:00:00Z",
        )
