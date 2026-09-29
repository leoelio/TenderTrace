from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from tendertrace.capability_matching import analyze_capability_matches, upsert_capability
from tendertrace.config import ModelMode, Settings
from tendertrace.db import connection, init_db
from tendertrace.llm.gateway import ModelCallResult
from tendertrace.opportunity_requirements import upsert_requirement
from tendertrace.requirement_review_agents import (
    AGENT_PERSONAS,
    list_review_agent_runs,
    list_review_opinions,
    retry_review_agent,
    review_agent_suggestions,
    run_review_agents,
)
from tendertrace.requirement_review_board import (
    list_requirement_review_cases,
    resolve_requirement_review_case,
    sync_requirement_review_cases,
)


class _RoleGateway:
    def __init__(self, decisions: dict[str, str] | None = None, fail_roles: set[str] | None = None):
        self.decisions = decisions or {}
        self.fail_roles = fail_roles or set()
        self.calls: list[str] = []

    def generate_json(self, *, system: str, user: str) -> ModelCallResult:
        role = next(key for key in AGENT_PERSONAS if f"（{key}）" in system)
        self.calls.append(role)
        if role in self.fail_roles:
            return ModelCallResult(mode="local", provider="test", model="role-test", status="failed", error=f"{role} timeout")
        decision = self.decisions.get(role, "accept")
        return ModelCallResult(
            mode="local",
            provider="test",
            model="role-test",
            status="ok",
            parsed={
                "decision": decision,
                "confidence": 88 if decision == "accept" else 72,
                "rationale": f"{role} 基于指定要求和能力证据形成独立意见。",
                "evidence_ids": [],
                "risks": ["证书有效期需持续关注"] if role == "evidence_audit" else [],
                "pending_items": ["人工裁决"] if decision != "accept" else [],
                "recommended_actions": ["打开证据显微镜"] if decision != "accept" else ["进入执行计划"],
            },
        )


