from __future__ import annotations

from typing import Any, Callable

from tendertrace.config import Settings
from tendertrace.delivery.feishu_bitable import update_opportunity_workflow_in_bitable
from tendertrace.scheduling.ingest_subscriptions import IngestSubscription
from tendertrace.scheduling.subscriptions import Subscription
from tendertrace.integrations.feishu_opportunity import build_opportunity_card
from tendertrace.integrations.feishu_memory import build_memory_weekly_card
from tendertrace.memory import (
    record_activity,
)
from tendertrace.memory_actions import apply_memory_advice_feedback
from tendertrace.opportunity import get_opportunity
from tendertrace.workflow import WorkflowGateError, apply_action, update_workflow


class OpportunityNotFoundError(ValueError):
    pass


def process_feishu_card_action(
    settings: Settings,
    payload: dict[str, object],
    *,
    bitable_updater: Callable[..., object] = update_opportunity_workflow_in_bitable,
    schedule_ingest: Callable[[IngestSubscription], None] | None = None,
    schedule_subscription: Callable[[Subscription], None] | None = None,
    send_opportunity_briefing: Callable[[str | None, str | None], object] | None = None,
    start_collaboration: Callable[[dict[str, object], str, str], object] | None = None,
) -> dict[str, object]:
    event = _mapping(payload.get("event")) or payload
    value = _mapping(_mapping(event.get("action")).get("value"))
    if value.get("advice_id"):
        return process_memory_advice_card_action(
            settings,
            payload,
            schedule_ingest=schedule_ingest,
            schedule_subscription=schedule_subscription,
            send_opportunity_briefing=send_opportunity_briefing,
        )
    return process_opportunity_card_action(
        settings,
        payload,
        bitable_updater=bitable_updater,
        start_collaboration=start_collaboration,
    )


def process_opportunity_card_action(
    settings: Settings,
    payload: dict[str, object],
    *,
    bitable_updater: Callable[..., object] = update_opportunity_workflow_in_bitable,
    start_collaboration: Callable[[dict[str, object], str, str], object] | None = None,
) -> dict[str, object]:
    event = _mapping(payload.get("event")) or payload
    action_payload = _mapping(event.get("action"))
    value = _mapping(action_payload.get("value"))
    action = str(value.get("action") or "").strip()
    notice_id = str(value.get("notice_id") or "").strip()
    if not action or not notice_id:
        raise ValueError("callback action and notice_id are required")
    operator = _mapping(event.get("operator"))
    operator_id = _mapping(operator.get("operator_id"))
    actor_open_id = str(operator_id.get("open_id") or operator.get("open_id") or "")
    actor_name = str(operator.get("name") or actor_open_id or "飞书用户")
    opportunity = get_opportunity(settings, notice_id)
    if opportunity is None:
        raise OpportunityNotFoundError("opportunity not found")
    try:
        workflow = apply_action(
            settings,
            notice_id,
            action,
            actor_open_id=actor_open_id,
            actor_name=actor_name,
            qualification=_mapping(opportunity.get("qualification")),
            decision_reason=str(value.get("reason") or "").strip(),
            payload={"event_id": _event_id(payload), "channel": "feishu"},
        )
    except WorkflowGateError as exc:
        return {
            "toast": {
                "type": "warning",
                "content": f"暂不能推进：{'、'.join(exc.reasons)}",
            },
            "blocked": True,
            "reasons": list(exc.reasons),
        }
    refreshed_opportunity = get_opportunity(settings, notice_id)
    if refreshed_opportunity is None:
        raise OpportunityNotFoundError("opportunity not found")
    qualification = _mapping(refreshed_opportunity.get("qualification"))
    collaboration = {
        "attempted": False,
        "task_status": "not_requested",
        "task_assigned": False,
        "calendar_status": "not_requested",
    }
    if action == "claim" and start_collaboration is not None:
        previous_task = workflow.feishu_task_guid
        previous_event = workflow.feishu_event_id
        collaboration_result = start_collaboration(
            refreshed_opportunity,
            actor_open_id,
            actor_name,
        )
        collaboration_workflow = getattr(collaboration_result, "workflow", None)
        if collaboration_workflow is None:
            raise ValueError("opportunity collaboration did not return a workflow")
        workflow = collaboration_workflow
        task_guid = str(getattr(collaboration_result, "task_guid", "") or "")
        event_id = str(getattr(collaboration_result, "event_id", "") or "")
        collaboration = {
            "attempted": True,
            "task_status": (
                "created" if task_guid and not previous_task else "reused" if task_guid else "not_created"
            ),
            "task_assigned": bool(getattr(collaboration_result, "task_assigned", False)),
            "calendar_status": (
                "created"
                if event_id and not previous_event
                else "reused"
                if event_id
                else "not_configured"
                if not settings.feishu_calendar_id
                else "not_created"
            ),
        }
        bitable_status = str(getattr(collaboration_result, "bitable_status", "unknown"))
        refreshed_opportunity = get_opportunity(settings, notice_id)
        if refreshed_opportunity is None:
            raise OpportunityNotFoundError("opportunity not found")
        qualification = _mapping(refreshed_opportunity.get("qualification"))
    else:
        workflow = update_workflow(
            settings,
            notice_id,
            qualification_score=int(qualification.get("score") or 0),
            qualification_status=str(qualification.get("status") or "pending"),
        )
        refreshed_opportunity["workflow"] = workflow.to_dict()
        refreshed_opportunity["qualification"] = qualification
        bitable = bitable_updater(
            settings,
            notice_id=notice_id,
            workflow=_workflow_sync_payload(workflow, refreshed_opportunity),
        )
        bitable_status = str(getattr(bitable, "status", "unknown"))
    record_activity(
        settings,
        event_type="feishu_opportunity_action",
        target=notice_id,
        label=workflow.stage_label,
        metadata={
            "action": action,
            "actor_open_id": actor_open_id,
            "task_status": collaboration["task_status"],
        },
    )
    toast_content = f"机会已更新为{workflow.stage_label}"
    if collaboration["task_status"] == "created" and collaboration["task_assigned"]:
        toast_content = f"机会已更新为{workflow.stage_label}，任务已创建并分派给你"
    elif collaboration["task_status"] == "reused" and collaboration["task_assigned"]:
        toast_content = f"机会已更新为{workflow.stage_label}，已复用并分派现有任务"
    return {
        "toast": {"type": "success", "content": toast_content},
        "card": build_opportunity_card(
            refreshed_opportunity,
            workflow,
            next_action=workflow.next_action or "根据当前阶段继续推进",
            qualification=qualification,
        ),
        "workflow": workflow.to_dict(),
        "qualification": qualification,
        "bitable_status": bitable_status,
        "collaboration": collaboration,
    }


