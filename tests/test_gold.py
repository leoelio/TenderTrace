from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps
from tendertrace.adapters.ccgp import Notice
from tendertrace.gold import build_gold_candidates, build_gold_coverage, evaluate_gold_recall
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

    def test_gold_candidates_can_resume_finished_case(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings.load(root)
            gold_path = _write_candidate_gold(root)

            result = build_gold_candidates(
                settings,
                gold_path=gold_path,
                case_ids=["case-2"],
                existing_payload={
                    "items": [
                        {
                            "id": "case-2",
                            "query": "最近1个月上海服务器招标信息",
                            "status": "finished",
                            "candidate_count": 1,
                            "candidates": [{"title": "cached"}],
                        }
                    ]
                },
                adapter=FailingAdapter(),
            )

        self.assertEqual(result["selected_case_count"], 1)
        self.assertTrue(result["items"][0]["cached"])
        self.assertEqual(result["items"][0]["candidates"][0]["title"], "cached")

    def test_gold_candidates_continue_after_case_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings.load(root)
            gold_path = _write_candidate_gold(root)

            result = build_gold_candidates(
                settings,
                gold_path=gold_path,
                max_results=3,
                case_timeout_seconds=0,
                adapter=FlakyCandidateAdapter(),
            )

        self.assertEqual([item["status"] for item in result["items"]], ["failed", "finished"])
        self.assertEqual(result["items"][1]["candidate_count"], 1)

    def test_gold_coverage_reports_annotation_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings.load(root)
            gold_path = root / "gold.json"
            gold_path.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "id": "case-1",
                                "query": "recent Shanghai charging pile bids",
                                "gold_notices": [{"source_url": "https://example.com/a.html"}],
                            },
                            {
                                "id": "case-2",
                                "query": "recent Shanghai server bids",
                                "gold_notices": [],
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = build_gold_coverage(settings, gold_path=gold_path)

        self.assertTrue(result.available)
        self.assertFalse(result.complete)
        self.assertEqual(result.case_count, 2)
        self.assertEqual(result.annotated_case_count, 1)
        self.assertEqual(result.empty_case_count, 1)
        self.assertEqual(result.expected_total, 1)
        self.assertEqual(result.annotation_completion, 0.5)
        self.assertEqual(result.cases[1]["status"], "needs_annotation")


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


def _write_candidate_gold(root: Path) -> Path:
    path = root / "gold.json"
    path.write_text(
        json.dumps(
            {
                "cases": [
                    {"id": "case-1", "query": "最近1个月上海充电桩招标信息"},
                    {"id": "case-2", "query": "最近1个月上海服务器招标信息"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


class FailingAdapter:
    def collect(self, *args, **kwargs):
        raise AssertionError("cached case should not collect")


class FlakyCandidateAdapter:
    def __init__(self) -> None:
        self.calls = 0
        self.last_source_stats = []

    def collect(self, *args, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("source unavailable")
        return [
            Notice(
                id="notice-1",
                source_site="ccgp",
                title="上海服务器采购招标公告",
                publish_time="2026-07-01",
                region="上海",
                purchaser="上海某单位",
                source_url="https://example.com/notice-1.html",
            )
        ]


if __name__ == "__main__":
    unittest.main()
