from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.integrations.feishu_war_room import (
    archive_war_room,
    build_war_room_plan,
    launch_war_room,
    retry_war_room_step,
    sync_war_room_back,
)
from tendertrace.opportunity_requirements import upsert_requirement
from tendertrace.organization_memory import create_workspace, search_memories
from tendertrace.workflow import update_workflow


class WarRoomWorkspaceTests(unittest.TestCase):
    def test_launch_three_times_reuses_resources_and_keeps_step_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed(settings)
            starter = _Starter()
            syncer = _RequirementSyncer()

            for _ in range(3):
                result = launch_war_room(
                    settings,
                    NOTICE_ID,
                    receive_id="oc_demo_team",
                    receive_id_type="chat_id",
                    actor="项目经理",
                    collaboration_starter=starter,
                    requirement_syncer=syncer,
                    requirement_bitable_syncer=lambda *args, **kwargs: {"status": "sent"},
                )

            plan = build_war_room_plan(settings, NOTICE_ID, receive_id="oc_demo_team")
            receipts = {item["step_key"]: item for item in plan["receipts"]}
            resources = {item["step_key"]: item for item in plan["resources"]}

        self.assertEqual(result["status"], "started")
        self.assertEqual(result["session"]["launch_count"], 3)
        self.assertEqual(starter.calls, 3)
        self.assertEqual(receipts["group_card"]["attempt_count"], 3)
        self.assertTrue(receipts["group_card"]["reused"])
        self.assertEqual(resources["group_card"]["resource_id"], "om_war_room_demo")
        self.assertIn("oc_demo_team", resources["group_card"]["resource_url"])
        self.assertEqual(len({item["id"] for item in plan["receipts"]}), len(plan["receipts"]))
        self.assertEqual(len(plan["journey"]), 7)

    def test_failed_requirement_step_can_retry_without_recreating_other_resources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed(settings)
            starter = _Starter()
            failed = launch_war_room(
                settings,
                NOTICE_ID,
                receive_id="oc_demo_team",
                receive_id_type="chat_id",
                collaboration_starter=starter,
                requirement_syncer=_RequirementSyncer(fail=True),
                requirement_bitable_syncer=lambda *args, **kwargs: {"status": "sent"},
            )
            retried = retry_war_room_step(
                settings,
                NOTICE_ID,
                "requirement_tasks",
                actor="项目经理",
                requirement_syncer=_RequirementSyncer(),
            )
            receipt = next(item for item in retried["receipts"] if item["step_key"] == "requirement_tasks")

        self.assertEqual(failed["status"], "partial")
        self.assertEqual(receipt["status"], "completed")
        self.assertEqual(receipt["attempt_count"], 2)
        self.assertEqual(starter.calls, 1)

    def test_failed_resource_retry_is_persisted_without_losing_existing_resource(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed(settings)
            launch_war_room(
                settings,
                NOTICE_ID,
                receive_id="oc_demo_team",
                receive_id_type="chat_id",
                collaboration_starter=_Starter(),
                requirement_syncer=_RequirementSyncer(),
                requirement_bitable_syncer=lambda *args, **kwargs: {"status": "sent"},
            )
            retried = retry_war_room_step(
                settings,
                NOTICE_ID,
                "group_card",
                actor="项目经理",
                collaboration_starter=_FailingStarter(),
            )
            receipt = next(item for item in retried["receipts"] if item["step_key"] == "group_card")

        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["attempt_count"], 2)
        self.assertEqual(receipt["resource_id"], "om_war_room_demo")
        self.assertIn("simulated resource failure", receipt["last_error"])

    def test_task_writeback_creates_confirmation_conflict_instead_of_overwriting_human_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            requirement = _seed(settings)
            launch_war_room(
                settings,
                NOTICE_ID,
                receive_id="oc_demo_team",
                receive_id_type="chat_id",
                collaboration_starter=_Starter(),
                requirement_syncer=_RequirementSyncer(),
                requirement_bitable_syncer=lambda *args, **kwargs: {"status": "sent"},
            )
            with connection(settings) as conn:
                conn.execute(
                    "UPDATE opportunity_requirements SET feishu_task_guid = 'task_requirement_demo', feishu_task_status = 'open', status = 'in_progress' WHERE id = ?",
                    (requirement.id,),
                )
            result = sync_war_room_back(
                settings,
                NOTICE_ID,
                actor="项目经理",
                client=_CompletedTaskClient(),
            )
            with connection(settings) as conn:
                row = conn.execute("SELECT status, feishu_task_status FROM opportunity_requirements WHERE id = ?", (requirement.id,)).fetchone()

        self.assertEqual(result["status"], "finished")
        self.assertEqual(result["conflict_count"], 1)
        self.assertEqual(row["status"], "in_progress")
        self.assertEqual(row["feishu_task_status"], "completed")
        self.assertTrue(result["session"]["last_sync_at"])

    def test_archive_writes_a_scoped_organization_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed(settings)
            workspace = create_workspace(
                settings,
                name="政务云投标项目群",
                feishu_chat_id="oc_demo_team",
                actor="项目经理",
            )
            launch_war_room(
                settings,
                NOTICE_ID,
                receive_id="oc_demo_team",
                receive_id_type="chat_id",
                workspace_id=workspace.id,
                actor="项目经理",
                collaboration_starter=_Starter(),
                requirement_syncer=_RequirementSyncer(),
                requirement_bitable_syncer=lambda *args, **kwargs: {"status": "sent"},
            )
            archived = archive_war_room(settings, NOTICE_ID, actor="项目经理")
            memories = search_memories(settings, workspace_id=workspace.id, query="战情室归档")

        self.assertEqual(archived["session"]["status"], "archived")
        self.assertTrue(archived["session"]["archive_memory_id"])
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0].related_notice_id, NOTICE_ID)


