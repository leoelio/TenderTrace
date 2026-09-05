from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tempfile
from unittest import TestCase
from zoneinfo import ZoneInfo

from tendertrace.adapters.ccgp import Notice
from tendertrace.config import Settings
from tendertrace.runner import run_once


class _FlakyAdapter:
    """Returns no notices on the first call, then one notice afterwards."""

    def __init__(self) -> None:
        self.calls = 0

    def collect(
        self,
        bidql: dict[str, object],
        *,
        max_pages: int = 1,
        max_results: int = 10,
    ) -> list[Notice]:
        self.calls += 1
        if self.calls == 1:
            return []
        return [
            Notice(
                id="repair-1",
                source_site="ccgp",
                title="上海某单位服务器采购公开招标公告",
                publish_time="2026-07-06 09:30",
                region="上海",
                purchaser="上海某单位",
                source_url="https://www.ccgp.gov.cn/repair-1.html",
                core_content="项目概况：上海某单位服务器采购项目。预算金额：120万元。",
            )
        ]


class _EmptyAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def collect(
        self,
        bidql: dict[str, object],
        *,
        max_pages: int = 1,
        max_results: int = 10,
    ) -> list[Notice]:
        self.calls += 1
        return []


class ReflectionLoopTests(TestCase):
    def test_repair_round_recovers_when_second_collect_finds_notices(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            adapter = _FlakyAdapter()

            result = run_once(
                settings=settings,
                query="最近1个月上海服务器招标信息都有哪些",
                now=datetime(2026, 7, 6, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                adapter=adapter,
            )

        self.assertEqual(adapter.calls, 2)
        self.assertEqual(result.notice_count, 1)
        self.assertEqual(result.stats["repair_rounds"], 1)

    def test_repair_round_converges_when_collect_stays_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            adapter = _EmptyAdapter()

            result = run_once(
                settings=settings,
                query="最近1个月上海服务器招标信息都有哪些",
                now=datetime(2026, 7, 6, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                adapter=adapter,
            )

        self.assertEqual(adapter.calls, 2)
        self.assertEqual(result.notice_count, 0)
        self.assertEqual(result.stats["repair_rounds"], 1)


if __name__ == "__main__":
    import unittest

    unittest.main()
