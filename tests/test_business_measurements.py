from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tendertrace.business_measurements import (
    business_measurement_summary,
    upsert_business_measurement,
)
from tendertrace.config import Settings
from tendertrace.db import init_db
from tendertrace.db import connection


class BusinessMeasurementTests(unittest.TestCase):
    def test_only_quality_passed_samples_contribute_to_time_saving(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            upsert_business_measurement(
                settings,
                task_type="capability_matching",
                sample_ref="notice-1",
                baseline_minutes=40,
                assisted_minutes=25,
                quality_status="passed",
                reviewer="售前负责人",
                note="逐项核验结果一致。",
                recorded_by="测试员",
                participant="售前甲",
                document_type="PDF招标文件",
                conditions="同一文件与同一任务清单",
                raw_record_url="https://evidence.example/raw/notice-1",
                gold_standard_url="https://evidence.example/gold/notice-1",
            )
            upsert_business_measurement(
                settings,
                task_type="change_review",
                sample_ref="notice-2",
                baseline_minutes=30,
                assisted_minutes=10,
                quality_status="not_reviewed",
                reviewer="",
                note="等待复核。",
                recorded_by="测试员",
            )
            upsert_business_measurement(
                settings,
                task_type="group_handoff",
                sample_ref="notice-3",
                baseline_minutes=20,
                assisted_minutes=5,
                quality_status="failed",
                reviewer="项目经理",
                gold_standard_url="https://evidence.example/gold/notice-3",
                note="缺少责任人，未通过。",
                recorded_by="测试员",
            )
            summary = business_measurement_summary(settings)

        self.assertEqual(summary["record_count"], 3)
        self.assertEqual(summary["quality_passed_count"], 1)
        self.assertEqual(summary["baseline_minutes"], 40.0)
        self.assertEqual(summary["assisted_minutes"], 25.0)
        self.assertEqual(summary["saved_minutes"], 15.0)
        self.assertEqual(summary["time_saving_rate"], 0.375)
        self.assertEqual(summary["status"], "sample_only")
        self.assertFalse(summary["generalization_allowed"])
        self.assertEqual(summary["quality_failed_count"], 1)

    def test_reviewed_measurement_requires_named_reviewer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            with self.assertRaisesRegex(ValueError, "reviewer is required"):
                upsert_business_measurement(
                    settings,
                    task_type="opportunity_verification",
                    sample_ref="notice-1",
                    baseline_minutes=10,
                    assisted_minutes=8,
                    quality_status="passed",
                    reviewer="",
                    note="",
                    recorded_by="测试员",
                    gold_standard_url="https://evidence.example/gold/notice-1",
                )

    def test_recomputes_medians_ranges_quality_and_keeps_outliers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            pairs = [(50, 20), (40, 18), (60, 30), (45, 17), (20, 25)]
            for index, (baseline, assisted) in enumerate(pairs, 1):
                upsert_business_measurement(
                    settings,
                    experiment_id="paired-public-files",
                    experiment_version=2,
                    task_type="requirement_breakdown",
                    sample_ref=f"public-{index}",
                    participant=f"复核员{1 + index % 2}",
                    document_type="PDF招标文件",
                    file_count=1,
                    sequence_order="manual_first" if index % 2 else "assisted_first",
                    conditions="同一文件、固定任务清单、相同计时起止点",
                    source_url=f"https://source.example/{index}",
                    raw_record_url=f"https://evidence.example/raw/{index}",
                    gold_standard_url=f"https://evidence.example/gold/{index}",
                    baseline_minutes=baseline,
                    assisted_minutes=assisted,
                    baseline_active_minutes=baseline - 2,
                    assisted_active_minutes=max(1, assisted - 3),
                    assisted_machine_wait_seconds=40 + index,
                    baseline_omissions=4,
                    assisted_omissions=1 if index != 5 else 5,
                    baseline_false_satisfied=2,
                    assisted_false_satisfied=0 if index != 5 else 3,
                    baseline_rework_count=2,
                    assisted_rework_count=1 if index != 5 else 3,
                    is_outlier=index == 5,
                    outlier_reason="辅助处理更慢且质量较差" if index == 5 else "",
                    quality_status="passed",
                    reviewer="金标负责人",
                    note="逐项对照人工金标。",
                    recorded_by="实验管理员",
                )
            upsert_business_measurement(
                settings,
                task_type="source_verification",
                sample_ref="failed-public-6",
                baseline_minutes=30,
                assisted_minutes=12,
                quality_status="failed",
                reviewer="金标负责人",
                gold_standard_url="https://evidence.example/gold/6",
                note="辅助结果漏掉关键来源，质量未通过。",
                recorded_by="实验管理员",
            )
            summary = business_measurement_summary(settings)
            with connection(settings) as conn:
                event_count = conn.execute("SELECT COUNT(*) FROM business_measurement_events").fetchone()[0]

        self.assertEqual(summary["status"], "measured")
        self.assertEqual(summary["eligible_sample_count"], 5)
        self.assertEqual(summary["quality_failed_count"], 1)
        self.assertEqual(summary["outlier_count"], 1)
        self.assertEqual(summary["metrics"]["total_time"]["baseline_median"], 45.0)
        self.assertEqual(summary["metrics"]["total_time"]["assisted_median"], 20.0)
        self.assertEqual(summary["metrics"]["total_time"]["delta_range"], {"min": -5.0, "max": 30.0})
        self.assertIn(-5.0, [item["delta"] for item in summary["metrics"]["total_time"]["paired_values"]])
        self.assertEqual(len(summary["direction_coverage"]), 18)
        self.assertEqual(event_count, 6)

    def test_api_exposes_recorded_measurements_in_evaluation(self) -> None:
        from unittest.mock import patch

        from fastapi.testclient import TestClient
        from tendertrace.app import api as api_module

        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            with patch.object(api_module.Settings, "load", return_value=settings):
                client = TestClient(api_module.create_app())
                saved = client.post(
                    "/api/evaluations/business-measurements",
                    json={
                        "task_type": "opportunity_verification",
                        "sample_ref": "case-01",
                        "baseline_minutes": 24,
                        "assisted_minutes": 12,
                        "quality_status": "passed",
                        "reviewer": "销售经理",
                        "recorded_by": "测试员",
                        "note": "同一核验清单通过。",
                        "participant": "销售甲",
                        "document_type": "公告网页",
                        "conditions": "同一网页与固定核验清单",
                        "raw_record_url": "https://evidence.example/raw/case-01",
                        "gold_standard_url": "https://evidence.example/gold/case-01",
                        "baseline_active_minutes": 20,
                        "assisted_active_minutes": 9,
                        "baseline_omissions": 2,
                        "assisted_omissions": 0,
                    },
                )
                evaluation = client.get("/api/evaluations/agent")
                direct = client.get("/api/evaluations/business-measurements")

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["summary"]["saved_minutes"], 12.0)
        self.assertEqual(evaluation.status_code, 200)
        self.assertEqual(evaluation.json()["business"]["quality_passed_count"], 1)
        self.assertEqual(evaluation.json()["business"]["time_saving_rate"], 0.5)
        self.assertEqual(direct.status_code, 200)
        self.assertEqual(direct.json()["metrics"]["omissions"]["reduction_rate"], 1.0)


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text("TENDERTRACE_DB_PATH=data/test.sqlite3\n", encoding="utf-8")
    settings = Settings.load(root)
    init_db(settings)
    return settings


if __name__ == "__main__":
    unittest.main()
