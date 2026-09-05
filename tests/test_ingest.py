from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from tendertrace.adapters.ccgp import Notice
from tendertrace.config import Settings
from tendertrace.db import connection
from tendertrace.ingest import run_ingest_cycle
from tendertrace.intent import compile_intent
from tendertrace.retrieval import search_notices
from tendertrace.source_map import source_health


class PoolAdapter:
    def __init__(self) -> None:
        self.calls = 0
        self.last_source_stats = []

    def collect(
        self,
        bidql: dict[str, object],
        *,
        max_pages: int = 1,
        max_results: int = 10,
    ) -> list[Notice]:
        self.calls += 1
        self.last_source_stats = [
            {
                "source": "fake",
                "status": "finished",
                "count": 1,
                "error": None,
                "fetch_stats": {"requests": 1, "succeeded": 1, "avg_elapsed_ms": 12},
            }
        ]
        return [
            Notice(
                id=f"notice-{self.calls}",
                source_site="fake",
                title="苏州充电设施采购公开招标公告",
                publish_time="2026-07-01 09:00",
                region="江苏苏州",
                purchaser="苏州某单位",
                source_url=f"https://example.com/{self.calls}.html",
                content_text="本项目采购新能源汽车充电基础设施。",
                core_content="本项目采购新能源汽车充电基础设施。",
            )
        ]


class IngestTests(unittest.TestCase):
    def test_ingest_cycle_persists_notices_for_later_local_retrieval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            adapter = PoolAdapter()
            result = run_ingest_cycle(
                settings,
                topics=["充电桩"],
                regions=["苏州"],
                now=datetime(2026, 7, 6, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                max_results=1,
                adapter=adapter,
            )
            bidql = compile_intent(
                "最近1个月苏州充电桩招标信息都有哪些",
                now=datetime(2026, 7, 6, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            )
            local = search_notices(settings, bidql, max_results=5)
            with connection(settings) as conn:
                notice_count = conn.execute("SELECT COUNT(*) FROM notices").fetchone()[0]
                observation_count = conn.execute("SELECT COUNT(*) FROM source_observations").fetchone()[0]
            health = source_health(settings)["fake"]

        self.assertEqual(result.query_count, 1)
        self.assertEqual(result.persisted, 1)
        self.assertEqual(adapter.calls, 1)
        self.assertEqual(notice_count, 1)
        self.assertEqual(observation_count, 1)
        self.assertEqual(health["runs"], 1)
        self.assertEqual(health["notices"], 1)
        self.assertEqual(health["health_status"], "healthy")
        self.assertEqual(local.notices[0].title, "苏州充电设施采购公开招标公告")


if __name__ == "__main__":
    unittest.main()
