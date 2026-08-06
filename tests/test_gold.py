from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps
from tendertrace.gold import evaluate_gold_recall
from tendertrace.retrieval import upsert_notice_fts


class GoldEvaluationTests(unittest.TestCase):
    def test_gold_recall_uses_annotated_notices_not_proxy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings.load(root)
            init_db(settings)
            _insert_notice(
                settings,
                notice_id="ccgp:gold-hit",
                title="上海充电设施建设项目公开招标公告",
                content_text="新能源汽车充电基础设施采购。",
                source_url="https://example.com/gold-hit.html",
            )
            gold_path = root / "gold.json"
            gold_path.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "id": "case-1",
                                "query": "最近1个月上海充电桩招标信息有哪些",
                                "now": "2026-07-06T10:00:00+08:00",
                                "gold_notices": [
                                    {"source_url": "https://example.com/gold-hit.html"}
                                ],
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = evaluate_gold_recall(settings, gold_path=gold_path, k_values=(1, 5))

        self.assertTrue(result.available)
        self.assertEqual(result.annotated_case_count, 1)
        self.assertEqual(result.expected_total, 1)
        self.assertEqual(result.recall_at["1"], 1.0)
        self.assertEqual(result.recall_at["5"], 1.0)

    def test_gold_without_annotations_is_explicitly_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings.load(root)
            init_db(settings)
            gold_path = root / "gold.json"
            gold_path.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "id": "case-1",
                                "query": "最近1个月上海充电桩招标信息有哪些",
                                "gold_notices": [],
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = evaluate_gold_recall(settings, gold_path=gold_path)

        self.assertFalse(result.available)
        self.assertEqual(result.cases[0]["status"], "needs_annotation")


def _insert_notice(
    settings: Settings,
    *,
    notice_id: str,
    title: str,
    content_text: str,
    source_url: str,
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
                source_url,
                source_url,
                title,
                datetime(2026, 7, 1, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai")).isoformat(),
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
