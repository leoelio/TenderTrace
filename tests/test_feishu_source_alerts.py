from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from tendertrace.config import Settings
from tendertrace.db import init_db
from tendertrace.delivery.preferences import save_feishu_receiver
from tendertrace.integrations.feishu_source_alerts import (
    build_source_alert_card,
    build_source_alert_snapshot,
    create_source_incident_task,
    send_source_health_alert,
)
from tendertrace.integrations.feishu_source_incidents import list_source_incidents


class _FakeClient:
    def __init__(self) -> None:
        self.cards: list[dict[str, object]] = []
        self.tasks: list[dict[str, object]] = []

    def send_card(self, card, **_):
        self.cards.append(card)
        return {"data": {"message_id": f"source-alert-{len(self.cards)}"}}

    def create_task(self, **kwargs):
        self.tasks.append(kwargs)
        return {"data": {"task": {"guid": f"incident-{len(self.tasks)}"}}}


class FeishuSourceAlertTests(unittest.TestCase):
    def test_snapshot_reports_observed_slo_breaches_and_login_expiry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp), ingest_enabled=True)
            now = datetime(2026, 8, 16, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

            snapshot = build_source_alert_snapshot(
                settings,
                source_map_loader=_source_map,
                now=now,
            )

        self.assertEqual(snapshot["status"], "attention")
        self.assertEqual(snapshot["issue_count"], 2)
        self.assertEqual(snapshot["critical_count"], 1)
        self.assertEqual(snapshot["warning_count"], 1)
        self.assertEqual(
            [item["site"] for item in snapshot["issues"]],
            ["qianlima", "ggzy"],
        )
        self.assertNotIn("adb", [item["site"] for item in snapshot["issues"]])

    def test_inactive_ingestion_does_not_turn_historical_samples_into_alerts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp), ingest_enabled=False)
            snapshot = build_source_alert_snapshot(
                settings,
                source_map_loader=_source_map,
                now=datetime(2026, 8, 16, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            )

        self.assertEqual(
            [item["site"] for item in snapshot["issues"]],
            ["qianlima", "ggzy"],
        )
        self.assertFalse(snapshot["policy"]["stale_monitoring_active"])

    def test_same_daily_source_state_is_sent_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            init_db(settings)
            save_feishu_receiver(
                settings,
                receive_id="oc_ops",
                receive_id_type="chat_id",
                label="数据运营群",
            )
            client = _FakeClient()
            now = datetime(2026, 8, 16, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

            def snapshot_loader(*_args, **_kwargs):
                return build_source_alert_snapshot(
                    settings,
                    source_map_loader=_source_map,
                    now=now,
                )

            first = send_source_health_alert(
                settings,
                client=client,
                snapshot_loader=snapshot_loader,
                now=now,
            )
            duplicate = send_source_health_alert(
                settings,
                client=client,
                snapshot_loader=snapshot_loader,
                now=now,
            )

        self.assertEqual(first.status, "sent")
        self.assertEqual(first.issue_count, 2)
        self.assertEqual(first.message_id, "source-alert-1")
        self.assertEqual(duplicate.status, "skipped")
        self.assertIn("already sent", duplicate.reason)
        self.assertEqual(len(client.cards), 1)

    def test_healthy_snapshot_skips_without_receiver(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            init_db(settings)
            result = send_source_health_alert(
                settings,
                snapshot_loader=lambda *_args, **_kwargs: {"issues": []},
            )

        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.issue_count, 0)

    def test_source_incident_task_is_assigned_and_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            init_db(settings)
            save_feishu_receiver(
                settings,
                receive_id="ou_owner",
                receive_id_type="open_id",
                label="数据运营负责人",
            )
            client = _FakeClient()
            now = datetime(2026, 8, 16, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

            def snapshot_loader(*_args, **_kwargs):
                return build_source_alert_snapshot(
                    settings,
                    source_map_loader=_source_map,
                    now=now,
                )

            first = create_source_incident_task(
                settings,
                client=client,
                snapshot_loader=snapshot_loader,
                now=now,
            )
            duplicate = create_source_incident_task(
                settings,
                client=client,
                snapshot_loader=snapshot_loader,
                now=now,
            )
            incidents = list_source_incidents(settings)

        self.assertEqual(first.status, "sent")
        self.assertEqual(first.task_guid, "incident-1")
        self.assertTrue(first.assigned)
        self.assertEqual(duplicate.status, "skipped")
        self.assertEqual(duplicate.task_guid, "incident-1")
        self.assertTrue(duplicate.assigned)
        self.assertIn("already created", duplicate.reason)
        self.assertEqual(len(client.tasks), 1)
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0].status, "open")
        self.assertEqual(incidents[0].source_sites, ("qianlima", "ggzy"))
        task = client.tasks[0]
        self.assertEqual(task["assignee_open_id"], "ou_owner")
        self.assertEqual(task["due_timestamp_ms"], "1786860000000")
        self.assertEqual(task["reminder_minutes"], 60)
        self.assertIn("qianlima", str(task["summary"]))
        self.assertIn("https://example.com/ggzy", str(task["description"]))

    def test_healthy_snapshot_does_not_create_incident_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            init_db(settings)
            client = _FakeClient()
            result = create_source_incident_task(
                settings,
                client=client,
                snapshot_loader=lambda *_args, **_kwargs: {"issues": []},
            )

        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.issue_count, 0)
        self.assertEqual(client.tasks, [])

    def test_card_contains_source_evidence_and_official_route(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            now = datetime(2026, 8, 16, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
            snapshot = build_source_alert_snapshot(
                settings,
                source_map_loader=_source_map,
                now=now,
            )

        card = build_source_alert_card(snapshot, now=now)
        text = str(card)
        self.assertIn("qianlima", text)
        self.assertIn("ggzy", text)
        self.assertIn("https://example.com/ggzy", text)
        self.assertIn("来源健康告警", text)


def _settings(root: Path, *, ingest_enabled: bool = False) -> Settings:
    (root / ".env.local").write_text(
        "TENDERTRACE_SOURCE_ALERT_MIN_RELIABILITY=0.75\n"
        "TENDERTRACE_SOURCE_ALERT_STALE_HOURS=24\n"
        f"TENDERTRACE_INGEST_ENABLED={'true' if ingest_enabled else 'false'}\n",
        encoding="utf-8",
    )
    return Settings.load(root)


def _source_map(_settings: Settings) -> dict[str, object]:
    return {
        "source_count": 4,
        "items": [
            {
                "site": "ccgp",
                "status": "healthy",
                "health": {
                    "runs": 12,
                    "reliability_score": 0.92,
                    "health_status": "healthy",
                    "last_success_at": "2026-08-16T09:30:00+08:00",
                },
                "routes": [{"url": "https://example.com/ccgp"}],
            },
            {
                "site": "ggzy",
                "status": "degraded",
                "health": {
                    "runs": 8,
                    "reliability_score": 0.68,
                    "health_status": "degraded",
                    "last_success_at": "2026-08-14T08:00:00+08:00",
                },
                "routes": [{"url": "https://example.com/ggzy"}],
            },
            {
                "site": "qianlima",
                "status": "login_expired",
                "health": {
                    "runs": 5,
                    "reliability_score": 0.8,
                    "health_status": "degraded",
                    "last_success_at": "2026-08-16T09:00:00+08:00",
                },
                "routes": [{"url": "https://www.qianlima.com"}],
            },
            {
                "site": "adb",
                "status": "configured",
                "health": {
                    "runs": 0,
                    "reliability_score": 0,
                    "health_status": "unknown",
                    "last_success_at": "",
                },
                "routes": [{"url": "https://www.adb.org"}],
            },
        ],
    }


if __name__ == "__main__":
    unittest.main()
