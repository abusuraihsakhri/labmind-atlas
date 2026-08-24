import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from agents.atlas import ContextPacket
    HAS_ATLAS = True
except ImportError:
    HAS_ATLAS = False


@pytest.mark.skipif(not HAS_ATLAS, reason="sentence-transformers not installed")
class TestContextPacket:
    def test_to_dict(self):
        packet = ContextPacket(
            working_state={"token": "abc"},
            history=[{"event": "ORDERED"}],
            episodic_recalls=[{"summary": "similar case"}],
            semantic_rules=[{"rule": "TAT", "value": 60}]
        )
        result = packet.to_dict()
        assert result["working_state"]["token"] == "abc"
        assert len(result["history"]) == 1
        assert len(result["episodic_recalls"]) == 1
        assert len(result["semantic_rules"]) == 1

    def test_empty_context(self):
        packet = ContextPacket({}, [], [], [])
        result = packet.to_dict()
        assert result["working_state"] == {}
        assert result["history"] == []
