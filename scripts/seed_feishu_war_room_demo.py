from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from tendertrace.change_impact_engine import confirm_change_impact_action, get_change_impact
from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.digital_twin import build_digital_twin
from tendertrace.integrations.feishu_war_room import (
    archive_war_room,
    build_war_room_plan,
    dispatch_war_room_changes,
    launch_war_room,
    retry_war_room_step,
    sync_war_room_back,
)
from tendertrace.notice_changes import record_notice_revision
from tendertrace.opportunity_requirements import upsert_requirement
from tendertrace.organization_memory import create_workspace
from tendertrace.workflow import update_workflow


ROOT = Path(__file__).resolve().parents[1]
NOTICE_ID = "demo-feishu-war-room"
CHAT_ID = "oc_demo_war_room_two_accounts"


class DemoCollaborationStarter:
    def __call__(self, *args, **kwargs):
        return SimpleNamespace(
            message_id="om_demo_war_room_overview",
            task_guid="task_demo_war_room_owner",
            event_id="event_demo_bid_deadline",
            bitable_status="sent",
        )


class DemoRequirementSyncer:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def __call__(self, *args, **kwargs):
        return SimpleNamespace(
            status="partial" if self.fail else "finished",
            created_count=0 if self.fail else 3,
            skipped_count=0,
            failures=({"error": "演示：要求任务首次同步超时"},) if self.fail else (),
        )


class DemoFeishuClient:
    def get_task(self, task_guid: str):
        return {"data": {"task": {"guid": task_guid, "completed_at": "1790586000000"}}}

    def send_card(self, card, *, receive_id: str, receive_id_type: str):
        return {"data": {"message_id": "om_demo_change_impact"}}

    def create_task(self, *, client_token: str, **kwargs):
        return {"data": {"task": {"guid": f"task-change-{client_token[:8]}"}}}

    def create_calendar_event(self, *, idempotency_key: str, **kwargs):
        return {"data": {"event": {"event_id": "event-demo-change"}}}


def seed() -> dict[str, object]:
    settings = Settings.load(ROOT)
    init_db(settings)
    _reset_demo(settings)
    _seed_notice(settings)
    workspace = create_workspace(
        settings,
        name="政务云投标战情室（双账号演示）",
        feishu_chat_id=CHAT_ID,
        members=[
            {"open_id": "ou_demo_bid_manager", "name": "李经理（脱敏）", "role": "owner"},
            {"open_id": "ou_demo_solution_lead", "name": "周工（脱敏）", "role": "member"},
        ],
        actor="demo:项目负责人",
    )
    update_workflow(
        settings,
        NOTICE_ID,
        owner_open_id="ou_demo_bid_manager",
        owner_name="李经理（脱敏）",
    )
    requirements = _seed_requirements(settings)

    starter = DemoCollaborationStarter()
    first = launch_war_room(
        settings,
        NOTICE_ID,
        receive_id=CHAT_ID,
        receive_id_type="chat_id",
        workspace_id=workspace.id,
        actor="李经理（脱敏）",
        collaboration_starter=starter,
        requirement_syncer=DemoRequirementSyncer(fail=True),
        requirement_bitable_syncer=lambda *args, **kwargs: {"status": "sent", "records": 3},
    )
    retry_war_room_step(
        settings,
        NOTICE_ID,
        "requirement_tasks",
        actor="李经理（脱敏）",
        requirement_syncer=DemoRequirementSyncer(),
    )
    for _ in range(2):
        launch_war_room(
            settings,
            NOTICE_ID,
            receive_id=CHAT_ID,
            receive_id_type="chat_id",
            workspace_id=workspace.id,
            actor="李经理（脱敏）",
            collaboration_starter=starter,
            requirement_syncer=DemoRequirementSyncer(),
            requirement_bitable_syncer=lambda *args, **kwargs: {"status": "sent", "records": 3},
        )

    with connection(settings) as conn:
        conn.execute(
            "UPDATE opportunity_requirements SET feishu_task_guid = 'task-demo-requirement', feishu_task_status = 'open', status = 'in_progress' WHERE id = ?",
            (requirements[0].id,),
        )
    writeback = sync_war_room_back(
        settings,
        NOTICE_ID,
        actor="周工（脱敏）",
        client=DemoFeishuClient(),
    )

    impact = get_change_impact(settings, NOTICE_ID)
    assert impact is not None
    current_round = impact["current_round"]
    affected_action = next(item for item in current_round["actions"] if item["status"] == "open")
    confirm_change_impact_action(
        settings,
        NOTICE_ID,
        affected_action["id"],
        actor="李经理（脱敏）",
        note="已核对更正公告原文，只同步受影响行动。",
    )
    dispatched = dispatch_war_room_changes(
        settings,
        NOTICE_ID,
        actor="李经理（脱敏）",
        client=DemoFeishuClient(),
    )
    archived = archive_war_room(settings, NOTICE_ID, actor="李经理（脱敏）")
    plan = build_war_room_plan(settings, NOTICE_ID, receive_id=CHAT_ID)
    twin = build_digital_twin(settings, NOTICE_ID)
    receipt_ids = [str(item.get("id")) for item in plan["receipts"]]
    resource_ids = {str(item["step_key"]): str(item["resource_id"]) for item in plan["resources"]}
    result = {
        "notice_id": NOTICE_ID,
        "title": "政务云一键投标战情室",
        "workspace_id": workspace.id,
        "demo_url": f"http://127.0.0.1:8000/?opportunity={NOTICE_ID}",
        "first_launch_status": first["status"],
        "final_status": archived["session"]["status"],
        "launch_count": archived["session"]["launch_count"],
        "preflight_ready_count": plan["preflight_ready_count"],
        "preflight_total": len(plan["preflight"]),
        "journey_steps": len(plan["journey"]),
        "receipt_count": len(plan["receipts"]),
        "resource_ids": resource_ids,
        "writeback_conflict_count": writeback["conflict_count"],
        "incremental_dispatch_status": dispatched["status"],
        "digital_twin_war_room_resources": twin["counts"]["war_room_resources"] if twin else 0,
        "proof": {
            "two_account_collaboration_fixture": workspace.member_count == 2,
            "seven_stage_journey": len(plan["journey"]) == 7,
            "three_launches_without_duplicate_receipts": archived["session"]["launch_count"] == 3 and len(receipt_ids) == len(set(receipt_ids)),
            "stable_external_resource_ids": all(resource_ids.get(key) for key in ("group_card", "owner_task", "deadline_calendar", "workflow_bitable")),
            "failed_step_retried_independently": any(item["step_key"] == "requirement_tasks" and item["status"] == "completed" and item["attempt_count"] >= 4 for item in plan["receipts"]),
            "human_state_not_overwritten": writeback["conflict_count"] == 1,
            "affected_changes_only_after_confirmation": dispatched["status"] == "sent" and dispatched["sent"] > 0,
            "organization_memory_archived": bool(archived["session"]["archive_memory_id"]),
            "all_receipts_finished": not any(item["status"] == "failed" for item in plan["receipts"]),
        },
        "boundary": "本演示使用两个脱敏账号身份与确定性飞书客户端验证闭环；真实双账号协作仍需在已发布应用、真实群和对应权限下进行现场验收。",
    }
    output = ROOT / "docs" / "demo" / "feishu_war_room_live_demo_20260928.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _reset_demo(settings: Settings) -> None:
    with connection(settings) as conn:
        round_ids = [str(row["id"]) for row in conn.execute("SELECT id FROM change_impact_rounds WHERE notice_id = ?", (NOTICE_ID,)).fetchall()]
        for round_id in round_ids:
            conn.execute("DELETE FROM change_impact_audit_events WHERE round_id = ?", (round_id,))
            conn.execute("DELETE FROM change_impact_actions WHERE round_id = ?", (round_id,))
            conn.execute("DELETE FROM change_impact_items WHERE round_id = ?", (round_id,))
            conn.execute("DELETE FROM change_impact_events WHERE round_id = ?", (round_id,))
        conn.execute("DELETE FROM change_impact_rounds WHERE notice_id = ?", (NOTICE_ID,))
        conn.execute("DELETE FROM notice_revisions WHERE notice_id = ?", (NOTICE_ID,))
        room_ids = [str(row["id"]) for row in conn.execute("SELECT id FROM feishu_war_rooms WHERE notice_id = ?", (NOTICE_ID,)).fetchall()]
        for room_id in room_ids:
            conn.execute("DELETE FROM feishu_war_room_sync_events WHERE war_room_id = ?", (room_id,))
            conn.execute("DELETE FROM feishu_war_room_steps WHERE war_room_id = ?", (room_id,))
        conn.execute("DELETE FROM feishu_war_rooms WHERE notice_id = ?", (NOTICE_ID,))
        conn.execute("DELETE FROM opportunity_events WHERE notice_id = ?", (NOTICE_ID,))