NOTICE_ID = "notice-war-room-workspace"


class _Starter:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return SimpleNamespace(
            message_id="om_war_room_demo",
            task_guid="task_war_room_demo",
            event_id="event_war_room_demo",
            bitable_status="sent",
        )


class _RequirementSyncer:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def __call__(self, *args, **kwargs):
        return SimpleNamespace(
            status="partial" if self.fail else "finished",
            created_count=0 if self.fail else 2,
            skipped_count=0,
            failures=({"error": "simulated"},) if self.fail else (),
        )


class _FailingStarter:
    def __call__(self, *args, **kwargs):
        raise ValueError("simulated resource failure")


class _CompletedTaskClient:
    def get_task(self, task_guid: str):
        return {"data": {"task": {"completed_at": "1790000000000"}}}


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text(
        "\n".join((
            "TENDERTRACE_DB_PATH=data/test.sqlite3",
            "TENDERTRACE_SCHEDULER_ENABLED=false",
            "FEISHU_ENABLED=true",
            "FEISHU_APP_ID=cli_test",
            "FEISHU_APP_SECRET=secret",
            "FEISHU_DEFAULT_RECEIVE_ID=oc_demo_team",
            "FEISHU_CALENDAR_ID=calendar_demo",
            "TENDERTRACE_FEISHU_BITABLE_APP_TOKEN=base_demo",
            "TENDERTRACE_FEISHU_BITABLE_TABLE_ID=table_demo",
        )) + "\n",
        encoding="utf-8",
    )
    settings = Settings.load(root)
    init_db(settings)
    return settings


def _seed(settings: Settings):
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(
                id, source_site, source_url, canonical_url, title, purchaser,
                region, fields_json, content_text, core_content
            ) VALUES (?, 'demo', ?, ?, '政务云协作空间', '某政务单位（脱敏）', '北京',
                '{"structured_fields":{"project_no":"TT-WR-001","bid_deadline":"2026-10-20 17:00"}}',
                '政务云招标项目', '团队协作演示')
            """,
            (NOTICE_ID, "https://example.com/war-room", "https://example.com/war-room"),
        )
    update_workflow(settings, NOTICE_ID, owner_open_id="ou_manager", owner_name="项目经理")
    return upsert_requirement(
        settings,
        notice_id=NOTICE_ID,
        requirement_key="QUAL-WR-01",
        requirement_type="qualification",
        title="投标资格文件",
        evidence_text="须提交有效资格材料。",
        source_url="https://example.com/war-room",
        source_locator="招标文件第8页",
        mandatory=True,
        status="in_progress",
        assignee_member_id="",
        actor="seed",
    )


if __name__ == "__main__":
    unittest.main()
