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
                )

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
                    },
                )
                evaluation = client.get("/api/evaluations/agent")

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["summary"]["saved_minutes"], 12.0)
        self.assertEqual(evaluation.status_code, 200)
        self.assertEqual(evaluation.json()["business"]["quality_passed_count"], 1)
        self.assertEqual(evaluation.json()["business"]["time_saving_rate"], 0.5)


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text("TENDERTRACE_DB_PATH=data/test.sqlite3\n", encoding="utf-8")
    settings = Settings.load(root)
    init_db(settings)
    return settings


if __name__ == "__main__":
    unittest.main()
