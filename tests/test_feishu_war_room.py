from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from tendertrace.app import api as api_module
from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.integrations.feishu_war_room import build_war_room_plan, launch_war_room
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
        self.assertEqual(steps["review_board"]["status"], "ready")
        self.assertIn("启动时按要求账本", steps["review_board"]["detail"])
        self.assertEqual(plan["launch"]["endpoint"], "/api/opportunities/notice-1/war-room/launch")
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

    def test_launch_executes_existing_collaboration_and_requirement_sync_then_audits_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
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
            calls: list[str] = []

            def starter(*args, **kwargs):
                calls.append("collaboration")
                self.assertEqual(args[1]["review_board"]["pending_count"], 2)
                return SimpleNamespace(
                    message_id="om_war_room",
                    task_guid="task_war_room",
                    event_id="event_war_room",
                    bitable_status="sent",
                )

            def syncer(*args, **kwargs):
                calls.append("requirements")
                return SimpleNamespace(status="finished", created_count=2)

            result = launch_war_room(
                settings,
                "notice-1",
                receive_id="oc_team",
                receive_id_type="chat_id",
                collaboration_starter=starter,
                requirement_syncer=syncer,
            )
            with connection(settings) as conn:
                actions = [
                    row["action"]
                    for row in conn.execute(
                        "SELECT action FROM opportunity_events WHERE notice_id = ?",
                        ("notice-1",),
                    )
                ]

        self.assertEqual(result["status"], "started")
        self.assertEqual(result["completed_count"], 6)
        review_step = next(step for step in result["steps"] if step["key"] == "review_board")
        self.assertIn("新增 2 项；待裁决 2 项", review_step["detail"])
        self.assertEqual(calls, ["collaboration", "requirements"])
        self.assertIn("war_room_launched", actions)

    def test_launch_without_a_receiver_stays_side_effect_free_and_reports_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            called = False

            def starter(*args, **kwargs):
                nonlocal called
                called = True
                raise AssertionError("starter must not be called")

            result = launch_war_room(
                settings,
                "notice-1",
                receive_id="",
                receive_id_type="chat_id",
                collaboration_starter=starter,
            )

        self.assertEqual(result["status"], "blocked")
        self.assertFalse(called)


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
