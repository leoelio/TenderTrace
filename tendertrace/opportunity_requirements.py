from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection, init_db


REQUIREMENT_TYPE_LABELS = {
    "qualification": "资格条件",
    "deadline": "截止时间",
    "scoring": "评分项",
    "disqualification": "废标条款",
    "attachment": "附件清单",
    "technical": "技术参数",
    "commercial": "商务条款",
}

REQUIREMENT_STATUS_LABELS = {
    "pending": "待确认",
    "confirmed": "已确认",
    "assigned": "待准备",
    "in_progress": "准备中",
    "review": "待复核",
    "completed": "已完成",
    "superseded": "已拆分/合并",
}


@dataclass(frozen=True)
class OpportunityRequirement:
    id: str
    notice_id: str
    requirement_key: str
    requirement_type: str
    requirement_type_label: str
    title: str
    evidence_text: str
    source_url: str
    source_locator: str
    mandatory: bool
    confidence: int
    weight: float
    status: str
    status_label: str
    assignee_member_id: str
    due_at: str
    note: str
    source_revision_id: str
    parent_requirement_id: str
    confirmed_at: str
    extraction_mode: str
    created_by: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def upsert_requirement(
    settings: Settings,
    *,
    notice_id: str,
    requirement_key: str,
    requirement_type: str,
    title: str,
    evidence_text: str,
    source_url: str,
    source_locator: str,
    mandatory: bool = False,
    confidence: int = 0,
    weight: float = 0,
    status: str = "pending",
    assignee_member_id: str = "",
    due_at: str = "",
    note: str = "",
    source_revision_id: str = "",
    parent_requirement_id: str = "",
    extraction_mode: str = "manual",
    actor: str = "admin",
) -> OpportunityRequirement:
    init_db(settings)
    values = {
        "notice_id": notice_id.strip(),
        "requirement_key": requirement_key.strip(),
        "requirement_type": requirement_type.strip(),
        "title": title.strip(),
        "evidence_text": evidence_text.strip(),
        "source_url": source_url.strip(),
        "source_locator": source_locator.strip(),
        "status": status.strip(),
        "assignee_member_id": assignee_member_id.strip(),
        "due_at": due_at.strip(),
        "note": note.strip(),
        "source_revision_id": source_revision_id.strip(),
        "parent_requirement_id": parent_requirement_id.strip(),
        "extraction_mode": extraction_mode.strip() or "manual",
        "actor": actor.strip() or "admin",
    }
    _validate(values, confidence, weight)
    requirement_id = _requirement_id(values["notice_id"], values["requirement_key"])
    with connection(settings) as conn:
        if conn.execute("SELECT 1 FROM notices WHERE id = ?", (values["notice_id"],)).fetchone() is None:
            raise LookupError("opportunity notice not found")
        if values["assignee_member_id"] and conn.execute(
            """
            SELECT 1 FROM opportunity_team_members
            WHERE id = ? AND notice_id = ? AND status = 'active'
            """,
            (values["assignee_member_id"], values["notice_id"]),
        ).fetchone() is None:
            raise ValueError("assignee_member_id must be an active member of this opportunity")
        before = conn.execute(
            "SELECT * FROM opportunity_requirements WHERE id = ?", (requirement_id,)
        ).fetchone()
        conn.execute(
            """
            INSERT INTO opportunity_requirements(
                id, notice_id, requirement_key, requirement_type, title, evidence_text,
                source_url, source_locator, mandatory, confidence, status,
                assignee_member_id, due_at, note, created_by, weight,
                source_revision_id, parent_requirement_id, confirmed_at, extraction_mode
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(notice_id, requirement_key) DO UPDATE SET
                requirement_type = excluded.requirement_type,
                title = excluded.title,
                evidence_text = excluded.evidence_text,
                source_url = excluded.source_url,
                source_locator = excluded.source_locator,
                mandatory = excluded.mandatory,
                confidence = excluded.confidence,
                status = excluded.status,
                assignee_member_id = excluded.assignee_member_id,
                due_at = excluded.due_at,
                note = excluded.note,
                weight = excluded.weight,
                source_revision_id = excluded.source_revision_id,
                parent_requirement_id = excluded.parent_requirement_id,
                confirmed_at = CASE
                    WHEN excluded.status IN ('confirmed', 'assigned', 'in_progress', 'review', 'completed')
                    THEN COALESCE(opportunity_requirements.confirmed_at, datetime('now'))
                    ELSE opportunity_requirements.confirmed_at
                END,
                extraction_mode = excluded.extraction_mode,
                created_by = excluded.created_by,
                updated_at = datetime('now')
            """,
            (
                requirement_id,
                values["notice_id"],
                values["requirement_key"],
                values["requirement_type"],
                values["title"],
                values["evidence_text"],
                values["source_url"],
                values["source_locator"],
                int(bool(mandatory)),
                int(confidence),
                values["status"],
                values["assignee_member_id"] or None,
                values["due_at"] or None,
                values["note"] or None,
                values["actor"],
                float(weight),
                values["source_revision_id"],
                values["parent_requirement_id"],
                datetime.now(timezone.utc).isoformat(timespec="seconds")
                if values["status"] in {"confirmed", "assigned", "in_progress", "review", "completed"}
                else None,
                values["extraction_mode"],
            ),
        )
        _record_requirement_event(
            conn,
            notice_id=values["notice_id"],
            requirement_id=requirement_id,
            requirement_key=values["requirement_key"],
            actor=values["actor"],
        )
        row = conn.execute(
            "SELECT * FROM opportunity_requirements WHERE id = ?", (requirement_id,)
        ).fetchone()
        assert row is not None
        _record_bid_history(
            conn,
            notice_id=values["notice_id"],
            requirement_id=requirement_id,
            action="created" if before is None else "edited",
            before=dict(before) if before is not None else {},
            after=dict(row),
            actor=values["actor"],
        )
    return _from_row(row)


