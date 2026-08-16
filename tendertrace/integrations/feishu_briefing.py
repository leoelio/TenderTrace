from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
from typing import Any, Callable
from zoneinfo import ZoneInfo

from tendertrace.config import Settings
from tendertrace.db import connection
from tendertrace.delivery.ledger import record_delivery_attempt
from tendertrace.delivery.preferences import resolve_feishu_receiver
from tendertrace.integrations.feishu import FeishuClient, FeishuError
from tendertrace.opportunity import list_opportunities
from tendertrace.source_map import source_health


@dataclass(frozen=True)
class BriefingDeliveryResult:
    status: str
    opportunity_count: int
    artifact_key: str
    message_id: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def send_opportunity_briefing(
    settings: Settings,
    *,
    force: bool = False,
    receive_id: str | None = None,
    receive_id_type: str | None = None,
    client: FeishuClient | None = None,
    opportunity_loader: Callable[..., dict[str, object]] = list_opportunities,
    source_health_loader: Callable[..., dict[str, dict[str, object]]] = source_health,
    now: datetime | None = None,
) -> BriefingDeliveryResult:
    payload = opportunity_loader(settings, limit=200, sort="priority")
    items = payload.get("items")
    opportunities = items if isinstance(items, list) else []
    if not opportunities:
        return BriefingDeliveryResult(
            status="skipped",
            opportunity_count=0,
            artifact_key="",
            reason="no opportunities available",
        )
    summary = _mapping(payload.get("summary"))
    health = source_health_loader(settings)
    target_id, target_type = resolve_feishu_receiver(
        settings,
        receive_id=receive_id,
        receive_id_type=receive_id_type,
    )
    artifact_key = _artifact_key(
        settings,
        opportunities,
        summary,
        now=now,
        receive_id=target_id,
        receive_id_type=target_type,
    )
    if not force and _already_sent(settings, artifact_key):
        return BriefingDeliveryResult(
            status="skipped",
            opportunity_count=len(opportunities),
            artifact_key=artifact_key,
            reason="same opportunity briefing already sent today",
        )
    feishu = client or FeishuClient(settings)
    try:
        response = feishu.send_card(
            build_opportunity_briefing_card(
                summary,
                opportunities,
                health,
                now=now or datetime.now(ZoneInfo(settings.timezone)),
            ),
            receive_id=target_id,
            receive_id_type=target_type,
        )
        message_id = _nested_string(response, "data", "message_id")
        record_delivery_attempt(
            settings,
            channel="feishu",
            artifact_type="opportunity_briefing",
            artifact_key=artifact_key,
            status="sent",
            external_id=message_id or None,
        )
    except (FeishuError, ValueError) as exc:
        record_delivery_attempt(
            settings,
            channel="feishu",
            artifact_type="opportunity_briefing",
            artifact_key=artifact_key,
            status="failed",
            error=str(exc),
        )
        raise
    return BriefingDeliveryResult(
        status="sent",
        opportunity_count=len(opportunities),
        artifact_key=artifact_key,
        message_id=message_id,
    )


def build_opportunity_briefing_card(
    summary: dict[str, Any],
    opportunities: list[object],
    health: dict[str, dict[str, object]],
    *,
    now: datetime,
) -> dict[str, object]:
    action_queue = _mapping(summary.get("action_queue"))
    levels = _mapping(summary.get("levels"))
    market = _mapping(summary.get("market"))
    top = [_mapping(item) for item in opportunities[:5] if _mapping(item)]
    elements: list[dict[str, object]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**机会池 {summary.get('total') or len(opportunities)} 条** · "
                    f"A 级 {levels.get('A') or 0} 条 · "
                    f"高优先未认领 {action_queue.get('unowned_priority') or 0} 条\n"
                    f"资格可决策 {action_queue.get('qualification_ready') or 0} 条 · "
                    f"待管理决策 {action_queue.get('decision_pending') or 0} 条 · "
                    f"决策超时 {action_queue.get('decision_overdue') or 0} 条"
                ),
            },
        },
        {"tag": "hr"},
    ]
    for index, item in enumerate(top, start=1):
        elements.extend(_opportunity_elements(index, item))
    signals = market.get("signals")
    market_signals = signals if isinstance(signals, list) else []
    source_alerts = _source_alerts(health)
    if market_signals or source_alerts:
        elements.extend(
            [
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "\n".join(
                            ["**经营提示**"]
                            + [f"• {_text(value)}" for value in market_signals[:3]]
                            + source_alerts[:2]
                        ),
                    },
                },
            ]
        )
    elements.append(
        {
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": "数据来自 TenderTrace 本地机会库、工作流、证据链与来源健康记录。",
                }
            ],
        }
    )
    return {
        "config": {"wide_screen_mode": True, "update_multi": True},
        "header": {
            "template": "blue",
            "title": {
                "tag": "plain_text",
                "content": f"TenderTrace 机会经营晨报 · {now:%m月%d日}",
            },
        },
        "elements": elements,
    }


