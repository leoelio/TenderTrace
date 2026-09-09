from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
from typing import Any
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.llm.gateway import ModelGateway, model_status
from tendertrace.opportunity_requirements import OpportunityRequirement, list_requirements


CAPABILITY_TYPE_LABELS = {
    "product": "产品与方案",
    "qualification": "资质与合规",
    "delivery": "交付与服务",
    "case": "项目案例",
}
VERIFICATION_STATUS_LABELS = {
    "draft": "待核验",
    "verified": "已核验",
    "expired": "已失效",
}
MATCH_VERDICT_LABELS = {
    "supported": "证据可支撑",
    "gap": "存在缺口",
    "needs_evidence": "需补充证据",
}
MATCH_STATUS_LABELS = {
    "proposed": "AI 建议待确认",
    "confirmed": "人工已确认",
    "recheck": "公告变化待复核",
    "rejected": "未采纳",
}


@dataclass(frozen=True)
class EnterpriseCapability:
    id: str
    capability_key: str
    title: str
    capability_type: str
    capability_type_label: str
    evidence_text: str
    source_url: str
    source_locator: str
    verification_status: str
    verification_status_label: str
    owner: str
    valid_until: str
    created_by: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RequirementCapabilityMatch:
    id: str
    notice_id: str
    requirement_id: str
    requirement_key: str
    requirement_title: str
    capability_id: str
    capability_title: str
    capability_type: str
    capability_evidence_text: str
    capability_source_url: str
    capability_source_locator: str
    verdict: str
    verdict_label: str
    confidence: int
    rationale: str
    status: str
    status_label: str
    decided_by: str
    decision_note: str
    decided_at: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def upsert_capability(
    settings: Settings,
    *,
    capability_key: str,
    title: str,
    capability_type: str,
    evidence_text: str,
    source_url: str,
    source_locator: str,
    verification_status: str = "draft",
    owner: str = "",
    valid_until: str = "",
    actor: str = "admin",
) -> EnterpriseCapability:
    init_db(settings)
    values = {
        "capability_key": capability_key.strip(),
        "title": title.strip(),
        "capability_type": capability_type.strip(),
        "evidence_text": evidence_text.strip(),
        "source_url": source_url.strip(),
        "source_locator": source_locator.strip(),
        "verification_status": verification_status.strip(),
        "owner": owner.strip(),
        "valid_until": valid_until.strip(),
        "actor": actor.strip() or "admin",
    }
    _validate_capability(values)
    capability_id = _capability_id(values["capability_key"])
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO enterprise_capabilities(
                id, capability_key, title, capability_type, evidence_text, source_url,
                source_locator, verification_status, owner, valid_until, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(capability_key) DO UPDATE SET
                title = excluded.title,
                capability_type = excluded.capability_type,
                evidence_text = excluded.evidence_text,
                source_url = excluded.source_url,
                source_locator = excluded.source_locator,
                verification_status = excluded.verification_status,
                owner = excluded.owner,
                valid_until = excluded.valid_until,
                created_by = excluded.created_by,
                updated_at = datetime('now')
            """,
            (
                capability_id,
                values["capability_key"],
                values["title"],
                values["capability_type"],
                values["evidence_text"],
                values["source_url"],
                values["source_locator"],
                values["verification_status"],
                values["owner"],
                values["valid_until"] or None,
                values["actor"],
            ),
        )
        row = conn.execute("SELECT * FROM enterprise_capabilities WHERE id = ?", (capability_id,)).fetchone()
    assert row is not None
    return _capability_from_row(row)


def list_capabilities(settings: Settings, *, verified_only: bool = False) -> list[EnterpriseCapability]:
    init_db(settings)
    where = (
        "WHERE verification_status = 'verified' "
        "AND (COALESCE(valid_until, '') = '' OR date(valid_until) >= date('now'))"
        if verified_only
        else ""
    )
    with connection(settings) as conn:
        rows = conn.execute(
            f"SELECT * FROM enterprise_capabilities {where} ORDER BY verification_status, capability_type, title, rowid"
        ).fetchall()
    return [_capability_from_row(row) for row in rows]


def list_requirement_capability_matches(
    settings: Settings,
    notice_id: str,
) -> list[RequirementCapabilityMatch]:
    init_db(settings)
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT matched.*, requirement.requirement_key, requirement.title AS requirement_title,
                   capability.title AS capability_title, capability.capability_type,
                   capability.evidence_text AS capability_evidence_text,
                   capability.source_url AS capability_source_url,
                   capability.source_locator AS capability_source_locator
            FROM requirement_capability_matches matched
            JOIN opportunity_requirements requirement ON requirement.id = matched.requirement_id
            LEFT JOIN enterprise_capabilities capability ON capability.id = matched.capability_id
            WHERE matched.notice_id = ?
            ORDER BY requirement.mandatory DESC, requirement.requirement_key, matched.created_at, matched.rowid
            """,
            (notice_id.strip(),),
        ).fetchall()
    return [_match_from_row(row) for row in rows]


