from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from tendertrace.adapters.ccgp import Notice
from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.runlog import get_run, list_outbox_messages
from tendertrace.runner import RunOnceResult
from tendertrace.scheduling.subscriptions import (
    create_subscription,
    ensure_subscription,
    list_subscriptions,
    run_subscription,
)


class StableAdapter:
    def collect(self, bidql, *, max_pages: int = 1, max_results: int = 10) -> list[Notice]:
        return [
            Notice(
                id="stable-notice-1",
                source_site="ccgp",
                title="上海某单位服务器采购公开招标公告",
                publish_time="2026-07-06 09:30",
                region="上海",
                purchaser="上海某单位",
                source_url="https://www.ccgp.gov.cn/stable-notice-1.htm",
                core_content="项目概况：上海某单位服务器采购项目。预算金额：120万元。",
            )
        ]


class SubscriptionTests(unittest.TestCase):
    def test_ensure_subscription_reuses_semantic_match_and_separates_receivers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            schedule = {"kind": "recurring", "frequency": "daily", "time": "09:00"}
            first, first_created = ensure_subscription(
                settings,
                query="最近1个月苏州充电桩招标信息",
                schedule_override=schedule,
                delivery_channels=("web", "outbox", "feishu"),
                feishu_receive_id="oc_team_a",
                feishu_receive_id_type="chat_id",
            )
            with connection(settings) as conn:
                conn.execute("UPDATE subscriptions SET status = 'deleted' WHERE id = ?", (first.id,))
            reused, reused_created = ensure_subscription(
                settings,
                query="  最近1个月苏州充电桩招标信息  ",
                schedule_override=schedule,
                delivery_channels=("feishu", "outbox", "web"),
                feishu_receive_id="oc_team_a",
                feishu_receive_id_type="chat_id",
            )
            other, other_created = ensure_subscription(
                settings,
                query="最近1个月苏州充电桩招标信息",
                schedule_override=schedule,
                delivery_channels=("web", "outbox", "feishu"),
                feishu_receive_id="oc_team_b",
                feishu_receive_id_type="chat_id",
            )

        self.assertTrue(first_created)
        self.assertFalse(reused_created)
        self.assertEqual(reused.id, first.id)
        self.assertEqual(reused.status, "active")
        self.assertTrue(other_created)
        self.assertNotEqual(other.id, first.id)

    def test_create_subscription_requires_schedule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            with self.assertRaises(ValueError):
                create_subscription(
                    settings,
                    query="最近1个月的上海区域内的服务器招标信息都有哪些",
                    now=datetime(2026, 7, 6, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                )

    def test_subscription_run_is_incremental_with_sent_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            subscription = create_subscription(
                settings,
                query="最近1个月的上海区域内的服务器招标信息都有哪些，请汇总后每天9:00发送给我",
                now=datetime(2026, 7, 6, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                max_pages=2,
                max_results=5,
            )
            adapter = StableAdapter()

            first = run_subscription(
                settings,
                subscription_id=subscription.id,
                now=datetime(2026, 7, 6, 10, 1, tzinfo=ZoneInfo("Asia/Shanghai")),
                adapter=adapter,
            )
            second = run_subscription(
                settings,
                subscription_id=subscription.id,
                now=datetime(2026, 7, 6, 10, 2, tzinfo=ZoneInfo("Asia/Shanghai")),
                adapter=adapter,
            )

            subscriptions = list_subscriptions(settings)
            first_run = get_run(settings, first.run_id)
            second_run = get_run(settings, second.run_id)
            messages = list_outbox_messages(settings)
            with connection(settings) as conn:
                sent_rows = conn.execute("SELECT * FROM sent_history").fetchall()
            first_docx_exists = Path(first.docx_path).exists()
            second_docx_exists = Path(second.docx_path).exists()

        self.assertEqual(subscription.schedule_kind, "recurring")
        self.assertEqual(subscription.cron, "0 9 * * *")
        self.assertEqual(len(subscriptions), 1)
        self.assertEqual(first.notice_count, 1)
        self.assertEqual(second.notice_count, 0)
        self.assertTrue(first_docx_exists)
        self.assertTrue(second_docx_exists)
        self.assertEqual(first_run["subscription_id"], subscription.id)
        self.assertEqual(first_run["mode"], "incremental")
        self.assertEqual(first_run["stats"]["new"], 1)
        self.assertEqual(second_run["stats"]["skipped_sent"], 1)
        self.assertEqual(len(sent_rows), 1)
        self.assertEqual(sent_rows[0]["cluster_key"], "ccgp:stable-notice-1")
        self.assertTrue(all(message.subscription_id == subscription.id for message in messages))

    def test_create_subscription_accepts_ui_schedule_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))

            subscription = create_subscription(
                settings,
                query="最近36个月杭州市的空调或者服务器投标信息都有哪些",
                now=datetime(2026, 7, 6, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                max_pages=3,
                max_results=8,
                schedule_override={"kind": "recurring", "frequency": "weekly", "weekday": 1, "time": "10:30"},
                model_strategy="hybrid",
            )

        self.assertEqual(subscription.schedule_kind, "recurring")
        self.assertEqual(subscription.cron, "30 10 * * 1")
        self.assertEqual(subscription.bidql["schedule"]["origin"], "ui_override")
        self.assertEqual(
            subscription.bidql["_runtime"],
            {"max_pages": 3, "max_results": 8, "model_strategy": "hybrid"},
        )

    def test_subscription_preserves_feishu_origin_chat_for_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            subscription = create_subscription(
                settings,
                query="最近一个月上海服务器招标，每天9点发送给我",
                now=datetime(2026, 7, 6, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                delivery_channels=("web", "outbox", "feishu"),
                feishu_receive_id="oc_origin",
                feishu_receive_id_type="chat_id",
            )
            with patch(
                "tendertrace.scheduling.subscriptions.run_once",
                return_value=RunOnceResult(
                    run_id="run-origin",
                    status="finished",
                    notice_count=0,
                    docx_path="report.docx",
                    outbox_path="outbox/report.docx",
                    trace_events=1,
                ),
            ) as mocked:
                run_subscription(settings, subscription_id=subscription.id)

        runtime = subscription.bidql["_runtime"]
        self.assertEqual(runtime["feishu_receive_id"], "oc_origin")
        self.assertEqual(mocked.call_args.kwargs["feishu_receive_id"], "oc_origin")
        self.assertEqual(mocked.call_args.kwargs["feishu_receive_id_type"], "chat_id")


if __name__ == "__main__":
    unittest.main()
