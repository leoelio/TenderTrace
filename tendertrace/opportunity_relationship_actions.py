from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from tendertrace.config import Settings
from tendertrace.db import connection, init_db


ACTION_TYPES = {
    "engagement": "客户沟通",
    "discovery": "信息验证",
    "validation": "决策确认",
    "mitigation": "风险化解",
    "internal_alignment": "内部协同",
}
PRIORITY_LABELS = {
    "low": "低",
    "normal": "普通",
    "high": "高",
    "critical": "紧急",
}
STATUSES = {"open", "completed", "cancelled"}
SOURCE_TYPES = {"manual", "stakeholder_strategy", "stage_gap", "organization_memory"}


@dataclass(frozen=True)
class OpportunityRelationshipAction:
    id: str
    notice_id: str
    stakeholder_id: str
    stakeholder_name: str
    action_key: str
    title: str
    action_type: str
    action_type_label: str
    priority: str
    priority_label: str
    assignee_member_id: str
    assignee_member_name: str
    assignee_open_id: str
    due_at: str
    status: str
    outcome_note: str
    source_type: str
    source_ref: str
    feishu_task_guid: str
    feishu_task_status: str
    feishu_task_synced_at: str
    feishu_sync_error: str
    completed_at: str
    created_by: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def create_relationship_action(
    settings: Settings,
    *,
    notice_id: str,
    title: str,
    due_at: str,
    stakeholder_id: str = "",
    action_type: str = "engagement",
    priority: str = "normal",
    assignee_member_id: str = "",
    source_type: str = "manual",
    source_ref: str = "",
    actor: str = "admin",
) -> OpportunityRelationshipAction:
    init_db(settings)
    values = {
        "notice_id": notice_id.strip(),
        "title": title.strip(),
        "due_at": _normalize_due_at(due_at, settings.timezone),
        "stakeholder_id": stakeholder_id.strip(),
        "action_type": action_type.strip(),
        "priority": priority.strip(),
        "assignee_member_id": assignee_member_id.strip(),
        "source_type": source_type.strip(),
        "source_ref": source_ref.strip(),
    }
    _validate_create(values)
    action_key = _action_key(values)
    action_id = hashlib.sha256(
        f"{values['notice_id']}|{action_key}".encode("utf-8")
    ).hexdigest()[:24]
    with connection(settings) as conn:
        if conn.execute(
            "SELECT 1 FROM notices WHERE id = ?", (values["notice_id"],)
        ).fetchone() is None:
            raise LookupError("opportunity notice not found")
        _validate_relations(conn, values)
        existing = conn.execute(
            "SELECT 1 FROM opportunity_relationship_actions WHERE id = ?",
            (action_id,),
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO opportunity_relationship_actions(
                    id, notice_id, stakeholder_id, action_key, title, action_type,
                    priority, assignee_member_id, due_at, status, source_type,
                    source_ref, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)
                """,
                (
                    action_id,
                    values["notice_id"],
                    values["stakeholder_id"] or None,
                    action_key,
                    values["title"],
                    values["action_type"],
                    values["priority"],
                    values["assignee_member_id"] or None,
                    values["due_at"],
                    values["source_type"],
                    values["source_ref"],
                    actor.strip() or "admin",
                ),
            )
            _record_event(
                conn,
                notice_id=values["notice_id"],
                action="relationship_action_created",
                actor=actor,
                payload={
                    "relationship_action_id": action_id,
                    "stakeholder_id": values["stakeholder_id"],
                    "priority": values["priority"],
                    "due_at": values["due_at"],
                },
            )
        row = _select_row(conn, action_id, notice_id=values["notice_id"])
    assert row is not None
    return _from_row(row)


def update_relationship_action(
    settings: Settings,
    *,
    notice_id: str,
    action_id: str,
    status: str,
    outcome_note: str = "",
    actor: str = "admin",
) -> OpportunityRelationshipAction:
    normalized_status = status.strip()
    normalized_note = outcome_note.strip()
    if normalized_status not in STATUSES:
        raise ValueError("relationship action status must be open, completed, or cancelled")
    if normalized_status == "completed" and not normalized_note:
        raise ValueError("outcome_note is required when completing a relationship action")
    with connection(settings) as conn:
        current = _select_row(conn, action_id, notice_id=notice_id, active_only=False)
        if current is None:
            raise LookupError("relationship action not found")
        completed_at = ""
        if normalized_status == "completed":
            completed_at = str(current["completed_at"] or "") or datetime.now(
                timezone.utc
            ).isoformat(timespec="seconds")
        conn.execute(
            """
            UPDATE opportunity_relationship_actions
            SET status = ?, outcome_note = ?, completed_at = ?, updated_at = datetime('now')
            WHERE id = ? AND notice_id = ?
            """,
            (
                normalized_status,
                normalized_note,
                completed_at or None,
                action_id,
                notice_id,
            ),
        )
        _record_event(
            conn,
            notice_id=notice_id,
            action=f"relationship_action_{normalized_status}",
            actor=actor,
            payload={
                "relationship_action_id": action_id,
                "from_status": str(current["status"] or "open"),
                "to_status": normalized_status,
                "outcome_recorded": bool(normalized_note),
            },
        )
        updated = _select_row(conn, action_id, notice_id=notice_id)
    assert updated is not None
    return _from_row(updated)


def mark_relationship_action_task(
    settings: Settings,
    *,
    action_id: str,
    task_guid: str | None = None,
    task_status: str | None = None,
    synced_at: str | None = None,
    sync_error: str | None = None,
    completed_at: str | None = None,
) -> OpportunityRelationshipAction:
    with connection(settings) as conn:
        row = _select_row(conn, action_id)
        if row is None:
            raise LookupError("relationship action not found")
        values = {
            "task_guid": str(row["feishu_task_guid"] or "")
            if task_guid is None
            else task_guid.strip(),
            "task_status": str(row["feishu_task_status"] or "not_created")
            if task_status is None
            else task_status.strip(),
            "synced_at": str(row["feishu_task_synced_at"] or "")
            if synced_at is None
            else synced_at.strip(),
            "sync_error": str(row["feishu_sync_error"] or "")
            if sync_error is None
            else sync_error.strip(),
            "completed_at": str(row["completed_at"] or "")
            if completed_at is None
            else completed_at.strip(),
        }
        local_status = "completed" if values["task_status"] == "completed" else str(row["status"])
        conn.execute(
            """
            UPDATE opportunity_relationship_actions
            SET feishu_task_guid = ?, feishu_task_status = ?,
                feishu_task_synced_at = ?, feishu_sync_error = ?,
                status = ?, completed_at = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                values["task_guid"] or None,
                values["task_status"],
                values["synced_at"] or None,
                values["sync_error"] or None,
                local_status,
                values["completed_at"] or None,
                action_id,
            ),
        )
        previous_task_status = str(row["feishu_task_status"] or "not_created")
        if previous_task_status != values["task_status"]:
            _record_event(
                conn,
                notice_id=str(row["notice_id"]),
                action="relationship_action_task_synced",
                actor="feishu",
                payload={
                    "relationship_action_id": action_id,
                    "from_status": previous_task_status,
                    "to_status": values["task_status"],
                },
            )
        updated = _select_row(conn, action_id)
    assert updated is not None
    return _from_row(updated)


