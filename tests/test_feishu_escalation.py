from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from tendertrace.config import Settings
from tendertrace.db import init_db
from tendertrace.delivery.preferences import save_feishu_receiver
from tendertrace.integrations.feishu_escalation import (
    build_escalation_card,
    send_opportunity_escalation_summary,
)


class _FakeClient:
    def __init__(self) -> None:
        self.cards: list[dict[str, object]] = []

    def send_card(self, card, **_):
        self.cards.append(card)
        return {"data": {"message_id": f"message-{len(self.cards)}"}}


class FeishuEscalationTests(unittest.TestCase):
    def test_summary_is_sent_once_per_daily_escalation_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            save_feishu_receiver(
                settings,
                receive_id="oc_test",
                receive_id_type="chat_id",
                label="销售管理群",
            )
            client = _FakeClient()
            now = datetime(2026, 8, 16, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

            first = send_opportunity_escalation_summary(
                settings,
                client=client,
                opportunity_loader=_overdue_payload,
                now=now,
            )
            duplicate = send_opportunity_escalation_summary(
                settings,
                client=client,
                opportunity_loader=_overdue_payload,
                now=now,
            )
            forced = send_opportunity_escalation_summary(
                settings,
                force=True,
                client=client,
                opportunity_loader=_overdue_payload,
                now=now,
            )

        self.assertEqual(first.status, "sent")
        self.assertEqual(first.escalation_count, 1)
        self.assertEqual(duplicate.status, "skipped")
        self.assertIn("already sent", duplicate.reason)
        self.assertEqual(forced.status, "sent")
        self.assertEqual(len(client.cards), 2)

    def test_empty_queue_skips_delivery_without_receiver_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)

            result = send_opportunity_escalation_summary(
                settings,
                opportunity_loader=lambda *_args, **_kwargs: {
                    "summary": {"action_queue": {"escalations": []}}
                },
            )

        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.escalation_count, 0)

    def test_card_contains_real_owner_wait_and_sla(self) -> None:
        payload = _overdue_payload()
        queue = payload["summary"]["action_queue"]

        card = build_escalation_card(queue["escalations"], queue)
        card_text = str(card)

        self.assertIn("服务器采购项目", card_text)
        self.assertIn("张三", card_text)
        self.assertIn("31.5", card_text)
        self.assertIn("24", card_text)


def _overdue_payload(*_args, **_kwargs) -> dict[str, object]:
    return {
        "summary": {
            "action_queue": {
                "decision_sla_hours": 24,
                "escalations": [
                    {
                        "notice_id": "notice-1",
                        "title": "服务器采购项目",
                        "owner": "张三",
                        "wait_hours": 31.5,
                        "due_at": "2026-08-15T09:00:00+00:00",
                    }
                ],
            }
        }
    }


if __name__ == "__main__":
    unittest.main()
