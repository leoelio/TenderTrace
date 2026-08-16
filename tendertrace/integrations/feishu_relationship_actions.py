from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
from typing import Any, Callable

from tendertrace.config import Settings
from tendertrace.delivery.feishu_bitable import (
    update_opportunity_relationship_actions_in_bitable,
)
from tendertrace.integrations.feishu import FeishuClient, FeishuError
from tendertrace.opportunity import get_opportunity
from tendertrace.opportunity_relationship_actions import (
    OpportunityRelationshipAction,
    mark_relationship_action_task,
    pending_relationship_action_tasks,
    relationship_action,
    relationship_action_snapshots,
)


@dataclass(frozen=True)
class RelationshipActionTaskResult:
    status: str
    action: OpportunityRelationshipAction
    task_guid: str
    assigned: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "action": self.action.to_dict(),
            "task_guid": self.task_guid,
            "assigned": self.assigned,
        }


@dataclass(frozen=True)
class RelationshipActionSyncResult:
    status: str
    scanned_count: int
    updated_count: int
    completed_count: int
    overdue_count: int
    outcome_pending_count: int
    bitable_updated_count: int
    failed_count: int
    failures: tuple[dict[str, str], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def create_relationship_action_task(
    settings: Settings,
    action_id: str,
    *,
    client: FeishuClient | None = None,
) -> RelationshipActionTaskResult:
    current = relationship_action(settings, action_id)
    if current.status != "open":
        raise ValueError("only open relationship actions can create Feishu tasks")
    if current.feishu_task_guid:
        return RelationshipActionTaskResult(
            status="reused",
            action=current,
            task_guid=current.feishu_task_guid,
            assigned=bool(current.assignee_open_id),
        )
    opportunity = get_opportunity(settings, current.notice_id)
    if opportunity is None:
        raise LookupError("opportunity not found for relationship action")
    due_at = _parse_due_at(current.due_at, settings.timezone)
    feishu = client or FeishuClient(settings)
    try:
        response = feishu.create_task(
            summary=f"客户关系行动：{current.title}"[:3000],
            description=_task_description(current, opportunity),
            client_token=_client_token(current.id),
            due_timestamp_ms=str(int(due_at.timestamp() * 1000)),
            assignee_open_id=current.assignee_open_id,
        )
        task_guid = _nested_string(response, "data", "task", "guid")
        if not task_guid:
            raise ValueError("Feishu relationship action task guid is missing")
    except (FeishuError, ValueError, TypeError) as exc:
        mark_relationship_action_task(
            settings,
            action_id=current.id,
            sync_error=f"{type(exc).__name__}: {exc}"[:1000],
            synced_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        raise
    updated = mark_relationship_action_task(
        settings,
        action_id=current.id,
        task_guid=task_guid,
        task_status="open",
        synced_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        sync_error="",
    )
    return RelationshipActionTaskResult(
        status="created",
        action=updated,
        task_guid=task_guid,
        assigned=bool(updated.assignee_open_id),
    )


def sync_relationship_action_tasks(
    settings: Settings,
    *,
    limit: int = 200,
    client: FeishuClient | None = None,
    bitable_updater: Callable[..., object] = update_opportunity_relationship_actions_in_bitable,
    now: datetime | None = None,
) -> RelationshipActionSyncResult:
    actions = pending_relationship_action_tasks(settings, limit=limit)
    if not actions:
        return RelationshipActionSyncResult(
            status="skipped",
            scanned_count=0,
            updated_count=0,
            completed_count=0,
            overdue_count=0,
            outcome_pending_count=0,
            bitable_updated_count=0,
            failed_count=0,
        )
    feishu = client or FeishuClient(settings)
    reference_time = _as_utc(now or datetime.now(timezone.utc), settings.timezone)
    updated_count = completed_count = overdue_count = outcome_pending_count = 0
    bitable_updated_count = 0
    failures: list[dict[str, str]] = []
    changed_notices: set[str] = set()
    for current in actions:
        try:
            payload = feishu.get_task(current.feishu_task_guid)
            task = _task(payload)
            status, completed_at = _task_status(task, reference_time)
            updated = mark_relationship_action_task(
                settings,
                action_id=current.id,
                task_status=status,
                synced_at=reference_time.isoformat(timespec="seconds"),
                sync_error="",
                completed_at=completed_at or None,
            )
            changed_notices.add(current.notice_id)
            updated_count += int(current.feishu_task_status != status)
            completed_count += int(status == "completed")
            overdue_count += int(status == "overdue")
            outcome_pending_count += int(status == "completed" and not updated.outcome_note)
        except (FeishuError, ValueError, TypeError) as exc:
            mark_relationship_action_task(
                settings,
                action_id=current.id,
                synced_at=reference_time.isoformat(timespec="seconds"),
                sync_error=f"{type(exc).__name__}: {exc}"[:1000],
            )
            failures.append(
                {
                    "notice_id": current.notice_id,
                    "action_id": current.id,
                    "stage": "task_read",
                    "error": f"{type(exc).__name__}: {exc}"[:500],
                }
            )
    summaries = relationship_action_snapshots(settings, list(changed_notices), now=reference_time)
    for notice_id, action_plan in summaries.items():
        try:
            result = bitable_updater(
                settings,
                notice_id=notice_id,
                action_plan=action_plan,
            )
            bitable_updated_count += int(getattr(result, "status", "") == "sent")
            if getattr(result, "status", "") == "failed":
                failures.append(
                    {
                        "notice_id": notice_id,
                        "action_id": "",
                        "stage": "bitable_write",
                        "error": str(getattr(result, "message", "write failed"))[:500],
                    }
                )
        except Exception as exc:
            failures.append(
                {
                    "notice_id": notice_id,
                    "action_id": "",
                    "stage": "bitable_write",
                    "error": f"{type(exc).__name__}: {exc}"[:500],
                }
            )
    return RelationshipActionSyncResult(
        status="partial" if failures else "finished",
        scanned_count=len(actions),
        updated_count=updated_count,
        completed_count=completed_count,
        overdue_count=overdue_count,
        outcome_pending_count=outcome_pending_count,
        bitable_updated_count=bitable_updated_count,
        failed_count=len(failures),
        failures=tuple(failures),
    )


def _task_description(
    action: OpportunityRelationshipAction,
    opportunity: dict[str, object],
) -> str:
    return "\n".join(
        value
        for value in (
            f"机会：{opportunity.get('title') or '未命名机会'}",
            f"关键人：{action.stakeholder_name}" if action.stakeholder_name else "",
            f"行动类型：{action.action_type_label}",
            f"优先级：{action.priority_label}",
            f"公告链接：{opportunity.get('source_url') or ''}",
        )
        if value
    )


def _client_token(action_id: str) -> str:
    return hashlib.sha256(
        f"tendertrace:relationship-action:{action_id}".encode("utf-8")
    ).hexdigest()


def _parse_due_at(value: str, timezone_name: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        from zoneinfo import ZoneInfo

        parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
    return parsed


def _task(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    task = data.get("task") if isinstance(data, dict) else None
    if not isinstance(task, dict):
        raise ValueError("Feishu task is missing in response")
    return task


def _task_status(task: dict[str, Any], now: datetime) -> tuple[str, str]:
    completed = _timestamp_ms(task.get("completed_at"))
    if completed is not None:
        return "completed", completed.isoformat(timespec="seconds")
    due = task.get("due")
    due_at = _timestamp_ms(due.get("timestamp")) if isinstance(due, dict) else None
    return ("overdue", "") if due_at is not None and due_at < now else ("open", "")


def _timestamp_ms(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text or text == "0":
        return None
    try:
        return datetime.fromtimestamp(int(text) / 1000, tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def _as_utc(value: datetime, timezone_name: str) -> datetime:
    if value.tzinfo is None:
        from zoneinfo import ZoneInfo

        value = value.replace(tzinfo=ZoneInfo(timezone_name))
    return value.astimezone(timezone.utc)


def _nested_string(payload: dict[str, Any], *keys: str) -> str:
    value: object = payload
    for key in keys:
        if not isinstance(value, dict):
            return ""
        value = value.get(key)
    return str(value or "")
