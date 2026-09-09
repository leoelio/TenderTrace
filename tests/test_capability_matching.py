from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from tendertrace.capability_matching import (
    analyze_capability_matches,
    decide_capability_match,
    list_requirement_capability_matches,
    mark_capability_matches_for_recheck,
    upsert_capability,
)
from tendertrace.config import ModelMode, Settings
from tendertrace.db import connection, init_db
from tendertrace.llm.gateway import ModelCallResult
from tendertrace.opportunity_requirements import upsert_requirement


class _FakeGateway:
    def __init__(self, parsed: dict[str, object]) -> None:
        self.parsed = parsed

    def generate_json(self, *, system: str, user: str) -> ModelCallResult:
        return ModelCallResult(
            mode="local",
            provider="ollama",
            model="test-model",
            status="ok",
            parsed=self.parsed,
        )


class CapabilityMatchingTests(unittest.TestCase):
    def test_without_verified_evidence_never_claims_supported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice_and_requirement(settings)
            upsert_capability(
                settings,
                capability_key="CAP-DRAFT",
                title="未核验服务器方案",
                capability_type="product",
                evidence_text="内部整理材料。",
                source_url="https://example.com/internal/cap-draft",
                source_locator="第 1 页",
                verification_status="draft",
            )

            result = analyze_capability_matches(settings, "notice-1")
            matches = list_requirement_capability_matches(settings, "notice-1")

        self.assertEqual(result["mode"], "evidence_only")
        self.assertEqual(result["verified_capability_count"], 0)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].verdict, "needs_evidence")
        self.assertEqual(matches[0].capability_id, "")

    def test_model_can_only_reference_verified_capability_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _model_settings(Path(tmp))
            _insert_notice_and_requirement(settings)
            capability = _verified_capability(settings)

            result = analyze_capability_matches(
                settings,
                "notice-1",
                gateway=_FakeGateway(
                    {
                        "matches": [
                            {
                                "capability_id": capability.id,
                                "verdict": "supported",
                                "confidence": 88,
                                "rationale": "证据中列明同型号算力服务器并给出交付范围。",
                            },
                            {
                                "capability_id": "invented-capability",
                                "verdict": "supported",
                                "confidence": 100,
                                "rationale": "不应被接受。",
                            },
                        ]
                    }
                ),
            )
            matches = list_requirement_capability_matches(settings, "notice-1")

        self.assertEqual(result["mode"], "ai_assisted")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].capability_id, capability.id)
        self.assertEqual(matches[0].verdict, "supported")
        self.assertEqual(matches[0].status, "proposed")

    def test_human_confirmation_and_notice_change_recheck_are_auditable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _model_settings(Path(tmp))
            requirement = _insert_notice_and_requirement(settings)
            capability = _verified_capability(settings)
            analyze_capability_matches(
                settings,
                "notice-1",
                gateway=_FakeGateway(
                    {
                        "matches": [
                            {
                                "capability_id": capability.id,
                                "verdict": "supported",
                                "confidence": 86,
                                "rationale": "技术规格存在明确对应。",
                            }
                        ]
                    }
                ),
            )
            proposed = list_requirement_capability_matches(settings, "notice-1")[0]
            decided = decide_capability_match(
                settings,
                "notice-1",
                proposed.id,
                verdict="supported",
                actor="技术负责人",
                note="已核对产品规格书第 2 页。",
                accept=True,
            )
            rechecked = mark_capability_matches_for_recheck(settings, "notice-1", {requirement.id})
            refreshed = list_requirement_capability_matches(settings, "notice-1")[0]
            with connection(settings) as conn:
                event_count = conn.execute(
                    "SELECT COUNT(*) AS count FROM opportunity_events WHERE action = 'capability_match_decided'"
                ).fetchone()["count"]

        self.assertEqual(decided.status, "confirmed")
        self.assertEqual(rechecked, 1)
        self.assertEqual(refreshed.status, "recheck")
        self.assertEqual(refreshed.decided_by, "技术负责人")
        self.assertEqual(event_count, 1)

    def test_review_board_marks_confirmed_match_for_recheck_when_notice_evidence_changes(self) -> None:
        from unittest.mock import patch

        from tendertrace.requirement_review_board import sync_requirement_review_cases

        with tempfile.TemporaryDirectory() as tmp:
            settings = _model_settings(Path(tmp))
            requirement = _insert_notice_and_requirement(settings)
            capability = _verified_capability(settings)
            analyze_capability_matches(
                settings,
                "notice-1",
                gateway=_FakeGateway(
                    {"matches": [{"capability_id": capability.id, "verdict": "supported", "confidence": 86, "rationale": "规格对应。"}]}
                ),
            )
            proposed = list_requirement_capability_matches(settings, "notice-1")[0]
            decide_capability_match(
                settings,
                "notice-1",
                proposed.id,
                verdict="supported",
                actor="技术负责人",
                note="已人工核验。",
                accept=True,
            )
            with patch(
                "tendertrace.requirement_review_board.requirement_change_impact",
                return_value={"items": [{"id": requirement.id}]},
            ):
                result = sync_requirement_review_cases(settings, "notice-1")
            refreshed = list_requirement_capability_matches(settings, "notice-1")[0]

        self.assertEqual(result["capability_recheck_count"], 1)
        self.assertEqual(refreshed.status, "recheck")

    def test_rerunning_ai_does_not_overwrite_human_confirmed_conclusion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _model_settings(Path(tmp))
            _insert_notice_and_requirement(settings)
            capability = _verified_capability(settings)
            analyze_capability_matches(
                settings,
                "notice-1",
                gateway=_FakeGateway(
                    {"matches": [{"capability_id": capability.id, "verdict": "supported", "confidence": 84, "rationale": "首次建议。"}]}
                ),
            )
            first = list_requirement_capability_matches(settings, "notice-1")[0]
            decide_capability_match(
                settings,
                "notice-1",
                first.id,
                verdict="gap",
                actor="技术负责人",
                note="人工发现型号不一致。",
                accept=True,
            )
            analyze_capability_matches(
                settings,
                "notice-1",
                gateway=_FakeGateway(
                    {"matches": [{"capability_id": capability.id, "verdict": "supported", "confidence": 99, "rationale": "后续模型建议。"}]}
                ),
            )
            refreshed = list_requirement_capability_matches(settings, "notice-1")[0]

        self.assertEqual(refreshed.status, "confirmed")
        self.assertEqual(refreshed.verdict, "gap")
        self.assertEqual(refreshed.rationale, "首次建议。")
        self.assertEqual(refreshed.decision_note, "人工发现型号不一致。")

    def test_api_exposes_evidence_and_decision_workflow(self) -> None:
        from unittest.mock import patch

        from fastapi.testclient import TestClient
        from tendertrace.app import api as api_module

        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice_and_requirement(settings)
            with patch.object(api_module.Settings, "load", return_value=settings):
                client = TestClient(api_module.create_app())
                saved = client.post(
                    "/api/capabilities",
                    json={
                        "capability_key": "CAP-API",
                        "title": "已核验服务器产品规格",
                        "capability_type": "product",
                        "evidence_text": "规格书列明服务器配置与交付边界。",
                        "source_url": "https://example.com/cap-api",
                        "source_locator": "规格书第 2 页",
                        "verification_status": "verified",
                    },
                )
                analyzed = client.post("/api/opportunities/notice-1/capability-matches/analyze")
                listed = client.get("/api/opportunities/notice-1/capability-matches")

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(analyzed.status_code, 200)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["items"][0]["verdict"], "needs_evidence")
        self.assertEqual(listed.json()["summary"]["needs_evidence_count"], 1)


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text(
        "TENDERTRACE_DB_PATH=data/test.sqlite3\nTENDERTRACE_SCHEDULER_ENABLED=false\n",
        encoding="utf-8",
    )
    settings = Settings.load(root)
    init_db(settings)
    return settings