def _opportunity_elements(index: int, item: dict[str, Any]) -> list[dict[str, object]]:
    intelligence = _mapping(item.get("intelligence"))
    workflow = _mapping(item.get("workflow"))
    action_state = _mapping(item.get("action_state"))
    qualification = _mapping(item.get("qualification"))
    level = _text(intelligence.get("level"), "D")
    score = _text(intelligence.get("score"), "0")
    owner = _text(workflow.get("owner_name"), "待认领")
    deadline = _text(item.get("bid_deadline"), "待核对")
    blockers = _blockers(qualification)
    notice_id = _text(item.get("notice_id"))
    actions: list[dict[str, object]] = []
    action = _next_action(workflow)
    if action and notice_id:
        actions.append(
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": action[1]},
                "type": "primary",
                "value": {"action": action[0], "notice_id": notice_id},
            }
        )
    source_url = _text(item.get("source_url"))
    if source_url:
        actions.append(
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "查看原文"},
                "type": "default",
                "url": source_url,
            }
        )
    values: list[dict[str, object]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**{index}. {_text(item.get('title'), '未命名机会')}**\n"
                    f"{level} 级 · {score} 分 · 负责人 {owner} · 截止 {deadline}\n"
                    f"资格：{blockers or '已满足当前推进条件'} · "
                    f"行动优先级 {action_state.get('priority') or 0}"
                ),
            },
        }
    ]
    if actions:
        values.append({"tag": "action", "actions": actions})
    return values


def _next_action(workflow: dict[str, Any]) -> tuple[str, str] | None:
    stage = _text(workflow.get("stage"), "identified")
    decision = _text(workflow.get("decision"), "pending")
    if stage == "identified":
        return "claim", "认领机会"
    if stage == "qualifying":
        return "pursue", "完成机会确认"
    if stage == "pursuing" and decision != "go":
        return "approve_bid", "Go · 批准投标"
    if stage == "pursuing" and decision == "go":
        return "prepare_bid", "进入投标准备"
    return None


def _blockers(qualification: dict[str, Any]) -> str:
    blocker_map = _mapping(qualification.get("blockers"))
    values = blocker_map.get("approve_bid")
    items = values if isinstance(values, list) else []
    return "、".join(_text(value) for value in items[:3] if _text(value))


def _source_alerts(health: dict[str, dict[str, object]]) -> list[str]:
    alerts = []
    for site, item in sorted(health.items()):
        status = _text(item.get("health_status"))
        if status not in {"degraded", "unhealthy"}:
            continue
        alerts.append(
            f"• 来源 {site} 当前{status}，可靠度 {_text(item.get('reliability_score'), '0')}"
        )
    return alerts


def _artifact_key(
    settings: Settings,
    opportunities: list[object],
    summary: dict[str, Any],
    *,
    now: datetime | None,
    receive_id: str | None,
    receive_id_type: str | None,
) -> str:
    reference = now or datetime.now(ZoneInfo(settings.timezone))
    queue = _mapping(summary.get("action_queue"))
    parts = [
        _text(_mapping(item).get("notice_id"))
        for item in opportunities[:20]
        if _mapping(item)
    ]
    parts.extend(
        str(queue.get(key) or 0)
        for key in ("unowned_priority", "due_soon", "decision_pending", "decision_overdue")
    )
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]
    receiver_scope = hashlib.sha256(
        f"{receive_id_type or ''}:{receive_id or ''}".encode("utf-8")
    ).hexdigest()[:12]
    return f"opportunity_briefing:{reference.date().isoformat()}:{receiver_scope}:{digest}"


def _already_sent(settings: Settings, artifact_key: str) -> bool:
    with connection(settings) as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM delivery_attempts
            WHERE channel = 'feishu'
              AND artifact_type = 'opportunity_briefing'
              AND artifact_key = ?
              AND status = 'sent'
            LIMIT 1
            """,
            (artifact_key,),
        ).fetchone()
    return row is not None


def _nested_string(payload: dict[str, Any], *keys: str) -> str:
    value: object = payload
    for key in keys:
        if not isinstance(value, dict):
            return ""
        value = value.get(key)
    return str(value or "")


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: object, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default
