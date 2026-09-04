from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.opportunity_requirements import OpportunityRequirement, list_requirements
from tendertrace.requirement_change_impact import requirement_change_impact


REVIEW_ROLE_LABELS = {
    "compliance": "合规",
    "project_control": "项目统筹",
    "commercial": "商务",
    "document": "文书",
    "technical": "技术",
    "evidence_audit": "证据审计",
}
DECISION_LABELS = {
    "accepted": "已采纳",
    "returned": "退回修订",
    "escalated": "升级会审",
}


@dataclass(frozen=True)
class RequirementReviewCase:
    id: str
    notice_id: str
    requirement_id: str
    requirement_key: str
    reviewer_role: str
    reviewer_role_label: str
    reason: str
    status: str
    decision: str
    decision_label: str
    decision_note: str
    decided_by: str
    decided_at: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def sync_requirement_review_cases(settings: Settings, notice_id: str) -> dict[str, object]:
    init_db(settings)
    requirements = list_requirements(settings, notice_id)
    impacts = {
        str(item.get("id") or ""): item
        for item in requirement_change_impact(settings, notice_id).get("items", [])
        if isinstance(item, dict)
    }
    candidates = [
        candidate
        for requirement in requirements
        for candidate in _review_candidates(requirement, impacted=requirement.id in impacts)
    ]
    created_count = 0
    with connection(settings) as conn:
        for requirement, reviewer_role, reason in candidates:
            review_id = _review_id(requirement.id, reviewer_role, reason)
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO requirement_review_cases(
                    id, notice_id, requirement_id, reviewer_role, reason
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (review_id, notice_id, requirement.id, reviewer_role, reason),
            )
            if not cursor.rowcount:
                continue
            created_count += 1
            conn.execute(
                """
                INSERT INTO opportunity_events(id, notice_id, action, actor_open_id, payload_json)
                VALUES (?, ?, 'requirement_review_created', 'system:review_board', ?)
                """,
                (
                    str(uuid4()),
                    notice_id,
                    json.dumps(
                        {
                            "review_id": review_id,
                            "requirement_id": requirement.id,
                            "requirement_key": requirement.requirement_key,
                            "reviewer_role": reviewer_role,
                            "reason": reason,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                ),
            )
    return {
        "created_count": created_count,
        "items": [item.to_dict() for item in list_requirement_review_cases(settings, notice_id)],
        "summary": requirement_review_summary(settings, notice_id),
    }


def list_requirement_review_cases(
    settings: Settings,
    notice_id: str,
) -> list[RequirementReviewCase]:
    init_db(settings)
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT review.*, requirement.requirement_key
            FROM requirement_review_cases review
            JOIN opportunity_requirements requirement ON requirement.id = review.requirement_id
            WHERE review.notice_id = ?
            ORDER BY review.status, review.created_at, review.rowid
            """,
            (notice_id,),
        ).fetchall()
    return [_from_row(row) for row in rows]


def requirement_review_summary(settings: Settings, notice_id: str) -> dict[str, object]:
    items = list_requirement_review_cases(settings, notice_id)
    return {
        "total_count": len(items),
        "pending_count": sum(item.status == "pending" for item in items),
        "resolved_count": sum(item.status == "resolved" for item in items),
        "by_role": {
            role: sum(item.reviewer_role == role and item.status == "pending" for item in items)
            for role in REVIEW_ROLE_LABELS
        },
    }


def resolve_requirement_review_case(
    settings: Settings,
    notice_id: str,
    review_id: str,
    *,
    decision: str,
    actor: str,
    note: str,
) -> RequirementReviewCase:
    if decision not in DECISION_LABELS:
        raise ValueError(f"unsupported review decision: {decision}")
    if not actor.strip():
        raise ValueError("review actor is required")
    if not note.strip():
        raise ValueError("review decision note is required")
    with connection(settings) as conn:
        row = conn.execute(
            """
            SELECT review.*, requirement.requirement_key
            FROM requirement_review_cases review
            JOIN opportunity_requirements requirement ON requirement.id = review.requirement_id
            WHERE review.id = ? AND review.notice_id = ?
            """,
            (review_id, notice_id),
        ).fetchone()
        if row is None:
            raise LookupError("requirement review case not found")
        if str(row["status"]) != "pending":
            raise ValueError("requirement review case is already resolved")
        conn.execute(
            """
            UPDATE requirement_review_cases
            SET status = 'resolved', decision = ?, decision_note = ?, decided_by = ?,
                decided_at = datetime('now'), updated_at = datetime('now')
            WHERE id = ?
            """,
            (decision, note.strip(), actor.strip(), review_id),
        )
        conn.execute(
            """
            INSERT INTO opportunity_events(id, notice_id, action, actor_open_id, payload_json)
            VALUES (?, ?, 'requirement_review_resolved', ?, ?)
            """,
            (
                str(uuid4()),
                notice_id,
                actor.strip(),
                json.dumps(
                    {"review_id": review_id, "decision": decision, "note": note.strip()},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            ),
        )
        updated = conn.execute(
            """
            SELECT review.*, requirement.requirement_key
            FROM requirement_review_cases review
            JOIN opportunity_requirements requirement ON requirement.id = review.requirement_id
            WHERE review.id = ?
            """,
            (review_id,),
        ).fetchone()
    assert updated is not None
    return _from_row(updated)


def _review_candidates(
    requirement: OpportunityRequirement,
    *,
    impacted: bool,
) -> list[tuple[OpportunityRequirement, str, str]]:
    role = _reviewer_role(requirement)
    candidates: list[tuple[OpportunityRequirement, str, str]] = []
    if requirement.status == "review":
        candidates.append((requirement, role, "requirement_marked_for_review"))
    if requirement.confidence < 70:
        candidates.append((requirement, role, "low_confidence"))
    if requirement.mandatory and requirement.status in {"pending", "review"}:
        candidates.append((requirement, role, "mandatory_pending"))
    if impacted:
        candidates.append((requirement, "evidence_audit", "notice_change_impact"))
    return candidates


def _reviewer_role(requirement: OpportunityRequirement) -> str:
    text = f"{requirement.title} {requirement.evidence_text}"
    if any(value in text for value in ("技术", "参数", "性能", "接口", "配置", "方案")):
        return "technical"
    return {
        "qualification": "compliance",
        "deadline": "project_control",
        "scoring": "commercial",
        "disqualification": "compliance",
        "attachment": "document",
    }.get(requirement.requirement_type, "evidence_audit")


def _review_id(requirement_id: str, reviewer_role: str, reason: str) -> str:
    return hashlib.sha256(
        f"{requirement_id}|{reviewer_role}|{reason}".encode("utf-8")
    ).hexdigest()[:24]


def _from_row(row: Any) -> RequirementReviewCase:
    role = str(row["reviewer_role"])
    decision = str(row["decision"] or "")
    return RequirementReviewCase(
        id=str(row["id"]),
        notice_id=str(row["notice_id"]),
        requirement_id=str(row["requirement_id"]),
        requirement_key=str(row["requirement_key"]),
        reviewer_role=role,
        reviewer_role_label=REVIEW_ROLE_LABELS.get(role, role),
        reason=str(row["reason"]),
        status=str(row["status"]),
        decision=decision,
        decision_label=DECISION_LABELS.get(decision, decision),
        decision_note=str(row["decision_note"] or ""),
        decided_by=str(row["decided_by"] or ""),
        decided_at=str(row["decided_at"] or ""),
        created_at=str(row["created_at"] or ""),
        updated_at=str(row["updated_at"] or ""),
    )
