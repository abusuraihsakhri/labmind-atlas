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

from agents.base import assert_no_phi, SecurityException, ActionProposed, ActionExecutor


class TestPHIGuard:
    def test_blocks_raw_mrn(self):
        with pytest.raises(SecurityException, match="raw MRN"):
            assert_no_phi("Patient MRN-123456 has results")

    def test_blocks_patient_name(self):
        with pytest.raises(SecurityException, match="PHI keyword"):
            assert_no_phi("Patient John Doe arrived")

    def test_allows_deidentified_text(self):
        assert_no_phi("Specimen SPECIMEN_abc123 is processing normally")

    def test_allows_empty_text(self):
        assert_no_phi("")

    def test_blocks_phone_number(self):
        with pytest.raises(SecurityException, match="phone number"):
            assert_no_phi("Contact +971-50-123-4567 for urgent results")

    def test_allows_short_numbers(self):
        assert_no_phi("Test code 42 is valid")


class TestActionProposed:
    def test_valid_action(self):
        action = ActionProposed(
            action_type="TAT_DELAY_ALERT",
            specimen_token="SPECIMEN_abc123",
            payload={"risk_level": "red"},
            confidence=0.95,
            reasoning="Specimen is overdue"
        )
        assert action.action_type == "TAT_DELAY_ALERT"
        assert action.confidence == 0.95

    def test_confidence_bounds(self):
        action = ActionProposed(
            action_type="TEST",
            specimen_token="TOKEN",
            payload={},
            confidence=1.5,
            reasoning="test"
        )
        assert action.confidence == 1.5