def relationship_action_snapshots(
    settings: Settings,
    notice_ids: list[str],
    *,
    now: datetime | None = None,
) -> dict[str, dict[str, object]]:
    unique_ids = list(dict.fromkeys(value for value in notice_ids if value))
    if not unique_ids:
        return {}
    placeholders = ",".join("?" for _ in unique_ids)
    with connection(settings) as conn:
        rows = conn.execute(
            f"""
            SELECT a.*, s.stakeholder_name, t.member_name AS assignee_member_name,
                   t.member_open_id AS assignee_open_id
            FROM opportunity_relationship_actions a
            LEFT JOIN opportunity_stakeholders s ON s.id = a.stakeholder_id
            LEFT JOIN opportunity_team_members t ON t.id = a.assignee_member_id
            WHERE a.notice_id IN ({placeholders})
            ORDER BY CASE a.status WHEN 'open' THEN 1 ELSE 2 END,
                     a.due_at, CASE a.priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2 ELSE 3 END
            """,
            unique_ids,
        ).fetchall()
    by_notice: dict[str, list[OpportunityRelationshipAction]] = {
        notice_id: [] for notice_id in unique_ids
    }
    for row in rows:
        item = _from_row(row)
        by_notice.setdefault(item.notice_id, []).append(item)
    reference_time = _as_utc(now or datetime.now(timezone.utc), settings.timezone)
    return {
        notice_id: relationship_action_summary(
            by_notice.get(notice_id, []),
            now=reference_time,
            timezone_name=settings.timezone,
        )
        for notice_id in unique_ids
    }