def _model_settings(root: Path) -> Settings:
    return replace(
        _settings(root),
        model_mode=ModelMode.LOCAL,
        model_enhancement_enabled=True,
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="test-model",
    )


def _insert_notice_and_requirement(settings: Settings):
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(id, source_site, source_url, canonical_url, title)
            VALUES ('notice-1', 'ccgp', 'https://example.com/notice-1',
                    'https://example.com/notice-1', '服务器采购项目')
            """
        )
    return upsert_requirement(
        settings,
        notice_id="notice-1",
        requirement_key="TECH-01",
        requirement_type="qualification",
        title="服务器技术规格满足采购要求",
        evidence_text="投标产品须满足招标文件所列服务器技术规格。",
        source_url="https://example.com/notice-1",
        source_locator="招标文件第 3 页",
        mandatory=True,
        confidence=80,
    )


def _verified_capability(settings: Settings):
    return upsert_capability(
        settings,
        capability_key="CAP-SERVER-01",
        title="服务器产品规格与交付说明",
        capability_type="product",
        evidence_text="规格书列明服务器配置、性能参数和交付范围。",
        source_url="https://example.com/cap-server-01",
        source_locator="规格书第 2 页",
        verification_status="verified",
        actor="证据管理员",
    )


if __name__ == "__main__":
    unittest.main()
