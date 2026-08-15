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


@dataclass(frozen=True)
class EscalationDeliveryResult:
    status: str
    escalation_count: int
    artifact_key: str
    message_id: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def send_opportunity_escalation_summary(
    settings: Settings,
    *,
    force: bool = False,
    client: FeishuClient | None = None,
    opportunity_loader: Callable[..., dict[str, object]] = list_opportunities,
    now: datetime | None = None,
) -> EscalationDeliveryResult:
    payload = opportunity_loader(settings, limit=200, sort="priority")
    summary = _mapping(payload.get("summary"))
    queue = _mapping(summary.get("action_queue"))
    escalations = queue.get("escalations")
    items = escalations if isinstance(escalations, list) else []
    if not items:
        return EscalationDeliveryResult(
            status="skipped",
            escalation_count=0,
            artifact_key="",
            reason="no overdue opportunity decisions",
        )
    artifact_key = _artifact_key(settings, items, now=now)
    if not force and _already_sent(settings, artifact_key):
        return EscalationDeliveryResult(
            status="skipped",
            escalation_count=len(items),
            artifact_key=artifact_key,
            reason="same escalation set already sent today",
        )
    receive_id, receive_id_type = resolve_feishu_receiver(settings)
    feishu = client or FeishuClient(settings)
    try:
        response = feishu.send_card(
            build_escalation_card(items, queue),
            receive_id=receive_id,
            receive_id_type=receive_id_type,
        )
        message_id = _nested_string(response, "data", "message_id")
        record_delivery_attempt(
            settings,
            channel="feishu",
            artifact_type="opportunity_escalation",
            artifact_key=artifact_key,
            status="sent",
            external_id=message_id or None,
        )
    except (FeishuError, ValueError) as exc:
        record_delivery_attempt(
            settings,
            channel="feishu",
            artifact_type="opportunity_escalation",
            artifact_key=artifact_key,
            status="failed",
            error=str(exc),
        )
        raise
    return EscalationDeliveryResult(
        status="sent",
        escalation_count=len(items),
        artifact_key=artifact_key,
        message_id=message_id,
    )


def build_escalation_card(
    escalations: list[object],
    action_queue: dict[str, Any],
) -> dict[str, object]:
    rows = []
    for index, raw in enumerate(escalations[:8], start=1):
        item = _mapping(raw)
        rows.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**{index}. {_text(item.get('title'), '未命名机会')}**\n"
                        f"负责人：{_text(item.get('owner'), '待分配')} · "
                        f"已等待 {_text(item.get('wait_hours'), '0')} 小时 · "
                        f"决策截止 {_text(item.get('due_at'), '-')}"
                    ),
                },
            }
        )
    return {
        "config": {"wide_screen_mode": True, "update_multi": True},
        "header": {
            "template": "red",
            "title": {"tag": "plain_text", "content": "TenderTrace 决策 SLA 升级"},
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**{len(escalations)} 条机会超过 "
                        f"{action_queue.get('decision_sla_hours') or 0} 小时决策时限**\n"
                        "请机会负责人补齐阻断项，管理者完成 Go/Hold/No-Go 决策。"
                    ),
                },
            },
            {"tag": "hr"},
            *rows,
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": "数据来自 TenderTrace 本地机会状态与审计事件。",
                    }
                ],
            },
        ],
    }


def _artifact_key(
    settings: Settings,
    escalations: list[object],
    *,
    now: datetime | None,
) -> str:
    reference = now or datetime.now(ZoneInfo(settings.timezone))
    notice_ids = sorted(
        _text(_mapping(item).get("notice_id")) for item in escalations if _mapping(item)
    )
    digest = hashlib.sha256("\n".join(notice_ids).encode("utf-8")).hexdigest()[:16]
    return f"decision_sla:{reference.date().isoformat()}:{digest}"


def _already_sent(settings: Settings, artifact_key: str) -> bool:
    with connection(settings) as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM delivery_attempts
            WHERE channel = 'feishu'
              AND artifact_type = 'opportunity_escalation'
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
