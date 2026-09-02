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
    def test_accepting_opportunity_advice_sends_default_feishu_briefing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            _insert_priority_opportunity(settings)
            report = build_weekly_report(settings, now=NOW)
            advice = next(
                item
                for item in report["recommendation_plan"]
                if item["kind"] == "opportunity_followup"
            )
            targets: list[tuple[str | None, str | None]] = []

            result = apply_memory_advice_feedback(
                settings,
                advice_id=str(advice["id"]),
                status="accepted",
                now=NOW,
                send_opportunity_briefing=lambda receive_id, receive_id_type: (
                    targets.append((receive_id, receive_id_type))
                    or {"status": "sent", "opportunity_count": 1, "reason": ""}
                ),
            )

        self.assertEqual(targets, [(None, None)])
        self.assertEqual(result.automation["status"], "sent")
        self.assertEqual(result.automation["kind"], "opportunity_briefing")
        self.assertFalse(result.automation["receiver_bound"])
        self.assertNotIn("message_id", result.automation["briefing"])
        self.assertIn("默认飞书协作目标", result.automation["message"])

    def test_accepting_subscription_advice_creates_schedules_and_reuses_user_subscription(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            for _ in range(2):
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
                item for item in report["recommendation_plan"] if item["kind"] == "subscription"
            )
            scheduled: list[str] = []

            first = apply_memory_advice_feedback(
                settings,
                advice_id=str(advice["id"]),
                status="accepted",
                now=NOW,
                schedule_subscription=lambda subscription: scheduled.append(subscription.id),
            )
            second = apply_memory_advice_feedback(
                settings,
                advice_id=str(advice["id"]),
                status="accepted",
                now=NOW,
                schedule_subscription=lambda subscription: scheduled.append(subscription.id),
            )
            with connection(settings) as conn:
                subscriptions = conn.execute(
                    "SELECT original_query, cron, bidql_json FROM subscriptions"
                ).fetchall()

        self.assertEqual(first.automation["status"], "created")
        self.assertEqual(second.automation["status"], "reused")
        self.assertTrue(first.automation["scheduled"])
        self.assertEqual(scheduled[0], scheduled[1])
        self.assertEqual(len(subscriptions), 1)
        self.assertEqual(subscriptions[0]["original_query"], QUERY)
        self.assertEqual(subscriptions[0]["cron"], "0 9 * * *")
        self.assertNotIn("feishu_receive_id", subscriptions[0]["bidql_json"])

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


def _insert_priority_opportunity(settings: Settings) -> None:
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(
                id, source_site, source_url, canonical_url, title, publish_time,
                region, purchaser, content_text, fields_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "memory-priority-opportunity",
                "ccgp",
                "https://example.com/memory-priority-opportunity",
                "https://example.com/memory-priority-opportunity",
                "服务器采购优先机会",
                "2026-08-16",
                "上海",
                "示例采购人",
                "服务器采购项目",
                '{"opportunity_intelligence":{"level":"A","score":90}}',
                "2026-08-16 09:00:00",
            ),
        )


if __name__ == "__main__":
    unittest.main()
