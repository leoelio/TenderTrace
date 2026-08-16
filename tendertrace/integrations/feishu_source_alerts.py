from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import hashlib
from typing import Any, Callable
from zoneinfo import ZoneInfo

from tendertrace.config import Settings
from tendertrace.db import connection
from tendertrace.delivery.ledger import record_delivery_attempt
from tendertrace.delivery.preferences import resolve_feishu_receiver
from tendertrace.integrations.feishu import FeishuClient, FeishuError
from tendertrace.integrations.feishu_source_incidents import upsert_source_incident
from tendertrace.source_map import build_source_map


@dataclass(frozen=True)
class SourceAlertDeliveryResult:
    status: str
    issue_count: int
    artifact_key: str
    message_id: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SourceIncidentTaskResult:
    status: str
    issue_count: int
    artifact_key: str
    task_guid: str = ""
    assigned: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_source_alert_snapshot(
    settings: Settings,
    *,
    source_map_loader: Callable[[Settings], dict[str, object]] = build_source_map,
    now: datetime | None = None,
) -> dict[str, object]:
    reference = now or datetime.now(ZoneInfo(settings.timezone))
    source_map = source_map_loader(settings)
    raw_items = source_map.get("items")
    items = raw_items if isinstance(raw_items, list) else []
    issues: list[dict[str, object]] = []
    for value in items:
        item = value if isinstance(value, dict) else {}
        issue = _source_issue(settings, item, reference)
        if issue:
            issues.append(issue)
    issues.sort(
        key=lambda item: (
            0 if item["severity"] == "critical" else 1,
            float(item.get("reliability_score") or 0),
            str(item["site"]),
        )
    )
    return {
        "status": "attention" if issues else "healthy",
        "checked_at": reference.isoformat(timespec="seconds"),
        "source_count": int(source_map.get("source_count") or len(items)),
        "issue_count": len(issues),
        "critical_count": sum(item["severity"] == "critical" for item in issues),
        "warning_count": sum(item["severity"] == "warning" for item in issues),
        "policy": {
            "minimum_reliability": settings.source_alert_min_reliability,
            "stale_hours": settings.source_alert_stale_hours,
            "automation_enabled": settings.source_alert_enabled,
            "cron": settings.source_alert_cron,
        },
        "issues": issues,
    }


def send_source_health_alert(
    settings: Settings,
    *,
    force: bool = False,
    receive_id: str = "",
    receive_id_type: str = "",
    client: FeishuClient | None = None,
    snapshot_loader: Callable[..., dict[str, object]] = build_source_alert_snapshot,
    now: datetime | None = None,
) -> SourceAlertDeliveryResult:
    reference = now or datetime.now(ZoneInfo(settings.timezone))
    snapshot = snapshot_loader(settings, now=reference)
    issues = snapshot.get("issues")
    issue_items = issues if isinstance(issues, list) else []
    if not issue_items:
        return SourceAlertDeliveryResult(
            status="skipped",
            issue_count=0,
            artifact_key="",
            reason="all observed sources satisfy the current SLO",
        )
    artifact_key = _artifact_key(issue_items, reference)
    if not force and _already_sent(settings, artifact_key):
        return SourceAlertDeliveryResult(
            status="skipped",
            issue_count=len(issue_items),
            artifact_key=artifact_key,
            reason="same source health state already sent today",
        )
    target_id, target_type = resolve_feishu_receiver(
        settings,
        receive_id=receive_id or None,
        receive_id_type=receive_id_type or None,
    )
    feishu = client or FeishuClient(settings)
    try:
        response = feishu.send_card(
            build_source_alert_card(snapshot, now=reference),
            receive_id=target_id,
            receive_id_type=target_type,
        )
        message_id = _nested_string(response, "data", "message_id")
        record_delivery_attempt(
            settings,
            channel="feishu",
            artifact_type="source_health_alert",
            artifact_key=artifact_key,
            status="sent",
            external_id=message_id or None,
        )
    except (FeishuError, ValueError) as exc:
        record_delivery_attempt(
            settings,
            channel="feishu",
            artifact_type="source_health_alert",
            artifact_key=artifact_key,
            status="failed",
            error=str(exc),
        )
        raise
    return SourceAlertDeliveryResult(
        status="sent",
        issue_count=len(issue_items),
        artifact_key=artifact_key,
        message_id=message_id,
    )


