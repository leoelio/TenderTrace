from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.integrations.feishu_card_actions import (
    callback_response_payload,
    process_opportunity_card_action,
)


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