def _seed_notice(settings: Settings) -> None:
    fields = {"structured_fields": {"project_no": "TT-WR-20260928", "budget": 8600000, "bid_deadline": "2026-10-20 17:00"}, "demo_scope": "投标战情室脱敏验收样本"}
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(id, source_site, source_url, canonical_url, title, purchaser,
                publish_time, region, content_text, core_content, fields_json, updated_at, last_seen_at)
            VALUES (?, 'demo', ?, ?, ?, ?, '2026-09-28', '北京', ?, ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(id) DO UPDATE SET title = excluded.title, purchaser = excluded.purchaser,
                content_text = excluded.content_text, core_content = excluded.core_content,
                fields_json = excluded.fields_json, updated_at = datetime('now'), last_seen_at = datetime('now')
            """,
            (NOTICE_ID, "https://example.com/feishu-war-room", "https://example.com/feishu-war-room", "政务云一键投标战情室", "某政务单位（脱敏）", "资格、技术、报价和交付要求已确认，团队进入执行。", "把确认结果编排为群卡片、任务、日历、多维表格和状态回执。", json.dumps(fields, ensure_ascii=False)),
        )
        record_notice_revision(
            conn,
            notice_id=NOTICE_ID,
            before={"bid_deadline": "2026-10-18 17:00", "content_text": "原截止时间为2026-10-18。"},
            after={"bid_deadline": "2026-10-20 17:00", "content_text": "更正截止时间为2026-10-20。"},
        )


def _seed_requirements(settings: Settings):
    return [
        upsert_requirement(settings, notice_id=NOTICE_ID, requirement_key=key, requirement_type=kind, title=title, evidence_text=evidence, source_url="https://example.com/feishu-war-room", source_locator=locator, mandatory=True, confidence=97, status="confirmed", extraction_mode="rules", actor="demo:需求负责人")
        for key, kind, title, evidence, locator in (
            ("QUAL-WR-01", "qualification", "投标主体资格文件", "须提供有效营业执照和信用材料。", "采购文件第8页"),
            ("TECH-WR-01", "technical", "政务云容灾与安全响应", "须提交双活容灾和安全响应方案。", "技术规格第22页"),
            ("COMM-WR-01", "commercial", "报价与交付承诺", "须按更正后的截止时间提交报价和交付计划。", "商务条款第36页"),
        )
    ]


if __name__ == "__main__":
    print(json.dumps(seed(), ensure_ascii=False, indent=2))
