from pathlib import Path
import tempfile
import unittest

from tendertrace.adapters.ccgp import Notice
from tendertrace.config import Settings
from tendertrace.db import connection
from tendertrace.scheduling.ingest_subscriptions import (
    create_ingest_subscription,
    list_ingest_subscriptions,
    run_ingest_subscription,
)


class StaticIngestAdapter:
    def __init__(self) -> None:
        self.last_source_stats = []

    def collect(self, bidql, *, max_pages: int = 1, max_results: int = 10) -> list[Notice]:
        self.last_source_stats = [
            {"source": "fake", "status": "finished", "count": 1, "error": None}
        ]
        return [
            Notice(
                id="ingest-sub-notice",
                source_site="fake",
                title="苏州充电设施采购公开招标公告",
                publish_time="2026-07-01 09:00",
                region="江苏苏州",
                purchaser="苏州某单位",
                source_url="https://example.com/ingest-sub-notice.html",
                content_text="本项目采购新能源汽车充电基础设施。",
                core_content="本项目采购新能源汽车充电基础设施。",
            )
        ]


class IngestSubscriptionTests(unittest.TestCase):
    def test_ingest_subscription_is_separate_from_user_subscription(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            subscription = create_ingest_subscription(
                settings,
                name="苏州充电桩采集",
                topics=["充电桩"],
                regions=["苏州"],
                cron="0 */6 * * *",
            )
            listed = list_ingest_subscriptions(settings)
            result = run_ingest_subscription(
                settings,
                subscription_id=subscription.id,
                adapter=StaticIngestAdapter(),
            )
            with connection(settings) as conn:
                user_subscription_count = conn.execute(
                    "SELECT COUNT(*) FROM subscriptions"
                ).fetchone()[0]
                ingest_subscription_count = conn.execute(
                    "SELECT COUNT(*) FROM ingest_subscriptions"
                ).fetchone()[0]
                notice_count = conn.execute("SELECT COUNT(*) FROM notices").fetchone()[0]

        self.assertEqual([item.id for item in listed], [subscription.id])
        self.assertEqual(result.persisted, 1)
        self.assertEqual(user_subscription_count, 0)
        self.assertEqual(ingest_subscription_count, 1)
        self.assertEqual(notice_count, 1)


if __name__ == "__main__":
    unittest.main()
