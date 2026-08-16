from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from typing import Iterable
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection, json_dumps
from tendertrace.notice_changes import NoticeRevision


ACTIVE_STAGES = {"qualifying", "pursuing", "bidding"}
CRITICAL_FIELDS = {
    "attachment_fingerprints",
    "attachments",
    "bid_deadline",
    "budget",
    "project_no",
    "purchaser",
}
HIGH_FIELDS = {"content_text", "core_content", "region", "title"}
SEVERITY_RANK = {"normal": 1, "high": 2, "critical": 3}


@dataclass(frozen=True)
class NoticeChangeReview:
    revision_id: str
    notice_id: str
    severity: str
    status: str
    required_by: str
    previous_decision: str
    previous_decision_at: str
    acknowledged_by: str
    acknowledgment_note: str
    acknowledged_at: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def register_notice_change_review(
    conn: sqlite3.Connection,
    revision: NoticeRevision,
    *,
    review_sla_hours: int,
) -> NoticeChangeReview | None:
    severity = change_severity(revision.changed_fields)
    if not severity:
        return None
    workflow = conn.execute(
        "SELECT * FROM opportunity_workflows WHERE notice_id = ?",
        (revision.notice_id,),
    ).fetchone()
    if workflow is None or str(workflow["stage"] or "identified") not in ACTIVE_STAGES:
        return None
    existing = conn.execute(
        "SELECT * FROM notice_change_reviews WHERE revision_id = ?",
        (revision.id,),
    ).fetchone()
    if existing is not None:
        return _from_row(existing)

    now = datetime.now(timezone.utc)
    required_by = now + timedelta(hours=max(1, int(review_sla_hours)))
    previous_decision = str(workflow["decision"] or "pending")
    conn.execute(
        """
        INSERT INTO notice_change_reviews(
            revision_id, notice_id, severity, required_by,
            previous_decision, previous_decision_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            revision.id,
            revision.notice_id,
            severity,
            required_by.isoformat(timespec="seconds"),
            previous_decision,
            str(workflow["decision_at"] or ""),
        ),
    )
    conn.execute(
        """
        UPDATE opportunity_workflows
        SET next_action = '复核公告重大变更', qualification_status = 'pending',
            updated_by = 'system:notice_change', updated_at = datetime('now')
        WHERE notice_id = ?
        """,
        (revision.notice_id,),
    )
    if previous_decision != "pending":
        conn.execute(
            """
            UPDATE opportunity_workflows
            SET decision = 'pending',
                decision_reason = '公告发生重大变化，原决策已失效，等待重新复核',
                decision_by = '', decision_at = '',
                decision_requested_at = ?,
                updated_by = 'system:notice_change', updated_at = datetime('now')
            WHERE notice_id = ?
            """,
            (now.isoformat(timespec="seconds"), revision.notice_id),
        )
    conn.execute(
        """
        INSERT INTO opportunity_events(
            id, notice_id, action, from_stage, to_stage, actor_open_id, payload_json
        ) VALUES (?, ?, 'notice_change_review_required', ?, ?, 'system:notice_change', ?)
        """,
        (
            str(uuid4()),
            revision.notice_id,
            str(workflow["stage"]),
            str(workflow["stage"]),
            json_dumps(
                {
                    "revision_id": revision.id,
                    "severity": severity,
                    "changed_fields": list(revision.changed_fields),
                    "previous_decision": previous_decision,
                    "required_by": required_by.isoformat(timespec="seconds"),
                }
            ),
        ),
    )
    row = conn.execute(
        "SELECT * FROM notice_change_reviews WHERE revision_id = ?",
        (revision.id,),
    ).fetchone()
    return _from_row(row)


def acknowledge_notice_change_reviews(
    settings: Settings,
    notice_id: str,
    *,
    actor: str,
    note: str = "",
) -> dict[str, object]:
    actor = actor.strip()
    if not actor:
        raise ValueError("change review actor is required")
    acknowledged_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with connection(settings) as conn:
        pending = conn.execute(
            """
            SELECT revision_id FROM notice_change_reviews
            WHERE notice_id = ? AND status = 'pending'
            ORDER BY created_at
            """,
            (notice_id,),
        ).fetchall()
        if not pending:
            raise ValueError("no pending notice change review")
        revision_ids = [str(row["revision_id"]) for row in pending]
        conn.execute(
            """
            UPDATE notice_change_reviews
            SET status = 'acknowledged', acknowledged_by = ?,
                acknowledgment_note = ?, acknowledged_at = ?,
                updated_at = datetime('now')
            WHERE notice_id = ? AND status = 'pending'
            """,
            (actor, note.strip(), acknowledged_at, notice_id),
        )
        workflow = conn.execute(
            "SELECT stage FROM opportunity_workflows WHERE notice_id = ?",
            (notice_id,),
        ).fetchone()
        stage = str(workflow["stage"] or "identified") if workflow else "identified"
        if stage in {"pursuing", "bidding"}:
            conn.execute(
                """
                UPDATE opportunity_workflows
                SET decision_requested_at = ?, next_action = '重新完成投标决策',
                    updated_by = ?, updated_at = datetime('now')
                WHERE notice_id = ?
                """,
                (acknowledged_at, actor, notice_id),
            )
        else:
            conn.execute(
                """
                UPDATE opportunity_workflows
                SET next_action = '继续完成机会确认', updated_by = ?,
                    updated_at = datetime('now')
                WHERE notice_id = ?
                """,
                (actor, notice_id),
            )
        conn.execute(
            """
            INSERT INTO opportunity_events(
                id, notice_id, action, from_stage, to_stage, actor_open_id, payload_json
            ) VALUES (?, ?, 'acknowledge_notice_change', ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                notice_id,
                stage,
                stage,
                actor,
                json_dumps({"revision_ids": revision_ids, "note": note.strip()}),
            ),
        )
    summary = change_review_summaries(settings, [notice_id]).get(notice_id, {})
    return {"acknowledged_count": len(revision_ids), "summary": summary}


