from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tendertrace.app import api as api_module
from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.integrations.feishu_war_room import build_war_room_plan
from tendertrace.opportunity_requirements import upsert_requirement
from tendertrace.workflow import update_workflow


class FeishuWarRoomTests(unittest.TestCase):
    def test_local_plan_reports_each_war_room_prerequisite_without_calling_feishu(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            update_workflow(settings, "notice-1", owner_open_id="ou_owner", owner_name="张三")
            upsert_requirement(
                settings,
                notice_id="notice-1",
                requirement_key="QUAL-01",
                requirement_type="qualification",
                title="营业执照有效",
                evidence_text="投标人须具有有效的营业执照。",
                source_url="https://example.com/notice-1",
                source_locator="招标文件第 3 页",
                mandatory=True,
            )

            plan = build_war_room_plan(settings, "notice-1")

        steps = {item["key"]: item for item in plan["steps"]}
        self.assertEqual(plan["mode"], "local_plan")
        self.assertEqual(plan["requirements"]["task_candidate_count"], 1)
        self.assertEqual(steps["owner_task"]["status"], "ready")
        self.assertEqual(steps["group_card"]["status"], "needs_configuration")
        self.assertEqual(plan["launch"]["endpoint"], "/api/opportunities/send-feishu")
        self.assertEqual(plan["event"]["type"], "war_room.plan_ready")

    def test_plan_api_is_local_and_returns_the_launch_contract(self) -> None:
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            with patch.object(api_module.Settings, "load", return_value=settings):
                response = TestClient(api_module.create_app()).get(
                    "/api/opportunities/notice-1/war-room"
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "local_plan")
        self.assertEqual(response.json()["launch"]["method"], "POST")


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text(
        "TENDERTRACE_DB_PATH=data/test.sqlite3\nTENDERTRACE_SCHEDULER_ENABLED=false\n",
        encoding="utf-8",
    )
    settings = Settings.load(root)
    init_db(settings)
    return settings


def _insert_notice(settings: Settings) -> None:
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(id, source_site, source_url, canonical_url, title, fields_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "notice-1",
                "ccgp",
                "https://example.com/notice-1",
                "https://example.com/notice-1",
                "服务器采购项目",
                '{"structured_fields":{"bid_deadline":"2026-09-16 09:00"}}',
            ),
        )


if __name__ == "__main__":
    unittest.main()