def capability_match_summary(settings: Settings, notice_id: str) -> dict[str, object]:
    items = list_requirement_capability_matches(settings, notice_id)
    return {
        "total_count": len(items),
        "supported_count": sum(item.verdict == "supported" and item.status == "confirmed" for item in items),
        "gap_count": sum(item.verdict == "gap" for item in items),
        "needs_evidence_count": sum(item.verdict == "needs_evidence" for item in items),
        "recheck_count": sum(item.status == "recheck" for item in items),
        "confirmed_count": sum(item.status == "confirmed" for item in items),
    }


def analyze_capability_matches(
    settings: Settings,
    notice_id: str,
    *,
    gateway: ModelGateway | None = None,
) -> dict[str, object]:
    """Create advisory matches using only verified, source-linked capabilities.

    The model is deliberately optional. Its output cannot create a supported claim
    unless it cites one of the capability identifiers provided in the prompt.
    """
    init_db(settings)
    requirements = list_requirements(settings, notice_id)
    if not requirements:
        raise LookupError("opportunity requirements not found; extract requirements first")
    capabilities = list_capabilities(settings, verified_only=True)
    model_gateway = gateway or ModelGateway(settings)
    status = model_status(settings)
    model_enabled = (
        settings.model_enhancement_enabled
        and status.configured
        and status.mode != "disabled"
    )
    persisted_count = 0
    model_used = False
    for requirement in requirements:
        proposals: list[dict[str, object]] = []
        if capabilities and model_enabled:
            result = model_gateway.generate_json(
                system=_matching_system_prompt(),
                user=_matching_prompt(requirement, capabilities),
            )
            proposals = _normalize_model_matches(result.parsed, capabilities) if result.status == "ok" else []
            model_used = model_used or bool(proposals)
        if not proposals:
            proposals = _evidence_only_proposals(capabilities)
        for proposal in proposals:
            _persist_match(settings, notice_id, requirement, proposal)
            persisted_count += 1
    return {
        "status": "finished",
        "mode": "ai_assisted" if model_used else "evidence_only",
        "scanned_requirement_count": len(requirements),
        "verified_capability_count": len(capabilities),
        "proposal_count": persisted_count,
        "items": [item.to_dict() for item in list_requirement_capability_matches(settings, notice_id)],
        "summary": capability_match_summary(settings, notice_id),
    }


def decide_capability_match(
    settings: Settings,
    notice_id: str,
    match_id: str,
    *,
    verdict: str,
    actor: str,
    note: str,
    accept: bool,
) -> RequirementCapabilityMatch:
    if verdict not in MATCH_VERDICT_LABELS:
        raise ValueError(f"unsupported capability match verdict: {verdict}")
    if not actor.strip() or not note.strip():
        raise ValueError("decision actor and note are required")
    with connection(settings) as conn:
        row = conn.execute(
            "SELECT * FROM requirement_capability_matches WHERE id = ? AND notice_id = ?",
            (match_id, notice_id),
        ).fetchone()
        if row is None:
            raise LookupError("capability match not found")
        conn.execute(
            """
            UPDATE requirement_capability_matches
            SET verdict = ?, status = ?, decided_by = ?, decision_note = ?,
                decided_at = datetime('now'), updated_at = datetime('now')
            WHERE id = ?
            """,
            (verdict, "confirmed" if accept else "rejected", actor.strip(), note.strip(), match_id),
        )
        _record_event(
            conn,
            notice_id=notice_id,
            action="capability_match_decided",
            payload={"match_id": match_id, "verdict": verdict, "accepted": accept, "note": note.strip()},
            actor=actor.strip(),
        )
    return next(item for item in list_requirement_capability_matches(settings, notice_id) if item.id == match_id)