def process_memory_advice_card_action(
    settings: Settings,
    payload: dict[str, object],
    *,
    schedule_ingest: Callable[[IngestSubscription], None] | None = None,
    schedule_subscription: Callable[[Subscription], None] | None = None,
    send_opportunity_briefing: Callable[[str | None, str | None], object] | None = None,
) -> dict[str, object]:
    event = _mapping(payload.get("event")) or payload
    value = _mapping(_mapping(event.get("action")).get("value"))
    action = str(value.get("action") or "").strip()
    advice_id = str(value.get("advice_id") or "").strip()
    status_by_action = {
        "memory_advice_accept": "accepted",
        "memory_advice_complete": "completed",
        "memory_advice_dismiss": "dismissed",
    }
    status = status_by_action.get(action)
    if not advice_id or status is None:
        raise ValueError("valid memory advice action and advice_id are required")
    operator = _mapping(event.get("operator"))
    operator_id = _mapping(operator.get("operator_id"))
    actor_open_id = str(operator_id.get("open_id") or operator.get("open_id") or "")
    actor_name = str(operator.get("name") or actor_open_id or "飞书用户")
    user_id = str(value.get("user_id") or "admin")
    event_context = _mapping(event.get("context"))
    open_chat_id = str(event_context.get("open_chat_id") or "").strip()
    feedback_context = {
        "event_id": _event_id(payload),
        "actor_open_id": actor_open_id,
    }
    if open_chat_id:
        feedback_context["feishu_receive_id"] = open_chat_id
        feedback_context["feishu_receive_id_type"] = "chat_id"
    result = apply_memory_advice_feedback(
        settings,
        advice_id=advice_id,
        status=status,
        user_id=user_id,
        source="feishu",
        actor=actor_name,
        context=feedback_context,
        schedule_ingest=schedule_ingest,
        schedule_subscription=schedule_subscription,
        send_opportunity_briefing=send_opportunity_briefing,
    )
    feedback = result.feedback
    record_activity(
        settings,
        event_type="advice_feedback",
        target=advice_id,
        label=status,
        metadata={
            "source": "feishu",
            "actor_open_id": actor_open_id,
            "automation_status": result.automation.get("status") or "not_applicable",
        },
        user_id=user_id,
    )
    labels = {"accepted": "已采纳", "completed": "已完成", "dismissed": "已忽略"}
    automation_message = str(result.automation.get("message") or "")
    return {
        "toast": {
            "type": "success",
            "content": automation_message or f"建议{labels[status]}",
        },
        "card": build_memory_weekly_card(result.report),
        "feedback": feedback,
        "automation": result.automation,
    }


def callback_response_payload(result: dict[str, object]) -> dict[str, object]:
    return {
        key: result[key]
        for key in ("toast", "card")
        if isinstance(result.get(key), dict)
    }


def _workflow_sync_payload(workflow, opportunity: dict[str, object]) -> dict[str, object]:
    payload = workflow.to_dict()
    action_state = _mapping(opportunity.get("action_state"))
    payload.update(
        {
            "decision_sla_status": action_state.get("decision_sla_status") or "not_applicable",
            "decision_sla_hours": action_state.get("decision_sla_hours") or 0,
            "decision_wait_hours": action_state.get("decision_wait_hours") or 0,
            "decision_due_at": action_state.get("decision_due_at") or "",
        }
    )
    return payload


def _event_id(payload: dict[str, object]) -> str:
    header = _mapping(payload.get("header"))
    event = _mapping(payload.get("event"))
    return str(header.get("event_id") or event.get("event_id") or payload.get("event_id") or "")


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
