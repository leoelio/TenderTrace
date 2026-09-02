from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.opportunity import list_opportunities
from tendertrace.opportunity_facts import load_fact_audit, upsert_verified_facts


class OpportunityFactTests(unittest.TestCase):
    def test_verified_facts_are_merged_without_mutating_raw_notice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            _insert_notice(settings)
            as_of = datetime(2026, 8, 16, tzinfo=timezone.utc)
            before = list_opportunities(settings, now=as_of)["items"][0]

            overrides = upsert_verified_facts(
                settings,
                notice_id="notice-facts-1",
                facts={
                    "purchaser": "华东数据中心",
                    "project_no": "SH-2026-100",
                    "budget": "预算 180 万元",
                    "bid_deadline": "2026-08-30 17:00",
                    "region": "上海市",
                },
                source_url="https://example.com/notice-facts-1",
                evidence_text="原文披露采购主体、预算和截止时间。",
                note="人工复核原始公告",
                actor="测试分析师",
            )
            after = list_opportunities(settings, now=as_of)["items"][0]
            with connection(settings) as conn:
                raw = conn.execute(
                    "SELECT purchaser, region, fields_json FROM notices WHERE id = ?",
                    ("notice-facts-1",),
                ).fetchone()

        self.assertEqual(len(overrides), 5)
        self.assertEqual(before["purchaser"], "")
        self.assertEqual(after["purchaser"], "华东数据中心")
        self.assertEqual(after["project_no"], "SH-2026-100")
        self.assertEqual(after["budget"], "预算 180 万元")
        self.assertEqual(after["bid_deadline"], "2026-08-30")
        self.assertGreater(
            after["intelligence"]["scores"]["completeness"],
            before["intelligence"]["scores"]["completeness"],
        )
        gates = {gate["key"]: gate["status"] for gate in after["qualification"]["gates"]}
        self.assertEqual(gates["purchaser"], "passed")
        self.assertEqual(gates["deadline"], "passed")
        self.assertEqual(raw["purchaser"], "")
        self.assertEqual(raw["region"], "")
        self.assertEqual(raw["fields_json"], "{}")

    def test_fact_updates_keep_before_after_and_provenance_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            _insert_notice(settings)
            upsert_verified_facts(
                settings,
                notice_id="notice-facts-1",
                facts={"budget": "100 万元"},
                source_url="https://example.com/notice-facts-1",
                evidence_text="首次预算核验",
                actor="分析师甲",
            )
            upsert_verified_facts(
                settings,
                notice_id="notice-facts-1",
                facts={"budget": "120 万元"},
                source_url="https://example.com/notice-facts-1-correction",
                evidence_text="更正公告中的预算",
                actor="分析师乙",
            )
            audit = load_fact_audit(settings, "notice-facts-1")

        self.assertEqual(len(audit), 2)
        self.assertEqual(audit[0]["payload"]["before"]["budget"], "100 万元")
        self.assertEqual(audit[0]["payload"]["after"]["budget"], "120 万元")
        self.assertEqual(audit[0]["actor"], "分析师乙")
        self.assertIn("correction", audit[0]["payload"]["source_url"])

    def test_identical_fact_submission_does_not_duplicate_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            _insert_notice(settings)
            request = {
                "settings": settings,
                "notice_id": "notice-facts-1",
                "facts": {"budget": "120 万元"},
                "source_url": "https://example.com/notice-facts-1",
                "evidence_text": "预算事实摘录",
                "actor": "飞书分析师",
                "channel": "feishu_record_view",
            }

            upsert_verified_facts(**request)
            upsert_verified_facts(**request)
            audit = load_fact_audit(settings, "notice-facts-1")

        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0]["payload"]["channel"], "feishu_record_view")

    def test_fact_source_requires_absolute_http_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            _insert_notice(settings)
            with self.assertRaisesRegex(ValueError, "source_url"):
                upsert_verified_facts(
                    settings,
                    notice_id="notice-facts-1",
                    facts={"budget": "100 万元"},
                    source_url="javascript:alert(1)",
                )


def _insert_notice(settings: Settings) -> None:
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(
                id, source_site, source_url, canonical_url, title, publish_time,
                region, purchaser, content_text, core_content, fields_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "notice-facts-1",
                "ccgp",
                "https://example.com/notice-facts-1",
                "https://example.com/notice-facts-1",
                "服务器扩容采购公告",
                "2026-08-15",
                "",
                "",
                "服务器扩容采购，技术参数与服务要求详见采购文件。",
                "服务器扩容采购。",
                "{}",
            ),
        )


if __name__ == "__main__":
    unittest.main()