def relationship_action_summary(
    actions: list[OpportunityRelationshipAction],
    *,
    now: datetime,
    timezone_name: str,
) -> dict[str, object]:
    items: list[dict[str, object]] = []
    open_count = completed_count = cancelled_count = overdue_count = unassigned_count = 0
    outcome_pending_count = 0
    for action in actions:
        payload = action.to_dict()
        due = _parse_datetime(action.due_at, timezone_name)
        overdue = action.status == "open" and due < now
        effective_status = "overdue" if overdue else action.status
        payload["effective_status"] = effective_status
        payload["overdue"] = overdue
        items.append(payload)
        open_count += int(action.status == "open")
        completed_count += int(action.status == "completed")
        cancelled_count += int(action.status == "cancelled")
        overdue_count += int(overdue)
        unassigned_count += int(action.status == "open" and not action.assignee_member_id)
        outcome_pending_count += int(action.status == "completed" and not action.outcome_note)
    completed_base = open_count + completed_count
    next_open = next((item for item in items if item["effective_status"] in {"open", "overdue"}), None)
    return {
        "total_count": len(actions),
        "open_count": open_count,
        "completed_count": completed_count,
        "cancelled_count": cancelled_count,
        "overdue_count": overdue_count,
        "unassigned_count": unassigned_count,
        "outcome_pending_count": outcome_pending_count,
        "completion_rate": round(completed_count / completed_base * 100) if completed_base else 0,
        "status": (
            "critical"
            if overdue_count
            else "warning"
            if unassigned_count or outcome_pending_count
            else "normal"
        ),
        "next_action": next_open or {},
        "items": items,
    }


def relationship_action(settings: Settings, action_id: str) -> OpportunityRelationshipAction:
    with connection(settings) as conn:
        row = _select_row(conn, action_id)
    if row is None:
        raise LookupError("relationship action not found")
    return _from_row(row)


def pending_relationship_action_tasks(
    settings: Settings,
    *,
    limit: int = 200,
) -> list[OpportunityRelationshipAction]:
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT a.*, s.stakeholder_name, t.member_name AS assignee_member_name,
                   t.member_open_id AS assignee_open_id
            FROM opportunity_relationship_actions a
            LEFT JOIN opportunity_stakeholders s ON s.id = a.stakeholder_id
            LEFT JOIN opportunity_team_members t ON t.id = a.assignee_member_id
            WHERE COALESCE(a.feishu_task_guid, '') <> '' AND a.status != 'cancelled'
            ORDER BY a.updated_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 500)),),
        ).fetchall()
    return [_from_row(row) for row in rows]


def _validate_create(values: dict[str, str]) -> None:
    for field in ("notice_id", "title", "due_at"):
        if not values[field]:
            raise ValueError(f"{field} is required")
    if values["action_type"] not in ACTION_TYPES:
        raise ValueError(f"unsupported relationship action type: {values['action_type']}")
    if values["priority"] not in PRIORITY_LABELS:
        raise ValueError(f"unsupported relationship action priority: {values['priority']}")
    if values["source_type"] not in SOURCE_TYPES:
        raise ValueError(f"unsupported relationship action source_type: {values['source_type']}")


