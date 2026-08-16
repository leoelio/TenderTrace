from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.memory import build_weekly_report, record_activity
from tendertrace.memory_actions import apply_memory_advice_feedback


NOW = "2026-08-16T12:00:00+08:00"
QUERY = "最近1个月苏州充电桩招标信息"


class MemoryAdviceActionTests(unittest.TestCase):
    def test_accepting_knowledge_advice_creates_schedules_and_reuses_ingest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            record_activity(
                settings,
                event_type="run_start",
                target="web",
                label=QUERY,
                metadata={"query": QUERY},
                created_at=NOW,
            )
            report = build_weekly_report(settings, now=NOW)
            advice = next(
                item for item in report["recommendation_plan"] if item["kind"] == "knowledge_base"
            )
            scheduled: list[str] = []

            first = apply_memory_advice_feedback(
                settings,
                advice_id=str(advice["id"]),
                status="accepted",
                now=NOW,
                schedule_ingest=lambda subscription: scheduled.append(subscription.id),
            )
            second = apply_memory_advice_feedback(
                settings,
                advice_id=str(advice["id"]),
                status="accepted",
                now=NOW,
                schedule_ingest=lambda subscription: scheduled.append(subscription.id),
            )
            with connection(settings) as conn:
                subscriptions = conn.execute(
                    "SELECT topics_json, regions_json FROM ingest_subscriptions"
                ).fetchall()

        self.assertEqual(first.feedback["status"], "accepted")
        self.assertEqual(first.automation["status"], "created")
        self.assertTrue(first.automation["scheduled"])
        self.assertEqual(second.automation["status"], "reused")
        self.assertEqual(first.report["knowledge_coverage"]["active_count"], 1)
        self.assertEqual(scheduled[0], scheduled[1])
        self.assertEqual(len(subscriptions), 1)
        self.assertIn("充电桩", subscriptions[0]["topics_json"])
        self.assertIn("苏州", subscriptions[0]["regions_json"])


if __name__ == "__main__":
    unittest.main()
