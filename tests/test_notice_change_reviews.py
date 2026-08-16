from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from tendertrace.adapters.ccgp import Notice
from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.notice_change_reviews import change_review_summaries
from tendertrace.opportunity import get_opportunity, list_opportunities
from tendertrace.runner import persist_notices_and_clusters
from tendertrace.workflow import WorkflowGateError, apply_action, get_workflow, update_workflow


class NoticeChangeReviewTests(unittest.TestCase):
    def test_material_change_invalidates_go_until_owner_acknowledges_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            persist_notices_and_clusters(settings, [_notice("100 万元")])
            update_workflow(
                settings,
                "ccgp:change-review-1",
                stage="bidding",
                owner_open_id="ou_owner",
                owner_name="张三",
                decision="go",
                decision_by="销售经理",
                decision_at="2026-08-15T10:00:00+08:00",
            )

            persist_notices_and_clusters(settings, [_notice("130 万元")])
            opportunity = get_opportunity(settings, "ccgp:change-review-1")
            workflow = get_workflow(settings, "ccgp:change-review-1")
            with self.assertRaises(WorkflowGateError) as blocked:
                apply_action(settings, "ccgp:change-review-1", "mark_won")

            acknowledged = apply_action(
                settings,
                "ccgp:change-review-1",
                "acknowledge_change",
                actor_open_id="ou_owner",
                actor_name="张三",
                decision_reason="预算变化已核对，重新评估报价空间",
            )
            refreshed = get_opportunity(settings, "ccgp:change-review-1")
            with connection(settings) as conn:
                event_actions = [
                    str(row["action"])
                    for row in conn.execute(
                        """
                        SELECT action FROM opportunity_events
                        WHERE notice_id = ? ORDER BY rowid
                        """,
                        ("ccgp:change-review-1",),
                    ).fetchall()
                ]

        assert opportunity is not None
        assert refreshed is not None
        self.assertEqual(workflow.decision, "pending")
        self.assertEqual(workflow.next_action, "复核公告重大变更")
        self.assertEqual(opportunity["change_review"]["pending_count"], 1)
        self.assertEqual(
            opportunity["action_contract"]["actions"][0]["action"],
            "acknowledge_change",
        )
        self.assertIn("尚未复核", blocked.exception.reasons[0])
        self.assertTrue(acknowledged.decision_requested_at)
        self.assertEqual(refreshed["change_review"]["status"], "acknowledged")
        self.assertEqual(refreshed["change_review"]["acknowledged_by"], "张三")
        self.assertEqual(
            refreshed["action_contract"]["actions"][0]["action"],
            "approve_bid",
        )
        self.assertEqual(
            event_actions,
            ["notice_change_review_required", "acknowledge_notice_change"],
        )

    def test_non_material_timestamp_change_does_not_create_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            notice = _notice("100 万元")
            persist_notices_and_clusters(settings, [notice])
            update_workflow(
                settings,
                "ccgp:change-review-1",
                stage="pursuing",
                decision="go",
            )

            persist_notices_and_clusters(
                settings,
                [replace(notice, publish_time="2026-08-16 10:00")],
            )
            summary = change_review_summaries(settings, ["ccgp:change-review-1"])
            workflow = get_workflow(settings, "ccgp:change-review-1")

        self.assertEqual(summary, {})
        self.assertEqual(workflow.decision, "go")

    def test_overdue_change_review_enters_shared_management_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            persist_notices_and_clusters(settings, [_notice("100 万元")])
            update_workflow(
                settings,
                "ccgp:change-review-1",
                stage="pursuing",
                owner_name="张三",
                decision="go",
            )
            persist_notices_and_clusters(settings, [_notice("130 万元")])
            with connection(settings) as conn:
                conn.execute(
                    """
                    UPDATE notice_change_reviews
                    SET required_by = '2020-01-01T00:00:00+00:00'
                    """
                )

            payload = list_opportunities(settings, limit=20)

        queue = payload["summary"]["action_queue"]
        self.assertEqual(queue["change_review_pending"], 1)
        self.assertEqual(queue["change_review_overdue"], 1)
        self.assertEqual(queue["decision_pending"], 0)
        self.assertEqual(queue["escalations"][0]["issue_types"], ["change_review"])
        self.assertEqual(
            queue["escalations"][0]["change_review_due_at"],
            "2020-01-01T00:00:00+00:00",
        )


def _notice(budget: str) -> Notice:
    return Notice(
        id="change-review-1",
        source_site="ccgp",
        title="服务器采购项目",
        publish_time="2026-08-16 09:00",
        region="上海",
        purchaser="测试采购人",
        source_url="https://example.com/change-review-1",
        content_text=f"预算 {budget}，投标截止 2026-09-20",
        core_content=f"预算 {budget}，投标截止 2026-09-20",
        fields={
            "structured_fields": {
                "budget": budget,
                "bid_deadline": "2026-09-20 17:00",
                "project_no": "CHANGE-REVIEW-001",
            }
        },
    )


if __name__ == "__main__":
    unittest.main()
