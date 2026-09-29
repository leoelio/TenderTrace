from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tendertrace.capability_matching import (
    analyze_capability_matches,
    decide_capability_match,
    list_capabilities,
    list_requirement_capability_matches,
    upsert_capability,
)
from tendertrace.capability_passport import (
    build_capability_passport,
    complete_gap_action,
    create_gap_action,
    similar_case_rankings,
    sync_project_results_to_passport,
)
from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.opportunity_outcomes import record_outcome
from tendertrace.opportunity_requirements import upsert_requirement


class CapabilityPassportTests(unittest.TestCase):
    def test_exact_model_snapshot_and_version_are_auditable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            requirement = _fixture(settings)
            capability = _capability(settings, "CAP-X100", "TT-X100")

            analyze_capability_matches(settings, "notice-passport")
            match = next(item for item in list_requirement_capability_matches(settings, "notice-passport") if item.capability_id == capability.id)
            self.assertEqual(match.verdict, "supported")
            self.assertTrue(match.capability_version_id)
            self.assertTrue(match.project_snapshot_id)

            decided = decide_capability_match(settings, "notice-passport", match.id, verdict="supported", actor="评审负责人", note="主体、型号和原文均核验", accept=True)
            self.assertEqual(decided.status, "confirmed")
            _capability(settings, "CAP-X100", "TT-X100", evidence="第二版规格书，型号与参数保持一致。")
            changed = next(item for item in list_requirement_capability_matches(settings, "notice-passport") if item.id == match.id)
            self.assertEqual(changed.status, "recheck")
            with connection(settings) as conn:
                versions = conn.execute("SELECT COUNT(*) FROM capability_versions WHERE capability_id = ?", (capability.id,)).fetchone()[0]
                decisions = conn.execute("SELECT COUNT(*) FROM capability_audit_events WHERE action = 'match_decided'", ()).fetchone()[0]
            self.assertEqual(versions, 2)
            self.assertEqual(decisions, 1)
            self.assertEqual(requirement.status, "confirmed")

    def test_model_mismatch_is_conflict_and_workspace_is_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _fixture(settings)
            _capability(settings, "CAP-X90", "TT-X90")
            _capability(settings, "CAP-OTHER", "TT-X100", workspace_id="other")

            result = analyze_capability_matches(settings, "notice-passport")
            conflict = next(item for item in result["items"] if item["capability_product_model"] == "TT-X90")
            self.assertEqual(conflict["verdict"], "conflict")
            self.assertEqual(conflict["conflict_code"], "model_mismatch")
            self.assertEqual(len(list_capabilities(settings, workspace_id="default")), 1)
            self.assertEqual(len(list_capabilities(settings, workspace_id="other")), 1)

    def test_gap_action_enters_workplan_and_completion_flows_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _fixture(settings)
            _capability(settings, "CAP-X90", "TT-X90")
            analyze_capability_matches(settings, "notice-passport")
            match = list_requirement_capability_matches(settings, "notice-passport")[0]

            action = create_gap_action(settings, "notice-passport", match.id, action_type="partner_support", actor="项目经理")
            with connection(settings) as conn:
                task = conn.execute("SELECT * FROM bid_plan_tasks WHERE id = ?", (action["bid_plan_task_id"],)).fetchone()
            self.assertEqual(task["milestone_type"], "capability_gap")
            self.assertEqual(task["formal"], 1)
            completed = complete_gap_action(settings, "notice-passport", action["id"], actor="伙伴经理", note="已取得项目授权函")
            self.assertEqual(completed["status"], "completed")
            passport = build_capability_passport(settings, "notice-passport")
            self.assertEqual(passport["summary"]["open_gap_action_count"], 0)

    def test_won_project_flows_back_to_similar_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _fixture(settings)
            capability = _capability(settings, "CAP-X100", "TT-X100")
            analyze_capability_matches(settings, "notice-passport")
            match = next(item for item in list_requirement_capability_matches(settings, "notice-passport") if item.capability_id == capability.id)
            decide_capability_match(settings, "notice-passport", match.id, verdict="supported", actor="负责人", note="核验通过", accept=True)
            record_outcome(settings, "notice-passport", {"result": "won", "reason_code": "technical_fit", "winner_name": "示例科技", "award_amount": 1200000, "currency": "CNY", "summary": "能力证据准确", "lessons": "保持型号证据版本", "evidence_text": "中标通知书（脱敏）"}, actor="复盘负责人")
            self.assertEqual(sync_project_results_to_passport(settings, "notice-passport")["synced_count"], 1)

            with connection(settings) as conn:
                conn.execute("INSERT INTO notices(id, source_site, source_url, canonical_url, title, region) VALUES ('notice-next', 'demo', 'https://example.com/next', 'https://example.com/next', '下一项目', '北京')")
            cases = similar_case_rankings(settings, "notice-next")
            self.assertEqual(cases[0]["result"], "won")
            self.assertEqual(cases[0]["sample_count"], 1)


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text(
        "TENDERTRACE_DB_PATH=data/test.sqlite3\n"
        "TENDERTRACE_SCHEDULER_ENABLED=false\n"
        "TENDERTRACE_MODEL_ENHANCEMENT_ENABLED=false\n",
        encoding="utf-8",
    )
    return Settings.load(root)


def _fixture(settings: Settings):
    init_db(settings)
    with connection(settings) as conn:
        conn.execute("INSERT INTO notices(id, source_site, source_url, canonical_url, title, region) VALUES ('notice-passport', 'demo', 'https://example.com/passport', 'https://example.com/passport', '政务服务器采购', '北京')")
    return upsert_requirement(settings, notice_id="notice-passport", requirement_key="TECH-01", requirement_type="technical", title="服务器型号要求", evidence_text="投标产品型号：TT-X100，参数应符合规格书。", source_url="https://example.com/passport", source_locator="采购文件第18页", mandatory=True, confidence=96, status="confirmed", actor="测试")


def _capability(settings: Settings, key: str, model: str, *, workspace_id: str = "default", evidence: str = "规格书明确列示型号和技术参数。"):
    return upsert_capability(settings, capability_key=key, title=f"服务器 {model} 产品参数", capability_type="product_parameter", evidence_text=evidence, source_url=f"https://example.com/{key}", source_locator="规格书第3页", verification_status="verified", workspace_id=workspace_id, applicable_entity="示例科技有限公司", product_model=model, regions=["北京"], source_file_name=f"{model}-规格书.pdf", valid_from="2026-01-01", valid_until="2027-12-31", industry="政府", sample_redacted=True, actor="证据管理员")


if __name__ == "__main__":
    unittest.main()