def create_source_incident_task(
    settings: Settings,
    *,
    force: bool = False,
    client: FeishuClient | None = None,
    snapshot_loader: Callable[..., dict[str, object]] = build_source_alert_snapshot,
    now: datetime | None = None,
) -> SourceIncidentTaskResult:
    reference = now or datetime.now(ZoneInfo(settings.timezone))
    snapshot = snapshot_loader(settings, now=reference)
    raw_issues = snapshot.get("issues")
    issues = [item for item in raw_issues or [] if isinstance(item, dict)]
    if not issues:
        return SourceIncidentTaskResult(
            status="skipped",
            issue_count=0,
            artifact_key="",
            reason="all observed sources satisfy the current SLO",
        )
    alert_key = _artifact_key(issues, reference)
    artifact_key = alert_key.replace("source_health:", "source_health_task:", 1)
    due_at = reference + timedelta(hours=settings.source_incident_sla_hours)
    existing_task = _sent_external_id(settings, "source_health_task", artifact_key)
    if existing_task and not force:
        assigned = _default_receiver_is_member(settings)
        upsert_source_incident(
            settings,
            snapshot=snapshot,
            artifact_key=artifact_key,
            task_guid=existing_task,
            assigned=assigned,
            due_at=due_at,
        )
        return SourceIncidentTaskResult(
            status="skipped",
            issue_count=len(issues),
            artifact_key=artifact_key,
            task_guid=existing_task,
            assigned=assigned,
            reason="same source incident task already created today",
        )
    target_id, target_type = resolve_feishu_receiver(settings)
    assignee_open_id = str(target_id or "") if target_type == "open_id" else ""
    feishu = client or FeishuClient(settings)
    try:
        response = feishu.create_task(
            summary=_task_summary(issues),
            description=_task_description(snapshot, issues),
            client_token=hashlib.sha256(artifact_key.encode("utf-8")).hexdigest(),
            due_timestamp_ms=str(int(due_at.timestamp() * 1000)),
            assignee_open_id=assignee_open_id,
            reminder_minutes=min(60, settings.source_incident_sla_hours * 60),
        )
        task_guid = _nested_string(response, "data", "task", "guid")
        if not task_guid:
            raise FeishuError("Feishu source incident task response is missing task guid")
        record_delivery_attempt(
            settings,
            channel="feishu",
            artifact_type="source_health_task",
            artifact_key=artifact_key,
            status="sent",
            external_id=task_guid,
        )
        upsert_source_incident(
            settings,
            snapshot=snapshot,
            artifact_key=artifact_key,
            task_guid=task_guid,
            assigned=bool(assignee_open_id),
            due_at=due_at,
        )
    except (FeishuError, ValueError) as exc:
        record_delivery_attempt(
            settings,
            channel="feishu",
            artifact_type="source_health_task",
            artifact_key=artifact_key,
            status="failed",
            error=str(exc),
        )
        raise
    return SourceIncidentTaskResult(
        status="sent",
        issue_count=len(issues),
        artifact_key=artifact_key,
        task_guid=task_guid,
        assigned=bool(assignee_open_id),
    )


def build_source_alert_card(
    snapshot: dict[str, object],
    *,
    now: datetime,
) -> dict[str, object]:
    raw_issues = snapshot.get("issues")
    issues = [item for item in raw_issues or [] if isinstance(item, dict)]
    elements: list[dict[str, object]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**监测来源 {snapshot.get('source_count') or 0} 个 · "
                    f"异常 {len(issues)} 个**\n"
                    f"严重 {snapshot.get('critical_count') or 0} 个 · "
                    f"关注 {snapshot.get('warning_count') or 0} 个"
                ),
            },
        },
        {"tag": "hr"},
    ]
    for issue in issues[:8]:
        severity = "严重" if issue.get("severity") == "critical" else "关注"
        reasons = issue.get("reasons")
        reason_text = "；".join(str(value) for value in reasons or [])
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**[{severity}] {issue.get('site') or '-'}**\n"
                        f"{reason_text}\n"
                        f"可靠度 {float(issue.get('reliability_score') or 0):.1%} · "
                        f"最近成功 {issue.get('last_success_at') or '暂无证据'}"
                    ),
                },
            }
        )
        route_url = str(issue.get("route_url") or "")
        if route_url:
            elements.append(
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "检查来源"},
                            "type": "default",
                            "url": route_url,
                        }
                    ],
                }
            )
        elements.append({"tag": "hr"})
    elements.append(
        {
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": "基于真实运行、请求成功率、命中率、登录态和最近成功时间计算。",
                }
            ],
        }
    )
    return {
        "config": {"wide_screen_mode": True, "update_multi": True},
        "header": {
            "template": "red" if snapshot.get("critical_count") else "orange",
            "title": {
                "tag": "plain_text",
                "content": f"TenderTrace 来源健康告警 · {now:%m月%d日 %H:%M}",
            },
        },
        "elements": elements,
    }


