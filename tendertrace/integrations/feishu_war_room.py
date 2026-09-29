from __future__ import annotations

import hashlib
from typing import Any, Callable
from uuid import uuid4
import json

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.integrations.feishu import FeishuClient, FeishuError
from tendertrace.integrations.feishu_opportunity import start_opportunity_collaboration
from tendertrace.integrations.feishu_requirement_sync import sync_requirements_to_feishu
from tendertrace.integrations.feishu_requirement_sync import (
    sync_bid_workplan_task_status,
    sync_requirement_task_status,
    sync_requirements_to_bitable,
)
from tendertrace.change_impact_engine import dispatch_change_impact
from tendertrace.organization_memory import record_memory
from tendertrace.opportunity import get_opportunity
from tendertrace.opportunity_requirements import list_requirements, requirement_summary
from tendertrace.requirement_review_board import (
    requirement_review_summary,
    sync_requirement_review_cases,
)


def build_war_room_plan(
    settings: Settings,
    notice_id: str,
    *,
    receive_id: str = "",
) -> dict[str, object]:
    """Return a local, side-effect-free plan for initializing an opportunity war room."""
    init_db(settings)
    opportunity = get_opportunity(settings, notice_id)
    if opportunity is None:
        raise LookupError("opportunity not found")

    workflow = _mapping(opportunity.get("workflow"))
    requirements = list_requirements(settings, notice_id)
    summary = requirement_summary(settings, notice_id)
    review_summary = requirement_review_summary(settings, notice_id)
    owner_ready = bool(workflow.get("owner_open_id"))
    group_ready = bool(
        settings.feishu_message_app_id_present
        and settings.feishu_message_app_secret_present
        and (receive_id or settings.feishu_default_receive_id)
    )
    calendar_ready = bool(settings.feishu_calendar_id and opportunity.get("bid_deadline"))
    bitable_ready = bool(
        settings.feishu_bitable_app_token and settings.feishu_bitable_table_id
    )
    task_candidates = sum(
        item.mandatory and item.status in {"pending", "review"}
        for item in requirements
    )
    steps = [
        _step(
            "group_card",
            "战情室卡片",
            group_ready,
            "发送机会卡片到当前项目群" if receive_id else "复用已配置的飞书群并发送机会卡片",
            "需要配置飞书消息应用和默认接收群",
        ),
        _step(
            "owner_task",
            "主责跟进任务",
            owner_ready,
            f"为负责人创建主任务；当前有 {task_candidates} 项强制要求待处理",
            "需要先在机会工作流中认领负责人",
        ),
        _step(
            "deadline_calendar",
            "截止日历",
            calendar_ready,
            "创建投标截止提醒日程",
            "需要识别投标截止时间并配置飞书日历",
        ),
        _step(
            "workflow_bitable",
            "机会工作流台账",
            bitable_ready,
            "同步机会、负责人和推进状态到飞书多维表格",
            "需要配置飞书多维表格应用和数据表",
        ),
        _step(
            "review_board",
            "可质询多角色会审",
            True,
            _review_board_detail(review_summary),
            "",
        ),
    ]
    persisted = _war_room_state(settings, notice_id)
    preflight = _preflight_checks(
        settings,
        receive_id=receive_id,
        owner_ready=owner_ready,
        deadline_ready=bool(opportunity.get("bid_deadline")),
        requirement_count=int(summary.get("total_count") or 0),
    )
    return {
        "mode": "local_plan",
        "notice_id": notice_id,
        "title": str(opportunity.get("title") or "未命名机会"),
        "workflow": {
            "stage": str(workflow.get("stage") or "identified"),
            "owner_name": str(workflow.get("owner_name") or ""),
            "owner_ready": owner_ready,
            "bid_deadline": str(opportunity.get("bid_deadline") or ""),
        },
        "requirements": {
            **summary,
            "task_candidate_count": task_candidates,
        },
        "review_board": review_summary,
        "steps": steps,
        "preflight": preflight,
        "preflight_ready_count": sum(item["status"] == "ready" for item in preflight),
        "journey": _journey(persisted, preflight, review_summary),
        "session": persisted.get("session"),
        "receipts": persisted.get("receipts", []),
        "resources": persisted.get("resources", []),
        "sync": _sync_summary(settings, notice_id, persisted),
        "change_actions": _change_action_summary(settings, notice_id),
        "ready_step_count": sum(step["status"] == "ready" for step in steps),
        "launch": {
            "method": "POST",
            "endpoint": f"/api/opportunities/{notice_id}/war-room/launch",
            "external_side_effects": ["card", "task", "calendar", "bitable", "requirement_tasks"],
            "ready": group_ready,
        },
        "event": {
            "type": "war_room.plan_ready",
            "notice_id": notice_id,
            "task_candidate_count": task_candidates,
        },
    }