def change_review_summaries(
    settings: Settings,
    notice_ids: Iterable[str],
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
            SELECT review.*, revision.changed_fields_json
            FROM notice_change_reviews review
            JOIN notice_revisions revision ON revision.id = review.revision_id
            WHERE review.notice_id IN ({placeholders})
            ORDER BY review.created_at DESC, review.rowid DESC
            """,
            unique_ids,
        ).fetchall()
    reference = now or datetime.now(timezone.utc)
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault(str(row["notice_id"]), []).append(row)
    return {
        notice_id: _review_summary(group_rows, reference)
        for notice_id, group_rows in grouped.items()
    }


def pending_review_revision_ids(
    settings: Settings,
    revision_ids: Iterable[str],
) -> set[str]:
    values = list(dict.fromkeys(value for value in revision_ids if value))
    if not values:
        return set()
    placeholders = ",".join("?" for _ in values)
    with connection(settings) as conn:
        rows = conn.execute(
            f"""
            SELECT revision_id FROM notice_change_reviews
            WHERE revision_id IN ({placeholders}) AND status = 'pending'
            """,
            values,
        ).fetchall()
    return {str(row["revision_id"]) for row in rows}


def reviews_by_revision(
    settings: Settings,
    revision_ids: Iterable[str],
) -> dict[str, dict[str, object]]:
    values = list(dict.fromkeys(value for value in revision_ids if value))
    if not values:
        return {}
    placeholders = ",".join("?" for _ in values)
    with connection(settings) as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM notice_change_reviews
            WHERE revision_id IN ({placeholders})
            """,
            values,
        ).fetchall()
    return {
        str(row["revision_id"]): _from_row(row).to_dict()
        for row in rows
    }


def change_severity(changed_fields: Iterable[str]) -> str:
    values = set(changed_fields)
    if values & CRITICAL_FIELDS:
        return "critical"
    if values & HIGH_FIELDS:
        return "high"
    return ""


def _review_summary(rows: list[sqlite3.Row], now: datetime) -> dict[str, object]:
    pending = [row for row in rows if str(row["status"]) == "pending"]
    pending_fields = sorted(
        {
            field
            for row in pending
            for field in _string_list(row["changed_fields_json"])
        }
    )
    due_values = [
        value
        for value in (_timestamp(row["required_by"]) for row in pending)
        if value is not None
    ]
    due_at = min(due_values) if due_values else None
    severity = max(
        (str(row["severity"]) for row in pending),
        key=lambda value: SEVERITY_RANK.get(value, 0),
        default="",
    )
    latest = rows[0]
    return {
        "count": len(rows),
        "pending_count": len(pending),
        "status": "pending" if pending else "acknowledged",
        "severity": severity or str(latest["severity"] or ""),
        "changed_fields": pending_fields,
        "required_by": due_at.isoformat(timespec="seconds") if due_at else "",
        "overdue": bool(due_at and due_at < now),
        "latest_at": str(latest["created_at"] or ""),
        "acknowledged_by": str(latest["acknowledged_by"] or ""),
        "acknowledged_at": str(latest["acknowledged_at"] or ""),
    }


def _from_row(row: sqlite3.Row) -> NoticeChangeReview:
    return NoticeChangeReview(
        revision_id=str(row["revision_id"]),
        notice_id=str(row["notice_id"]),
        severity=str(row["severity"]),
        status=str(row["status"]),
        required_by=str(row["required_by"] or ""),
        previous_decision=str(row["previous_decision"] or "pending"),
        previous_decision_at=str(row["previous_decision_at"] or ""),
        acknowledged_by=str(row["acknowledged_by"] or ""),
        acknowledgment_note=str(row["acknowledgment_note"] or ""),
        acknowledged_at=str(row["acknowledged_at"] or ""),
        created_at=str(row["created_at"] or ""),
        updated_at=str(row["updated_at"] or ""),
    )


def _timestamp(value: object) -> datetime | None:
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _string_list(value: object) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, ValueError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []
