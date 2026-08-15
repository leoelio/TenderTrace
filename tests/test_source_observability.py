from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import init_db
from tendertrace.runlog import finish_run, start_run
from tendertrace.source_map import build_source_map


class SourceObservabilityTests(unittest.TestCase):
    def test_skipped_sources_are_not_counted_as_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            start_run(
                settings,
                run_id="run-global",
                original_query="全球服务器采购",
                mode="full",
            )
            finish_run(
                settings,
                run_id="run-global",
                status="finished",
                output_docx_path=None,
                stats={
                    "source_stats": [
                        {
                            "source": "ted",
                            "status": "finished",
                            "count": 3,
                            "fetch_stats": {
                                "requests": 2,
                                "succeeded": 2,
                                "avg_elapsed_ms": 800,
                            },
                        },
                        {
                            "source": "ccgp",
                            "status": "skipped",
                            "count": 0,
                        },
                        {
                            "source": "qianlima",
                            "status": "finished",
                            "count": 0,
                            "fetch_stats": {
                                "requests": 1,
                                "succeeded": 1,
                                "avg_elapsed_ms": 800,
                            },
                        },
                        {
                            "source": "ggzy",
                            "status": "finished",
                            "count": 2,
                        },
                    ]
                },
            )
            start_run(
                settings,
                run_id="run-failed",
                original_query="上海服务器采购",
                mode="full",
            )
            finish_run(
                settings,
                run_id="run-failed",
                status="finished",
                output_docx_path=None,
                stats={
                    "source_stats": [
                        {
                            "source": "ggzy",
                            "status": "failed",
                            "count": 0,
                        }
                    ]
                },
            )

            source_map = build_source_map(settings)

        health = {item["site"]: item["health"] for item in source_map["items"]}
        self.assertEqual(source_map["source_count"], 8)
        self.assertEqual(health["ted"]["runs"], 1)
        self.assertEqual(health["ted"]["hit_runs"], 1)
        self.assertEqual(health["ted"]["notices"], 3)
        self.assertEqual(health["ted"]["success_rate"], 1.0)
        self.assertEqual(health["ted"]["health_status"], "healthy")
        self.assertEqual(health["ccgp"]["runs"], 0)
        self.assertEqual(health["ccgp"]["skipped_runs"], 1)
        self.assertEqual(health["ccgp"]["health_status"], "unknown")
        self.assertEqual(health["qianlima"]["hit_rate"], 0.0)
        self.assertEqual(health["qianlima"]["health_status"], "degraded")
        self.assertEqual(health["ggzy"]["runs"], 2)
        self.assertEqual(health["ggzy"]["hit_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