def launch_war_room(
    settings: Settings,
    notice_id: str,
    *,
    receive_id: str,
    receive_id_type: str,
    client: FeishuClient | None = None,
    collaboration_starter: Callable[..., object] = start_opportunity_collaboration,
    requirement_syncer: Callable[..., object] = sync_requirements_to_feishu,
    requirement_bitable_syncer: Callable[..., object] = sync_requirements_to_bitable,
    actor: str = "admin",
    workspace_id: str = "",
) -> dict[str, object]:
    """Start the configured Feishu collaboration resources and persist the result.

    The plan remains safe to inspect. This function is the only path that causes
    external side effects, and it reports each resource independently afterwards.
    """
    plan = build_war_room_plan(settings, notice_id, receive_id=receive_id)
    session_id = _ensure_war_room(
        settings,
        notice_id,
        workspace_id=workspace_id,
        receive_id=receive_id,
        receive_id_type=receive_id_type,
        actor=actor,
    )
    if not receive_id:
        result = _record_launch(
            settings,
            notice_id,
            plan,
            status="blocked",
            message="未配置飞书接收群，无法启动战情室",
            steps=_blocked_steps(plan, "需要配置飞书默认接收群"),
        )
        _persist_launch(settings, session_id, result, actor=actor)
        return result
    opportunity = get_opportunity(settings, notice_id)
    assert opportunity is not None
    review_result = sync_requirement_review_cases(settings, notice_id)
    opportunity = {
        **opportunity,
        "review_board": review_result.get("summary", {}),
    }
    workflow = _mapping(opportunity.get("workflow"))
    try:
        collaboration = collaboration_starter(
            settings,
            opportunity,
            receive_id=receive_id,
            receive_id_type=receive_id_type,
            owner_open_id=str(workflow.get("owner_open_id") or ""),
            owner_name=str(workflow.get("owner_name") or ""),
            create_task=bool(workflow.get("owner_open_id")),
            create_calendar_event=bool(settings.feishu_calendar_id and opportunity.get("bid_deadline")),
            client=client,
        )
    except (FeishuError, ValueError, TypeError) as exc:
        result = _record_launch(
            settings,
            notice_id,
            plan,
            status="failed",
            message=f"战情室启动失败：{type(exc).__name__}: {exc}",
            steps=_blocked_steps(plan, f"启动失败：{type(exc).__name__}"),
        )
        _persist_launch(settings, session_id, result, actor=actor)
        return result

    requirement_result: object | None = None
    requirement_error = ""
    try:
        requirement_result = requirement_syncer(settings, notice_id, client=client)
    except (FeishuError, ValueError, TypeError) as exc:
        requirement_error = f"{type(exc).__name__}: {exc}"
    bitable_requirement_result: object | None = None
    bitable_requirement_error = ""
    if settings.feishu_bitable_app_token and settings.feishu_bitable_table_id:
        try:
            bitable_requirement_result = requirement_bitable_syncer(settings, notice_id)
        except (FeishuError, ValueError, TypeError) as exc:
            bitable_requirement_error = f"{type(exc).__name__}: {exc}"
    steps = _launch_steps(
        plan,
        collaboration,
        requirement_result,
        requirement_error,
        review_result,
    )
    failed_count = sum(step["status"] == "failed" for step in steps)
    status = "partial" if failed_count else "started"
    message = "飞书战情室已启动" if not failed_count else "飞书战情室已部分启动，请处理失败步骤"
    result = _record_launch(settings, notice_id, plan, status=status, message=message, steps=steps)
    result["war_room_id"] = session_id
    result["requirement_bitable"] = (
        _safe_result(bitable_requirement_result)
        if bitable_requirement_result is not None
        else {"status": "failed" if bitable_requirement_error else "skipped", "error": bitable_requirement_error}
    )
    _persist_launch(
        settings,
        session_id,
        result,
        actor=actor,
        resource_ids={
            "group_card": str(getattr(collaboration, "message_id", "") or ""),
            "owner_task": str(getattr(collaboration, "task_guid", "") or ""),
            "deadline_calendar": str(getattr(collaboration, "event_id", "") or ""),
            "workflow_bitable": _bitable_resource_id(settings),
        },
        receive_id=receive_id,
    )
    return {**result, **_war_room_state(settings, notice_id)}


