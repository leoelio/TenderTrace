from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tendertrace.config import Settings
from tendertrace.db import init_db


class GoldEvaluationApiTests(unittest.TestCase):
    def test_human_annotation_endpoint_records_audited_source_notice(self) -> None:
        from fastapi.testclient import TestClient

        from tendertrace.app import api as api_module

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings.load(root)
            init_db(settings)
            gold_path = root / "docs" / "evaluation" / "gold_benchmark.json"
            gold_path.parent.mkdir(parents=True)
            gold_path.write_text(
                json.dumps(
                    {
                        "version": "1.0",
                        "cases": [
                            {
                                "id": "case-1",
                                "query": "最近1个月上海服务器招标信息",
                                "gold_notices": [],
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with patch.object(api_module.Settings, "load", return_value=settings):
                client = TestClient(api_module.create_app())
                response = client.post(
                    "/api/evaluations/gold/cases/case-1/notices",
                    json={
                        "reviewer": "评审人",
                        "note": "已在源站人工核验。",
                        "notice": {
                            "source_site": "ccgp",
                            "notice_id": "n-1",
                            "title": "上海服务器采购公告",
                            "source_url": "https://example.com/n-1",
                        },
                    },
                )
                coverage = client.get("/api/evaluations/gold/coverage")

            payload = json.loads(gold_path.read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["annotation"]["status"], "recorded")
        self.assertEqual(response.json()["coverage"]["annotated_case_count"], 1)
        self.assertEqual(coverage.status_code, 200)
        self.assertTrue(coverage.json()["complete"])
        self.assertEqual(payload["cases"][0]["annotation_log"][0]["reviewer"], "评审人")

    def test_human_annotation_endpoint_rejects_automatic_or_invalid_payload(self) -> None:
        from fastapi.testclient import TestClient

        from tendertrace.app import api as api_module

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings.load(root)
            init_db(settings)
            gold_path = root / "docs" / "evaluation" / "gold_benchmark.json"
            gold_path.parent.mkdir(parents=True)
            gold_path.write_text(
                json.dumps({"cases": [{"id": "case-1", "query": "查询"}]}, ensure_ascii=False),
                encoding="utf-8",
            )
            with patch.object(api_module.Settings, "load", return_value=settings):
                client = TestClient(api_module.create_app())
                missing_reviewer = client.post(
                    "/api/evaluations/gold/cases/case-1/notices",
                    json={"notice": {"source_url": "https://example.com/n-1"}},
                )
                missing_notice = client.post(
                    "/api/evaluations/gold/cases/case-1/notices",
                    json={"reviewer": "评审人"},
                )

        self.assertEqual(missing_reviewer.status_code, 400)
        self.assertIn("reviewer", missing_reviewer.json()["detail"])
        self.assertEqual(missing_notice.status_code, 400)
        self.assertIn("notice", missing_notice.json()["detail"])


if __name__ == "__main__":
    unittest.main()
