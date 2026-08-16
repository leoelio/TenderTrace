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
    decision_count: int = 0
    task_count: int = 0
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
    decision_count, task_count = _issue_counts(items)
    if not items:
        return EscalationDeliveryResult(
            status="skipped",
            escalation_count=0,
            artifact_key="",
            reason="no overdue opportunity decisions or tasks",
        )
    artifact_key = _artifact_key(settings, items, now=now)
    if not force and _already_sent(settings, artifact_key):
        return EscalationDeliveryResult(
            status="skipped",
            escalation_count=len(items),
            artifact_key=artifact_key,
            decision_count=decision_count,
            task_count=task_count,
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
        decision_count=decision_count,
        task_count=task_count,
        message_id=message_id,
    )


def build_escalation_card(
    escalations: list[object],
    action_queue: dict[str, Any],
) -> dict[str, object]:
    decision_count, task_count = _issue_counts(escalations)
    rows = []
    for index, raw in enumerate(escalations[:8], start=1):
        item = _mapping(raw)
        issue_types = _issue_types(item)
        wait_text = (
            f"已等待 {_text(item.get('wait_hours'), '0')} 小时 · "
            if "decision" in issue_types
            else ""
        )
        deadline_text = (
            f"决策截止 {_text(item.get('decision_due_at') or item.get('due_at'), '-')} · "
            f"任务截止 {_text(item.get('task_due_at') or item.get('due_at'), '-')}"
            if len(issue_types) > 1
            else (
                f"任务截止 {_text(item.get('task_due_at') or item.get('due_at'), '-')}"
                if "task" in issue_types
                else f"决策截止 {_text(item.get('decision_due_at') or item.get('due_at'), '-')}"
            )
        )
        rows.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**{index}. {_text(item.get('title'), '未命名机会')}**\n"
                        f"风险：{_issue_label(issue_types)} · "
                        f"负责人：{_text(item.get('owner'), '待分配')}\n"
                        f"阶段：{_text(item.get('stage'), '-')} · {wait_text}"
                        f"{deadline_text}"
                    ),
                },
            }
        )
    return {
        "config": {"wide_screen_mode": True, "update_multi": True},
        "header": {
            "template": "red",
            "title": {"tag": "plain_text", "content": "TenderTrace 机会协同升级"},
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**{len(escalations)} 条机会需要管理介入**\n"
                        f"决策超时 {decision_count} 条 · "
                        f"任务逾期 {task_count} 条 · "
                        f"决策 SLA {action_queue.get('decision_sla_hours') or 0} 小时\n"
                        "请负责人补齐阻断项和逾期任务，管理者完成资源协调或 "
                        "Go/Hold/No-Go 决策。"
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
    normalized = [
        (
            _text(_mapping(item).get("notice_id")),
            _issue_types(_mapping(item)),
        )
        for item in escalations
        if _mapping(item)
    ]
    if normalized and all(issue_types == ("decision",) for _, issue_types in normalized):
        notice_ids = sorted(notice_id for notice_id, _ in normalized)
        digest = hashlib.sha256("\n".join(notice_ids).encode("utf-8")).hexdigest()[:16]
        return f"decision_sla:{reference.date().isoformat()}:{digest}"
    rows = sorted(
        f"{notice_id}:{','.join(issue_types)}"
        for notice_id, issue_types in normalized
    )
    digest = hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()[:16]
    return f"opportunity_escalation:{reference.date().isoformat()}:{digest}"


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


def _issue_types(item: dict[str, Any]) -> tuple[str, ...]:
    raw = item.get("issue_types")
    if isinstance(raw, list):
        present = {str(item).strip() for item in raw}
        values = tuple(value for value in ("decision", "task") if value in present)
        if values:
            return values
    issue_type = str(item.get("issue_type") or "decision")
    present = set(issue_type.split("_"))
    values = tuple(value for value in ("decision", "task") if value in present)
    return values or ("decision",)


def _issue_counts(escalations: list[object]) -> tuple[int, int]:
    issue_sets = [_issue_types(_mapping(item)) for item in escalations if _mapping(item)]
    return (
        sum("decision" in values for values in issue_sets),
        sum("task" in values for values in issue_sets),
    )


def _issue_label(issue_types: tuple[str, ...]) -> str:
    if set(issue_types) == {"decision", "task"}:
        return "决策超时 + 任务逾期"
    if "task" in issue_types:
        return "任务逾期"
    return "决策超时"
