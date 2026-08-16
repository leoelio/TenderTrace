from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.integrations.feishu_opportunity import (
    build_opportunity_card,
    start_opportunity_collaboration,
)
from tendertrace.workflow import (
    WorkflowGateError,
    apply_action,
    get_workflow,
    update_workflow,
    workflow_action_contract,
)


class _FakeFeishuClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def create_task(self, **_: object) -> dict:
        self.calls.append("task")
        return {"data": {"task": {"guid": "task-guid"}}}

    def create_calendar_event(self, **_: object) -> dict:
        self.calls.append("calendar")
        return {"data": {"event": {"event_id": "event-id"}}}

    def send_card(self, *_: object, **__: object) -> dict:
        self.calls.append("card")
        return {"data": {"message_id": "message-id"}}

    def add_task_members(self, *_: object, **__: object) -> dict:
        self.calls.append("assign")
        return {"data": {}}


class _BitableResult:
    status = "sent"


class OpportunityWorkflowTests(unittest.TestCase):
    def test_actions_update_stage_and_create_audit_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)

            initial = get_workflow(settings, "notice-1")
            claimed = apply_action(
                settings,
                "notice-1",
                "claim",
                actor_open_id="ou_owner",
            )
            with connection(settings) as conn:
                event_count = conn.execute(
                    "SELECT COUNT(*) FROM opportunity_events WHERE notice_id = ?",
                    ("notice-1",),
                ).fetchone()[0]

        self.assertEqual(initial.stage, "identified")
        self.assertEqual(claimed.stage, "qualifying")
        self.assertEqual(claimed.owner_open_id, "ou_owner")
        self.assertTrue(claimed.stage_changed_at)
        self.assertEqual(event_count, 1)

    def test_metadata_sync_does_not_reset_stage_clock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            claimed = apply_action(
                settings,
                "notice-1",
                "claim",
                actor_open_id="ou_owner",
            )
            synced = update_workflow(
                settings,
                "notice-1",
                feishu_message_id="message-id",
            )

        self.assertEqual(synced.stage_changed_at, claimed.stage_changed_at)

    def test_collaboration_creates_task_calendar_and_card_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            client = _FakeFeishuClient()
            opportunity = {
                "notice_id": "notice-1",
                "title": "服务器采购项目",
                "region": "上海",
                "purchaser": "示例采购人",
                "source_site": "ccgp",
                "source_url": "https://example.com/notice-1",
                "bid_deadline": "2026-08-30 17:00",
                "intelligence": {
                    "level": "A",
                    "score": 88,
                    "recommended_actions": [
                        {"role": "机会负责人", "action": "确认客户预算与技术边界"}
                    ],
                },
                "stakeholder_map": {
                    "coverage_score": 67,
                    "relationship_score": 50,
                    "risks": [{"message": "尚未识别内部支持者"}],
                },
            }

            first = start_opportunity_collaboration(
                settings,
                opportunity,
                receive_id="oc_test",
                receive_id_type="chat_id",
                owner_open_id="ou_owner",
                owner_name="张三",
                client=client,
                bitable_updater=lambda *args, **kwargs: _BitableResult(),
            )
            second = start_opportunity_collaboration(
                settings,
                opportunity,
                receive_id="oc_test",
                receive_id_type="chat_id",
                client=client,
                bitable_updater=lambda *args, **kwargs: _BitableResult(),
            )

        self.assertEqual(client.calls, ["task", "calendar", "card", "card"])
        self.assertEqual(first.task_guid, "task-guid")
        self.assertTrue(first.task_assigned)
        self.assertEqual(first.event_id, "event-id")
        self.assertEqual(first.workflow.owner_name, "张三")
        self.assertEqual(second.workflow.feishu_message_id, "message-id")

    def test_collaboration_can_create_task_without_message_receiver(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            client = _FakeFeishuClient()
            opportunity = {
                "notice_id": "notice-1",
                "title": "服务器采购项目",
                "source_url": "https://example.com/notice-1",
            }

            result = start_opportunity_collaboration(
                settings,
                opportunity,
                create_calendar_event=False,
                client=client,
                bitable_updater=lambda *args, **kwargs: _BitableResult(),
            )

        self.assertEqual(client.calls, ["task"])
        self.assertEqual(result.task_guid, "task-guid")
        self.assertEqual(result.message_id, "")
        self.assertEqual(result.workflow.feishu_task_status, "open")
        self.assertFalse(result.task_assigned)

    def test_existing_unassigned_task_is_assigned_when_owner_is_selected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            update_workflow(settings, "notice-1", feishu_task_guid="task-guid")
            client = _FakeFeishuClient()
            opportunity = {
                "notice_id": "notice-1",
                "title": "服务器采购项目",
                "source_url": "https://example.com/notice-1",
            }

            result = start_opportunity_collaboration(
                settings,
                opportunity,
                owner_open_id="ou_owner",
                owner_name="张三",
                create_calendar_event=False,
                client=client,
                bitable_updater=lambda *args, **kwargs: _BitableResult(),
            )

        self.assertEqual(client.calls, ["assign"])
        self.assertTrue(result.task_assigned)
        self.assertEqual(result.workflow.owner_open_id, "ou_owner")
        self.assertEqual(result.workflow.owner_name, "张三")

    def test_go_decision_is_required_before_bid_preparation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            ready = {
                "score": 82,
                "status": "ready",
                "blockers": {"pursue": [], "approve_bid": []},
            }
            apply_action(
                settings,
                "notice-1",
                "claim",
                actor_open_id="ou_owner",
                actor_name="张三",
            )
            pursued = apply_action(settings, "notice-1", "pursue", qualification=ready)

            with self.assertRaises(WorkflowGateError):
                apply_action(settings, "notice-1", "prepare_bid", qualification=ready)

            approved = apply_action(
                settings,
                "notice-1",
                "approve_bid",
                actor_name="销售经理",
                qualification=ready,
            )
            bidding = apply_action(settings, "notice-1", "prepare_bid", qualification=ready)

        self.assertEqual(pursued.stage, "pursuing")
        self.assertEqual(approved.decision, "go")
        self.assertEqual(approved.decision_by, "销售经理")
        self.assertEqual(bidding.stage, "bidding")

    def test_stage_and_qualification_gates_reject_invalid_progression(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)

            with self.assertRaises(WorkflowGateError) as stage_error:
                apply_action(settings, "notice-1", "approve_bid")

            apply_action(settings, "notice-1", "claim", actor_open_id="ou_owner")
            with self.assertRaises(WorkflowGateError) as qualification_error:
                apply_action(
                    settings,
                    "notice-1",
                    "pursue",
                    qualification={
                        "blockers": {"pursue": ["采购主体"], "approve_bid": []}
                    },
                )

        self.assertIn("当前阶段", stage_error.exception.reasons[0])
        self.assertEqual(qualification_error.exception.reasons, ("采购主体",))

    def test_feishu_card_only_exposes_actions_valid_for_current_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            workflow = get_workflow(settings, "notice-1")
            opportunity = {
                "notice_id": "notice-1",
                "title": "服务器采购项目",
                "source_url": "https://example.com/notice-1",
                "intelligence": {
                    "trust_assessment": {
                        "verification_label": "多源已印证",
                        "basis": ["来源：中国政府采购网", "近 10 次采集可靠度 95%"],
                    }
                },
            }

            card = build_opportunity_card(
                opportunity,
                workflow,
                next_action="认领机会",
            )
            actions = [
                button["value"]["action"]
                for element in card["elements"]
                if element.get("tag") == "action"
                for button in element["actions"]
            ]
            identified_contract = workflow_action_contract(workflow)
            apply_action(
                settings,
                "notice-1",
                "claim",
                actor_open_id="ou_owner",
            )
            qualifying_contract = workflow_action_contract(
                get_workflow(settings, "notice-1"),
                {"blockers": {"pursue": ["采购主体"]}},
            )
            qualifying_card = build_opportunity_card(
                {
                    **opportunity,
                    "qualification": {"blockers": {"pursue": ["采购主体"]}},
                },
                get_workflow(settings, "notice-1"),
                next_action="补齐采购主体",
            )
            qualifying_actions = [
                button["value"]["action"]
                for element in qualifying_card["elements"]
                if element.get("tag") == "action"
                for button in element["actions"]
            ]

        self.assertTrue(card["config"]["update_multi"])
        self.assertIn("多源已印证", str(card))
        self.assertIn("采集可靠度 95%", str(card))
        self.assertIn("客户关系", str(card))
        self.assertIn("关系风险", str(card))
        self.assertEqual(actions, ["claim", "hold", "reject"])
        self.assertEqual(identified_contract["version"], 2)
        self.assertTrue(identified_contract["actions"][0]["requires_member_identity"])
        self.assertEqual(qualifying_contract["actions"][0]["action"], "pursue")
        self.assertFalse(qualifying_contract["actions"][0]["enabled"])
        self.assertEqual(
            qualifying_contract["actions"][0]["blocked_reasons"],
            ["采购主体"],
        )
        self.assertEqual(qualifying_actions, ["pursue", "hold", "reject"])
        self.assertIn("待补充", str(qualifying_card))


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text(
        "TENDERTRACE_DB_PATH=data/test.sqlite3\n"
        "FEISHU_ENABLED=true\n"
        "FEISHU_APP_ID=cli_test\n"
        "FEISHU_APP_SECRET=secret\n"
        "FEISHU_CALENDAR_ID=primary\n",
        encoding="utf-8",
    )
    settings = Settings.load(root)
    init_db(settings)
    return settings


def _insert_notice(settings: Settings) -> None:
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(id, source_site, source_url, canonical_url, title)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "notice-1",
                "ccgp",
                "https://example.com/notice-1",
                "https://example.com/notice-1",
                "服务器采购项目",
            ),
        )


if __name__ == "__main__":
    unittest.main()
