from __future__ import annotations

from typing import Any, Callable

from tendertrace.config import Settings
from tendertrace.delivery.feishu_bitable import update_opportunity_workflow_in_bitable
from tendertrace.integrations.feishu_opportunity import build_opportunity_card
from tendertrace.integrations.feishu_memory import build_memory_weekly_card
from tendertrace.memory import (
    build_weekly_report,
    record_activity,
    record_advice_feedback,
)
from tendertrace.opportunity import get_opportunity
from tendertrace.workflow import WorkflowGateError, apply_action, update_workflow


class OpportunityNotFoundError(ValueError):
    pass


def process_feishu_card_action(
    settings: Settings,
    payload: dict[str, object],
    *,
    bitable_updater: Callable[..., object] = update_opportunity_workflow_in_bitable,
) -> dict[str, object]:
    event = _mapping(payload.get("event")) or payload
    value = _mapping(_mapping(event.get("action")).get("value"))
    if value.get("advice_id"):
        return process_memory_advice_card_action(settings, payload)
    return process_opportunity_card_action(
        settings,
        payload,
        bitable_updater=bitable_updater,
    )


def process_opportunity_card_action(
    settings: Settings,
    payload: dict[str, object],
    *,
    bitable_updater: Callable[..., object] = update_opportunity_workflow_in_bitable,
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
    record_activity(
        settings,
        event_type="feishu_opportunity_action",
        target=notice_id,
        label=workflow.stage_label,
        metadata={"action": action, "actor_open_id": actor_open_id},
    )
    return {
        "toast": {"type": "success", "content": f"机会已更新为{workflow.stage_label}"},
        "card": build_opportunity_card(
            refreshed_opportunity,
            workflow,
            next_action=workflow.next_action or "根据当前阶段继续推进",
            qualification=qualification,
        ),
        "workflow": workflow.to_dict(),
        "qualification": qualification,
        "bitable_status": str(getattr(bitable, "status", "unknown")),
    }


def process_memory_advice_card_action(
    settings: Settings,
    payload: dict[str, object],
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
    feedback = record_advice_feedback(
        settings,
        advice_id=advice_id,
        status=status,
        user_id=user_id,
        source="feishu",
        actor=actor_name,
        context={"event_id": _event_id(payload), "actor_open_id": actor_open_id},
    )
    record_activity(
        settings,
        event_type="advice_feedback",
        target=advice_id,
        label=status,
        metadata={"source": "feishu", "actor_open_id": actor_open_id},
        user_id=user_id,
    )
    report = build_weekly_report(settings, user_id=user_id)
    labels = {"accepted": "已采纳", "completed": "已完成", "dismissed": "已忽略"}
    return {
        "toast": {"type": "success", "content": f"建议{labels[status]}"},
        "card": build_memory_weekly_card(report),
        "feedback": feedback,
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
