from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.opportunity_stakeholders import (
    remove_stakeholder,
    stakeholder_snapshots,
    stakeholder_summary,
    upsert_stakeholder,
)
from tendertrace.workflow import update_workflow


class OpportunityStakeholderTests(unittest.TestCase):
    def test_stakeholder_requires_traceable_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)

            with self.assertRaisesRegex(ValueError, "evidence_text"):
                upsert_stakeholder(
                    settings,
                    notice_id="notice-1",
                    stakeholder_name="客户经理",
                    role="champion",
                    next_action="确认预算范围",
                    evidence_source="客户访谈",
                    evidence_text="",
                )

    def test_stakeholder_upsert_is_idempotent_and_audited(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)

            first = _upsert(settings, name="李总", role="economic_buyer")
            second = _upsert(
                settings,
                name="李总",
                role="economic_buyer",
                relationship_strength="strong",
            )
            with connection(settings) as conn:
                row_count = conn.execute(
                    "SELECT COUNT(*) FROM opportunity_stakeholders"
                ).fetchone()[0]
                event_count = conn.execute(
                    "SELECT COUNT(*) FROM opportunity_events "
                    "WHERE action = 'stakeholder_upserted'"
                ).fetchone()[0]

        self.assertEqual(first.id, second.id)
        self.assertEqual(second.relationship_strength, "strong")
        self.assertEqual(row_count, 1)
        self.assertEqual(event_count, 2)

    def test_stage_coverage_and_relationship_risk_are_data_driven(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            workflow = update_workflow(
                settings,
                "notice-1",
                owner_name="张三",
            )
            pursuing = replace(workflow, stage="pursuing", stage_label="策略制定")
            decision = _upsert(
                settings,
                name="李总",
                role="economic_buyer",
                influence="high",
                stance="resistant",
                relationship_strength="weak",
                next_action="由商务负责人验证价格阻力并形成应对方案",
            )
            summary = stakeholder_snapshots(
                settings,
                {"notice-1": pursuing},
            )["notice-1"]
            remove_stakeholder(
                settings,
                notice_id="notice-1",
                stakeholder_id=decision.id,
            )
            after_removal = stakeholder_snapshots(
                settings,
                {"notice-1": pursuing},
            )["notice-1"]

        self.assertEqual(summary["coverage_score"], 67)
        self.assertEqual(summary["missing_roles"], ["内部支持者"])
        self.assertEqual(summary["risk_level"], "critical")
        self.assertEqual(
            summary["stakeholders"][0]["owner_member_name"],
            "张三",
        )
        self.assertEqual(
            summary["stakeholders"][0]["owner_source"],
            "opportunity_owner",
        )
        self.assertTrue(
            any("价格阻力" in action for action in summary["strategy_actions"])
        )
        self.assertEqual(after_removal["stakeholder_count"], 0)

    def test_empty_terminal_stage_has_no_artificial_gap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            workflow = update_workflow(settings, "notice-1")
            archived = replace(workflow, stage="archived", stage_label="已归档")

        summary = stakeholder_summary(archived, [])
        self.assertEqual(summary["coverage_score"], 100)
        self.assertEqual(summary["risk_level"], "normal")

    def test_unmapped_identified_lead_does_not_claim_full_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            workflow = update_workflow(settings, "notice-1")

        summary = stakeholder_summary(workflow, [])
        self.assertEqual(summary["coverage_score"], 0)
        self.assertEqual(summary["status"], "not_started")
        self.assertEqual(summary["status_label"], "关系尚未建档")


def _upsert(
    settings: Settings,
    *,
    name: str,
    role: str,
    influence: str = "medium",
    stance: str = "unknown",
    relationship_strength: str = "developing",
    next_action: str = "确认决策标准与下一次沟通安排",
):
    return upsert_stakeholder(
        settings,
        notice_id="notice-1",
        stakeholder_name=name,
        organization_name="示例采购单位",
        role=role,
        influence=influence,
        stance=stance,
        relationship_strength=relationship_strength,
        next_action=next_action,
        evidence_source="客户访谈",
        evidence_text="会议纪要已确认该成员参与项目决策。",
        actor="ou_owner",
    )


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text(
        "TENDERTRACE_DB_PATH=data/test.sqlite3\n",
        encoding="utf-8",
    )
    settings = Settings.load(root)
    init_db(settings)
    return settings


def _insert_notice(settings: Settings) -> None:
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(id, source_site, source_url, canonical_url, title)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "notice-1",
                "ccgp",
                "https://example.com/notice-1",
                "https://example.com/notice-1",
                "服务器采购项目",
            ),
        )


if __name__ == "__main__":
    unittest.main()