def _validate_relations(conn, values: dict[str, str]) -> None:
    if values["stakeholder_id"] and conn.execute(
        """
        SELECT 1 FROM opportunity_stakeholders
        WHERE id = ? AND notice_id = ? AND status = 'active'
        """,
        (values["stakeholder_id"], values["notice_id"]),
    ).fetchone() is None:
        raise ValueError("stakeholder_id must reference an active opportunity stakeholder")
    if values["assignee_member_id"] and conn.execute(
        """
        SELECT 1 FROM opportunity_team_members
        WHERE id = ? AND notice_id = ? AND status = 'active'
        """,
        (values["assignee_member_id"], values["notice_id"]),
    ).fetchone() is None:
        raise ValueError("assignee_member_id must reference an active opportunity team member")


def _action_key(values: dict[str, str]) -> str:
    raw = "|".join(
        (
            values["stakeholder_id"],
            values["title"].casefold(),
            values["due_at"],
            values["source_type"],
            values["source_ref"],
        )
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _normalize_due_at(value: str, timezone_name: str) -> str:
    text = value.strip()
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("due_at must be an ISO date or datetime") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
    return parsed.isoformat(timespec="minutes")


def _parse_datetime(value: str, timezone_name: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return _as_utc(parsed, timezone_name)


def _as_utc(value: datetime, timezone_name: str) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo(timezone_name))
    return value.astimezone(timezone.utc)


def _select_row(
    conn,
    action_id: str,
    *,
    notice_id: str = "",
    active_only: bool = False,
):
    conditions = ["a.id = ?"]
    params = [action_id]
    if notice_id:
        conditions.append("a.notice_id = ?")
        params.append(notice_id)
    if active_only:
        conditions.append("a.status = 'open'")
    return conn.execute(
        f"""
        SELECT a.*, s.stakeholder_name, t.member_name AS assignee_member_name,
               t.member_open_id AS assignee_open_id
        FROM opportunity_relationship_actions a
        LEFT JOIN opportunity_stakeholders s ON s.id = a.stakeholder_id
        LEFT JOIN opportunity_team_members t ON t.id = a.assignee_member_id
        WHERE {' AND '.join(conditions)}
        """,
        params,
    ).fetchone()


def _from_row(row: Any) -> OpportunityRelationshipAction:
    action_type = str(row["action_type"] or "engagement")
    priority = str(row["priority"] or "normal")
    return OpportunityRelationshipAction(
        id=str(row["id"]),
        notice_id=str(row["notice_id"]),
        stakeholder_id=str(row["stakeholder_id"] or ""),
        stakeholder_name=str(row["stakeholder_name"] or ""),
        action_key=str(row["action_key"] or ""),
        title=str(row["title"] or ""),
        action_type=action_type,
        action_type_label=ACTION_TYPES.get(action_type, action_type),
        priority=priority,
        priority_label=PRIORITY_LABELS.get(priority, priority),
        assignee_member_id=str(row["assignee_member_id"] or ""),
        assignee_member_name=str(row["assignee_member_name"] or ""),
        assignee_open_id=str(row["assignee_open_id"] or ""),
        due_at=str(row["due_at"] or ""),
        status=str(row["status"] or "open"),
        outcome_note=str(row["outcome_note"] or ""),
        source_type=str(row["source_type"] or "manual"),
        source_ref=str(row["source_ref"] or ""),
        feishu_task_guid=str(row["feishu_task_guid"] or ""),
        feishu_task_status=str(row["feishu_task_status"] or "not_created"),
        feishu_task_synced_at=str(row["feishu_task_synced_at"] or ""),
        feishu_sync_error=str(row["feishu_sync_error"] or ""),
        completed_at=str(row["completed_at"] or ""),
        created_by=str(row["created_by"] or ""),
        created_at=str(row["created_at"] or ""),
        updated_at=str(row["updated_at"] or ""),
    )


def _record_event(
    conn,
    *,
    notice_id: str,
    action: str,
    actor: str,
    payload: dict[str, object],
) -> None:
    conn.execute(
        """
        INSERT INTO opportunity_events(id, notice_id, action, actor_open_id, payload_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            str(uuid4()),
            notice_id,
            action,
            actor.strip() or "admin",
            json.dumps(payload, ensure_ascii=False),
        ),
    )
