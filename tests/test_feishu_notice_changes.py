from pathlib import Path
import tempfile
import unittest

from tendertrace.adapters.ccgp import Notice
from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.integrations.feishu import FeishuError
from tendertrace.integrations.feishu_notice_changes import send_opportunity_change_alerts
from tendertrace.runner import persist_notices_and_clusters
from tendertrace.workflow import update_workflow


class _ChangeClient:
    def __init__(self, *, fail_attempts: int = 0) -> None:
        self.fail_attempts = fail_attempts
        self.cards: list[tuple[dict, str, str]] = []

    def send_card(self, card, *, receive_id: str, receive_id_type: str):
        self.cards.append((card, receive_id, receive_id_type))
        if len(self.cards) <= self.fail_attempts:
            raise FeishuError("temporary send failure")
        return {"data": {"message_id": f"message-{len(self.cards)}"}}


class FeishuNoticeChangeTests(unittest.TestCase):
    def test_owner_alert_retries_then_deduplicates_each_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            persist_notices_and_clusters(settings, [_notice("100 万元", "2026-09-20")])
            update_workflow(
                settings,
                "ccgp:notice-alert-1",
                stage="pursuing",
                owner_open_id="ou_owner",
                owner_name="张三",
            )
            persist_notices_and_clusters(settings, [_notice("120 万元", "2026-09-30")])
            client = _ChangeClient(fail_attempts=1)

            failed = send_opportunity_change_alerts(settings, client=client)
            sent = send_opportunity_change_alerts(settings, client=client)
            duplicate = send_opportunity_change_alerts(settings, client=client)
            with connection(settings) as conn:
                statuses = [
                    str(row["status"])
                    for row in conn.execute(
                        """
                        SELECT status FROM delivery_attempts
                        WHERE artifact_type = 'opportunity_notice_change'
                        ORDER BY rowid
                        """
                    ).fetchall()
                ]

        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.failed_count, 1)
        self.assertEqual(sent.status, "sent")
        self.assertEqual(sent.sent_count, 1)
        self.assertEqual(duplicate.status, "skipped")
        self.assertEqual(duplicate.skipped_count, 1)
        self.assertEqual(statuses, ["failed", "sent"])
        self.assertEqual(len(client.cards), 2)
        card, receive_id, receive_type = client.cards[-1]
        self.assertEqual((receive_id, receive_type), ("ou_owner", "open_id"))
        self.assertIn("机会公告变更提醒", str(card))
        self.assertIn("预算", str(card))
        self.assertIn("投标截止", str(card))

    def test_sent_recent_revisions_do_not_starve_older_pending_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            persist_notices_and_clusters(settings, [_notice("0 万元", "2026-09-20")])
            update_workflow(
                settings,
                "ccgp:notice-alert-1",
                stage="pursuing",
                owner_open_id="ou_owner",
                owner_name="张三",
            )
            for index in range(1, 202):
                persist_notices_and_clusters(
                    settings,
                    [_notice(f"{index} 万元", "2026-09-20")],
                )
            client = _ChangeClient()

            recent = send_opportunity_change_alerts(settings, client=client, limit=200)
            older = send_opportunity_change_alerts(settings, client=client, limit=1)
            duplicate = send_opportunity_change_alerts(settings, client=client, limit=1)

        self.assertEqual(recent.sent_count, 200)
        self.assertEqual(recent.message_count, 20)
        self.assertEqual(older.sent_count, 1)
        self.assertEqual(older.message_count, 1)
        self.assertEqual(older.revision_count, 201)
        self.assertEqual(duplicate.status, "skipped")
        self.assertEqual(len(client.cards), 21)


def _notice(budget: str, deadline: str) -> Notice:
    return Notice(
        id="notice-alert-1",
        source_site="ccgp",
        title="服务器采购项目",
        publish_time="2026-08-16 09:00",
        region="上海",
        purchaser="测试采购人",
        source_url="https://example.com/notice-alert-1",
        content_text=f"预算 {budget}，投标截止 {deadline}",
        core_content=f"预算 {budget}，投标截止 {deadline}",
        fields={
            "structured_fields": {
                "budget": budget,
                "bid_deadline": deadline,
                "project_no": "TEST-ALERT-001",
            }
        },
    )


if __name__ == "__main__":
    unittest.main()
