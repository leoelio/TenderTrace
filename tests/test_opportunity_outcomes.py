from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import SCHEMA_VERSION, connection, database_health, init_db
from tendertrace.opportunity_outcomes import (
    get_outcome,
    outcome_snapshots,
    record_outcome,
)
from tendertrace.opportunity import list_opportunities


class OpportunityOutcomeTests(unittest.TestCase):
    def test_records_and_updates_evidence_backed_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)

            created = record_outcome(
                settings,
                "notice-1",
                {
                    "result": "lost",
                    "reason_code": "price",
                    "winner_name": "示例竞争公司",
                    "award_amount": 880000,
                    "currency": "cny",
                    "summary": "最终报价高于中标方，技术评分接近。",
                    "lessons": "下一项目需要提前完成成本拆解与伙伴询价。",
                    "customer_feedback": "价格项差距明显。",
                    "follow_up_action": "两周内完成同类项目报价复盘。",
                    "evidence_url": "https://example.com/award-1",
                },
                expected_result="lost",
                actor="销售负责人",
            )
            updated = record_outcome(
                settings,
                "notice-1",
                {
                    **created.to_dict(),
                    "summary": "复核结果确认价格项为主要失标原因。",
                },
                expected_result="lost",
                actor="销售经理",
            )
            snapshots = outcome_snapshots(settings, ["notice-1", "missing"])

        self.assertEqual(created.reason_label, "价格竞争力")
        self.assertEqual(created.award_amount, 880000)
        self.assertEqual(created.currency, "CNY")
        self.assertEqual(updated.recorded_by, "销售经理")
        self.assertEqual(len(snapshots), 1)
        self.assertIn("复核结果", snapshots["notice-1"].summary)

    def test_rejects_incomplete_or_inconsistent_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            base = {
                "result": "won",
                "reason_code": "technical_fit",
                "summary": "方案评分领先并确认中标。",
                "lessons": "沉淀可复用技术方案。",
                "evidence_text": "客户书面通知确认中标。",
            }

            with self.assertRaisesRegex(ValueError, "must be lost"):
                record_outcome(
                    settings,
                    "notice-1",
                    base,
                    expected_result="lost",
                )
            with self.assertRaisesRegex(ValueError, "lessons"):
                record_outcome(
                    settings,
                    "notice-1",
                    {**base, "lessons": ""},
                )
            with self.assertRaisesRegex(ValueError, "evidence"):
                record_outcome(
                    settings,
                    "notice-1",
                    {**base, "evidence_text": ""},
                )
            with self.assertRaisesRegex(ValueError, "currency"):
                record_outcome(
                    settings,
                    "notice-1",
                    {**base, "award_amount": 100, "currency": ""},
                )
            self.assertIsNone(get_outcome(settings, "notice-1"))

    def test_schema_migration_registers_outcome_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            health = database_health(settings)

        self.assertIn(SCHEMA_VERSION, health["schema_versions"])
        self.assertIn("opportunity_outcomes", health["tables"])

    def test_outcome_is_exposed_and_reused_by_market_learning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            record_outcome(
                settings,
                "notice-1",
                {
                    "result": "lost",
                    "reason_code": "price",
                    "winner_name": "示例竞争公司",
                    "award_amount": 880000,
                    "currency": "CNY",
                    "summary": "价格评分差距导致未中标。",
                    "lessons": "提前完成成本拆解和伙伴询价。",
                    "evidence_url": "https://example.com/result",
                },
            )

            payload = list_opportunities(settings)

        self.assertEqual(payload["items"][0]["outcome"]["result"], "lost")
        learning = payload["summary"]["market"]["outcome_learning"]
        self.assertEqual(learning["sample_count"], 1)
        self.assertEqual(learning["loss_reasons"][0]["name"], "价格竞争力")


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text(
        "TENDERTRACE_DB_PATH=data/test.sqlite3\n",
        encoding="utf-8",
    )
    settings = Settings.load(root)
    init_db(settings)
    return settings


def _insert_notice(settings: Settings) -> None:
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(id, source_site, source_url, canonical_url, title)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "notice-1",
                "ccgp",
                "https://example.com/notice-1",
                "https://example.com/notice-1",
                "服务器采购项目",
            ),
        )


if __name__ == "__main__":
    unittest.main()
