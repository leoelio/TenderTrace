from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from tendertrace.config import Settings
from tendertrace.db import init_db
from tendertrace.delivery.preferences import save_feishu_receiver
from tendertrace.integrations.feishu_briefing import (
    build_opportunity_briefing_card,
    send_opportunity_briefing,
)


class _FakeClient:
    def __init__(self) -> None:
        self.cards: list[dict[str, object]] = []
        self.receivers: list[str] = []

    def send_card(self, card, **kwargs):
        self.cards.append(card)
        self.receivers.append(str(kwargs.get("receive_id") or ""))
        return {"data": {"message_id": f"briefing-{len(self.cards)}"}}


class FeishuBriefingTests(unittest.TestCase):
    def test_briefing_is_sent_once_for_same_daily_opportunity_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            save_feishu_receiver(
                settings,
                receive_id="oc_sales",
                receive_id_type="chat_id",
                label="机会经营群",
            )
            client = _FakeClient()
            now = datetime(2026, 8, 16, 8, 45, tzinfo=ZoneInfo("Asia/Shanghai"))

            first = send_opportunity_briefing(
                settings,
                client=client,
                opportunity_loader=_opportunity_payload,
                source_health_loader=_source_health,
                now=now,
            )
            duplicate = send_opportunity_briefing(
                settings,
                client=client,
                opportunity_loader=_opportunity_payload,
                source_health_loader=_source_health,
                now=now,
            )

        self.assertEqual(first.status, "sent")
        self.assertEqual(first.opportunity_count, 1)
        self.assertEqual(first.message_id, "briefing-1")
        self.assertEqual(duplicate.status, "skipped")
        self.assertIn("already sent", duplicate.reason)
        self.assertEqual(len(client.cards), 1)

    def test_same_briefing_is_delivered_once_per_receiver(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            client = _FakeClient()
            now = datetime(2026, 8, 16, 8, 45, tzinfo=ZoneInfo("Asia/Shanghai"))

            first = send_opportunity_briefing(
                settings,
                receive_id="oc_team_a",
                receive_id_type="chat_id",
                client=client,
                opportunity_loader=_opportunity_payload,
                source_health_loader=_source_health,
                now=now,
            )
            second = send_opportunity_briefing(
                settings,
                receive_id="oc_team_b",
                receive_id_type="chat_id",
                client=client,
                opportunity_loader=_opportunity_payload,
                source_health_loader=_source_health,
                now=now,
            )

        self.assertEqual(first.status, "sent")
        self.assertEqual(second.status, "sent")
        self.assertNotEqual(first.artifact_key, second.artifact_key)
        self.assertNotIn("oc_team_a", first.artifact_key)
        self.assertEqual(client.receivers, ["oc_team_a", "oc_team_b"])

    def test_empty_opportunity_pool_skips_before_receiver_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)

            result = send_opportunity_briefing(
                settings,
                opportunity_loader=lambda *_args, **_kwargs: {"items": []},
            )

        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.opportunity_count, 0)

    def test_card_contains_live_management_context_and_actions(self) -> None:
        payload = _opportunity_payload()
        card = build_opportunity_briefing_card(
            payload["summary"],
            payload["items"],
            _source_health(),
            now=datetime(2026, 8, 16, 8, 45),
        )
        card_text = str(card)

        self.assertIn("服务器采购项目", card_text)
        self.assertIn("张三", card_text)
        self.assertIn("2026-08-30 17:00", card_text)
        self.assertIn("完成机会确认", card_text)
        self.assertIn("qualification", card_text)
        self.assertIn("qianlima", card_text)
        self.assertIn("确认预算审批链路", card_text)
        self.assertIn("关系行动待办 1 项", card_text)


def _opportunity_payload(*_args, **_kwargs) -> dict[str, object]:
    return {
        "summary": {
            "total": 1,
            "levels": {"A": 1},
            "action_queue": {
                "unowned_priority": 0,
                "qualification_ready": 1,
                "decision_pending": 0,
                "decision_overdue": 0,
                "relationship_action_open": 1,
                "relationship_action_overdue": 0,
                "relationship_action_outcome_pending": 0,
            },
            "market": {"signals": ["服务器采购需求在本周集中释放"]},
        },
        "items": [
            {
                "notice_id": "notice-1",
                "title": "服务器采购项目",
                "source_url": "https://example.com/notices/1",
                "bid_deadline": "2026-08-30 17:00",
                "intelligence": {"level": "A", "score": 88},
                "workflow": {
                    "stage": "qualifying",
                    "decision": "pending",
                    "owner_name": "张三",
                },
                "qualification": {
                    "blockers": {"approve_bid": ["qualification evidence missing"]}
                },
                "action_state": {"priority": 96},
                "relationship_actions": {
                    "open_count": 1,
                    "overdue_count": 0,
                    "next_action": {"title": "确认预算审批链路"},
                },
            }
        ],
    }


def _source_health(*_args, **_kwargs) -> dict[str, dict[str, object]]:
    return {
        "qianlima": {
            "health_status": "degraded",
            "reliability_score": 72,
        }
    }


if __name__ == "__main__":
    unittest.main()