def retry_war_room_step(
    settings: Settings,
    notice_id: str,
    step_key: str,
    *,
    actor: str,
    client: FeishuClient | None = None,
    collaboration_starter: Callable[..., object] = start_opportunity_collaboration,
    requirement_syncer: Callable[..., object] = sync_requirements_to_feishu,
    requirement_bitable_syncer: Callable[..., object] = sync_requirements_to_bitable,
) -> dict[str, object]:
    state = _war_room_state(settings, notice_id)
    session = _mapping(state.get("session"))
    if not session:
        raise LookupError("war room has not been launched")
    if step_key not in {"group_card", "owner_task", "deadline_calendar", "workflow_bitable", "review_board", "requirement_tasks"}:
        raise ValueError("unsupported war room step")
    receive_id = str(session.get("receive_id") or "")
    receive_id_type = str(session.get("receive_id_type") or "chat_id")
    if step_key == "requirement_tasks":
        try:
            value = requirement_syncer(settings, notice_id, client=client)
            status = "completed" if str(getattr(value, "status", "")) == "finished" else "failed"
            detail = f"已创建 {getattr(value, 'created_count', 0)} 项，复用 {getattr(value, 'skipped_count', 0)} 项"
            error = "" if status == "completed" else str(getattr(value, "failures", ""))[:500]
            _persist_single_step(settings, str(session["id"]), notice_id, step_key, "要求账本任务", status, detail, error=error)
        except (FeishuError, ValueError, TypeError) as exc:
            _persist_single_step(settings, str(session["id"]), notice_id, step_key, "要求账本任务", "failed", "要求任务同步失败", error=f"{type(exc).__name__}: {exc}")
    elif step_key == "workflow_bitable":
        try:
            value = requirement_bitable_syncer(settings, notice_id)
            payload = _safe_result(value)
            status = "completed" if str(payload.get("status") or "") in {"sent", "updated", "finished"} else "failed"
            _persist_single_step(settings, str(session["id"]), notice_id, step_key, "多维表格要求台账", status, f"要求台账同步：{payload.get('status') or 'unknown'}", resource_id=_bitable_resource_id(settings), error="" if status == "completed" else str(payload)[:500])
        except (FeishuError, ValueError, TypeError) as exc:
            _persist_single_step(settings, str(session["id"]), notice_id, step_key, "多维表格要求台账", "failed", "多维表格同步失败", error=f"{type(exc).__name__}: {exc}")
    elif step_key == "review_board":
        value = sync_requirement_review_cases(settings, notice_id)
        _persist_single_step(settings, str(session["id"]), notice_id, step_key, "可质询多角色会审", "completed", f"待裁决 {(value.get('summary') or {}).get('pending_count', 0)} 项")
    else:
        opportunity = get_opportunity(settings, notice_id)
        if opportunity is None:
            raise LookupError("opportunity not found")
        workflow = _mapping(opportunity.get("workflow"))
        try:
            collaboration = collaboration_starter(
                settings,
                opportunity,
                receive_id=receive_id,
                receive_id_type=receive_id_type,
                owner_open_id=str(workflow.get("owner_open_id") or ""),
                owner_name=str(workflow.get("owner_name") or ""),
                create_task=bool(workflow.get("owner_open_id")),
                create_calendar_event=bool(settings.feishu_calendar_id and opportunity.get("bid_deadline")),
                client=client,
            )
        except (FeishuError, ValueError, TypeError) as exc:
            _persist_single_step(
                settings,
                str(session["id"]),
                notice_id,
                step_key,
                {"group_card": "项目总览卡片", "owner_task": "主责跟进任务", "deadline_calendar": "投标截止日历"}[step_key],
                "failed",
                "资源重试失败",
                receive_id=receive_id,
                error=f"{type(exc).__name__}: {exc}",
            )
            _record_sync_event(settings, str(session["id"]), notice_id, "step_retry", "outbound", "failed", actor, {"step_key": step_key, "error": str(exc)})
            _record_opportunity_event(settings, notice_id, "war_room_step_retried", actor, {"step_key": step_key, "status": "failed", "error": str(exc)})
            return _war_room_payload(settings, notice_id, receive_id=receive_id)
        resource_ids = {
            "group_card": str(getattr(collaboration, "message_id", "") or ""),
            "owner_task": str(getattr(collaboration, "task_guid", "") or ""),
            "deadline_calendar": str(getattr(collaboration, "event_id", "") or ""),
        }
        rid = resource_ids[step_key]
        _persist_single_step(settings, str(session["id"]), notice_id, step_key, {"group_card": "项目总览卡片", "owner_task": "主责跟进任务", "deadline_calendar": "投标截止日历"}[step_key], "completed" if rid else "failed", "资源已创建或复用" if rid else "未返回资源标识", resource_id=rid, receive_id=receive_id, error="" if rid else "resource id missing")
    _record_sync_event(settings, str(session["id"]), notice_id, "step_retry", "outbound", "finished", actor, {"step_key": step_key})
    _record_opportunity_event(settings, notice_id, "war_room_step_retried", actor, {"step_key": step_key, "status": "finished"})
    return _war_room_payload(settings, notice_id, receive_id=receive_id)


