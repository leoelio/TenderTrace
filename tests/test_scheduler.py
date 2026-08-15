import os
from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.scheduling.ingest_subscriptions import IngestSubscription
from tendertrace.scheduling.scheduler import (
    schedule_feishu_lead_import,
    schedule_ingest_pool,
    schedule_ingest_subscription,
    schedule_subscription,
)
from tendertrace.scheduling.subscriptions import Subscription


class FakeScheduler:
    def __init__(self) -> None:
        self.jobs = []

    def add_job(self, *args, **kwargs) -> None:
        self.jobs.append({"args": args, "kwargs": kwargs})


class SchedulerTests(unittest.TestCase):
    def test_recurring_subscription_registers_cron_job(self) -> None:
        scheduler = FakeScheduler()
        settings = Settings.load()
        subscription = Subscription(
            id="sub-1",
            original_query="每天9:00发送服务器招标信息",
            bidql={"schedule": {"kind": "recurring"}},
            schedule_kind="recurring",
            cron="0 9 * * *",
            timezone="Asia/Shanghai",
            status="active",
        )

        schedule_subscription(scheduler, settings, subscription)

        self.assertEqual(len(scheduler.jobs), 1)
        self.assertEqual(scheduler.jobs[0]["kwargs"]["id"], "subscription:sub-1")
        self.assertEqual(scheduler.jobs[0]["kwargs"]["kwargs"]["subscription_id"], "sub-1")
        self.assertTrue(scheduler.jobs[0]["kwargs"]["replace_existing"])

    def test_ingest_pool_registers_cron_job(self) -> None:
        scheduler = FakeScheduler()
        old_env = {
            "TENDERTRACE_INGEST_CRON": os.environ.get("TENDERTRACE_INGEST_CRON"),
        }
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["TENDERTRACE_INGEST_CRON"] = "0 */6 * * *"
            try:
                settings = Settings.load(Path(tmp))
                schedule_ingest_pool(scheduler, settings)
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual(len(scheduler.jobs), 1)
        self.assertEqual(scheduler.jobs[0]["kwargs"]["id"], "ingest:pool")
        self.assertTrue(scheduler.jobs[0]["kwargs"]["replace_existing"])

    def test_ingest_subscription_registers_separate_job(self) -> None:
        scheduler = FakeScheduler()
        settings = Settings.load()
        subscription = IngestSubscription(
            id="ingest-1",
            name="苏州充电桩采集",
            topics=["充电桩"],
            regions=["苏州"],
            cron="0 */6 * * *",
            timezone="Asia/Shanghai",
            window_days=30,
            max_pages=1,
            max_results=20,
            status="active",
        )

        schedule_ingest_subscription(scheduler, settings, subscription)

        self.assertEqual(len(scheduler.jobs), 1)
        self.assertEqual(scheduler.jobs[0]["kwargs"]["id"], "ingest_subscription:ingest-1")
        self.assertEqual(scheduler.jobs[0]["kwargs"]["kwargs"]["subscription_id"], "ingest-1")

    def test_feishu_lead_import_registers_single_coalesced_job(self) -> None:
        scheduler = FakeScheduler()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.local").write_text(
                "TENDERTRACE_FEISHU_APP_ID=cli_test\n"
                "TENDERTRACE_FEISHU_APP_SECRET=secret\n"
                "TENDERTRACE_FEISHU_BITABLE_APP_TOKEN=base_test\n"
                "TENDERTRACE_FEISHU_BITABLE_TABLE_ID=tbl_test\n"
                "TENDERTRACE_FEISHU_LEAD_IMPORT_ENABLED=true\n"
                "TENDERTRACE_FEISHU_LEAD_IMPORT_CRON=*/10 * * * *\n",
                encoding="utf-8",
            )
            settings = Settings.load(root)

        schedule_feishu_lead_import(scheduler, settings)

        job = scheduler.jobs[0]["kwargs"]
        self.assertEqual(job["id"], "feishu:partner-leads")
        self.assertTrue(job["replace_existing"])
        self.assertTrue(job["coalesce"])
        self.assertEqual(job["max_instances"], 1)


if __name__ == "__main__":
    unittest.main()
