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
    _artifact_key,
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
        self.assertEqual(first.decision_count, 1)
        self.assertEqual(first.task_count, 1)
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
        self.assertIn("决策超时 + 任务逾期", card_text)
        self.assertIn("2026-08-15T09:00:00+00:00", card_text)
        self.assertIn("2026-08-15T17:00:00+08:00", card_text)

    def test_decision_only_set_keeps_legacy_artifact_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            key = _artifact_key(
                settings,
                [{"notice_id": "notice-1", "issue_types": ["decision"]}],
                now=datetime(2026, 8, 16, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            )

        self.assertTrue(key.startswith("decision_sla:2026-08-16:"))

    def test_change_review_overdue_is_counted_and_rendered(self) -> None:
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
            result = send_opportunity_escalation_summary(
                settings,
                client=client,
                opportunity_loader=_change_review_payload,
                now=datetime(2026, 8, 16, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            )

        self.assertEqual(result.change_review_count, 1)
        self.assertEqual(result.decision_count, 0)
        self.assertEqual(result.task_count, 0)
        self.assertIn("变更复核逾期", str(client.cards[0]))
        self.assertIn("2026-08-15T08:00:00+00:00", str(client.cards[0]))


def _overdue_payload(*_args, **_kwargs) -> dict[str, object]:
    return {
        "summary": {
            "action_queue": {
                "decision_sla_hours": 24,
                "decision_overdue": 1,
                "task_overdue": 1,
                "escalations": [
                    {
                        "notice_id": "notice-1",
                        "title": "服务器采购项目",
                        "owner": "张三",
                        "stage": "策略制定",
                        "issue_type": "decision_task",
                        "issue_types": ["decision", "task"],
                        "wait_hours": 31.5,
                        "decision_due_at": "2026-08-15T09:00:00+00:00",
                        "task_due_at": "2026-08-15T17:00:00+08:00",
                        "due_at": "2026-08-15T09:00:00+00:00",
                    }
                ],
            }
        }
    }


def _change_review_payload(*_args, **_kwargs) -> dict[str, object]:
    return {
        "summary": {
            "action_queue": {
                "decision_sla_hours": 24,
                "change_review_overdue": 1,
                "escalations": [
                    {
                        "notice_id": "notice-review-1",
                        "title": "服务器采购项目更正公告",
                        "owner": "张三",
                        "stage": "投标准备",
                        "issue_type": "change_review",
                        "issue_types": ["change_review"],
                        "change_review_due_at": "2026-08-15T08:00:00+00:00",
                        "due_at": "2026-08-15T08:00:00+00:00",
                    }
                ],
            }
        }
    }


if __name__ == "__main__":
    unittest.main()
