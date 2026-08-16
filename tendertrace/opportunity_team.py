from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.workflow import OpportunityWorkflow


ROLE_LABELS = {
    "solution": "方案技术",
    "commercial": "商务报价",
    "delivery": "交付实施",
    "legal": "法务合规",
    "partner_lead": "伙伴负责人",
}

STAGE_REQUIRED_ROLES = {
    "identified": (),
    "qualifying": ("solution",),
    "pursuing": ("solution", "commercial"),
    "bidding": ("solution", "commercial", "delivery"),
    "won": ("delivery",),
    "lost": (),
    "archived": (),
}


@dataclass(frozen=True)
class OpportunityTeamMember:
    id: str
    notice_id: str
    member_open_id: str
    member_name: str
    role: str
    role_label: str
    organization_type: str
    organization_name: str
    responsibility: str
    status: str
    feishu_task_guid: str
    feishu_task_role: str
    feishu_sync_status: str
    feishu_sync_error: str
    feishu_synced_at: str
    added_by: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def upsert_team_member(
    settings: Settings,
    *,
    notice_id: str,
    member_name: str,
    role: str,
    member_open_id: str = "",
    organization_type: str = "internal",
    organization_name: str = "",
    responsibility: str = "",
    actor: str = "admin",
) -> OpportunityTeamMember:
    init_db(settings)
    notice_id = notice_id.strip()
    member_name = member_name.strip()
    member_open_id = member_open_id.strip()
    role = role.strip()
    organization_type = organization_type.strip()
    organization_name = organization_name.strip()
    responsibility = responsibility.strip()
    if not notice_id or not member_name:
        raise ValueError("notice_id and member_name are required")
    if role not in ROLE_LABELS:
        raise ValueError(f"unsupported opportunity team role: {role}")
    if organization_type not in {"internal", "partner"}:
        raise ValueError("organization_type must be internal or partner")
    if organization_type == "partner" and not organization_name:
        raise ValueError("partner organization_name is required")
    member_key = _member_key(member_open_id, member_name, organization_name)
    member_id = _member_id(notice_id, member_key, role)
    with connection(settings) as conn:
        notice = conn.execute("SELECT 1 FROM notices WHERE id = ?", (notice_id,)).fetchone()
        if notice is None:
            raise LookupError("opportunity notice not found")
        conn.execute(
            """
            INSERT INTO opportunity_team_members(
                id, notice_id, member_key, member_open_id, member_name, role,
                organization_type, organization_name, responsibility, status,
                feishu_sync_status, feishu_sync_error, added_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 'pending', '', ?)
            ON CONFLICT(notice_id, member_key, role) DO UPDATE SET
                member_open_id = excluded.member_open_id,
                member_name = excluded.member_name,
                organization_type = excluded.organization_type,
                organization_name = excluded.organization_name,
                responsibility = excluded.responsibility,
                status = 'active',
                feishu_sync_status = CASE
                    WHEN opportunity_team_members.member_open_id = excluded.member_open_id
                         AND opportunity_team_members.status = 'active'
                    THEN opportunity_team_members.feishu_sync_status
                    ELSE 'pending'
                END,
                feishu_sync_error = '',
                added_by = excluded.added_by,
                updated_at = datetime('now')
            """,
            (
                member_id,
                notice_id,
                member_key,
                member_open_id,
                member_name,
                role,
                organization_type,
                organization_name,
                responsibility,
                actor.strip() or "admin",
            ),
        )
        _record_team_event(
            conn,
            notice_id=notice_id,
            action="team_member_upserted",
            actor=actor,
            payload={
                "member_id": member_id,
                "role": role,
                "organization_type": organization_type,
            },
        )
        row = conn.execute(
            "SELECT * FROM opportunity_team_members WHERE id = ?",
            (member_id,),
        ).fetchone()
    assert row is not None
    return _from_row(row)


def remove_team_member(
    settings: Settings,
    *,
    notice_id: str,
    member_id: str,
    actor: str = "admin",
) -> OpportunityTeamMember:
    init_db(settings)
    with connection(settings) as conn:
        row = conn.execute(
            """
            SELECT * FROM opportunity_team_members
            WHERE id = ? AND notice_id = ? AND status = 'active'
            """,
            (member_id, notice_id),
        ).fetchone()
        if row is None:
            raise LookupError("opportunity team member not found")
        conn.execute(
            """
            UPDATE opportunity_team_members
            SET status = 'removed', feishu_sync_status = 'pending',
                feishu_sync_error = '', updated_at = datetime('now')
            WHERE id = ?
            """,
            (member_id,),
        )
        _record_team_event(
            conn,
            notice_id=notice_id,
            action="team_member_removed",
            actor=actor,
            payload={"member_id": member_id, "role": str(row["role"] or "")},
        )
        updated = conn.execute(
            "SELECT * FROM opportunity_team_members WHERE id = ?",
            (member_id,),
        ).fetchone()
    assert updated is not None
    return _from_row(updated)