def list_requirements(settings: Settings, notice_id: str) -> list[OpportunityRequirement]:
    init_db(settings)
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT * FROM opportunity_requirements
            WHERE notice_id = ?
            ORDER BY mandatory DESC, requirement_type, requirement_key
            """,
            (notice_id.strip(),),
        ).fetchall()
    return [_from_row(row) for row in rows]


def requirement_summary(settings: Settings, notice_id: str) -> dict[str, object]:
    requirements = list_requirements(settings, notice_id)
    active = [item for item in requirements if item.status != "superseded"]
    total_count = len(active)
    confirmed_count = sum(item.status in {"confirmed", "assigned", "in_progress", "review", "completed"} for item in active)
    completed_count = sum(item.status == "completed" for item in active)
    mandatory_pending_count = sum(
        item.mandatory and item.status in {"pending", "review"} for item in active
    )
    by_type = {
        requirement_type: sum(item.requirement_type == requirement_type for item in active)
        for requirement_type in REQUIREMENT_TYPE_LABELS
    }
    return {
        "total_count": total_count,
        "confirmed_count": confirmed_count,
        "completed_count": completed_count,
        "mandatory_pending_count": mandatory_pending_count,
        "coverage_score": round(confirmed_count / total_count * 100) if total_count else 0,
        "by_type": by_type,
    }


def _validate(values: dict[str, str], confidence: int, weight: float) -> None:
    for field in ("notice_id", "requirement_key", "title", "evidence_text", "source_url", "source_locator"):
        if not values[field]:
            raise ValueError(f"{field} is required")
    if values["requirement_type"] not in REQUIREMENT_TYPE_LABELS:
        raise ValueError(f"unsupported requirement_type: {values['requirement_type']}")
    if values["status"] not in REQUIREMENT_STATUS_LABELS:
        raise ValueError(f"unsupported requirement status: {values['status']}")
    if not isinstance(confidence, int) or not 0 <= confidence <= 100:
        raise ValueError("confidence must be an integer from 0 to 100")
    if not isinstance(weight, (int, float)) or not 0 <= float(weight) <= 100:
        raise ValueError("weight must be a number from 0 to 100")
    if values["extraction_mode"] not in {"manual", "rules", "ocr", "model"}:
        raise ValueError("unsupported extraction_mode")


def _from_row(row: Any) -> OpportunityRequirement:
    requirement_type = str(row["requirement_type"] or "")
    status = str(row["status"] or "pending")
    return OpportunityRequirement(
        id=str(row["id"]),
        notice_id=str(row["notice_id"]),
        requirement_key=str(row["requirement_key"]),
        requirement_type=requirement_type,
        requirement_type_label=REQUIREMENT_TYPE_LABELS.get(requirement_type, requirement_type),
        title=str(row["title"] or ""),
        evidence_text=str(row["evidence_text"] or ""),
        source_url=str(row["source_url"] or ""),
        source_locator=str(row["source_locator"] or ""),
        mandatory=bool(row["mandatory"]),
        confidence=int(row["confidence"] or 0),
        weight=float(row["weight"] or 0),
        status=status,
        status_label=REQUIREMENT_STATUS_LABELS.get(status, status),
        assignee_member_id=str(row["assignee_member_id"] or ""),
        due_at=str(row["due_at"] or ""),
        note=str(row["note"] or ""),
        source_revision_id=str(row["source_revision_id"] or ""),
        parent_requirement_id=str(row["parent_requirement_id"] or ""),
        confirmed_at=str(row["confirmed_at"] or ""),
        extraction_mode=str(row["extraction_mode"] or "manual"),
        created_by=str(row["created_by"] or ""),
        created_at=str(row["created_at"] or ""),
        updated_at=str(row["updated_at"] or ""),
    )


def _requirement_id(notice_id: str, requirement_key: str) -> str:
    raw = f"{notice_id}|{requirement_key}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _record_requirement_event(
    conn,
    *,
    notice_id: str,
    requirement_id: str,
    requirement_key: str,
    actor: str,
) -> None:
    conn.execute(
        """
        INSERT INTO opportunity_events(id, notice_id, action, actor_open_id, payload_json)
        VALUES (?, ?, 'requirement_upserted', ?, ?)
        """,
        (
            hashlib.sha256(f"{requirement_id}|{actor}|{uuid4()}".encode()).hexdigest()[:24],
            notice_id,
            actor,
            json.dumps(
                {"requirement_id": requirement_id, "requirement_key": requirement_key},
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
    )


def _record_bid_history(
    conn,
    *,
    notice_id: str,
    requirement_id: str,
    action: str,
    before: dict[str, Any],
    after: dict[str, Any],
    actor: str,
) -> None:
    conn.execute(
        """
        INSERT INTO bid_requirement_history(
            id, notice_id, requirement_id, action, before_json, after_json, actor
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            uuid4().hex,
            notice_id,
            requirement_id,
            action,
            json.dumps(before, ensure_ascii=False, sort_keys=True),
            json.dumps(after, ensure_ascii=False, sort_keys=True),
            actor,
        ),
    )
