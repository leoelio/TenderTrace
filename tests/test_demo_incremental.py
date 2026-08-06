from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from tendertrace.adapters.ccgp import Notice
from tendertrace.config import Settings
from tendertrace.demo_incremental import run_incremental_demo


class StableAdapter:
    def collect(self, bidql, *, max_pages: int = 1, max_results: int = 10) -> list[Notice]:
        return [
            Notice(
                id="stable-demo-1",
                source_site="ccgp",
                title="上海某单位服务器采购公开招标公告",
                publish_time="2026-07-06 09:30",
                region="上海",
                purchaser="上海某单位",
                source_url="https://www.ccgp.gov.cn/stable-demo-1.htm",
                core_content="项目概况：上海某单位服务器采购项目。预算金额：120万元。",
            )
        ]


class DemoIncrementalTests(unittest.TestCase):
    def test_demo_runs_twice_and_reports_second_run_incremental_skip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))

            result = run_incremental_demo(
                settings,
                query="最近1个月的上海区域内的服务器招标信息都有哪些，请汇总后每天9:00发送给我",
                now=datetime(2026, 7, 6, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                max_pages=1,
                max_results=5,
                adapter=StableAdapter(),
            )

        incremental = result["incremental"]
        self.assertEqual(incremental["first_notice_count"], 1)
        self.assertEqual(incremental["second_notice_count"], 0)
        self.assertEqual(incremental["second_skipped_sent"], 1)
        self.assertTrue(incremental["only_new_content_on_second_run"])
        self.assertEqual(result["subscription"]["cron"], "0 9 * * *")


if __name__ == "__main__":
    unittest.main()