def sync_war_room_back(
    settings: Settings,
    notice_id: str,
    *,
    actor: str,
    client: FeishuClient | None = None,
) -> dict[str, object]:
    state = _war_room_state(settings, notice_id)
    session = _mapping(state.get("session"))
    if not session:
        raise LookupError("war room has not been launched")
    requirement_result = sync_requirement_task_status(settings, notice_id, client=client)
    workplan_result = sync_bid_workplan_task_status(settings, notice_id, client=client)
    conflict_count = int(requirement_result.conflict_count) + int(workplan_result.get("conflict_count") or 0)
    failed_count = int(requirement_result.failed_count) + int(workplan_result.get("failed_count") or 0)
    result = {
        "status": "partial" if failed_count else "finished",
        "requirement_tasks": requirement_result.to_dict(),
        "workplan_tasks": workplan_result,
        "conflict_count": conflict_count,
        "failed_count": failed_count,
    }
    with connection(settings) as conn:
        conn.execute("UPDATE feishu_war_rooms SET last_sync_at = datetime('now'), updated_at = datetime('now') WHERE id = ?", (session["id"],))
    _record_sync_event(settings, str(session["id"]), notice_id, "task_status_sync", "inbound", str(result["status"]), actor, result)
    _record_opportunity_event(settings, notice_id, "war_room_task_status_synced", actor, result)
    return {**result, **_war_room_state(settings, notice_id)}


def dispatch_war_room_changes(
    settings: Settings,
    notice_id: str,
    *,
    actor: str,
    client: FeishuClient | None = None,
) -> dict[str, object]:
    if not actor.strip():
        raise ValueError("actor is required")
    state = _war_room_state(settings, notice_id)
    session = _mapping(state.get("session"))
    if not session:
        raise LookupError("war room has not been launched")
    with connection(settings) as conn:
        row = conn.execute("SELECT id FROM change_impact_rounds WHERE notice_id = ? ORDER BY round_number DESC LIMIT 1", (notice_id,)).fetchone()
    if row is None:
        result = {"status": "skipped", "message": "当前没有公告变更行动", "sent_count": 0}
    else:
        result = dispatch_change_impact(settings, notice_id, str(row["id"]), actor=actor, client=client)
    _record_sync_event(settings, str(session["id"]), notice_id, "affected_change_dispatch", "outbound", str(result.get("status") or "finished"), actor, result)
    _record_opportunity_event(settings, notice_id, "war_room_changes_dispatched", actor, result)
    return {**result, **_war_room_state(settings, notice_id)}


def archive_war_room(
    settings: Settings,
    notice_id: str,
    *,
    actor: str,
) -> dict[str, object]:
    state = _war_room_state(settings, notice_id)
    session = _mapping(state.get("session"))
    if not session:
        raise LookupError("war room has not been launched")
    workspace_id = str(session.get("workspace_id") or "")
    if not workspace_id:
        raise ValueError("war room is not linked to an organization workspace")
    opportunity = get_opportunity(settings, notice_id)
    if opportunity is None:
        raise LookupError("opportunity not found")
    receipts = list(state.get("receipts") or [])
    memory = record_memory(
        settings,
        workspace_id=workspace_id,
        memory_type="lesson",
        title=f"投标战情室归档：{opportunity.get('title') or notice_id}",
        content=f"战情室完成归档，共保留 {len(receipts)} 个执行步骤回执；项目状态、负责人、飞书资源和同步记录可回查。",
        source_type="web",
        related_notice_id=notice_id,
        evidence_url=str(opportunity.get("source_url") or ""),
        actor=actor,
    )
    with connection(settings) as conn:
        conn.execute("UPDATE feishu_war_rooms SET status = 'archived', archive_memory_id = ?, archived_at = datetime('now'), updated_at = datetime('now') WHERE id = ?", (memory.id, session["id"]))
    _record_sync_event(settings, str(session["id"]), notice_id, "war_room_archived", "internal", "finished", actor, {"memory_id": memory.id})
    _record_opportunity_event(settings, notice_id, "war_room_archived", actor, {"memory_id": memory.id})
    return _war_room_payload(settings, notice_id, receive_id=str(session.get("receive_id") or ""))


def _step(
    key: str,
    label: str,
    ready: bool,
    ready_detail: str,
    blocked_detail: str,
) -> dict[str, str]:
    return {
        "key": key,
        "label": label,
        "status": "ready" if ready else "needs_configuration",
        "detail": ready_detail if ready else blocked_detail,
        "event_type": f"war_room.{key}.requested",
    }


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _review_board_detail(summary: dict[str, object]) -> str:
    pending = int(summary.get("pending_count") or 0)
    total = int(summary.get("total_count") or 0)
    if pending:
        return f"会审队列已就绪，待裁决 {pending} 项"
    if total:
        return f"会审项已全部裁决，共 {total} 项"
    return "启动时按要求账本与公告变更生成会审项"


