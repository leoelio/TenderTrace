from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tendertrace.adapters.ccgp import Notice
from tendertrace.app import api as api_module
from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.demo_reliability import (
    demo_reliability_overview,
    freeze_demo_case,
    list_demo_layout_audits,
    prepare_default_demo_cases,
    record_demo_layout_audit,
    run_demo_rehearsal,
)
from tendertrace.live_challenge import create_live_challenge
from tendertrace.runner import persist_notices_and_clusters


class DemoReliabilityTests(unittest.TestCase):
    def test_freeze_uses_real_database_record_and_creates_verified_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            challenge = _seed_public_challenge(settings)

            case = freeze_demo_case(
                settings,
                role="main",
                label="UNGM服务器采购",
                source_type="live_challenge",
                source_id=challenge["id"],
                actor="acceptance",
            )

        self.assertEqual(case["evidence_kind"], "public_record")
        self.assertTrue(case["snapshot_verified"])
        self.assertTrue(case["replay_verified"])
        self.assertFalse(case["snapshot"]["synthetic"])
        self.assertTrue(case["snapshot"]["captured_from_database"])
        self.assertEqual(case["snapshot"]["result"]["results"][0]["source_site"], "ungm")

    def test_offline_rehearsal_switches_to_same_version_replay_and_logs_every_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            challenge = _seed_public_challenge(settings)
            case = freeze_demo_case(
                settings,
                role="main",
                label="主案例",
                source_type="live_challenge",
                source_id=challenge["id"],
            )

            result = run_demo_rehearsal(
                settings,
                case_id=case["id"],
                requested_mode="live",
                browser_online=False,
                viewport_width=1440,
                viewport_height=900,
                scenario="offline_fallback",
            )

        rehearsal = result["rehearsal"]
        self.assertEqual(rehearsal["status"], "passed")
        self.assertEqual(rehearsal["requested_mode"], "live")
        self.assertEqual(rehearsal["actual_mode"], "replay")
        self.assertIn("离线", rehearsal["switch_reason"])
        self.assertLess(rehearsal["opened_in_ms"], 10_000)
        self.assertEqual(len(rehearsal["events"]), 5)
        self.assertTrue(all(item["status"] == "passed" for item in rehearsal["events"]))

    def test_live_version_drift_opens_verified_history_with_visible_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            challenge = _seed_public_challenge(settings)
            case = freeze_demo_case(
                settings,
                role="main",
                label="主案例",
                source_type="live_challenge",
                source_id=challenge["id"],
            )
            with connection(settings) as conn:
                conn.execute(
                    "UPDATE live_challenge_sessions SET keyword = 'version-drift' WHERE id = ?",
                    (challenge["id"],),
                )

            result = run_demo_rehearsal(
                settings,
                case_id=case["id"],
                requested_mode="live",
                browser_online=True,
                viewport_width=1920,
                viewport_height=1080,
            )

        rehearsal = result["rehearsal"]
        self.assertEqual(rehearsal["status"], "passed")
        self.assertEqual(rehearsal["actual_mode"], "verified_history")
        self.assertIn("数据版本已变化", rehearsal["switch_reason"])

    def test_tampered_replay_is_rejected_instead_of_presented_as_verified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            challenge = _seed_public_challenge(settings)
            case = freeze_demo_case(
                settings,
                role="replay",
                label="回放案例",
                source_type="live_challenge",
                source_id=challenge["id"],
            )
            with connection(settings) as conn:
                conn.execute(
                    "UPDATE demo_replay_artifacts SET result_json = '{\"tampered\":true}' WHERE case_id = ?",
                    (case["id"],),
                )

            overview = demo_reliability_overview(settings)
            result = run_demo_rehearsal(
                settings,
                case_id=case["id"],
                requested_mode="replay",
                browser_online=False,
                viewport_width=1440,
                viewport_height=900,
            )

        self.assertFalse(overview["cases"][0]["replay_verified"])
        self.assertEqual(result["rehearsal"]["status"], "failed")
        failed_steps = [item["step_key"] for item in result["rehearsal"]["events"] if item["status"] == "failed"]
        self.assertIn("integrity", failed_steps)
        self.assertIn("mode", failed_steps)

    def test_browser_layout_audit_derives_status_from_measurements(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            passed = record_demo_layout_audit(
                settings,
                profile="projector_1440",
                viewport_width=1440,
                viewport_height=900,
                scroll_width=1440,
                critical_overflows=[],
                user_agent="test-browser",
            )
            failed = record_demo_layout_audit(
                settings,
                profile="full_hd_1920",
                viewport_width=1920,
                viewport_height=1080,
                scroll_width=1940,
                critical_overflows=["demo-console"],
            )
            audits = list_demo_layout_audits(settings)

        self.assertEqual(passed["status"], "passed")
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(passed["measurement"], "same_origin_browser_dom")
        projector = next(item for item in audits if item["profile"] == "projector_1440")
        self.assertEqual(projector["measurement"], "same_origin_browser_dom")
        self.assertTrue(projector["user_agent_present"])

    def test_prepare_builds_main_backup_and_replay_from_existing_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed_public_challenge(settings)

            prepared = prepare_default_demo_cases(settings, actor="acceptance")
            overview = demo_reliability_overview(settings)

        self.assertEqual(prepared["prepared"], 3)
        self.assertEqual({item["role"] for item in prepared["cases"]}, {"main", "backup", "replay"})
        self.assertEqual(overview["summary"]["case_count"], 3)
        self.assertEqual(overview["summary"]["verified_replay_count"], 3)

    def test_api_exposes_console_prepare_rehearsal_and_layout_audit(self) -> None:
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed_public_challenge(settings)
            with patch.object(api_module.Settings, "load", return_value=settings):
                with TestClient(api_module.create_app()) as client:
                    prepared = client.post(
                        "/api/demo-reliability/prepare",
                        json={"actor": "api-test"},
                    )
                    case_id = prepared.json()["cases"][0]["id"]
                    rehearsal = client.post(
                        "/api/demo-reliability/rehearsals",
                        json={
                            "case_id": case_id,
                            "requested_mode": "live",
                            "browser_online": False,
                            "viewport_width": 1440,
                            "viewport_height": 900,
                            "scenario": "api-offline",
                        },
                    )
                    layout = client.post(
                        "/api/demo-reliability/layout-audits",
                        json={
                            "profile": "projector_1440",
                            "viewport_width": 1440,
                            "viewport_height": 900,
                            "scroll_width": 1440,
                            "critical_overflows": [],
                            "user_agent": "api-test",
                        },
                    )
                    overview = client.get("/api/demo-reliability")
                    compact = client.get("/api/demo-reliability", params={"compact": True})

        self.assertEqual(prepared.status_code, 200)
        self.assertEqual(rehearsal.status_code, 200)
        self.assertEqual(rehearsal.json()["rehearsal"]["actual_mode"], "replay")
        self.assertEqual(layout.status_code, 200)
        self.assertEqual(layout.json()["status"], "passed")
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(overview.json()["summary"]["case_count"], 3)
        self.assertEqual(compact.status_code, 200)
        self.assertEqual(len(compact.json()["cases"]), 3)
        self.assertNotIn("summary", compact.json())
        compact_twin = compact.json()["cases"][0]["snapshot"]["result"]["digital_twin"]
        self.assertEqual(set(compact_twin), {"project", "scores", "next_actions"})


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text(
        "TENDERTRACE_DB_PATH=data/test.sqlite3\n"
        "TENDERTRACE_SCHEDULER_ENABLED=false\n"
        "FEISHU_ENABLED=false\n",
        encoding="utf-8",
    )
    settings = Settings.load(root)
    init_db(settings)
    return settings


def _seed_public_challenge(settings: Settings) -> dict[str, object]:
    persist_notices_and_clusters(
        settings,
        [
            Notice(
                id="public-server-1",
                source_site="ungm",
                title="Procurement of Server for DMZ for HAProxy",
                publish_time=date.today().isoformat(),
                region="Philippines",
                purchaser="WHO",
                source_url="https://www.ungm.org/Public/Notice/test-1",
                content_text="Server infrastructure procurement for HAProxy.",
                core_content="Server procurement.",
            )
        ],
    )
    return create_live_challenge(
        settings,
        category="Server",
        region="Philippines",
        time_window="365d",
        keyword="HAProxy",
        actor="test",
    )


if __name__ == "__main__":
    unittest.main()
