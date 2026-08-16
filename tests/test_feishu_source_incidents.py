from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import init_db
from tendertrace.integrations.feishu_source_incidents import (
    list_source_incidents,
    sync_source_incidents,
    upsert_source_incident,
)


class _FakeClient:
    def __init__(self, task: dict[str, object]) -> None:
        self.task = task
        self.requests: list[str] = []

    def get_task(self, task_guid: str) -> dict[str, object]:
        self.requests.append(task_guid)
        return {"data": {"task": self.task}}


class FeishuSourceIncidentTests(unittest.TestCase):
    def test_completed_task_requires_source_recovery_before_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            now = datetime(2026, 8, 16, 10, 0, tzinfo=timezone.utc)
            upsert_source_incident(
                settings,
                snapshot=_snapshot("qianlima"),
                artifact_key="source_health_task:2026-08-16:test",
                task_guid="task-guid",
                assigned=True,
                due_at=now + timedelta(hours=4),
            )
            client = _FakeClient(
                {
                    "guid": "task-guid",
                    "completed_at": str(int((now - timedelta(minutes=10)).timestamp() * 1000)),
                    "due": {"timestamp": str(int((now + timedelta(hours=4)).timestamp() * 1000))},
                }
            )

            not_recovered = sync_source_incidents(
                settings,
                client=client,
                snapshot_loader=lambda *_args, **_kwargs: _snapshot("qianlima"),
                now=now,
            )
            waiting = list_source_incidents(settings)[0]
            recovered = sync_source_incidents(
                settings,
                client=client,
                snapshot_loader=lambda *_args, **_kwargs: _snapshot(),
                now=now + timedelta(minutes=5),
            )
            resolved = list_source_incidents(settings)[0]

        self.assertEqual(not_recovered.verification_failed_count, 1)
        self.assertEqual(waiting.status, "verification_failed")
        self.assertEqual(recovered.resolved_count, 1)
        self.assertEqual(resolved.status, "resolved")
        self.assertTrue(resolved.resolved_at)
        self.assertNotIn("task-guid", str(resolved.safe_dict()))

    def test_open_task_tracks_overdue_and_recovered_states(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            now = datetime(2026, 8, 16, 10, 0, tzinfo=timezone.utc)
            upsert_source_incident(
                settings,
                snapshot=_snapshot("ggzy"),
                artifact_key="source_health_task:2026-08-16:overdue",
                task_guid="task-overdue",
                assigned=False,
                due_at=now - timedelta(hours=1),
            )
            client = _FakeClient(
                {
                    "guid": "task-overdue",
                    "completed_at": "0",
                    "due": {"timestamp": str(int((now - timedelta(hours=1)).timestamp() * 1000))},
                }
            )

            overdue = sync_source_incidents(
                settings,
                client=client,
                snapshot_loader=lambda *_args, **_kwargs: _snapshot("ggzy"),
                now=now,
            )
            recovered = sync_source_incidents(
                settings,
                client=client,
                snapshot_loader=lambda *_args, **_kwargs: _snapshot(),
                now=now + timedelta(minutes=5),
            )
            incident = list_source_incidents(settings)[0]

        self.assertEqual(overdue.overdue_count, 1)
        self.assertEqual(recovered.recovered_count, 1)
        self.assertEqual(incident.status, "recovered_pending_close")
        self.assertEqual(client.requests, ["task-overdue", "task-overdue"])


def _snapshot(*sites: str) -> dict[str, object]:
    return {
        "checked_at": "2026-08-16T18:00:00+08:00",
        "issues": [
            {
                "site": site,
                "severity": "critical" if site == "qianlima" else "warning",
                "reasons": ["test SLO breach"],
            }
            for site in sites
        ],
    }


if __name__ == "__main__":
    unittest.main()
