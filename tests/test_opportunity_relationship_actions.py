from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.opportunity_relationship_actions import (
    create_relationship_action,
    mark_relationship_action_task,
    relationship_action_snapshots,
    update_relationship_action,
)
from tendertrace.opportunity_stakeholders import upsert_stakeholder
from tendertrace.opportunity_team import upsert_team_member


class OpportunityRelationshipActionTests(unittest.TestCase):
    def test_action_requires_valid_opportunity_relations_and_completion_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)

            with self.assertRaisesRegex(ValueError, "stakeholder_id"):
                create_relationship_action(
                    settings,
                    notice_id="notice-1",
                    stakeholder_id="missing-stakeholder",
                    title="确认预算审批链路",
                    due_at="2026-08-18T09:00:00+08:00",
                )
            action = create_relationship_action(
                settings,
                notice_id="notice-1",
                title="确认预算审批链路",
                due_at="2026-08-18T09:00:00+08:00",
            )
            with self.assertRaisesRegex(ValueError, "outcome_note"):
                update_relationship_action(
                    settings,
                    notice_id="notice-1",
                    action_id=action.id,
                    status="completed",
                )

    def test_creation_is_idempotent_and_records_audit_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            stakeholder = _stakeholder(settings)
            member = upsert_team_member(
                settings,
                notice_id="notice-1",
                member_name="张三",
                member_open_id="ou_owner",
                role="solution",
            )

            first = create_relationship_action(
                settings,
                notice_id="notice-1",
                stakeholder_id=stakeholder.id,
                title="与客户确认决策标准",
                due_at="2026-08-18T09:00:00+08:00",
                priority="high",
                assignee_member_id=member.id,
                source_type="stakeholder_strategy",
                source_ref=stakeholder.id,
            )
            second = create_relationship_action(
                settings,
                notice_id="notice-1",
                stakeholder_id=stakeholder.id,
                title="与客户确认决策标准",
                due_at="2026-08-18T09:00:00+08:00",
                priority="high",
                assignee_member_id=member.id,
                source_type="stakeholder_strategy",
                source_ref=stakeholder.id,
            )
            with connection(settings) as conn:
                action_count = conn.execute(
                    "SELECT COUNT(*) FROM opportunity_relationship_actions"
                ).fetchone()[0]
                event_count = conn.execute(
                    "SELECT COUNT(*) FROM opportunity_events "
                    "WHERE action = 'relationship_action_created'"
                ).fetchone()[0]

        self.assertEqual(first.id, second.id)
        self.assertEqual(first.assignee_member_name, "张三")
        self.assertEqual(action_count, 1)
        self.assertEqual(event_count, 1)

    def test_summary_exposes_overdue_unassigned_and_completed_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            overdue = create_relationship_action(
                settings,
                notice_id="notice-1",
                title="核验高影响关键人立场",
                due_at="2026-08-16T10:00:00+08:00",
                priority="critical",
            )
            completed = create_relationship_action(
                settings,
                notice_id="notice-1",
                title="确认初次沟通窗口",
                due_at="2026-08-17T10:00:00+08:00",
            )
            update_relationship_action(
                settings,
                notice_id="notice-1",
                action_id=completed.id,
                status="completed",
                outcome_note="已确认下次会议时间并形成纪要。",
            )

            summary = relationship_action_snapshots(
                settings,
                ["notice-1"],
                now=datetime(2026, 8, 16, 4, tzinfo=timezone.utc),
            )["notice-1"]

        self.assertEqual(summary["open_count"], 1)
        self.assertEqual(summary["completed_count"], 1)
        self.assertEqual(summary["overdue_count"], 1)
        self.assertEqual(summary["unassigned_count"], 1)
        self.assertEqual(summary["completion_rate"], 50)
        self.assertEqual(summary["next_action"]["id"], overdue.id)
        self.assertEqual(summary["next_action"]["effective_status"], "overdue")

    def test_feishu_task_state_updates_local_action_without_losing_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            action = create_relationship_action(
                settings,
                notice_id="notice-1",
                title="确认采购流程",
                due_at="2026-08-18T09:00:00+08:00",
            )

            linked = mark_relationship_action_task(
                settings,
                action_id=action.id,
                task_guid="task-guid",
                task_status="open",
                synced_at="2026-08-16T08:00:00+00:00",
            )
            completed = mark_relationship_action_task(
                settings,
                action_id=action.id,
                task_status="completed",
                completed_at="2026-08-17T08:00:00+00:00",
            )
            with_outcome = update_relationship_action(
                settings,
                notice_id="notice-1",
                action_id=action.id,
                status="completed",
                outcome_note="已确认采购流程和下一次沟通安排。",
            )

        self.assertEqual(linked.feishu_task_guid, "task-guid")
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.completed_at, "2026-08-17T08:00:00+00:00")
        self.assertEqual(with_outcome.completed_at, "2026-08-17T08:00:00+00:00")


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
            VALUES ('notice-1', 'ccgp', 'https://example.com/1',
                    'https://example.com/1', '服务器采购项目')
            """
        )


def _stakeholder(settings: Settings):
    return upsert_stakeholder(
        settings,
        notice_id="notice-1",
        stakeholder_name="李总",
        organization_name="示例采购单位",
        role="economic_buyer",
        influence="high",
        stance="unknown",
        relationship_strength="weak",
        next_action="与客户确认决策标准",
        evidence_source="客户访谈",
        evidence_text="会议纪要确认该成员参与项目决策。",
    )


if __name__ == "__main__":
    unittest.main()
