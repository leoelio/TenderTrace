from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
import warnings

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.memory import (
    build_weekly_report,
    load_memory_profile,
    persist_weekly_report,
    record_advice_feedback,
    record_activity,
)


ENV_KEYS = (
    "TENDERTRACE_DB_PATH",
    "TENDERTRACE_OUTPUTS_DIR",
    "TENDERTRACE_OUTBOX_DIR",
    "TENDERTRACE_SNAPSHOTS_DIR",
    "TENDERTRACE_TRACES_DIR",
    "TENDERTRACE_SECRETS_DIR",
    "TENDERTRACE_SCHEDULER_ENABLED",
)


class MemoryTests(unittest.TestCase):
    def test_weekly_report_summarizes_events_runs_and_suggestions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings.load(root)
            init_db(settings)
            query = "最近1个月上海服务器招标信息"
            record_activity(
                settings,
                event_type="run_start",
                target="web",
                label=query,
                metadata={"query": query},
                created_at="2026-07-20T09:00:00+08:00",
            )
            record_activity(
                settings,
                event_type="click",
                target="runButton",
                label="开始运行",
                metadata={"query": query},
                created_at="2026-07-20T09:01:00+08:00",
            )
            record_activity(
                settings,
                event_type="download",
                target="outbox",
                label="report.docx",
                metadata={"filename": "report.docx", "query": query},
                created_at="2026-07-21T10:30:00+08:00",
            )
            with connection(settings) as conn:
                conn.execute(
                    """
                    INSERT INTO runs(
                        id, original_query, mode, status, started_at, finished_at, stats_json
                    )
                    VALUES (
                        'run-memory',
                        ?,
                        'full',
                        'finished',
                        '2026-07-20 09:00:00',
                        '2026-07-20 09:02:00',
                        '{"notice_count":3}'
                    )
                    """,
                    (query,),
                )

            report = build_weekly_report(
                settings,
                now="2026-07-24T18:00:00+08:00",
            )
            subscription_advice = next(
                item for item in report["recommendation_plan"] if item["kind"] == "subscription"
            )
            record_advice_feedback(
                settings,
                advice_id=subscription_advice["id"],
                status="accepted",
                source="web",
            )
            report = build_weekly_report(
                settings,
                now="2026-07-24T18:00:00+08:00",
            )
            saved = persist_weekly_report(settings, report)
            profile = load_memory_profile(settings)
            with connection(settings) as conn:
                saved_count = conn.execute("SELECT COUNT(*) AS count FROM weekly_reports").fetchone()[
                    "count"
                ]

        self.assertEqual(report["summary"]["downloads"], 1)
        self.assertEqual(report["summary"]["runs_finished"], 1)
        self.assertEqual(report["summary"]["active_days"], 2)
        self.assertEqual(report["top_queries"][0]["query"], query)
        self.assertTrue(any("订阅" in item for item in report["suggestions"]))
        self.assertIn("knowledge_profile", report)
        self.assertIn("generated_advice", report)
        self.assertIn("recommendation_plan", report)
        self.assertGreaterEqual(report["knowledge_profile"]["behavior"]["download_rate"], 1.0)
        self.assertTrue(any(item["kind"] == "subscription" for item in report["recommendation_plan"]))
        accepted = next(
            item for item in report["recommendation_plan"] if item["kind"] == "subscription"
        )
        self.assertEqual(accepted["feedback_status"], "accepted")
        self.assertEqual(report["recommendation_feedback"]["accepted"], 1)
        self.assertIn("saved_report_id", saved)
        self.assertIsNotNone(profile)
        self.assertEqual(profile["knowledge_profile"]["behavior"]["download_rate"], 1.0)
        self.assertEqual(saved_count, 1)

    def test_memory_api_records_event_and_builds_weekly_report(self) -> None:
        warnings.filterwarnings(
            "ignore",
            message="Using `httpx` with `starlette.testclient` is deprecated.*",
        )
        from fastapi.testclient import TestClient

        from tendertrace.app.api import create_app

        old_env = {key: os.environ.get(key) for key in ENV_KEYS}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.environ["TENDERTRACE_DB_PATH"] = str(root / "data" / "db.sqlite3")
            os.environ["TENDERTRACE_OUTPUTS_DIR"] = str(root / "outputs")
            os.environ["TENDERTRACE_OUTBOX_DIR"] = str(root / "outbox")
            os.environ["TENDERTRACE_SNAPSHOTS_DIR"] = str(root / "snapshots")
            os.environ["TENDERTRACE_TRACES_DIR"] = str(root / "traces")
            os.environ["TENDERTRACE_SECRETS_DIR"] = str(root / "secrets")
            os.environ["TENDERTRACE_SCHEDULER_ENABLED"] = "false"
            try:
                client = TestClient(create_app())
                event_response = client.post(
                    "/api/memory/events",
                    json={
                        "event_type": "click",
                        "target": "memoryView",
                        "label": "用户记忆",
                        "metadata": {"view": "workbenchView"},
                    },
                )
                client.post(
                    "/api/memory/events",
                    json={
                        "event_type": "run_start",
                        "target": "web",
                        "label": "苏州充电桩",
                        "metadata": {"query": "最近1个月苏州充电桩招标信息"},
                    },
                )
                client.post(
                    "/api/memory/events",
                    json={
                        "event_type": "run_start",
                        "target": "web",
                        "label": "苏州充电桩",
                        "metadata": {"query": "最近1个月苏州充电桩招标信息"},
                    },
                )
                report_response = client.get("/api/memory/weekly")
                advice_id = report_response.json()["recommendation_plan"][0]["id"]
                subscription_advice_id = next(
                    item["id"]
                    for item in report_response.json()["recommendation_plan"]
                    if item["kind"] == "subscription"
                )
                knowledge_advice_id = next(
                    item["id"]
                    for item in report_response.json()["recommendation_plan"]
                    if item["kind"] == "knowledge_base"
                )
                feedback_response = client.post(
                    f"/api/memory/advice/{advice_id}/feedback",
                    json={"status": "completed", "source": "web"},
                )
                subscription_automation_response = client.post(
                    f"/api/memory/advice/{subscription_advice_id}/feedback",
                    json={"status": "accepted", "source": "web"},
                )
                automation_response = client.post(
                    f"/api/memory/advice/{knowledge_advice_id}/feedback",
                    json={"status": "accepted", "source": "web"},
                )
                ingest_response = client.get("/api/ingest-subscriptions")
                subscriptions_response = client.get("/api/subscriptions")
                save_response = client.post("/api/memory/weekly", json={"days": 7})
                profile_response = client.get("/api/memory/profile")
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual(event_response.status_code, 200)
        self.assertEqual(event_response.json()["event_type"], "click")
        self.assertEqual(report_response.status_code, 200)
        self.assertGreaterEqual(report_response.json()["summary"]["clicks"], 1)
        self.assertEqual(feedback_response.status_code, 200)
        self.assertEqual(feedback_response.json()["feedback"]["status"], "completed")
        self.assertEqual(
            feedback_response.json()["report"]["recommendation_plan"][0]["feedback_status"],
            "completed",
        )
        self.assertEqual(subscription_automation_response.status_code, 200)
        self.assertEqual(
            subscription_automation_response.json()["automation"]["status"],
            "created",
        )
        self.assertFalse(subscription_automation_response.json()["automation"]["scheduled"])
        self.assertIn(
            "调度器未启用",
            subscription_automation_response.json()["automation"]["message"],
        )
        self.assertEqual(len(subscriptions_response.json()["items"]), 1)
        self.assertEqual(subscriptions_response.json()["items"][0]["cron"], "0 9 * * *")
        self.assertEqual(automation_response.status_code, 200)
        self.assertEqual(automation_response.json()["automation"]["status"], "created")
        self.assertFalse(automation_response.json()["automation"]["scheduled"])
        self.assertIn("调度器未启用", automation_response.json()["automation"]["message"])
        self.assertEqual(
            automation_response.json()["report"]["knowledge_coverage"]["active_count"],
            1,
        )
        self.assertEqual(len(ingest_response.json()["items"]), 1)
        self.assertEqual(save_response.status_code, 200)
        self.assertIn("saved_report_id", save_response.json())
        self.assertEqual(profile_response.status_code, 200)
        self.assertEqual(profile_response.json()["status"], "ready")
        self.assertIn("knowledge_profile", profile_response.json())


if __name__ == "__main__":
    unittest.main()
