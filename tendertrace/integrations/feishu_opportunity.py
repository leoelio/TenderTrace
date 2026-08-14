from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
from typing import Any
from zoneinfo import ZoneInfo

from tendertrace.config import Settings
from tendertrace.delivery.feishu_bitable import update_opportunity_workflow_in_bitable
from tendertrace.integrations.feishu import FeishuClient
from tendertrace.workflow import OpportunityWorkflow, get_workflow, update_workflow


@dataclass(frozen=True)
class CollaborationResult:
    workflow: OpportunityWorkflow
    message_id: str
    task_guid: str
    event_id: str
    bitable_status: str

    def to_dict(self) -> dict[str, object]:
        return {
            "workflow": self.workflow.to_dict(),
            "message_id": self.message_id,
            "task_guid": self.task_guid,
            "event_id": self.event_id,
            "bitable_status": self.bitable_status,
        }


def start_opportunity_collaboration(
    settings: Settings,
    opportunity: dict[str, Any],
    *,
    receive_id: str,
    receive_id_type: str,
    owner_open_id: str = "",
    owner_name: str = "",
    create_task: bool = True,
    create_calendar_event: bool = True,
    client: FeishuClient | None = None,
    bitable_updater=update_opportunity_workflow_in_bitable,
) -> CollaborationResult:
    notice_id = str(opportunity.get("notice_id") or "").strip()
    if not notice_id:
        raise ValueError("opportunity notice_id is required")
    feishu = client or FeishuClient(settings)
    workflow = get_workflow(settings, notice_id)
    next_action = _next_action(opportunity)
    due_at = _deadline(opportunity, settings.timezone)
    task_guid = workflow.feishu_task_guid
    event_id = workflow.feishu_event_id

    if create_task and not task_guid:
        task = feishu.create_task(
            summary=f"跟进机会：{_title(opportunity)}",
            description=_task_description(opportunity),
            client_token=_idempotency_key("task", notice_id),
            due_timestamp_ms=(str(int(due_at.timestamp() * 1000)) if due_at else ""),
            assignee_open_id=owner_open_id,
        )
        task_guid = _nested_string(task, "data", "task", "guid")

    if create_calendar_event and settings.feishu_calendar_id and due_at and not event_id:
        event = feishu.create_calendar_event(
            calendar_id=settings.feishu_calendar_id,
            summary=f"投标截止：{_title(opportunity)}",
            description=_task_description(opportunity),
            start_timestamp=str(int((due_at - timedelta(minutes=30)).timestamp())),
            end_timestamp=str(int(due_at.timestamp())),
            idempotency_key=_idempotency_key("calendar", notice_id),
        )
        event_id = _nested_string(event, "data", "event", "event_id")

    card_response = feishu.send_card(
        build_opportunity_card(opportunity, workflow, next_action=next_action),
        receive_id=receive_id,
        receive_id_type=receive_id_type,
    )
    message_id = _nested_string(card_response, "data", "message_id")
    workflow = update_workflow(
        settings,
        notice_id,
        owner_open_id=owner_open_id or None,
        owner_name=owner_name or None,
        next_action=next_action,
        due_at=due_at.isoformat(timespec="minutes") if due_at else "",
        feishu_task_guid=task_guid,
        feishu_event_id=event_id,
        feishu_message_id=message_id,
        updated_by=owner_open_id or "system",
    )
    bitable = bitable_updater(
        settings,
        notice_id=notice_id,
        workflow=workflow.to_dict(),
    )
    return CollaborationResult(
        workflow=workflow,
        message_id=message_id,
        task_guid=task_guid,
        event_id=event_id,
        bitable_status=bitable.status,
    )


def build_opportunity_card(
    opportunity: dict[str, Any],
    workflow: OpportunityWorkflow,
    *,
    next_action: str,
) -> dict[str, Any]:
    intelligence = _mapping(opportunity.get("intelligence"))
    level = str(intelligence.get("level") or "D")
    score = str(intelligence.get("score") or 0)
    source = str(opportunity.get("source_site") or "-")
    region = str(opportunity.get("region") or "-")
    deadline = str(opportunity.get("bid_deadline") or "待核对")
    owner = workflow.owner_name or "待认领"
    risks = intelligence.get("risks") if isinstance(intelligence.get("risks"), list) else []
    risk_text = "；".join(str(item) for item in risks[:2]) or "暂无高风险信号"
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": _title(opportunity)},
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**机会等级** {level} · {score} 分   **地区** {region}\n"
                        f"**来源** {source}   **截止时间** {deadline}\n"
                        f"**负责人** {owner}   **阶段** {workflow.stage_label}"
                    ),
                },
            },
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**下一步** {next_action}\n**风险** {risk_text}",
                },
            },
            {"tag": "hr"},
            {
                "tag": "action",
                "actions": [
                    _action_button("认领机会", "claim", opportunity),
                    _action_button("制定策略", "pursue", opportunity),
                    _action_button("进入投标", "prepare_bid", opportunity),
                    _action_button("归档", "archive", opportunity, button_type="default"),
                ],
            },
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "lark_md",
                        "content": f"[查看原始公告]({opportunity.get('source_url') or ''})",
                    }
                ],
            },
        ],
    }


def _action_button(
    label: str,
    action: str,
    opportunity: dict[str, Any],
    *,
    button_type: str = "primary",
) -> dict[str, Any]:
    return {
        "tag": "button",
        "text": {"tag": "plain_text", "content": label},
        "type": button_type,
        "value": {
            "action": action,
            "notice_id": str(opportunity.get("notice_id") or ""),
        },
    }


def _task_description(opportunity: dict[str, Any]) -> str:
    intelligence = _mapping(opportunity.get("intelligence"))
    return "\n".join(
        item
        for item in (
            f"项目：{_title(opportunity)}",
            f"采购人：{opportunity.get('purchaser') or '待核对'}",
            f"机会判断：{intelligence.get('strategy') or intelligence.get('level_label') or '待研判'}",
            f"公告链接：{opportunity.get('source_url') or ''}",
        )
        if item
    )


def _next_action(opportunity: dict[str, Any]) -> str:
    intelligence = _mapping(opportunity.get("intelligence"))
    actions = intelligence.get("recommended_actions")
    if isinstance(actions, list):
        for item in actions:
            if isinstance(item, dict) and item.get("action"):
                return str(item["action"])
    return str(intelligence.get("strategy") or "核对项目范围、预算与关键时间节点")


def _deadline(opportunity: dict[str, Any], timezone: str) -> datetime | None:
    raw = str(opportunity.get("bid_deadline") or "").strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        value = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            value = datetime.strptime(raw[:10], "%Y-%m-%d").replace(hour=17)
        except ValueError:
            return None
    zone = ZoneInfo(timezone)
    return value.replace(tzinfo=zone) if value.tzinfo is None else value.astimezone(zone)


def _idempotency_key(kind: str, notice_id: str) -> str:
    return hashlib.sha256(f"tendertrace:{kind}:{notice_id}".encode()).hexdigest()


def _nested_string(value: dict[str, Any], *keys: str) -> str:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return str(current or "")


def _title(opportunity: dict[str, Any]) -> str:
    return str(opportunity.get("title") or "未命名机会")[:120]


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
