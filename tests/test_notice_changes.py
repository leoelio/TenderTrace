from pathlib import Path
import tempfile
import unittest

from tendertrace.adapters.ccgp import Attachment, Notice
from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.notice_changes import list_notice_revisions, notice_change_summaries
from tendertrace.runner import persist_notices_and_clusters
from tendertrace.workflow import get_workflow, update_workflow


class NoticeChangeTests(unittest.TestCase):
    def test_reingest_preserves_workflow_and_records_only_meaningful_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            first = _notice(core_content="预算 100 万元", budget="100 万元")
            persist_notices_and_clusters(settings, [first])
            update_workflow(
                settings,
                "ccgp:notice-change-1",
                owner_open_id="ou_owner",
                owner_name="张三",
            )
            with connection(settings) as conn:
                conn.execute(
                    """
                    UPDATE notices
                    SET created_at = '2026-01-01 00:00:00',
                        updated_at = '2026-01-01 00:00:00'
                    WHERE id = 'ccgp:notice-change-1'
                    """
                )

            persist_notices_and_clusters(settings, [first])
            changed = _notice(
                core_content="预算调整为 120 万元，投标截止延后",
                budget="120 万元",
                bid_deadline="2026-09-30 17:00",
                attachments=[Attachment(name="更正公告.pdf", url="https://example.com/a.pdf")],
            )
            persist_notices_and_clusters(settings, [changed])
            persist_notices_and_clusters(settings, [changed])

            revisions = list_notice_revisions(settings)
            summaries = notice_change_summaries(settings, ["ccgp:notice-change-1"])
            workflow = get_workflow(settings, "ccgp:notice-change-1")
            with connection(settings) as conn:
                notice_row = conn.execute(
                    "SELECT created_at, updated_at, last_seen_at FROM notices WHERE id = ?",
                    ("ccgp:notice-change-1",),
                ).fetchone()

        self.assertEqual(workflow.owner_open_id, "ou_owner")
        self.assertEqual(workflow.owner_name, "张三")
        self.assertEqual(len(revisions), 1)
        self.assertIn("budget", revisions[0].changed_fields)
        self.assertIn("bid_deadline", revisions[0].changed_fields)
        self.assertIn("attachments", revisions[0].changed_fields)
        self.assertEqual(summaries["ccgp:notice-change-1"]["count"], 1)
        self.assertEqual(notice_row["created_at"], "2026-01-01 00:00:00")
        self.assertNotEqual(notice_row["updated_at"], "2026-01-01 00:00:00")
        self.assertTrue(notice_row["last_seen_at"])


def _notice(
    *,
    core_content: str,
    budget: str,
    bid_deadline: str = "2026-09-20 17:00",
    attachments: list[Attachment] | None = None,
) -> Notice:
    return Notice(
        id="notice-change-1",
        source_site="ccgp",
        title="服务器采购项目",
        publish_time="2026-08-16 09:00",
        region="上海",
        purchaser="测试采购人",
        source_url="https://example.com/notice-change-1",
        content_text=core_content,
        core_content=core_content,
        attachments=attachments or [],
        fields={
            "structured_fields": {
                "budget": budget,
                "bid_deadline": bid_deadline,
                "project_no": "TEST-001",
            }
        },
    )


if __name__ == "__main__":
    unittest.main()