class ReviewOpponentTests(unittest.TestCase):
    def test_review_board_api_exposes_runs_conflicts_and_structured_opinions(self) -> None:
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from tendertrace.app import api as api_module

        with tempfile.TemporaryDirectory() as tmp:
            settings, review_id, _ = _fixture(Path(tmp))
            run_review_agents(settings, "notice-review-opponent", gateway=_RoleGateway({"evidence_audit": "reject"}), review_ids=[review_id])
            with patch.object(api_module.Settings, "load", return_value=settings):
                client = TestClient(api_module.create_app())
                response = client.get("/api/opportunities/notice-review-opponent/review-board")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["agent_runtime"]["disagreement_count"], 1)
        self.assertTrue(body["agent_runs"][0]["evidence_scope_hash"])
        self.assertTrue(body["opinions"][0]["evidence_ids"])
        self.assertIn("recommended_actions", body["opinions"][0])

    def test_roles_share_revision_and_evidence_scope_and_disagreement_is_not_voted_away(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings, review_id, revision_id = _fixture(Path(tmp))
            gateway = _RoleGateway({"evidence_audit": "reject"})

            result = run_review_agents(settings, "notice-review-opponent", gateway=gateway, review_ids=[review_id])
            opinions = list_review_opinions(settings, "notice-review-opponent")
            suggestion = next(item for item in review_agent_suggestions(settings, "notice-review-opponent") if item["review_id"] == review_id)
            runs = list_review_agent_runs(settings, "notice-review-opponent")

            self.assertEqual(result["opinion_count"], 5)
            self.assertEqual({item.notice_revision_id for item in opinions}, {revision_id})
            self.assertTrue(all(item.evidence_ids for item in opinions))
            self.assertTrue(all(any(value.startswith("requirement:") for value in item.evidence_ids) for item in opinions))
            self.assertTrue(all(any(value.startswith("capability:") for value in item.evidence_ids) for item in opinions))
            self.assertEqual(suggestion["suggestion"], "escalate")
            self.assertEqual(suggestion["consensus_facts"], [])
            self.assertIn("conclusion_conflict", suggestion["conflict_types"])
            self.assertEqual(runs[0]["notice_revision_id"], revision_id)
            self.assertTrue(runs[0]["evidence_scope_hash"])
            self.assertEqual(runs[0]["prompt_version"], "review_opponent_v2")

    def test_one_role_failure_preserves_completed_opinions_and_can_retry_only_that_role(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings, review_id, _ = _fixture(Path(tmp))
            failed = run_review_agents(settings, "notice-review-opponent", gateway=_RoleGateway(fail_roles={"commercial"}), review_ids=[review_id])
            before = list_review_opinions(settings, "notice-review-opponent")
            failed_run = list_review_agent_runs(settings, "notice-review-opponent")[0]

            self.assertEqual(failed["failed_count"], 1)
            self.assertEqual(len(before), 4)
            self.assertEqual(failed_run["status"], "completed_with_errors")
            self.assertEqual(failed_run["failed_roles"][0]["agent_role"], "commercial")

            recovered_gateway = _RoleGateway()
            retry = retry_review_agent(settings, "notice-review-opponent", review_id, "commercial", gateway=recovered_gateway, actor="测试恢复")
            after = list_review_opinions(settings, "notice-review-opponent")
            self.assertEqual(retry["failed_count"], 0)
            self.assertEqual(recovered_gateway.calls, ["commercial"])
            self.assertEqual(len(after), 5)
            self.assertEqual({item.agent_role for item in before}, {item.agent_role for item in after if item.agent_role != "commercial"})

    def test_human_decision_is_not_overwritten_and_notice_change_runs_only_affected_roles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings, review_id, revision_id = _fixture(Path(tmp))
            run_review_agents(settings, "notice-review-opponent", gateway=_RoleGateway(), review_ids=[review_id])
            resolved = resolve_requirement_review_case(settings, "notice-review-opponent", review_id, decision="accepted", actor="总负责人", note="已核验证据与有效期")
            before = [(item.agent_role, item.updated_at) for item in list_review_opinions(settings, "notice-review-opponent")]
            rerun = run_review_agents(settings, "notice-review-opponent", gateway=_RoleGateway({"technical": "reject"}), review_ids=[review_id])
            after = [(item.agent_role, item.updated_at) for item in list_review_opinions(settings, "notice-review-opponent")]
            self.assertEqual(resolved.decision, "accepted")
            self.assertEqual(rerun["scanned_case_count"], 0)
            self.assertEqual(before, after)

            with connection(settings) as conn:
                changed_review_id = conn.execute(
                    "SELECT id FROM requirement_review_cases WHERE notice_id = 'notice-review-opponent' AND reason LIKE 'notice_change_impact:%' LIMIT 1"
                ).fetchone()[0]
            gateway = _RoleGateway()
            run_review_agents(settings, "notice-review-opponent", gateway=gateway, review_ids=[changed_review_id])
            self.assertEqual(gateway.calls, ["technical", "evidence_audit"])
            run = list_review_agent_runs(settings, "notice-review-opponent")[0]
            self.assertEqual(run["requested_roles"], ["technical", "evidence_audit"])


def _fixture(root: Path) -> tuple[Settings, str, str]:
    (root / ".env.local").write_text(
        "TENDERTRACE_DB_PATH=data/test.sqlite3\nTENDERTRACE_SCHEDULER_ENABLED=false\n",
        encoding="utf-8",
    )
    base = Settings.load(root)
    init_db(base)
    revision_id = "revision-review-001"
    with connection(base) as conn:
        conn.execute(
            """
            INSERT INTO notices(id, source_site, source_url, canonical_url, title, region, snapshot_sha256)
            VALUES ('notice-review-opponent', 'demo', 'https://example.com/review', 'https://example.com/review', '服务器会审项目', '北京', 'notice-snapshot-001')
            """
        )
        conn.execute(
            "INSERT INTO notice_revisions(id, notice_id, change_hash, changed_fields_json) VALUES (?, 'notice-review-opponent', 'change-001', '[\"content_text\"]')",
            (revision_id,),
        )
    upsert_requirement(
        base,
        notice_id="notice-review-opponent",
        requirement_key="TECH-OPP-01",
        requirement_type="technical",
        title="TT-X100 服务器技术与资质要求",
        evidence_text="产品型号：TT-X100，同时要求配套证书在投标日有效。",
        source_url="https://example.com/review",
        source_locator="招标文件第28页",
        mandatory=False,
        confidence=55,
        status="review",
        source_revision_id=revision_id,
        actor="测试",
    )
    upsert_capability(
        base,
        capability_key="CAP-OPP-X100",
        title="TT-X100 产品规格与证书",
        capability_type="product_parameter",
        evidence_text="规格书列示 TT-X100，证书有效至 2027-12-31。",
        source_url="https://example.com/capability",
        source_locator="规格书第3页",
        verification_status="verified",
        applicable_entity="示例科技有限公司",
        product_model="TT-X100",
        regions=["北京"],
        authorization_scope="北京政务项目",
        valid_until="2027-12-31",
        actor="证据管理员",
    )
    analyze_capability_matches(base, "notice-review-opponent")
    sync_requirement_review_cases(base, "notice-review-opponent")
    review_id = next(item.id for item in list_requirement_review_cases(base, "notice-review-opponent") if item.reason == "requirement_marked_for_review")
    settings = replace(base, model_mode=ModelMode.LOCAL, model_enhancement_enabled=True, ollama_base_url="http://127.0.0.1:11434", ollama_model="test-model")
    return settings, review_id, revision_id


if __name__ == "__main__":
    unittest.main()
