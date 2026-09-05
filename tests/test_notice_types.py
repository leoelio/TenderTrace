from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.pipeline.notice_types import (
    EXCLUDED_FROM_TENDER_SEARCH,
    classify_and_persist_notice,
    classify_notice_type,
    classify_notices,
)


class NoticeTypeClassifierTests(unittest.TestCase):
    def test_classifies_four_main_categories_from_title(self) -> None:
        cases = {
            "某服务器采购项目招标公告": "tender",
            "某服务器采购项目中标公告": "award",
            "某服务器采购项目废标公告": "cancelled",
            "某服务器采购项目更正公告": "correction",
        }
        for title, expected in cases.items():
            self.assertEqual(
                classify_notice_type(title).notice_type,
                expected,
                f"{title} should be {expected}",
            )

    def test_cancellation_and_correction_take_precedence_over_tender(self) -> None:
        self.assertEqual(classify_notice_type("某项目招标失败公告").notice_type, "cancelled")
        self.assertEqual(classify_notice_type("某项目采购更正公告").notice_type, "correction")
        self.assertEqual(classify_notice_type("某项目中标候选人公示").notice_type, "award")

    def test_title_match_has_higher_confidence_than_content_match(self) -> None:
        title_match = classify_notice_type("某项目招标公告")
        content_match = classify_notice_type("某项目公告", content_text="本项目现进行招标。")
        self.assertGreater(title_match.confidence, content_match.confidence)
        self.assertEqual(title_match.matched_in, "title")
        self.assertEqual(content_match.matched_in, "content")

    def test_unknown_falls_back_to_other_with_low_confidence(self) -> None:
        result = classify_notice_type("某项目公告", content_text="详见附件。")
        self.assertEqual(result.notice_type, "other")
        self.assertEqual(result.label, "其他")
        self.assertLess(result.confidence, 50)

    def test_exclusion_set_marks_result_like_types_only(self) -> None:
        self.assertIn("award", EXCLUDED_FROM_TENDER_SEARCH)
        self.assertIn("cancelled", EXCLUDED_FROM_TENDER_SEARCH)
        self.assertIn("correction", EXCLUDED_FROM_TENDER_SEARCH)
        self.assertNotIn("tender", EXCLUDED_FROM_TENDER_SEARCH)
        self.assertNotIn("other", EXCLUDED_FROM_TENDER_SEARCH)
        self.assertTrue(classify_notice_type("某项目中标公告").exclude_from_tender_search)
        self.assertFalse(classify_notice_type("某项目招标公告").exclude_from_tender_search)

    def test_classify_and_persist_notice_writes_type_and_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings, "notice-1", "某服务器采购项目招标公告")

            classification = classify_and_persist_notice(settings, "notice-1")
            with connection(settings) as conn:
                row = conn.execute(
                    "SELECT notice_type, notice_type_label FROM notices WHERE id = 'notice-1'"
                ).fetchone()

        self.assertEqual(classification.notice_type, "tender")
        self.assertEqual(row["notice_type"], "tender")
        self.assertEqual(row["notice_type_label"], "招标/采购")

    def test_batch_classify_returns_histogram(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings, "notice-1", "某服务器采购项目招标公告")
            _insert_notice(settings, "notice-2", "某服务器采购项目中标公告")

            result = classify_notices(settings, only_unclassified=True)

        self.assertEqual(result["status"], "finished")
        self.assertEqual(result["scanned_count"], 2)
        self.assertEqual(result["by_type"], {"tender": 1, "award": 1})


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text(
        "TENDERTRACE_DB_PATH=data/test.sqlite3\nTENDERTRACE_SCHEDULER_ENABLED=false\n",
        encoding="utf-8",
    )
    settings = Settings.load(root)
    init_db(settings)
    return settings


def _insert_notice(settings: Settings, notice_id: str, title: str) -> None:
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(id, source_site, source_url, canonical_url, title)
            VALUES (?, 'ccgp', 'https://example.com/' || ?, 'https://example.com/' || ?, ?)
            """,
            (notice_id, notice_id, notice_id, title),
        )


if __name__ == "__main__":
    unittest.main()
