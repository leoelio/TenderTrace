from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from tendertrace.config import ModelMode, Settings
from tendertrace.db import connection, init_db
from tendertrace.llm.gateway import ModelCallResult
from tendertrace.opportunity_requirements import list_requirements, upsert_requirement
from tendertrace.requirement_review_agents import (
    list_review_opinions,
    review_agent_suggestions,
    run_review_agents,
)
from tendertrace.requirement_review_board import (
    list_requirement_review_cases,
    sync_requirement_review_cases,
)


class _FakeGateway:
    """Returns scripted agent decisions keyed by agent_role."""

    def __init__(self, decision_map: dict[str, str]) -> None:
        self.decision_map = decision_map
        self.calls = 0

    def generate_json(self, *, system: str, user: str) -> ModelCallResult:
        self.calls += 1
        agent_role = json.loads(user)["agent_role"]
        decision = self.decision_map.get(agent_role, "accept")
        return ModelCallResult(
            mode="local",
            provider="ollama",
            model="test-model",
            status="ok",
            parsed={
                "decision": decision,
                "confidence": 80,
                "rationale": f"{agent_role} opinion",
                "concerns": [],
            },
        )


class RequirementReviewAgentsTests(unittest.TestCase):
    def test_unanimous_agents_produce_accept_suggestion_without_resolving_case(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _review_settings(Path(tmp))
            _insert_notice(settings)
            _requirement(settings)
            sync_requirement_review_cases(settings, "notice-1")
            case_before = list_requirement_review_cases(settings, "notice-1")[0]

            result = run_review_agents(
                settings,
                "notice-1",
                gateway=_FakeGateway(
                    {"compliance": "accept", "technical": "accept", "commercial": "accept", "evidence_audit": "accept"}
                ),
            )
            suggestions = review_agent_suggestions(settings, "notice-1")
            case_after = list_requirement_review_cases(settings, "notice-1")[0]

        self.assertEqual(result["mode"], "multi_agent")
        self.assertEqual(result["opinion_count"], 4)
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["suggestion"], "accept")
        self.assertEqual(suggestions[0]["consensus"], "unanimous")
        self.assertFalse(suggestions[0]["disagreement"])
        self.assertEqual(case_after.status, "pending")
        self.assertEqual(case_before.status, case_after.status)
        self.assertEqual(case_after.decision, "")

    def test_disagreeing_agents_escalate_with_disagreement_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _review_settings(Path(tmp))
            _insert_notice(settings)
            _requirement(settings)
            sync_requirement_review_cases(settings, "notice-1")

            result = run_review_agents(
                settings,
                "notice-1",
                gateway=_FakeGateway(
                    {"compliance": "accept", "technical": "reject", "commercial": "accept", "evidence_audit": "reject"}
                ),
            )
            suggestions = review_agent_suggestions(settings, "notice-1")

        self.assertEqual(result["mode"], "multi_agent")
        self.assertEqual(suggestions[0]["suggestion"], "escalate")
        self.assertTrue(suggestions[0]["disagreement"])
        self.assertEqual(suggestions[0]["consensus"], "split")
        self.assertEqual(suggestions[0]["votes"], {"accept": 2, "reject": 2})

    def test_rerun_is_idempotent_and_never_rewrites_requirement_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _review_settings(Path(tmp))
            _insert_notice(settings)
            requirement = _requirement(settings)
            sync_requirement_review_cases(settings, "notice-1")
            gateway = _FakeGateway({"compliance": "accept", "technical": "accept", "commercial": "accept", "evidence_audit": "accept"})

            first = run_review_agents(settings, "notice-1", gateway=gateway)
            second = run_review_agents(settings, "notice-1", gateway=gateway)
            opinions = list_review_opinions(settings, "notice-1")
            refreshed = list_requirements(settings, "notice-1")[0]

        self.assertEqual(first["opinion_count"], 4)
        self.assertEqual(second["opinion_count"], 4)
        self.assertEqual(len(opinions), 4)
        self.assertEqual(len({opinion.id for opinion in opinions}), 4)
        self.assertEqual(refreshed.status, requirement.status)
        self.assertEqual(refreshed.title, requirement.title)

    def test_disabled_model_degrades_to_rule_only_with_no_opinions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            _requirement(settings)
            sync_requirement_review_cases(settings, "notice-1")

            result = run_review_agents(settings, "notice-1")
            opinions = list_review_opinions(settings, "notice-1")

        self.assertEqual(result["mode"], "rule_only")
        self.assertEqual(result["opinion_count"], 0)
        self.assertEqual(opinions, [])

    def test_review_agent_api_is_wired_and_exposes_suggestions(self) -> None:
        from unittest.mock import patch

        from fastapi.testclient import TestClient

        from tendertrace.app import api as api_module

        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            _requirement(settings)
            sync_requirement_review_cases(settings, "notice-1")
            with patch.object(api_module.Settings, "load", return_value=settings):
                client = TestClient(api_module.create_app())
                ran = client.post("/api/opportunities/notice-1/review-board/agents")
                board = client.get("/api/opportunities/notice-1/review-board")

        self.assertEqual(ran.status_code, 200)
        self.assertEqual(ran.json()["mode"], "rule_only")
        self.assertIn("opinions", board.json())
        self.assertIn("suggestions", board.json())
        self.assertEqual(board.json()["suggestions"], [])


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text(
        "TENDERTRACE_DB_PATH=data/test.sqlite3\nTENDERTRACE_SCHEDULER_ENABLED=false\n",
        encoding="utf-8",
    )
    settings = Settings.load(root)
    init_db(settings)
    return settings


def _review_settings(root: Path) -> Settings:
    settings = _settings(root)
    return replace(
        settings,
        model_mode=ModelMode.LOCAL,
        model_enhancement_enabled=True,
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="test-model",
    )


def _insert_notice(settings: Settings) -> None:
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(id, source_site, source_url, canonical_url, title)
            VALUES ('notice-1', 'ccgp', 'https://example.com/notice-1',
                    'https://example.com/notice-1', '服务器采购项目')
            """
        )


def _requirement(settings: Settings):
    return upsert_requirement(
        settings,
        notice_id="notice-1",
        requirement_key="QUAL-01",
        requirement_type="qualification",
        title="营业执照有效",
        evidence_text="投标人须具有有效的营业执照。",
        source_url="https://example.com/notice-1",
        source_locator="招标文件第 3 页",
        mandatory=False,
        confidence=55,
        actor="测试",
    )


if __name__ == "__main__":
    unittest.main()
