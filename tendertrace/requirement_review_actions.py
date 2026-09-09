from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from typing import Any
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection, init_db


ACTION_STATUS_LABELS = {
    "open": "待处理",
    "completed": "已完成",
    "cancelled": "已取消",
}


@dataclass(frozen=True)
class RequirementReviewAction:
    id: str
    opinion_id: str
    notice_id: str
    requirement_id: str
    requirement_key: str
    requirement_title: str
    opinion_content: str
    opinion_actor: str
    opinion_channel: str
    assignee_member_id: str
    assignee_name: str
    due_at: str
    action_note: str
    status: str
    status_label: str
    completed_by: str
    completion_note: str
    completed_at: str
    created_by: str
    created_at: str
    updated_at: str
    feishu_task_guid: str
    feishu_task_status: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def create_review_action(
    settings: Settings,
    *,
    notice_id: str,
    opinion_id: str,
    assignee_member_id: str,
    due_at: str,
    action_note: str,
    actor: str,
) -> RequirementReviewAction:
    init_db(settings)
    values = {
        "notice_id": notice_id.strip(),
        "opinion_id": opinion_id.strip(),
        "assignee_member_id": assignee_member_id.strip(),
        "due_at": due_at.strip(),
        "action_note": " ".join(action_note.split())[:1000],
        "actor": " ".join(actor.split())[:120],
    }
    if not values["notice_id"] or not values["opinion_id"]:
        raise ValueError("notice_id and opinion_id are required")
    if not values["action_note"] or not values["actor"]:
        raise ValueError("action_note and actor are required")
    _validate_due_at(values["due_at"])
    with connection(settings) as conn:
        opinion = conn.execute(
            """
            SELECT opinion.id, opinion.requirement_id, requirement.requirement_key
            FROM requirement_review_human_opinions opinion
            JOIN opportunity_requirements requirement ON requirement.id = opinion.requirement_id
            WHERE opinion.id = ? AND opinion.notice_id = ?
            """,
            (values["opinion_id"], values["notice_id"]),
        ).fetchone()
        if opinion is None:
            raise LookupError("review opinion not found")
        if values["assignee_member_id"]:
            member = conn.execute(
                """
                SELECT 1 FROM opportunity_team_members
                WHERE id = ? AND notice_id = ? AND status = 'active'
                """,
                (values["assignee_member_id"], values["notice_id"]),
            ).fetchone()
            if member is None:
                raise ValueError("assignee_member_id must be an active opportunity member")
        action_id = _action_id(values["opinion_id"])
        inserted = conn.execute(
            """
            INSERT OR IGNORE INTO requirement_review_actions(
                id, opinion_id, notice_id, requirement_id, assignee_member_id,
                due_at, action_note, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action_id,
                values["opinion_id"],
                values["notice_id"],
                str(opinion["requirement_id"]),
                values["assignee_member_id"] or None,
                values["due_at"] or None,
                values["action_note"],
                values["actor"],
            ),
        ).rowcount
        if inserted:
            _record_event(
                conn,
                notice_id=values["notice_id"],
                action="requirement_review_action_created",
                actor=values["actor"],
                payload={
                    "action_id": action_id,
                    "opinion_id": values["opinion_id"],
                    "requirement_id": str(opinion["requirement_id"]),
                    "requirement_key": str(opinion["requirement_key"]),
                    "assignee_member_id": values["assignee_member_id"],
                    "due_at": values["due_at"],
                },
            )
    return _find_action(settings, values["notice_id"], action_id)


def complete_review_action(
    settings: Settings,
    *,
    notice_id: str,
    action_id: str,
    actor: str,
    completion_note: str,
) -> RequirementReviewAction:
    normalized_actor = " ".join(actor.split())[:120]
    normalized_note = " ".join(completion_note.split())[:1000]
    if not normalized_actor or not normalized_note:
        raise ValueError("completion actor and note are required")
    with connection(settings) as conn:
        action = conn.execute(
            "SELECT * FROM requirement_review_actions WHERE id = ? AND notice_id = ?",
            (action_id, notice_id.strip()),
        ).fetchone()
        if action is None:
            raise LookupError("review action not found")
        if str(action["status"]) != "open":
            raise ValueError("review action is no longer open")
        conn.execute(
            """
            UPDATE requirement_review_actions
            SET status = 'completed', completed_by = ?, completion_note = ?,
                completed_at = datetime('now'), updated_at = datetime('now')
            WHERE id = ?
            """,
            (normalized_actor, normalized_note, action_id),
        )
        _record_event(
            conn,
            notice_id=notice_id.strip(),
            action="requirement_review_action_completed",
            actor=normalized_actor,
            payload={"action_id": action_id, "completion_note": normalized_note},
        )
    return _find_action(settings, notice_id.strip(), action_id)


def list_review_actions(settings: Settings, notice_id: str) -> list[RequirementReviewAction]:
    init_db(settings)
    with connection(settings) as conn:
        rows = conn.execute(
            _SELECT_ACTIONS + " WHERE action.notice_id = ? ORDER BY action.status, action.created_at DESC, action.rowid DESC",
            (notice_id.strip(),),
        ).fetchall()
    return [_from_row(row) for row in rows]


def review_action(settings: Settings, notice_id: str, action_id: str) -> RequirementReviewAction:
    init_db(settings)
    return _find_action(settings, notice_id.strip(), action_id.strip())


def bind_review_action_to_requirement(
    settings: Settings,
    *,
    notice_id: str,
    action_id: str,
) -> RequirementReviewAction:
    """Bind an explicitly confirmed action to the existing requirement task channel."""
    action = review_action(settings, notice_id, action_id)
    if action.status != "open":
        raise ValueError("only open review actions can be synced")
    if not action.assignee_member_id or not action.due_at:
        raise ValueError("assign an owner and due date before syncing to Feishu")
    with connection(settings) as conn:
        conn.execute(
            """
            UPDATE opportunity_requirements
            SET assignee_member_id = ?, due_at = ?,
                status = CASE WHEN status IN ('pending', 'review') THEN 'assigned' ELSE status END,
                updated_at = datetime('now')
            WHERE id = ? AND notice_id = ?
            """,
            (action.assignee_member_id, action.due_at, action.requirement_id, notice_id),
        )
        _record_event(
            conn,
            notice_id=notice_id,
            action="requirement_review_action_bound_to_requirement_task",
            actor="system:review_action",
            payload={"action_id": action.id, "requirement_id": action.requirement_id},
        )
    return review_action(settings, notice_id, action_id)


def review_action_summary(settings: Settings, notice_id: str) -> dict[str, int]:
    actions = list_review_actions(settings, notice_id)
    return {
        "total_count": len(actions),
        "open_count": sum(item.status == "open" for item in actions),
        "completed_count": sum(item.status == "completed" for item in actions),
        "unassigned_count": sum(item.status == "open" and not item.assignee_member_id for item in actions),
        "undated_count": sum(item.status == "open" and not item.due_at for item in actions),
    }


_SELECT_ACTIONS = """
    SELECT action.*, requirement.requirement_key, requirement.title AS requirement_title,
           requirement.feishu_task_guid, requirement.feishu_task_status,
           opinion.content AS opinion_content, opinion.actor AS opinion_actor,
           opinion.channel AS opinion_channel, member.member_name AS assignee_name
    FROM requirement_review_actions action
    JOIN opportunity_requirements requirement ON requirement.id = action.requirement_id
    JOIN requirement_review_human_opinions opinion ON opinion.id = action.opinion_id
    LEFT JOIN opportunity_team_members member ON member.id = action.assignee_member_id
"""


def _find_action(settings: Settings, notice_id: str, action_id: str) -> RequirementReviewAction:
    with connection(settings) as conn:
        row = conn.execute(
            _SELECT_ACTIONS + " WHERE action.notice_id = ? AND action.id = ?",
            (notice_id, action_id),
        ).fetchone()
    if row is None:
        raise RuntimeError("review action was not persisted")
    return _from_row(row)


def _from_row(row: Any) -> RequirementReviewAction:
    status = str(row["status"] or "open")
    return RequirementReviewAction(
        id=str(row["id"]),
        opinion_id=str(row["opinion_id"]),
        notice_id=str(row["notice_id"]),
        requirement_id=str(row["requirement_id"]),
        requirement_key=str(row["requirement_key"]),
        requirement_title=str(row["requirement_title"]),
        opinion_content=str(row["opinion_content"]),
        opinion_actor=str(row["opinion_actor"]),
        opinion_channel=str(row["opinion_channel"]),
        assignee_member_id=str(row["assignee_member_id"] or ""),
        assignee_name=str(row["assignee_name"] or ""),
        due_at=str(row["due_at"] or ""),
        action_note=str(row["action_note"] or ""),
        status=status,
        status_label=ACTION_STATUS_LABELS.get(status, status),
        completed_by=str(row["completed_by"] or ""),
        completion_note=str(row["completion_note"] or ""),
        completed_at=str(row["completed_at"] or ""),
        created_by=str(row["created_by"] or ""),
        created_at=str(row["created_at"] or ""),
        updated_at=str(row["updated_at"] or ""),
        feishu_task_guid=str(row["feishu_task_guid"] or ""),
        feishu_task_status=str(row["feishu_task_status"] or ""),
    )


def _validate_due_at(value: str) -> None:
    if not value:
        return
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("due_at must be an ISO date or datetime") from exc


def _action_id(opinion_id: str) -> str:
    return hashlib.sha256(opinion_id.encode()).hexdigest()[:24]


def _record_event(conn, *, notice_id: str, action: str, actor: str, payload: dict[str, object]) -> None:
    conn.execute(
        """
        INSERT INTO opportunity_events(id, notice_id, action, actor_open_id, payload_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (str(uuid4()), notice_id, action, actor, json.dumps(payload, ensure_ascii=False, sort_keys=True)),
    )
