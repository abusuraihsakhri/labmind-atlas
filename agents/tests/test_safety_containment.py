"""P0 regression tests: unverified critical signals must never notify.

Uses stubs for optional ML/ORM dependencies so containment checks run in CI
without downloading models or requiring PostgreSQL.
"""
import ast
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

AGENTS = Path(__file__).resolve().parents[1]


def fake_module(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


class Proposed:
    def __init__(self, **fields):
        self.__dict__.update(fields)


def load_critical_worker():
    fake_base = fake_module(
        "agents.base",
        ActionProposed=Proposed,
        secure_invoke=lambda *_args: types.SimpleNamespace(
            content=json.dumps({
                "is_critical": True,
                "value_summary": "LLM-flagged text, not verified",
                "confidence": 0.95,
                "reasoning": "Model-only signal",
            })
        ),
    )
    fake_sqlalchemy = fake_module("sqlalchemy")
    fake_sqlalchemy.__path__ = []
    modules = {
        "sqlalchemy": fake_sqlalchemy,
        "sqlalchemy.orm": fake_module("sqlalchemy.orm", Session=object),
        "agents.llm_factory": fake_module("agents.llm_factory", get_llm=lambda **_kwargs: None),
        "agents.atlas": fake_module("agents.atlas", ContextPacket=object),
        "agents.base": fake_base,
        "langchain_core": fake_module("langchain_core"),
        "langchain_core.messages": fake_module(
            "langchain_core.messages",
            SystemMessage=lambda content: types.SimpleNamespace(content=content),
            HumanMessage=lambda content: types.SimpleNamespace(content=content),
        ),
    }
    spec = importlib.util.spec_from_file_location(
        "isolated_critical_worker_p0", AGENTS / "critical_worker.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
        yield module, modules


class RejectingDatabase:
    def add(self, _value):
        raise AssertionError("Unverified detection must not persist a routed alert")

    def commit(self):
        raise AssertionError("Unverified detection must not commit a routed alert")


class SafetyContainmentTests(unittest.TestCase):
    def test_regex_flag_generates_review_only_proposal(self):
        for module, _ in load_critical_worker():
            worker = module.CriticalValueRouterWorker()
            context = types.SimpleNamespace(
                history=[{"comments": "CRITICAL VALUE: potassium 6.8 mmol/L"}],
                working_state={"specimen_token": "SPECIMEN_synthetic"},
            )
            proposal = worker.analyze(context, RejectingDatabase(), "CLINICIAN_synthetic")
            self.assertEqual(proposal.action_type, "REVIEW_UNVERIFIED_CRITICAL_SIGNAL")
            self.assertEqual(proposal.payload["validation_status"], "unverified_free_text")
            self.assertIs(proposal.payload["dispatch_allowed"], False)
            self.assertNotIn("critical_event_id", proposal.payload)
            self.assertNotIn("routed_to_token", proposal.payload)

    def test_llm_flag_is_not_authorized_to_route(self):
        for module, modules in load_critical_worker():
            worker = module.CriticalValueRouterWorker()
            worker.model = object()
            context = types.SimpleNamespace(
                history=[{"comments": "Potential issue requiring review"}],
                working_state={"specimen_token": "SPECIMEN_synthetic"},
            )
            with patch.dict(sys.modules, modules):
                proposal = worker.analyze(context, RejectingDatabase(), "CLINICIAN_synthetic")
            self.assertEqual(proposal.action_type, "REVIEW_UNVERIFIED_CRITICAL_SIGNAL")
            self.assertIs(proposal.payload["dispatch_allowed"], False)

    def test_notification_entrypoint_blocks_even_when_destinations_are_present(self):
        from agents import notifications

        with (
            patch.object(notifications, "send_email", side_effect=AssertionError("SMTP invoked")),
            patch.object(notifications, "send_sms", side_effect=AssertionError("SMS invoked")),
        ):
            result = notifications.notify_critical_value(
                clinician_email="synthetic@example.invalid",
                clinician_phone="+15555550123",
                specimen_token="SPECIMEN_synthetic",
                value_summary="Unverified",
                routed_at="2026-11-01T00:00:00Z",
            )
            self.assertIs(result, False)

    def test_trust_stage_defaults_to_observe(self):
        main_tree = ast.parse((AGENTS / "main.py").read_text(encoding="utf-8"))
        defaults = [
            node.value for node in main_tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "GLOBAL_CONFIG" for t in node.targets)
        ]
        self.assertEqual(ast.literal_eval(defaults[0])["trust_stage"], "OBSERVE")

    def test_no_direct_critical_notification_calls_outside_transport(self):
        for source in AGENTS.glob("*.py"):
            if source.name == "notifications.py":
                continue
            tree = ast.parse(source.read_text(encoding="utf-8"))
            direct_calls = [
                n for n in ast.walk(tree)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == "notify_critical_value"
            ]
            self.assertFalse(direct_calls, f"Direct critical dispatch found in {source.name}")


if __name__ == "__main__":
    unittest.main()
