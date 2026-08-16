from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.integrations.feishu import FeishuError
from tendertrace.integrations.feishu_tasks import sync_feishu_tasks
from tendertrace.workflow import get_workflow, update_workflow


class _TaskClient:
    def __init__(self, tasks: dict[str, dict[str, object]]) -> None:
        self.tasks = tasks

    def get_task(self, task_guid: str) -> dict[str, object]:
        task = self.tasks.get(task_guid)
        if task is None:
            raise FeishuError("task unavailable")
        return {"data": {"task": task}}


class _BitableResult:
    status = "sent"
    message = ""


class _FailedBitableResult:
    status = "failed"
    message = "record update rejected"


class FeishuTaskSyncTests(unittest.TestCase):
    def test_sync_updates_completed_open_and_overdue_tasks_without_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            for notice_id, task_guid in (
                ("notice-completed", "task-completed"),
                ("notice-open", "task-open"),
                ("notice-overdue", "task-overdue"),
            ):
                _insert_notice(settings, notice_id)
                update_workflow(settings, notice_id, feishu_task_guid=task_guid)
            calls: list[str] = []
            client = _TaskClient(
                {
                    "task-completed": {"completed_at": "1786838400000"},
                    "task-open": {"completed_at": "0", "due": {"timestamp": "1787011200000"}},
                    "task-overdue": {"completed_at": "0", "due": {"timestamp": "1786752000000"}},
                }
            )
            now = datetime(2026, 8, 16, 12, tzinfo=timezone.utc)
            def updater(_settings, *, notice_id, workflow):
                calls.append(notice_id)
                return _BitableResult()

            first = sync_feishu_tasks(
                settings,
                client=client,
                bitable_updater=updater,
                now=now,
            )
            second = sync_feishu_tasks(
                settings,
                client=client,
                bitable_updater=updater,
                now=now,
            )
            with connection(settings) as conn:
                event_count = conn.execute(
                    "SELECT COUNT(*) FROM opportunity_events WHERE action = 'feishu_task_sync'"
                ).fetchone()[0]
            completed_status = get_workflow(
                settings, "notice-completed"
            ).feishu_task_status

        self.assertEqual(first.status, "finished")
        self.assertEqual(first.scanned_count, 3)
        self.assertEqual(first.updated_count, 3)
        self.assertEqual(first.completed_count, 1)
        self.assertEqual(first.overdue_count, 1)
        self.assertEqual(first.bitable_updated_count, 3)
        self.assertEqual(first.bitable_failed_count, 0)
        self.assertEqual(second.updated_count, 0)
        self.assertEqual(event_count, 3)
        self.assertEqual(len(calls), 6)
        self.assertEqual(completed_status, "completed")

    def test_single_task_failure_does_not_stop_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            for notice_id, task_guid in (
                ("notice-ok", "task-ok"),
                ("notice-failed", "task-failed"),
            ):
                _insert_notice(settings, notice_id)
                update_workflow(settings, notice_id, feishu_task_guid=task_guid)

            result = sync_feishu_tasks(
                settings,
                client=_TaskClient({"task-ok": {"completed_at": "0"}}),
                bitable_updater=lambda *_args, **_kwargs: _BitableResult(),
            )

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.scanned_count, 2)
        self.assertEqual(result.failed_count, 1)
        self.assertEqual(result.failures[0]["notice_id"], "notice-failed")
        self.assertEqual(result.failures[0]["stage"], "task_read")

    def test_bitable_failure_is_reported_without_stopping_task_sync(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            _insert_notice(settings, "notice-bitable-failed")
            update_workflow(
                settings,
                "notice-bitable-failed",
                feishu_task_guid="task-ok",
            )

            result = sync_feishu_tasks(
                settings,
                client=_TaskClient({"task-ok": {"completed_at": "0"}}),
                bitable_updater=lambda *_args, **_kwargs: _FailedBitableResult(),
            )

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.bitable_updated_count, 0)
        self.assertEqual(result.bitable_failed_count, 1)
        self.assertEqual(result.failed_count, 1)
        self.assertEqual(result.failures[0]["stage"], "bitable_write")


def _insert_notice(settings: Settings, notice_id: str) -> None:
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(id, source_site, source_url, canonical_url, title)
            VALUES (?, 'ccgp', ?, ?, ?)
            """,
            (
                notice_id,
                f"https://example.com/{notice_id}",
                f"https://example.com/{notice_id}",
                notice_id,
            ),
        )