def _launch_steps(
    plan: dict[str, object],
    collaboration: object,
    requirement_result: object | None,
    requirement_error: str,
    review_result: dict[str, object],
) -> list[dict[str, str]]:
    existing_steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    values = {str(step.get("key")): dict(step) for step in existing_steps if isinstance(step, dict)}
    message_id = str(getattr(collaboration, "message_id", "") or "")
    task_guid = str(getattr(collaboration, "task_guid", "") or "")
    event_id = str(getattr(collaboration, "event_id", "") or "")
    bitable_status = str(getattr(collaboration, "bitable_status", "unknown") or "unknown")
    outcomes = {
        "group_card": ("completed" if message_id else "skipped", "机会卡片已发送" if message_id else "未返回消息标识"),
        "owner_task": ("completed" if task_guid else "skipped", "负责人任务已创建或复用" if task_guid else "尚未认领负责人，未创建主任务"),
        "deadline_calendar": ("completed" if event_id else "skipped", "投标截止日程已创建" if event_id else "截止时间或日历未配置，未创建日程"),
        "workflow_bitable": ("completed" if bitable_status in {"sent", "updated", "finished"} else "skipped", f"多维表格同步：{bitable_status}"),
    }
    launched = []
    for key in ("group_card", "owner_task", "deadline_calendar", "workflow_bitable"):
        step = values.get(key, {"key": key, "label": key})
        status, detail = outcomes[key]
        launched.append({**step, "status": status, "detail": detail})
    review_summary = _mapping(review_result.get("summary"))
    review_step = values.get("review_board", {"key": "review_board", "label": "可质询多角色会审"})
    launched.append(
        {
            **review_step,
            "status": "completed",
            "detail": (
                f"会审队列已同步：新增 {review_result.get('created_count', 0)} 项；"
                f"待裁决 {review_summary.get('pending_count', 0)} 项"
            ),
        }
    )
    sync_status = str(getattr(requirement_result, "status", "") or "")
    sync_detail = (
        f"已同步 {getattr(requirement_result, 'created_count', 0)} 项要求任务"
        if requirement_result is not None
        else requirement_error or "要求任务未执行"
    )
    launched.append(
        {
            "key": "requirement_tasks",
            "label": "要求账本任务",
            "status": "failed" if requirement_error or sync_status == "partial" else "completed" if sync_status == "finished" else "skipped",
            "detail": sync_detail,
            "event_type": "war_room.requirement_tasks.requested",
        }
    )
    return launched


def _blocked_steps(plan: dict[str, object], detail: str) -> list[dict[str, str]]:
    source_steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    steps = [
        {**dict(step), "status": "blocked", "detail": detail}
        for step in source_steps
        if isinstance(step, dict)
    ]
    steps.append(
        {
            "key": "requirement_tasks",
            "label": "要求账本任务",
            "status": "blocked",
            "detail": detail,
            "event_type": "war_room.requirement_tasks.requested",
        }
    )
    return steps


def _record_launch(
    settings: Settings,
    notice_id: str,
    plan: dict[str, object],
    *,
    status: str,
    message: str,
    steps: list[dict[str, str]],
) -> dict[str, object]:
    init_db(settings)
    result = {
        "status": status,
        "notice_id": notice_id,
        "title": plan.get("title") or "",
        "message": message,
        "steps": steps,
        "completed_count": sum(step.get("status") == "completed" for step in steps),
        "failed_count": sum(step.get("status") == "failed" for step in steps),
    }
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO opportunity_events(id, notice_id, action, actor_open_id, payload_json)
            VALUES (?, ?, 'war_room_launched', 'system:war_room', ?)
            """,
            (str(uuid4()), notice_id, json.dumps(result, ensure_ascii=False, sort_keys=True)),
        )
    return result


def _war_room_payload(settings: Settings, notice_id: str, *, receive_id: str = "") -> dict[str, object]:
    return build_war_room_plan(settings, notice_id, receive_id=receive_id)


def _ensure_war_room(
    settings: Settings,
    notice_id: str,
    *,
    workspace_id: str,
    receive_id: str,
    receive_id_type: str,
    actor: str,
) -> str:
    war_room_id = hashlib.sha256(f"war-room|{notice_id}".encode()).hexdigest()[:24]
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO feishu_war_rooms(
                id, notice_id, workspace_id, receive_id, receive_id_type, created_by
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(notice_id) DO UPDATE SET
                workspace_id = CASE WHEN excluded.workspace_id <> '' THEN excluded.workspace_id ELSE feishu_war_rooms.workspace_id END,
                receive_id = CASE WHEN excluded.receive_id <> '' THEN excluded.receive_id ELSE feishu_war_rooms.receive_id END,
                receive_id_type = excluded.receive_id_type,
                updated_at = datetime('now')
            """,
            (war_room_id, notice_id, workspace_id.strip(), receive_id.strip(), receive_id_type.strip() or "chat_id", actor.strip() or "admin"),
        )
        row = conn.execute("SELECT id FROM feishu_war_rooms WHERE notice_id = ?", (notice_id,)).fetchone()
    assert row is not None
    return str(row["id"])


