import unittest

from tendertrace.adapters.ccgp import Notice
from tendertrace.adapters.multi import MultiSourceAdapter


class StaticAdapter:
    def __init__(self, name: str, notices: list[Notice]) -> None:
        self.name = name
        self.notices = notices

    def collect(self, bidql, *, max_pages: int = 1, max_results: int = 10) -> list[Notice]:
        return self.notices[:max_results]


class CitySensitiveAdapter:
    name = "city-sensitive"

    def collect(self, bidql, *, max_pages: int = 1, max_results: int = 10) -> list[Notice]:
        if bidql.get("region", {}).get("city"):
            return []
        return [_notice("ggzy", "province-1")]


class FailingAdapter:
    name = "failing"

    def collect(self, bidql, *, max_pages: int = 1, max_results: int = 10) -> list[Notice]:
        raise RuntimeError("source unavailable")


def _notice(source: str, notice_id: str) -> Notice:
    return Notice(
        id=notice_id,
        source_site=source,
        title=f"{source}-{notice_id}设备采购公告",
        publish_time="2026-07-06",
        region="上海",
        purchaser="采购人",
        source_url=f"https://example.com/{source}/{notice_id}.html",
        core_content="项目概况：设备采购。",
    )


class MultiSourceAdapterTests(unittest.TestCase):
    def test_collect_merges_sources_round_robin(self) -> None:
        adapter = MultiSourceAdapter(
            [
                StaticAdapter("ccgp", [_notice("ccgp", "1"), _notice("ccgp", "2")]),
                StaticAdapter("ggzy", [_notice("ggzy", "1")]),
            ]
        )

        notices = adapter.collect({}, max_results=3)

        self.assertEqual([notice.source_site for notice in notices], ["ccgp", "ggzy", "ccgp"])
        self.assertEqual([stat.source for stat in adapter.last_source_stats], ["ccgp", "ggzy"])
        self.assertEqual(adapter.last_source_stats[0].count, 2)

    def test_collect_keeps_other_sources_when_one_fails(self) -> None:
        adapter = MultiSourceAdapter(
            [
                FailingAdapter(),
                StaticAdapter("ggzy", [_notice("ggzy", "1")]),
            ]
        )

        notices = adapter.collect({}, max_results=2)

        self.assertEqual(len(notices), 1)
        self.assertEqual(adapter.last_source_stats[0].status, "failed")
        self.assertEqual(adapter.last_source_stats[1].status, "finished")

    def test_collect_relaxes_city_scope_when_exact_city_has_no_results(self) -> None:
        adapter = MultiSourceAdapter([CitySensitiveAdapter()])
        bidql = {
            "region": {
                "province": "浙江",
                "city": "杭州",
                "adcode": "330000",
                "city_aliases": ["杭州", "杭州市"],
            },
            "topic": {"core": []},
        }

        notices = adapter.collect(bidql, max_results=2)

        self.assertEqual(len(notices), 1)
        self.assertTrue(adapter.last_source_stats[0].relaxed_city)


if __name__ == "__main__":
    unittest.main()
