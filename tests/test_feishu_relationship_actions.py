from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.integrations.feishu import FeishuError
from tendertrace.integrations.feishu_relationship_actions import (
    create_relationship_action_task,
    sync_relationship_action_tasks,
)
from tendertrace.opportunity_relationship_actions import (
    create_relationship_action,
    relationship_action,
)
from tendertrace.opportunity_stakeholders import upsert_stakeholder
from tendertrace.opportunity_team import upsert_team_member


class _RelationshipTaskClient:
    def __init__(self, tasks: dict[str, dict[str, object]] | None = None) -> None:
        self.tasks = tasks or {}
        self.create_calls: list[dict[str, object]] = []

    def create_task(self, **kwargs):
        self.create_calls.append(kwargs)
        return {"data": {"task": {"guid": "relationship-task-guid"}}}

    def get_task(self, task_guid: str):
        if task_guid not in self.tasks:
            raise FeishuError("task unavailable")
        return {"data": {"task": self.tasks[task_guid]}}


class _FailedCreateClient(_RelationshipTaskClient):
    def create_task(self, **kwargs):
        raise FeishuError("permission denied")


class _BitableResult:
    status = "sent"
    message = ""


class FeishuRelationshipActionTests(unittest.TestCase):
    def test_task_creation_is_assigned_idempotent_and_does_not_copy_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            action = _action(settings, assigned=True)
            client = _RelationshipTaskClient()

            first = create_relationship_action_task(
                settings,
                action.id,
                client=client,
            )
            second = create_relationship_action_task(
                settings,
                action.id,
                client=client,
            )

        self.assertEqual(first.status, "created")
        self.assertTrue(first.assigned)
        self.assertEqual(second.status, "reused")
        self.assertEqual(len(client.create_calls), 1)
        call = client.create_calls[0]
        self.assertEqual(call["assignee_open_id"], "ou_solution")
        self.assertNotIn("会议纪要确认", str(call["description"]))
        self.assertIn("服务器采购项目", str(call["description"]))

    def test_task_creation_failure_keeps_retryable_local_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            action = _action(settings)

            with self.assertRaises(FeishuError):
                create_relationship_action_task(
                    settings,
                    action.id,
                    client=_FailedCreateClient(),
                )
            stored = relationship_action(settings, action.id)

        self.assertEqual(stored.status, "open")
        self.assertEqual(stored.feishu_task_guid, "")
        self.assertIn("permission denied", stored.feishu_sync_error)

    def test_sync_updates_remote_status_and_reports_missing_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            completed = _action(settings, title="确认预算", due_at="2026-08-18T09:00+08:00")
            overdue = _action(settings, title="确认采购流程", due_at="2026-08-15T09:00+08:00")
            first_client = _RelationshipTaskClient()
            create_relationship_action_task(settings, completed.id, client=first_client)
            with connection(settings) as conn:
                conn.execute(
                    "UPDATE opportunity_relationship_actions SET feishu_task_guid = ? WHERE id = ?",
                    ("overdue-guid", overdue.id),
                )
            client = _RelationshipTaskClient(
                {
                    "relationship-task-guid": {"completed_at": "1786924800000"},
                    "overdue-guid": {
                        "completed_at": "0",
                        "due": {"timestamp": "1786726800000"},
                    },
                }
            )
            updates: list[dict[str, object]] = []

            result = sync_relationship_action_tasks(
                settings,
                client=client,
                now=datetime(2026, 8, 16, 12, tzinfo=timezone.utc),
                bitable_updater=lambda _settings, **kwargs: (
                    updates.append(kwargs) or _BitableResult()
                ),
            )
            completed_status = relationship_action(settings, completed.id).status

        self.assertEqual(result.status, "finished")
        self.assertEqual(result.scanned_count, 2)
        self.assertEqual(result.updated_count, 2)
        self.assertEqual(result.completed_count, 1)
        self.assertEqual(result.overdue_count, 1)
        self.assertEqual(result.outcome_pending_count, 1)
        self.assertEqual(result.bitable_updated_count, 1)
        self.assertEqual(len(updates), 1)
        self.assertEqual(completed_status, "completed")


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text(
        "TENDERTRACE_DB_PATH=data/test.sqlite3\n",
        encoding="utf-8",
    )
    settings = Settings.load(root)
    init_db(settings)
    _insert_notice(settings)
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


def _action(
    settings: Settings,
    *,
    assigned: bool = False,
    title: str = "确认决策标准",
    due_at: str = "2026-08-18T09:00+08:00",
):
    stakeholder = upsert_stakeholder(
        settings,
        notice_id="notice-1",
        stakeholder_name="李总",
        organization_name="示例采购单位",
        role="economic_buyer",
        influence="high",
        stance="unknown",
        relationship_strength="weak",
        next_action=title,
        evidence_source="客户访谈",
        evidence_text="会议纪要确认该成员参与项目决策。",
    )
    member_id = ""
    if assigned:
        member_id = upsert_team_member(
            settings,
            notice_id="notice-1",
            member_name="方案专家",
            member_open_id="ou_solution",
            role="solution",
        ).id
    return create_relationship_action(
        settings,
        notice_id="notice-1",
        stakeholder_id=stakeholder.id,
        title=title,
        due_at=due_at,
        assignee_member_id=member_id,
        source_type="stakeholder_strategy",
        source_ref=stakeholder.id,
    )


if __name__ == "__main__":
    unittest.main()
