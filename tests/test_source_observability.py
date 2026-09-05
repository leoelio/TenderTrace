from pathlib import Path
import os
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.runlog import finish_run, start_run
from tendertrace.source_map import build_source_map, record_source_observations, source_health


class SourceObservabilityTests(unittest.TestCase):
    def test_background_observations_refresh_source_health(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            record_source_observations(
                settings,
                [
                    {
                        "source": "ccgp",
                        "status": "failed",
                        "count": 0,
                        "error": "temporary timeout",
                        "fetch_stats": {"requests": 1, "failed": 1},
                    }
                ],
            )
            with connection(settings) as conn:
                conn.execute(
                    "UPDATE source_observations SET observed_at = '2026-08-15 08:00:00'"
                )
            record_source_observations(
                settings,
                [
                    {
                        "source": "ccgp",
                        "status": "finished",
                        "count": 2,
                        "fetch_stats": {"requests": 1, "succeeded": 1},
                    }
                ],
            )
            with connection(settings) as conn:
                conn.execute(
                    "UPDATE source_observations SET observed_at = '2026-08-16 08:00:00' "
                    "WHERE status = 'finished'"
                )

            health = source_health(settings)["ccgp"]

        self.assertEqual(health["runs"], 2)
        self.assertEqual(health["notices"], 2)
        self.assertEqual(health["last_failure_at"], "2026-08-15 08:00:00")
        self.assertEqual(health["last_success_at"], "2026-08-16 08:00:00")
        self.assertEqual(health["last_run_at"], "2026-08-16 08:00:00")
        self.assertEqual(health["health_status"], "degraded")

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
        self.assertEqual(source_map["source_count"], 16)
        self.assertEqual(health["ted"]["runs"], 1)
        self.assertEqual(health["ted"]["hit_runs"], 1)
        self.assertEqual(health["ted"]["notices"], 3)
        self.assertEqual(health["ted"]["success_rate"], 1.0)
        self.assertEqual(health["ted"]["health_status"], "healthy")
        self.assertEqual(health["ccgp"]["runs"], 0)
        self.assertEqual(health["ccgp"]["skipped_runs"], 1)
        self.assertEqual(health["ccgp"]["health_status"], "unknown")
        self.assertEqual(health["qianlima"]["hit_rate"], 0.0)
        self.assertEqual(health["qianlima"]["health_status"], "healthy")
        self.assertEqual(health["ggzy"]["runs"], 2)
        self.assertEqual(health["ggzy"]["hit_rate"], 0.5)

    def test_latest_login_failure_marks_saved_session_expired(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            settings.ensure_directories()
            storage_state = settings.secrets_dir / "qianlima_storage_state.json"
            storage_state.write_text(
                '{"cookies":[{"domain":".qianlima.com","name":"session","value":"hidden"}],"origins":[]}',
                encoding="utf-8",
            )
            os.utime(storage_state, (946684800, 946684800))
            for run_id, error in (
                ("run-old", "TimeoutError: old network timeout"),
                (
                    "run-new",
                    "RuntimeError: qianlima login session expired; run login-qianlima again",
                ),
            ):
                start_run(settings, run_id=run_id, original_query="上海服务器采购", mode="full")
                finish_run(
                    settings,
                    run_id=run_id,
                    status="finished",
                    output_docx_path=None,
                    stats={
                        "source_stats": [
                            {
                                "source": "qianlima",
                                "status": "failed",
                                "count": 0,
                                "error": error,
                            }
                        ]
                    },
                )
            with connection(settings) as conn:
                conn.execute(
                    "UPDATE runs SET started_at = ? WHERE id = ?",
                    ("2026-08-15 08:00:00", "run-old"),
                )
                conn.execute(
                    "UPDATE runs SET started_at = ? WHERE id = ?",
                    ("2026-08-16 08:00:00", "run-new"),
                )

            source_map = build_source_map(settings)

        qianlima = next(item for item in source_map["items"] if item["site"] == "qianlima")
        self.assertEqual(qianlima["status"], "login_expired")
        self.assertFalse(source_map["login_source_ready"])
        self.assertTrue(source_map["qianlima"]["storage_state_ready"])
        self.assertFalse(source_map["qianlima"]["ready"])
        self.assertEqual(source_map["qianlima"]["validation"], "expired")
        self.assertIn("login session expired", qianlima["health"]["last_error"])

    def test_member_api_session_rejection_marks_saved_session_expired(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            settings.ensure_directories()
            storage_state = settings.secrets_dir / "qianlima_storage_state.json"
            storage_state.write_text(
                '{"cookies":[{"domain":".qianlima.com","name":"session","value":"hidden"}],"origins":[]}',
                encoding="utf-8",
            )
            os.utime(storage_state, (946684800, 946684800))
            start_run(settings, run_id="run-member-rejected", original_query="上海服务器采购", mode="full")
            finish_run(
                settings,
                run_id="run-member-rejected",
                status="finished",
                output_docx_path=None,
                stats={
                    "source_stats": [
                        {
                            "source": "qianlima",
                            "status": "failed",
                            "count": 0,
                            "error": "qianlima member APIs rejected saved session",
                        }
                    ]
                },
            )

            source_map = build_source_map(settings)

        qianlima = next(item for item in source_map["items"] if item["site"] == "qianlima")
        self.assertEqual(qianlima["status"], "login_expired")
        self.assertFalse(source_map["login_source_ready"])
        self.assertEqual(source_map["qianlima"]["validation"], "expired")
        self.assertIn("重新保存", source_map["qianlima"]["detail"])

    def test_later_qianlima_success_clears_historical_expiry_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            settings.ensure_directories()
            (settings.secrets_dir / "qianlima_storage_state.json").write_text(
                '{"cookies":[{"domain":".qianlima.com","name":"session","value":"hidden"}],"origins":[]}',
                encoding="utf-8",
            )
            for run_id, started_at, status, error in (
                (
                    "run-expired",
                    "2026-08-15 08:00:00",
                    "failed",
                    "qianlima member APIs rejected saved session",
                ),
                ("run-recovered", "2026-08-16 08:00:00", "finished", ""),
            ):
                start_run(settings, run_id=run_id, original_query="上海服务器采购", mode="full")
                finish_run(
                    settings,
                    run_id=run_id,
                    status="finished",
                    output_docx_path=None,
                    stats={
                        "source_stats": [
                            {
                                "source": "qianlima",
                                "status": status,
                                "count": 1 if status == "finished" else 0,
                                "error": error,
                            }
                        ]
                    },
                )
                with connection(settings) as conn:
                    conn.execute(
                        "UPDATE runs SET started_at = ? WHERE id = ?",
                        (started_at, run_id),
                    )

            source_map = build_source_map(settings)

        qianlima = next(item for item in source_map["items"] if item["site"] == "qianlima")
        self.assertEqual(qianlima["status"], "configured")
        self.assertTrue(source_map["login_source_ready"])
        self.assertEqual(qianlima["health"]["last_failure_at"], "2026-08-15 08:00:00")
        self.assertEqual(qianlima["health"]["last_success_at"], "2026-08-16 08:00:00")

    def test_newly_saved_storage_state_reenables_a_session_after_expiry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            settings.ensure_directories()
            storage_state = settings.secrets_dir / "qianlima_storage_state.json"
            storage_state.write_text(
                '{"cookies":[{"domain":".qianlima.com","name":"session","value":"hidden"}],"origins":[]}',
                encoding="utf-8",
            )
            os.utime(storage_state, (946684800, 946684800))
            start_run(settings, run_id="run-expired", original_query="上海服务器采购", mode="full")
            finish_run(
                settings,
                run_id="run-expired",
                status="finished",
                output_docx_path=None,
                stats={
                    "source_stats": [
                        {
                            "source": "qianlima",
                            "status": "failed",
                            "count": 0,
                            "error": "qianlima member APIs rejected saved session",
                        }
                    ]
                },
            )
            with connection(settings) as conn:
                conn.execute(
                    "UPDATE runs SET started_at = '2026-08-16 08:00:00' WHERE id = 'run-expired'"
                )
            os.utime(storage_state, (1797004800, 1797004800))

            source_map = build_source_map(settings)

        qianlima = next(item for item in source_map["items"] if item["site"] == "qianlima")
        self.assertEqual(qianlima["status"], "configured")
        self.assertTrue(source_map["login_source_ready"])


if __name__ == "__main__":
    unittest.main()