def team_snapshots(
    settings: Settings,
    workflows: dict[str, OpportunityWorkflow],
) -> dict[str, dict[str, object]]:
    notice_ids = list(workflows)
    if not notice_ids:
        return {}
    placeholders = ",".join("?" for _ in notice_ids)
    with connection(settings) as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM opportunity_team_members
            WHERE notice_id IN ({placeholders}) AND status = 'active'
            ORDER BY created_at, member_name
            """,
            notice_ids,
        ).fetchall()
    by_notice: dict[str, list[OpportunityTeamMember]] = {notice_id: [] for notice_id in notice_ids}
    for row in rows:
        member = _from_row(row)
        by_notice.setdefault(member.notice_id, []).append(member)
    return {
        notice_id: team_summary(workflows[notice_id], by_notice.get(notice_id, []))
        for notice_id in notice_ids
    }


def team_summary(
    workflow: OpportunityWorkflow,
    members: list[OpportunityTeamMember],
) -> dict[str, object]:
    required = ("owner", *STAGE_REQUIRED_ROLES.get(workflow.stage, ()))
    covered = {member.role for member in members}
    if workflow.owner_open_id or workflow.owner_name:
        covered.add("owner")
    missing = [role for role in required if role not in covered]
    coverage_score = round((len(required) - len(missing)) / len(required) * 100) if required else 100
    active_members = [member.to_dict() for member in members]
    partner_count = sum(
        1 for member in members if member.organization_type == "partner"
    )
    return {
        "member_count": len(active_members),
        "internal_count": len(active_members) - partner_count,
        "partner_count": partner_count,
        "coverage_score": coverage_score,
        "status": "ready" if not missing else "incomplete",
        "status_label": "团队就绪" if not missing else "角色待补",
        "required_roles": [_role_label(role) for role in required],
        "missing_roles": [_role_label(role) for role in missing],
        "members": active_members,
        "owner": {
            "name": workflow.owner_name,
            "bound_to_feishu": bool(workflow.owner_open_id),
        },
    }


def mark_team_sync(
    settings: Settings,
    *,
    member_ids: list[str],
    status: str,
    task_guid: str,
    error: str = "",
) -> None:
    if not member_ids:
        return
    placeholders = ",".join("?" for _ in member_ids)
    synced_at = (
        datetime.now(timezone.utc).isoformat(timespec="seconds") if status == "synced" else ""
    )
    with connection(settings) as conn:
        conn.execute(
            f"""
            UPDATE opportunity_team_members
            SET feishu_task_guid = ?, feishu_sync_status = ?, feishu_sync_error = ?,
                feishu_synced_at = ?, updated_at = datetime('now')
            WHERE id IN ({placeholders})
            """,
            (task_guid, status, error[:1000], synced_at, *member_ids),
        )


def pending_task_members(
    settings: Settings,
    notice_id: str,
    *,
    removed: bool = False,
) -> list[OpportunityTeamMember]:
    status = "removed" if removed else "active"
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT * FROM opportunity_team_members
            WHERE notice_id = ? AND status = ? AND member_open_id != ''
              AND feishu_sync_status != 'synced'
            ORDER BY created_at
            """,
            (notice_id, status),
        ).fetchall()
    return [_from_row(row) for row in rows]


def _from_row(row: Any) -> OpportunityTeamMember:
    role = str(row["role"] or "")
    return OpportunityTeamMember(
        id=str(row["id"]),
        notice_id=str(row["notice_id"]),
        member_open_id=str(row["member_open_id"] or ""),
        member_name=str(row["member_name"] or ""),
        role=role,
        role_label=ROLE_LABELS.get(role, role),
        organization_type=str(row["organization_type"] or "internal"),
        organization_name=str(row["organization_name"] or ""),
        responsibility=str(row["responsibility"] or ""),
        status=str(row["status"] or "active"),
        feishu_task_guid=str(row["feishu_task_guid"] or ""),
        feishu_task_role=str(row["feishu_task_role"] or "follower"),
        feishu_sync_status=str(row["feishu_sync_status"] or "pending"),
        feishu_sync_error=str(row["feishu_sync_error"] or ""),
        feishu_synced_at=str(row["feishu_synced_at"] or ""),
        added_by=str(row["added_by"] or ""),
        created_at=str(row["created_at"] or ""),
        updated_at=str(row["updated_at"] or ""),
    )


def _member_key(open_id: str, name: str, organization: str) -> str:
    if open_id:
        return f"feishu:{open_id}"
    raw = f"{name.casefold()}|{organization.casefold()}"
    return "manual:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _member_id(notice_id: str, member_key: str, role: str) -> str:
    raw = f"{notice_id}|{member_key}|{role}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _role_label(role: str) -> str:
    return "机会负责人" if role == "owner" else ROLE_LABELS.get(role, role)


def _record_team_event(
    conn,
    *,
    notice_id: str,
    action: str,
    actor: str,
    payload: dict[str, object],
) -> None:
    conn.execute(
        """
        INSERT INTO opportunity_events(
            id, notice_id, action, actor_open_id, payload_json
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            str(uuid4()),
            notice_id,
            action,
            actor.strip() or "admin",
            json.dumps(payload, ensure_ascii=False),
        ),
    )
