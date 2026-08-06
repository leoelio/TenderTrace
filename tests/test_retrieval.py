from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps
from tendertrace.intent import compile_intent
from tendertrace.retrieval import search_notices, upsert_notice_fts


NOW = datetime(2026, 7, 6, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


class RetrievalTests(unittest.TestCase):
    def test_fts_retrieval_matches_synonym_and_reuses_stored_notice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            _insert_notice(
                settings,
                notice_id="ccgp:charging-1",
                title="上海充电设施建设项目公开招标公告",
                content_text="采购内容为新能源汽车充电基础设施。",
            )

            bidql = compile_intent("最近1个月上海充电桩招标信息都有哪些", now=NOW)
            result = search_notices(settings, bidql, max_results=5)

        self.assertEqual(result.stats["engine"], "fts5")
        self.assertEqual([notice.title for notice in result.notices], ["上海充电设施建设项目公开招标公告"])

    def test_bm25_prefers_title_match_over_content_only_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            _insert_notice(
                settings,
                notice_id="ccgp:content-hit",
                title="上海市政配套工程公开招标公告",
                content_text="本项目包含充电设施采购与安装。",
            )
            _insert_notice(
                settings,
                notice_id="ccgp:title-hit",
                title="上海充电设施采购公开招标公告",
                content_text="本项目为配套工程采购。",
            )

            bidql = compile_intent("最近1个月上海充电桩招标信息都有哪些", now=NOW)
            result = search_notices(settings, bidql, max_results=5)

        self.assertEqual(result.notices[0].id, "title-hit")


def _insert_notice(
    settings: Settings,
    *,
    notice_id: str,
    title: str,
    content_text: str,
) -> None:
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(
                id, source_site, source_url, canonical_url, title, publish_time,
                region, purchaser, content_text, core_content, attachments_json,
                fields_json, snapshot_sha256, simhash64
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                notice_id,
                "ccgp",
                f"https://example.com/{notice_id}.html",
                f"https://example.com/{notice_id}.html",
                title,
                "2026-07-01 09:00",
                "上海",
                "上海某单位",
                content_text,
                content_text,
                "[]",
                json_dumps({"cluster_key": notice_id}),
                "",
                "",
            ),
        )
        upsert_notice_fts(
            conn,
            notice_id=notice_id,
            title=title,
            content_text=content_text,
            core_content=content_text,
        )


if __name__ == "__main__":
    unittest.main()