def mark_capability_matches_for_recheck(settings: Settings, notice_id: str, requirement_ids: set[str]) -> int:
    """Invalidate prior human confirmations when their tender evidence has changed."""
    if not requirement_ids:
        return 0
    placeholders = ",".join("?" for _ in requirement_ids)
    with connection(settings) as conn:
        cursor = conn.execute(
            f"""
            UPDATE requirement_capability_matches
            SET status = 'recheck', updated_at = datetime('now')
            WHERE notice_id = ? AND requirement_id IN ({placeholders}) AND status = 'confirmed'
            """,
            (notice_id, *sorted(requirement_ids)),
        )
        if cursor.rowcount:
            _record_event(
                conn,
                notice_id=notice_id,
                action="capability_matches_marked_for_recheck",
                payload={"requirement_ids": sorted(requirement_ids), "count": cursor.rowcount},
                actor="system:notice_change",
            )
        return cursor.rowcount


def _persist_match(
    settings: Settings,
    notice_id: str,
    requirement: OpportunityRequirement,
    proposal: dict[str, object],
) -> None:
    capability_id = str(proposal.get("capability_id") or "")
    match_id = _match_id(requirement.id, capability_id)
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO requirement_capability_matches(
                id, notice_id, requirement_id, capability_id, verdict, confidence, rationale, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'proposed')
            ON CONFLICT(requirement_id, capability_id) DO UPDATE SET
                verdict = CASE
                    WHEN requirement_capability_matches.status = 'confirmed'
                    THEN requirement_capability_matches.verdict
                    ELSE excluded.verdict
                END,
                confidence = CASE
                    WHEN requirement_capability_matches.status = 'confirmed'
                    THEN requirement_capability_matches.confidence
                    ELSE excluded.confidence
                END,
                rationale = CASE
                    WHEN requirement_capability_matches.status = 'confirmed'
                    THEN requirement_capability_matches.rationale
                    ELSE excluded.rationale
                END,
                status = CASE
                    WHEN requirement_capability_matches.status IN ('confirmed', 'recheck')
                    THEN requirement_capability_matches.status
                    ELSE 'proposed'
                END,
                updated_at = datetime('now')
            """,
            (
                match_id,
                notice_id,
                requirement.id,
                capability_id,
                str(proposal["verdict"]),
                int(proposal["confidence"]),
                str(proposal["rationale"]),
            ),
        )


def _evidence_only_proposals(capabilities: list[EnterpriseCapability]) -> list[dict[str, object]]:
    if not capabilities:
        return [{"capability_id": "", "verdict": "needs_evidence", "confidence": 0, "rationale": "暂无已核验的企业能力证据，不能判断该要求是否可满足。"}]
    return [
        {
            "capability_id": capability.id,
            "verdict": "needs_evidence",
            "confidence": 0,
            "rationale": "已发现可供比对的已核验证据，需人工或模型逐条确认与该要求的对应关系。",
        }
        for capability in capabilities
    ]


def _normalize_model_matches(
    parsed: dict[str, Any] | None,
    capabilities: list[EnterpriseCapability],
) -> list[dict[str, object]]:
    if not isinstance(parsed, dict) or not isinstance(parsed.get("matches"), list):
        return []
    allowed = {item.id for item in capabilities}
    normalized: list[dict[str, object]] = []
    for raw in parsed["matches"][:12]:
        if not isinstance(raw, dict):
            continue
        capability_id = str(raw.get("capability_id") or "")
        verdict = str(raw.get("verdict") or "").strip().lower()
        if capability_id not in allowed or verdict not in MATCH_VERDICT_LABELS:
            continue
        normalized.append(
            {
                "capability_id": capability_id,
                "verdict": verdict,
                "confidence": _confidence(raw.get("confidence")),
                "rationale": str(raw.get("rationale") or "").strip()[:1200],
            }
        )
    return normalized


def _matching_system_prompt() -> str:
    return (
        "You assess tender requirements against an enterprise evidence library. Return strict JSON only: "
        '{"matches":[{"capability_id":"","verdict":"supported|gap|needs_evidence","confidence":0,"rationale":""}]}. '
        "Use only supplied evidence. A supported verdict requires a cited capability_id. "
        "When evidence is insufficient, use needs_evidence. Do not invent qualifications, products, cases, or URLs."
    )


def _matching_prompt(requirement: OpportunityRequirement, capabilities: list[EnterpriseCapability]) -> str:
    return json.dumps(
        {
            "requirement": {
                "key": requirement.requirement_key,
                "title": requirement.title,
                "evidence_text": requirement.evidence_text,
                "source_locator": requirement.source_locator,
                "mandatory": requirement.mandatory,
            },
            "verified_capabilities": [
                {
                    "capability_id": item.id,
                    "title": item.title,
                    "type": item.capability_type,
                    "evidence_text": item.evidence_text,
                    "source_locator": item.source_locator,
                    "source_url": item.source_url,
                }
                for item in capabilities
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _validate_capability(values: dict[str, str]) -> None:
    for field in ("capability_key", "title", "evidence_text", "source_url", "source_locator"):
        if not values[field]:
            raise ValueError(f"{field} is required")
    if values["capability_type"] not in CAPABILITY_TYPE_LABELS:
        raise ValueError(f"unsupported capability_type: {values['capability_type']}")
    if values["verification_status"] not in VERIFICATION_STATUS_LABELS:
        raise ValueError(f"unsupported verification_status: {values['verification_status']}")
    if values["valid_until"]:
        try:
            date.fromisoformat(values["valid_until"])
        except ValueError as exc:
            raise ValueError("valid_until must use YYYY-MM-DD") from exc


def _capability_from_row(row: Any) -> EnterpriseCapability:
    capability_type = str(row["capability_type"] or "")
    verification_status = str(row["verification_status"] or "draft")
    valid_until = str(row["valid_until"] or "")
    if verification_status == "verified" and _is_expired(valid_until):
        verification_status = "expired"
    return EnterpriseCapability(
        id=str(row["id"]),
        capability_key=str(row["capability_key"]),
        title=str(row["title"]),
        capability_type=capability_type,
        capability_type_label=CAPABILITY_TYPE_LABELS.get(capability_type, capability_type),
        evidence_text=str(row["evidence_text"]),
        source_url=str(row["source_url"]),
        source_locator=str(row["source_locator"]),
        verification_status=verification_status,
        verification_status_label=VERIFICATION_STATUS_LABELS.get(verification_status, verification_status),
        owner=str(row["owner"] or ""),
        valid_until=valid_until,
        created_by=str(row["created_by"] or ""),
        created_at=str(row["created_at"] or ""),
        updated_at=str(row["updated_at"] or ""),
    )


def _match_from_row(row: Any) -> RequirementCapabilityMatch:
    verdict = str(row["verdict"] or "needs_evidence")
    status = str(row["status"] or "proposed")
    return RequirementCapabilityMatch(
        id=str(row["id"]),
        notice_id=str(row["notice_id"]),
        requirement_id=str(row["requirement_id"]),
        requirement_key=str(row["requirement_key"]),
        requirement_title=str(row["requirement_title"]),
        capability_id=str(row["capability_id"] or ""),
        capability_title=str(row["capability_title"] or "未关联企业证据"),
        capability_type=str(row["capability_type"] or ""),
        capability_evidence_text=str(row["capability_evidence_text"] or ""),
        capability_source_url=str(row["capability_source_url"] or ""),
        capability_source_locator=str(row["capability_source_locator"] or ""),
        verdict=verdict,
        verdict_label=MATCH_VERDICT_LABELS.get(verdict, verdict),
        confidence=int(row["confidence"] or 0),
        rationale=str(row["rationale"] or ""),
        status=status,
        status_label=MATCH_STATUS_LABELS.get(status, status),
        decided_by=str(row["decided_by"] or ""),
        decision_note=str(row["decision_note"] or ""),
        decided_at=str(row["decided_at"] or ""),
        created_at=str(row["created_at"] or ""),
        updated_at=str(row["updated_at"] or ""),
    )


def _capability_id(capability_key: str) -> str:
    return hashlib.sha256(capability_key.encode("utf-8")).hexdigest()[:24]


def _match_id(requirement_id: str, capability_id: str) -> str:
    return hashlib.sha256(f"{requirement_id}|{capability_id}".encode("utf-8")).hexdigest()[:24]


def _confidence(value: object) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0


def _is_expired(value: str) -> bool:
    if not value:
        return False
    try:
        return date.fromisoformat(value) < date.today()
    except ValueError:
        return True


def _record_event(conn, *, notice_id: str, action: str, payload: dict[str, object], actor: str) -> None:
    conn.execute(
        """
        INSERT INTO opportunity_events(id, notice_id, action, actor_open_id, payload_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            hashlib.sha256(f"{notice_id}|{action}|{uuid4()}".encode()).hexdigest()[:24],
            notice_id,
            action,
            actor,
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        ),
    )