def _source_issue(
    settings: Settings,
    item: dict[str, Any],
    reference: datetime,
) -> dict[str, object] | None:
    site = str(item.get("site") or "").strip()
    if not site:
        return None
    health = item.get("health") if isinstance(item.get("health"), dict) else {}
    runs = int(health.get("runs") or 0)
    reliability = float(health.get("reliability_score") or 0)
    health_status = str(health.get("health_status") or "unknown")
    reasons: list[str] = []
    severity = "warning"
    if item.get("status") == "login_expired":
        reasons.append("登录态已过期，需要重新保存登录状态")
        severity = "critical"
    if runs and reliability < settings.source_alert_min_reliability:
        reasons.append(
            f"可靠度 {reliability:.1%} 低于阈值 "
            f"{settings.source_alert_min_reliability:.1%}"
        )
        if health_status == "unhealthy":
            severity = "critical"
    last_success = str(health.get("last_success_at") or "")
    success_at = _parse_datetime(last_success, reference.tzinfo)
    if runs and success_at:
        age_hours = max(0, int((reference - success_at).total_seconds() // 3600))
        if age_hours > settings.source_alert_stale_hours:
            reasons.append(
                f"最近成功已过去 {age_hours} 小时，超过 {settings.source_alert_stale_hours} 小时 SLO"
            )
    if not reasons:
        return None
    routes = item.get("routes") if isinstance(item.get("routes"), list) else []
    first_route = routes[0] if routes and isinstance(routes[0], dict) else {}
    return {
        "site": site,
        "severity": severity,
        "reasons": reasons,
        "reliability_score": reliability,
        "health_status": health_status,
        "last_success_at": last_success,
        "last_error": str(health.get("last_error") or ""),
        "route_url": str(first_route.get("url") or ""),
    }


def _artifact_key(issues: list[object], reference: datetime) -> str:
    state = [
        {
            "site": item.get("site"),
            "severity": item.get("severity"),
            "reasons": item.get("reasons"),
        }
        for item in issues
        if isinstance(item, dict)
    ]
    digest = hashlib.sha256(repr(state).encode("utf-8")).hexdigest()[:16]
    return f"source_health:{reference.date().isoformat()}:{digest}"


def _task_summary(issues: list[dict[str, object]]) -> str:
    sites = "、".join(str(item.get("site") or "-") for item in issues[:3])
    suffix = f" 等 {len(issues)} 个" if len(issues) > 3 else ""
    return f"处理 TenderTrace 来源异常：{sites}{suffix}"


def _task_description(
    snapshot: dict[str, object],
    issues: list[dict[str, object]],
) -> str:
    lines = [
        f"检查时间：{snapshot.get('checked_at') or '-'}",
        f"异常来源：{len(issues)} 个",
        "",
    ]
    for issue in issues[:8]:
        reasons = "；".join(str(value) for value in issue.get("reasons") or [])
        lines.append(f"[{issue.get('severity') or 'warning'}] {issue.get('site') or '-'}")
        lines.append(reasons or "需要检查来源运行状态")
        if issue.get("route_url"):
            lines.append(str(issue["route_url"]))
        lines.append("")
    lines.append("完成后请在 TenderTrace 数据源页刷新验证来源 SLO。")
    return "\n".join(lines).strip()


def _already_sent(settings: Settings, artifact_key: str) -> bool:
    with connection(settings) as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM delivery_attempts
            WHERE channel = 'feishu'
              AND artifact_type = 'source_health_alert'
              AND artifact_key = ?
              AND status = 'sent'
            LIMIT 1
            """,
            (artifact_key,),
        ).fetchone()
    return row is not None


def _sent_external_id(
    settings: Settings,
    artifact_type: str,
    artifact_key: str,
) -> str:
    with connection(settings) as conn:
        row = conn.execute(
            """
            SELECT external_id
            FROM delivery_attempts
            WHERE channel = 'feishu'
              AND artifact_type = ?
              AND artifact_key = ?
              AND status = 'sent'
              AND COALESCE(external_id, '') <> ''
            LIMIT 1
            """,
            (artifact_type, artifact_key),
        ).fetchone()
    return str(row["external_id"] or "") if row is not None else ""


def _default_receiver_is_member(settings: Settings) -> bool:
    _, receive_id_type = resolve_feishu_receiver(settings)
    return receive_id_type == "open_id"


def _parse_datetime(value: str, tzinfo) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tzinfo)
    return parsed.astimezone(tzinfo)


def _nested_string(payload: dict[str, Any], *keys: str) -> str:
    value: object = payload
    for key in keys:
        if not isinstance(value, dict):
            return ""
        value = value.get(key)
    return str(value or "")