def _persist_launch(
    settings: Settings,
    war_room_id: str,
    result: dict[str, object],
    *,
    actor: str,
    resource_ids: dict[str, str] | None = None,
    receive_id: str = "",
) -> None:
    resource_ids = resource_ids or {}
    notice_id = str(result.get("notice_id") or "")
    status = str(result.get("status") or "failed")
    with connection(settings) as conn:
        conn.execute(
            """
            UPDATE feishu_war_rooms
            SET status = ?, launch_count = launch_count + 1,
                last_success_at = CASE WHEN ? IN ('started', 'partial') THEN datetime('now') ELSE last_success_at END,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (status, status, war_room_id),
        )
    for step in result.get("steps", []):
        if not isinstance(step, dict):
            continue
        step_key = str(step.get("key") or "")
        resource_id = resource_ids.get(step_key, "")
        _persist_single_step(
            settings,
            war_room_id,
            notice_id,
            step_key,
            str(step.get("label") or step_key),
            str(step.get("status") or "pending"),
            str(step.get("detail") or ""),
            resource_id=resource_id,
            receive_id=receive_id,
            error=str(step.get("detail") or "") if step.get("status") == "failed" else "",
        )
    _record_sync_event(settings, war_room_id, notice_id, "war_room_launch", "outbound", status, actor, result)


def _persist_single_step(
    settings: Settings,
    war_room_id: str,
    notice_id: str,
    step_key: str,
    label: str,
    status: str,
    detail: str,
    *,
    resource_id: str = "",
    receive_id: str = "",
    error: str = "",
) -> None:
    idempotency_key = hashlib.sha256(f"war-room|{notice_id}|{step_key}".encode()).hexdigest()
    step_id = idempotency_key[:24]
    resource_type = {
        "group_card": "message",
        "owner_task": "task",
        "deadline_calendar": "calendar",
        "workflow_bitable": "bitable",
        "requirement_tasks": "task_set",
        "review_board": "review_queue",
    }.get(step_key, "")
    resource_url = _resource_url(resource_type, resource_id, receive_id)
    with connection(settings) as conn:
        before = conn.execute(
            "SELECT resource_id, attempt_count FROM feishu_war_room_steps WHERE war_room_id = ? AND step_key = ?",
            (war_room_id, step_key),
        ).fetchone()
        reused = bool(before and (str(before["resource_id"] or "") == resource_id or int(before["attempt_count"] or 0) > 0))
        receipt = {"detail": detail, "resource_id": resource_id, "resource_type": resource_type}
        conn.execute(
            """
            INSERT INTO feishu_war_room_steps(
                id, war_room_id, notice_id, step_key, label, status, idempotency_key,
                resource_type, resource_id, resource_url, reused, attempt_count,
                last_error, receipt_json, last_attempt_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, datetime('now'),
                CASE WHEN ? = 'completed' THEN datetime('now') ELSE NULL END)
            ON CONFLICT(war_room_id, step_key) DO UPDATE SET
                label = excluded.label, status = excluded.status,
                resource_type = CASE WHEN excluded.resource_type <> '' THEN excluded.resource_type ELSE feishu_war_room_steps.resource_type END,
                resource_id = CASE WHEN excluded.resource_id <> '' THEN excluded.resource_id ELSE feishu_war_room_steps.resource_id END,
                resource_url = CASE WHEN excluded.resource_url <> '' THEN excluded.resource_url ELSE feishu_war_room_steps.resource_url END,
                reused = excluded.reused, attempt_count = feishu_war_room_steps.attempt_count + 1,
                last_error = excluded.last_error, receipt_json = excluded.receipt_json,
                last_attempt_at = datetime('now'),
                completed_at = CASE WHEN excluded.status = 'completed' THEN COALESCE(feishu_war_room_steps.completed_at, datetime('now')) ELSE feishu_war_room_steps.completed_at END,
                updated_at = datetime('now')
            """,
            (
                step_id, war_room_id, notice_id, step_key, label, status,
                idempotency_key, resource_type, resource_id, resource_url,
                int(reused), error[:500], json.dumps(receipt, ensure_ascii=False, sort_keys=True), status,
            ),
        )


def _war_room_state(settings: Settings, notice_id: str) -> dict[str, object]:
    with connection(settings) as conn:
        session_row = conn.execute("SELECT * FROM feishu_war_rooms WHERE notice_id = ?", (notice_id,)).fetchone()
        if session_row is None:
            return {"session": None, "receipts": [], "resources": []}
        receipt_rows = conn.execute(
            "SELECT * FROM feishu_war_room_steps WHERE war_room_id = ? ORDER BY created_at, rowid",
            (session_row["id"],),
        ).fetchall()
    session = dict(session_row)
    receipts = []
    resources = []
    for row in receipt_rows:
        receipt = {
            "id": str(row["id"]),
            "step_key": str(row["step_key"]),
            "label": str(row["label"]),
            "status": str(row["status"]),
            "resource_type": str(row["resource_type"] or ""),
            "resource_id": str(row["resource_id"] or ""),
            "resource_url": str(row["resource_url"] or ""),
            "reused": bool(row["reused"]),
            "attempt_count": int(row["attempt_count"] or 0),
            "last_error": str(row["last_error"] or ""),
            "last_attempt_at": str(row["last_attempt_at"] or ""),
            "completed_at": str(row["completed_at"] or ""),
            "receipt": _json_mapping(row["receipt_json"]),
        }
        receipts.append(receipt)
        if receipt["resource_id"]:
            resources.append({key: receipt[key] for key in ("step_key", "label", "resource_type", "resource_id", "resource_url", "reused")})
    return {"session": session, "receipts": receipts, "resources": resources}


def _preflight_checks(
    settings: Settings,
    *,
    receive_id: str,
    owner_ready: bool,
    deadline_ready: bool,
    requirement_count: int,
) -> list[dict[str, object]]:
    credentials = settings.feishu_message_app_id_present and settings.feishu_message_app_secret_present
    checks = [
        ("app", "应用身份", credentials, "飞书应用凭证已配置", "需要配置并发布飞书应用"),
        ("group", "项目群", bool(receive_id or settings.feishu_default_receive_id), "已选择真实项目群", "需要选择或创建项目群"),
        ("owner", "负责人身份", owner_ready, "负责人已绑定飞书身份", "需要认领负责人并绑定飞书身份"),
        ("bitable", "多维表格", bool(settings.feishu_bitable_app_token and settings.feishu_bitable_table_id), "要求台账目标已配置", "需要配置多维表格 App Token 和 Table ID"),
        ("task", "Task v2", credentials, "任务接口凭证已配置", "需要任务权限与应用凭证"),
        ("calendar", "日历", bool(settings.feishu_calendar_id and deadline_ready), "日历与投标截止已就绪", "需要日历权限和投标截止时间"),
        ("requirements", "执行数据", requirement_count > 0, f"已确认 {requirement_count} 条要求", "需要先建立要求账本"),
        ("listener", "状态回写", settings.feishu_enabled, "飞书长连接已启用", "需要启用飞书事件长连接"),
    ]
    return [
        {"key": key, "label": label, "status": "ready" if ready else "attention", "detail": ready_detail if ready else blocked_detail}
        for key, label, ready, ready_detail, blocked_detail in checks
    ]


def _journey(
    state: dict[str, object],
    preflight: list[dict[str, object]],
    review_summary: dict[str, object],
) -> list[dict[str, object]]:
    session = _mapping(state.get("session"))
    receipt_map = {str(item.get("step_key")): item for item in state.get("receipts", []) if isinstance(item, dict)}
    resource_keys = {"group_card", "owner_task", "deadline_calendar", "workflow_bitable", "requirement_tasks"}
    resource_receipts = [receipt_map[key] for key in resource_keys if key in receipt_map]
    resources_completed = sum(item.get("status") == "completed" for item in resource_receipts)
    preflight_ready = sum(item.get("status") == "ready" for item in preflight)
    change = _mapping(review_summary)
    return [
        {"key": "confirm", "label": "确认进入执行", "status": "completed" if session else "current", "detail": "用户确认后才创建外部资源"},
        {"key": "preflight", "label": "身份与权限预检", "status": "completed" if preflight_ready == len(preflight) else "attention", "detail": f"{preflight_ready}/{len(preflight)} 项就绪"},
        {"key": "resources", "label": "编排协作资源", "status": "completed" if resources_completed >= 4 else "current" if session else "pending", "detail": f"{resources_completed}/{len(resource_keys)} 类资源已有回执"},
        {"key": "team", "label": "团队协同执行", "status": "active" if session and str(session.get("status")) != "archived" else "pending", "detail": f"会审待裁决 {change.get('pending_count') or 0} 项"},
        {"key": "writeback", "label": "状态回写确认", "status": "completed" if session.get("last_sync_at") else "ready" if session else "pending", "detail": str(session.get("last_sync_at") or "等待首次同步")},
        {"key": "changes", "label": "变更增量推送", "status": "ready" if session else "pending", "detail": "只同步负责人已确认的受影响行动"},
        {"key": "archive", "label": "归档组织记忆", "status": "completed" if session.get("archived_at") else "ready" if session else "pending", "detail": str(session.get("archived_at") or "项目结束后执行")},
    ]


def _sync_summary(settings: Settings, notice_id: str, state: dict[str, object]) -> dict[str, object]:
    session = _mapping(state.get("session"))
    with connection(settings) as conn:
        conflicts = int(conn.execute("SELECT COUNT(*) FROM opportunity_events WHERE notice_id = ? AND action = 'requirement_task_conflict'", (notice_id,)).fetchone()[0])
        heartbeat = conn.execute("SELECT status, heartbeat_at, detail FROM integration_runtime_heartbeats WHERE integration_name = 'feishu_bot_listener'").fetchone()
        queued = int(conn.execute("SELECT COUNT(*) FROM feishu_war_room_steps WHERE notice_id = ? AND status = 'failed'", (notice_id,)).fetchone()[0])
    return {
        "last_success_at": str(session.get("last_success_at") or ""),
        "last_sync_at": str(session.get("last_sync_at") or ""),
        "conflict_count": conflicts,
        "retryable_failed_count": queued,
        "listener_status": str(heartbeat["status"] if heartbeat else "unknown"),
        "listener_heartbeat_at": str(heartbeat["heartbeat_at"] if heartbeat else ""),
        "listener_detail": str(heartbeat["detail"] if heartbeat else ""),
    }


def _change_action_summary(settings: Settings, notice_id: str) -> dict[str, object]:
    with connection(settings) as conn:
        row = conn.execute("SELECT id, round_number FROM change_impact_rounds WHERE notice_id = ? ORDER BY round_number DESC LIMIT 1", (notice_id,)).fetchone()
        if row is None:
            return {"round_id": "", "round_number": 0, "confirmed_count": 0, "pending_count": 0, "failed_count": 0}
        counts = conn.execute(
            """
            SELECT
                SUM(CASE WHEN status = 'confirmed' THEN 1 ELSE 0 END) confirmed_count,
                SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) pending_count,
                SUM(CASE WHEN message_status = 'failed' OR task_status = 'failed' OR calendar_status = 'failed' THEN 1 ELSE 0 END) failed_count
            FROM change_impact_actions WHERE round_id = ?
            """,
            (row["id"],),
        ).fetchone()
    return {
        "round_id": str(row["id"]),
        "round_number": int(row["round_number"] or 0),
        "confirmed_count": int(counts["confirmed_count"] or 0),
        "pending_count": int(counts["pending_count"] or 0),
        "failed_count": int(counts["failed_count"] or 0),
    }


def _record_sync_event(
    settings: Settings,
    war_room_id: str,
    notice_id: str,
    event_type: str,
    direction: str,
    status: str,
    actor: str,
    payload: dict[str, object],
) -> None:
    with connection(settings) as conn:
        conn.execute(
            "INSERT INTO feishu_war_room_sync_events(id, war_room_id, notice_id, event_type, direction, status, actor, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid4()), war_room_id, notice_id, event_type, direction, status, actor.strip() or "admin", json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)),
        )


def _record_opportunity_event(
    settings: Settings,
    notice_id: str,
    action: str,
    actor: str,
    payload: dict[str, object],
) -> None:
    with connection(settings) as conn:
        conn.execute(
            "INSERT INTO opportunity_events(id, notice_id, action, actor_open_id, payload_json) VALUES (?, ?, ?, ?, ?)",
            (str(uuid4()), notice_id, action, actor.strip() or "admin", json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)),
        )


def _resource_url(resource_type: str, resource_id: str, receive_id: str) -> str:
    if not resource_id:
        return ""
    if resource_type == "message" and receive_id:
        return f"https://applink.feishu.cn/client/chat/{receive_id}?message_id={resource_id}"
    if resource_type in {"task", "task_set"}:
        return f"https://applink.feishu.cn/client/todo/detail?guid={resource_id}"
    if resource_type == "calendar":
        return "https://applink.feishu.cn/client/calendar/event/detail"
    if resource_type == "bitable":
        app_token, _, table_id = resource_id.partition("?table=")
        suffix = f"?table={table_id}" if table_id else ""
        return f"https://feishu.cn/base/{app_token}{suffix}"
    return ""


def _bitable_resource_id(settings: Settings) -> str:
    if not settings.feishu_bitable_app_token:
        return ""
    table = f"?table={settings.feishu_bitable_table_id}" if settings.feishu_bitable_table_id else ""
    return f"{settings.feishu_bitable_app_token}{table}"


def _safe_result(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        result = value.to_dict()
        return result if isinstance(result, dict) else {}
    if isinstance(value, dict):
        return value
    return {"status": str(getattr(value, "status", "unknown"))}


def _json_mapping(value: object) -> dict[str, object]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
