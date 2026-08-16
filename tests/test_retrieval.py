from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps
from tendertrace.intent import compile_intent
from tendertrace.retrieval import parse_date, search_notices, upsert_notice_fts


NOW = datetime(2026, 7, 6, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


class RetrievalTests(unittest.TestCase):
    def test_parse_date_extracts_chinese_date_from_deadline_text(self) -> None:
        parsed = parse_date("提交投标文件截止时间：2026年08月03日 10:00（北京时间）")

        self.assertEqual(parsed.isoformat(), "2026-08-03")

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

    def test_fts_does_not_match_generic_service_tokens_for_server_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            _insert_notice(
                settings,
                notice_id="ccgp:server-hit",
                title="上海存储服务器扩容项目公开招标公告",
                content_text="采购机架式服务器及配套存储设备。",
            )
            _insert_notice(
                settings,
                notice_id="ccgp:medical-noise",
                title="上海社区卫生服务中心医疗设备采购公告",
                content_text="采购医用诊断设备和呼吸机。",
            )

            bidql = compile_intent("最近1个月上海服务器招标信息都有哪些", now=NOW)
            result = search_notices(settings, bidql, max_results=5)

        self.assertEqual([notice.id for notice in result.notices], ["server-hit"])

    def test_international_scope_filters_local_results_by_source_family(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            for source_site in ("ccgp", "worldbank", "adb", "find_tender"):
                _insert_notice(
                    settings,
                    notice_id=f"{source_site}:server-hit",
                    source_site=source_site,
                    title=f"{source_site} server procurement",
                    content_text="Supply of server hardware.",
                )

            base = {
                "topic": {"core": ["server"], "expanded": [], "negative": []},
                "time": {"resolved_window": {"from": "2026-06-01", "to": "2026-08-01"}},
            }
            uk = search_notices(
                settings,
                compile_intent("最近1个月英国服务器采购信息", now=NOW),
                max_results=10,
            )
            global_result = search_notices(
                settings,
                {**base, "region": {"scope": "global", "aliases": ["全球"]}},
                max_results=10,
            )
            domestic = search_notices(
                settings,
                {**base, "region": {"scope": "domestic", "aliases": []}},
                max_results=10,
            )

        self.assertEqual([notice.source_site for notice in uk.notices], ["find_tender"])
        self.assertEqual(
            {notice.source_site for notice in global_result.notices},
            {"worldbank", "adb", "find_tender"},
        )
        self.assertEqual([notice.source_site for notice in domestic.notices], ["ccgp"])


def _insert_notice(
    settings: Settings,
    *,
    notice_id: str,
    title: str,
    content_text: str,
    source_site: str = "ccgp",
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
                source_site,
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
