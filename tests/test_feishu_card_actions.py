from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.integrations.feishu_card_actions import (
    callback_response_payload,
    process_feishu_card_action,
    process_opportunity_card_action,
)
from tendertrace.memory import build_weekly_report, record_activity
from tendertrace.scheduling.subscriptions import list_subscriptions


class FeishuCardActionTests(unittest.TestCase):
    def test_shared_handler_updates_workflow_and_returns_refreshed_card(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            _insert_notice(settings)

            result = process_opportunity_card_action(
                settings,
                _payload("claim"),
                bitable_updater=lambda *_args, **_kwargs: SimpleNamespace(status="sent"),
            )

        actions = [
            button["value"]["action"]
            for element in result["card"]["elements"]
            if element.get("tag") == "action"
            for button in element["actions"]
        ]
        response = callback_response_payload(result)

        self.assertEqual(result["workflow"]["stage"], "qualifying")
        self.assertEqual(result["workflow"]["owner_name"], "张三")
        self.assertEqual(result["bitable_status"], "sent")
        self.assertEqual(actions, ["pursue", "hold", "reject"])
        self.assertEqual(set(response), {"toast", "card"})

    def test_gate_failure_returns_warning_without_mutating_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            _insert_notice(settings)

            result = process_opportunity_card_action(
                settings,
                _payload("approve_bid"),
                bitable_updater=lambda *_args, **_kwargs: SimpleNamespace(status="sent"),
            )

        self.assertTrue(result["blocked"])
        self.assertEqual(result["toast"]["type"], "warning")
        self.assertIn("当前阶段", result["reasons"][0])

    def test_memory_advice_action_updates_shared_feedback_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            report = build_weekly_report(settings)
            advice_id = report["recommendation_plan"][0]["id"]
            payload = {
                "header": {"event_id": "memory-event-1"},
                "event": {
                    "operator": {
                        "name": "张三",
                        "operator_id": {"open_id": "ou_owner"},
                    },
                    "action": {
                        "value": {
                            "action": "memory_advice_accept",
                            "advice_id": advice_id,
                            "user_id": "admin",
                        }
                    },
                },
            }

            result = process_feishu_card_action(settings, payload)
            refreshed = build_weekly_report(settings)

        self.assertEqual(result["feedback"]["status"], "accepted")
        self.assertEqual(refreshed["recommendation_plan"][0]["feedback_status"], "accepted")
        self.assertIn("已采纳", result["toast"]["content"])
        self.assertEqual(result["card"]["header"]["title"]["content"], "TenderTrace 使用与机会周报")

    def test_memory_knowledge_advice_creates_scheduled_ingest_from_feishu(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            query = "最近1个月苏州充电桩招标信息"
            record_activity(
                settings,
                event_type="run_start",
                target="feishu",
                label=query,
                metadata={"query": query},
            )
            report = build_weekly_report(settings)
            advice = next(
                item for item in report["recommendation_plan"] if item["kind"] == "knowledge_base"
            )
            scheduled: list[str] = []
            payload = {
                "header": {"event_id": "memory-ingest-event"},
                "event": {
                    "operator": {
                        "name": "张三",
                        "operator_id": {"open_id": "ou_owner"},
                    },
                    "action": {
                        "value": {
                            "action": "memory_advice_accept",
                            "advice_id": advice["id"],
                            "user_id": "admin",
                        }
                    },
                },
            }

            result = process_feishu_card_action(
                settings,
                payload,
                schedule_ingest=lambda subscription: scheduled.append(subscription.id),
            )
            with connection(settings) as conn:
                count = conn.execute("SELECT COUNT(*) FROM ingest_subscriptions").fetchone()[0]

        self.assertEqual(result["automation"]["status"], "created")
        self.assertTrue(result["automation"]["scheduled"])
        self.assertEqual(count, 1)
        self.assertEqual(len(scheduled), 1)
        self.assertIn("后台采集", result["toast"]["content"])

    def test_memory_subscription_advice_binds_current_feishu_chat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            query = "最近1个月苏州充电桩招标信息"
            for _ in range(2):
                record_activity(
                    settings,
                    event_type="run_start",
                    target="feishu",
                    label=query,
                    metadata={"query": query},
                )
            report = build_weekly_report(settings)
            advice = next(
                item for item in report["recommendation_plan"] if item["kind"] == "subscription"
            )
            scheduled: list[str] = []
            payload = {
                "header": {"event_id": "memory-subscription-event"},
                "event": {
                    "context": {"open_chat_id": "oc_sales_team"},
                    "operator": {
                        "name": "张三",
                        "operator_id": {"open_id": "ou_owner"},
                    },
                    "action": {
                        "value": {
                            "action": "memory_advice_accept",
                            "advice_id": advice["id"],
                            "user_id": "admin",
                        }
                    },
                },
            }

            result = process_feishu_card_action(
                settings,
                payload,
                schedule_subscription=lambda subscription: scheduled.append(subscription.id),
            )
            subscriptions = list_subscriptions(settings)

        runtime = subscriptions[0].bidql["_runtime"]
        self.assertEqual(result["automation"]["status"], "created")
        self.assertTrue(result["automation"]["scheduled"])
        self.assertEqual(subscriptions[0].cron, "0 9 * * *")
        self.assertEqual(runtime["delivery_channels"], ["web", "outbox", "feishu"])
        self.assertEqual(runtime["feishu_receive_id"], "oc_sales_team")
        self.assertEqual(runtime["feishu_receive_id_type"], "chat_id")
        self.assertEqual(scheduled, [subscriptions[0].id])
        self.assertIn("当前飞书会话", result["toast"]["content"])

    def test_memory_opportunity_advice_sends_briefing_to_current_chat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            _insert_priority_notice(settings)
            report = build_weekly_report(settings)
            advice = next(
                item
                for item in report["recommendation_plan"]
                if item["kind"] == "opportunity_followup"
            )
            targets: list[tuple[str | None, str | None]] = []
            payload = {
                "header": {"event_id": "memory-opportunity-event"},
                "event": {
                    "context": {"open_chat_id": "oc_opportunity_team"},
                    "operator": {
                        "name": "张三",
                        "operator_id": {"open_id": "ou_owner"},
                    },
                    "action": {
                        "value": {
                            "action": "memory_advice_accept",
                            "advice_id": advice["id"],
                            "user_id": "admin",
                        }
                    },
                },
            }

            result = process_feishu_card_action(
                settings,
                payload,
                send_opportunity_briefing=lambda receive_id, receive_id_type: (
                    targets.append((receive_id, receive_id_type))
                    or {"status": "sent", "opportunity_count": 1, "reason": ""}
                ),
            )

        self.assertEqual(targets, [("oc_opportunity_team", "chat_id")])
        self.assertEqual(result["automation"]["status"], "sent")
        self.assertTrue(result["automation"]["receiver_bound"])
        self.assertIn("当前飞书会话", result["toast"]["content"])


def _payload(action: str) -> dict[str, object]:
    return {
        "header": {"event_id": "event-1"},
        "event": {
            "operator": {
                "name": "张三",
                "operator_id": {"open_id": "ou_owner"},
            },
            "action": {"value": {"action": action, "notice_id": "notice-1"}},
        },
    }


def _insert_notice(settings: Settings) -> None:
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(
                id, source_site, source_url, canonical_url, title, purchaser,
                publish_time, content_text, fields_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "notice-1",
                "ccgp",
                "https://example.com/notice-1",
                "https://example.com/notice-1",
                "服务器采购项目",
                "示例采购人",
                "2026-08-15",
                "服务器采购项目，采购人为示例采购人。",
                '{"bid_deadline":"2026-08-30 17:00"}',
            ),
        )


def _insert_priority_notice(settings: Settings) -> None:
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(
                id, source_site, source_url, canonical_url, title, purchaser,
                publish_time, region, content_text, fields_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "priority-notice",
                "ccgp",
                "https://example.com/priority-notice",
                "https://example.com/priority-notice",
                "服务器采购优先机会",
                "示例采购人",
                "2026-08-16",
                "上海",
                "服务器采购项目",
                '{"opportunity_intelligence":{"level":"A","score":90}}',
            ),
        )


if __name__ == "__main__":
    unittest.main()
