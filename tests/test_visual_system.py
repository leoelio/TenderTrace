from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tendertrace.app import api as api_module
from tendertrace.config import Settings
from tendertrace.db import init_db
from tendertrace.visual_system import record_visual_system_audit, visual_system_overview


PASSING_CHECKS = {
    "state_words_with_symbols": True,
    "conclusion_titles_visible": True,
    "identity_consistent": True,
    "focus_visible": True,
    "motion_can_be_disabled": True,
    "presentation_preserves_content": True,
    "editors_hidden_in_presentation": True,
    "min_status_font_px": 16,
    "critical_component_count": 4,
    "conclusion_title_count": 4,
}


class VisualSystemTests(unittest.TestCase):
    def test_server_derives_pass_and_fail_from_browser_measurements(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            passed = record_visual_system_audit(
                settings,
                profile="projector_1440",
                viewport_width=1440,
                viewport_height=900,
                notice_id="notice-main",
                scroll_width=1440,
                critical_overflows=[],
                checks=PASSING_CHECKS,
                user_agent="test-browser",
            )
            failed = record_visual_system_audit(
                settings,
                profile="full_hd_1920",
                viewport_width=1920,
                viewport_height=1080,
                notice_id="notice-main",
                scroll_width=1920,
                critical_overflows=[],
                checks={**PASSING_CHECKS, "min_status_font_px": 15},
                user_agent="test-browser",
            )

        self.assertEqual(passed["status"], "passed")
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(passed["measurement"], "same_origin_browser_dom")

    def test_overview_requires_both_target_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            for profile, width, height in (
                ("projector_1440", 1440, 900),
                ("full_hd_1920", 1920, 1080),
            ):
                record_visual_system_audit(
                    settings,
                    profile=profile,
                    viewport_width=width,
                    viewport_height=height,
                    notice_id="notice-main",
                    scroll_width=width,
                    critical_overflows=[],
                    checks=PASSING_CHECKS,
                    user_agent="test-browser",
                )
            overview = visual_system_overview(settings)

        self.assertEqual(overview["status"], "ready")
        self.assertTrue(overview["summary"]["all_profiles_passed"])
        self.assertEqual(overview["summary"]["profiles_passed"], 2)
        self.assertTrue(all(item["user_agent_present"] for item in overview["audits"]))

    def test_api_records_and_returns_visual_audits(self) -> None:
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            with patch.object(api_module.Settings, "load", return_value=settings):
                with TestClient(api_module.create_app()) as client:
                    recorded = client.post(
                        "/api/visual-system/audits",
                        json={
                            "profile": "projector_1440",
                            "viewport_width": 1440,
                            "viewport_height": 900,
                            "notice_id": "notice-main",
                            "scroll_width": 1440,
                            "critical_overflows": [],
                            "checks": PASSING_CHECKS,
                            "user_agent": "api-test-browser",
                            "status": "failed",
                        },
                    )
                    overview = client.get("/api/visual-system")

        self.assertEqual(recorded.status_code, 200)
        self.assertEqual(recorded.json()["status"], "passed")
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(overview.json()["audits"][0]["notice_id"], "notice-main")


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


if __name__ == "__main__":
    unittest.main()
