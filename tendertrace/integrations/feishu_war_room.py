from __future__ import annotations

from typing import Any, Callable
from uuid import uuid4
import json

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.integrations.feishu import FeishuClient, FeishuError
from tendertrace.integrations.feishu_opportunity import start_opportunity_collaboration
from tendertrace.integrations.feishu_requirement_sync import sync_requirements_to_feishu
from tendertrace.opportunity import get_opportunity
from tendertrace.opportunity_requirements import list_requirements, requirement_summary


def build_war_room_plan(
    settings: Settings,
    notice_id: str,
    *,
    receive_id: str = "",
) -> dict[str, object]:
    """Return a local, side-effect-free plan for initializing an opportunity war room."""
    opportunity = get_opportunity(settings, notice_id)
    if opportunity is None:
        raise LookupError("opportunity not found")

    workflow = _mapping(opportunity.get("workflow"))
    requirements = list_requirements(settings, notice_id)
    summary = requirement_summary(settings, notice_id)
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
    ]
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
        "steps": steps,
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
) -> dict[str, object]:
    """Start the configured Feishu collaboration resources and persist the result.

    The plan remains safe to inspect. This function is the only path that causes
    external side effects, and it reports each resource independently afterwards.
    """
    plan = build_war_room_plan(settings, notice_id, receive_id=receive_id)
    if not receive_id:
        return _record_launch(
            settings,
            notice_id,
            plan,
            status="blocked",
            message="未配置飞书接收群，无法启动战情室",
            steps=_blocked_steps(plan, "需要配置飞书默认接收群"),
        )
    opportunity = get_opportunity(settings, notice_id)
    assert opportunity is not None
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
        return _record_launch(
            settings,
            notice_id,
            plan,
            status="failed",
            message=f"战情室启动失败：{type(exc).__name__}: {exc}",
            steps=_blocked_steps(plan, f"启动失败：{type(exc).__name__}"),
        )

    requirement_result: object | None = None
    requirement_error = ""
    try:
        requirement_result = requirement_syncer(settings, notice_id, client=client)
    except (FeishuError, ValueError, TypeError) as exc:
        requirement_error = f"{type(exc).__name__}: {exc}"
    steps = _launch_steps(plan, collaboration, requirement_result, requirement_error)
    failed_count = sum(step["status"] == "failed" for step in steps)
    status = "partial" if failed_count else "started"
    message = "飞书战情室已启动" if not failed_count else "飞书战情室已部分启动，请处理失败步骤"
    return _record_launch(settings, notice_id, plan, status=status, message=message, steps=steps)


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


def _launch_steps(
    plan: dict[str, object],
    collaboration: object,
    requirement_result: object | None,
    requirement_error: str,
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
            "status": "failed" if requirement_error else "completed" if sync_status == "finished" else "skipped",
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
