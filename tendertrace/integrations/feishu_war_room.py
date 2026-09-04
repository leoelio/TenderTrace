from __future__ import annotations

from typing import Any

from tendertrace.config import Settings
from tendertrace.opportunity import get_opportunity
from tendertrace.opportunity_requirements import list_requirements, requirement_summary


def build_war_room_plan(settings: Settings, notice_id: str) -> dict[str, object]:
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
        and settings.feishu_default_receive_id
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
            "复用已配置的飞书群并发送机会卡片",
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
            "endpoint": "/api/opportunities/send-feishu",
            "external_side_effects": ["card", "task", "calendar", "bitable"],
        },
        "event": {
            "type": "war_room.plan_ready",
            "notice_id": notice_id,
            "task_candidate_count": task_candidates,
        },
    }


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
