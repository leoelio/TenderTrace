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
from tendertrace.memory import build_weekly_report


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


if __name__ == "__main__":
    unittest.main()
