from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
import re
from typing import Any
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.llm.gateway import ModelGateway, model_status
from tendertrace.opportunity_requirements import OpportunityRequirement, list_requirements


CAPABILITY_TYPE_LABELS = {
    "product_parameter": "产品参数",
    "qualification_certificate": "资质证书",
    "personnel_skill": "人员能力",
    "delivery_service": "交付服务",
    "project_case": "项目案例",
    "partner_authorization": "合作伙伴授权",
    "product": "产品参数（兼容）",
    "qualification": "资质证书（兼容）",
    "delivery": "交付服务（兼容）",
    "case": "项目案例（兼容）",
}
VERIFICATION_STATUS_LABELS = {
    "draft": "待核验",
    "verified": "已核验",
    "expired": "已失效",
}
MATCH_VERDICT_LABELS = {
    "supported": "有据满足",
    "gap": "明确缺口",
    "needs_evidence": "证据不足",
    "conflict": "存在冲突",
    "pending": "待人工确认",
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
    workspace_id: str
    applicable_entity: str
    product_model: str
    regions: tuple[str, ...]
    authorization_scope: str
    source_file_name: str
    valid_from: str
    industry: str
    sample_redacted: bool
    content_hash: str
    version_number: int
    created_by: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["regions"] = list(self.regions)
        return value


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
    capability_applicable_entity: str
    capability_product_model: str
    capability_regions: tuple[str, ...]
    capability_authorization_scope: str
    capability_valid_until: str
    capability_version_id: str
    project_snapshot_id: str
    rule_details: dict[str, object]
    conflict_code: str
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
    workspace_id: str = "default",
    applicable_entity: str = "",
    product_model: str = "",
    regions: list[str] | tuple[str, ...] | None = None,
    authorization_scope: str = "",
    source_file_name: str = "",
    valid_from: str = "",
    industry: str = "",
    sample_redacted: bool = False,
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
        "workspace_id": workspace_id.strip() or "default",
        "applicable_entity": applicable_entity.strip(),
        "product_model": product_model.strip(),
        "authorization_scope": authorization_scope.strip(),
        "source_file_name": source_file_name.strip(),
        "valid_from": valid_from.strip(),
        "industry": industry.strip(),
        "actor": actor.strip() or "admin",
    }
    _validate_capability(values)
    normalized_regions = tuple(dict.fromkeys(str(item).strip() for item in (regions or ()) if str(item).strip()))
    capability_id = _capability_id(values["capability_key"])
    snapshot = {
        **{key: values[key] for key in (
            "capability_key", "title", "capability_type", "evidence_text", "source_url",
            "source_locator", "verification_status", "owner", "valid_until", "workspace_id",
            "applicable_entity", "product_model", "authorization_scope", "source_file_name",
            "valid_from", "industry",
        )},
        "regions": list(normalized_regions),
        "sample_redacted": bool(sample_redacted),
    }
    content_hash = hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    with connection(settings) as conn:
        previous = conn.execute(
            "SELECT content_hash, version_number FROM enterprise_capabilities WHERE id = ?",
            (capability_id,),
        ).fetchone()
        version_number = int(previous["version_number"] or 1) if previous else 1
        if previous and str(previous["content_hash"] or "") != content_hash:
            version_number += 1
        conn.execute(
            """
            INSERT INTO enterprise_capabilities(
                id, capability_key, title, capability_type, evidence_text, source_url,
                source_locator, verification_status, owner, valid_until, created_by,
                workspace_id, applicable_entity, product_model, regions_json,
                authorization_scope, source_file_name, valid_from, industry,
                sample_redacted, content_hash, version_number
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(capability_key) DO UPDATE SET
                title = excluded.title,
                capability_type = excluded.capability_type,
                evidence_text = excluded.evidence_text,
                source_url = excluded.source_url,
                source_locator = excluded.source_locator,
                verification_status = excluded.verification_status,
                owner = excluded.owner,
                valid_until = excluded.valid_until,
                workspace_id = excluded.workspace_id,
                applicable_entity = excluded.applicable_entity,
                product_model = excluded.product_model,
                regions_json = excluded.regions_json,
                authorization_scope = excluded.authorization_scope,
                source_file_name = excluded.source_file_name,
                valid_from = excluded.valid_from,
                industry = excluded.industry,
                sample_redacted = excluded.sample_redacted,
                content_hash = excluded.content_hash,
                version_number = excluded.version_number,
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
                values["workspace_id"],
                values["applicable_entity"],
                values["product_model"],
                json.dumps(normalized_regions, ensure_ascii=False),
                values["authorization_scope"],
                values["source_file_name"],
                values["valid_from"] or None,
                values["industry"],
                int(bool(sample_redacted)),
                content_hash,
                version_number,
            ),
        )
        version_id = hashlib.sha256(f"{capability_id}|{content_hash}".encode()).hexdigest()[:24]
        conn.execute(
            """
            INSERT OR IGNORE INTO capability_versions(
                id, capability_id, version_number, content_hash, snapshot_json, actor
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (version_id, capability_id, version_number, content_hash, json.dumps(snapshot, ensure_ascii=False, sort_keys=True), values["actor"]),
        )
        if previous and str(previous["content_hash"] or "") != content_hash:
            conn.execute(
                "UPDATE requirement_capability_matches SET status = 'recheck', updated_at = datetime('now') WHERE capability_id = ? AND status = 'confirmed'",
                (capability_id,),
            )
        conn.execute(
            """
            INSERT INTO capability_audit_events(
                id, workspace_id, capability_id, action, actor, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (str(uuid4()), values["workspace_id"], capability_id, "capability_created" if previous is None else "capability_updated", values["actor"], json.dumps({"version_number": version_number, "content_hash": content_hash}, ensure_ascii=False, sort_keys=True)),
        )
        row = conn.execute("SELECT * FROM enterprise_capabilities WHERE id = ?", (capability_id,)).fetchone()
    assert row is not None
    return _capability_from_row(row)


def list_capabilities(
    settings: Settings,
    *,
    verified_only: bool = False,
    workspace_id: str = "default",
) -> list[EnterpriseCapability]:
    init_db(settings)
    where = (
        "WHERE workspace_id = ? AND verification_status = 'verified' "
        "AND (COALESCE(valid_from, '') = '' OR date(valid_from) <= date('now')) "
        "AND (COALESCE(valid_until, '') = '' OR date(valid_until) >= date('now'))"
        if verified_only
        else "WHERE workspace_id = ?"
    )
    with connection(settings) as conn:
        rows = conn.execute(
            f"SELECT * FROM enterprise_capabilities {where} ORDER BY verification_status, capability_type, title, rowid",
            (workspace_id.strip() or "default",),
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
                   capability.source_locator AS capability_source_locator,
                   capability.applicable_entity AS capability_applicable_entity,
                   capability.product_model AS capability_product_model,
                   capability.regions_json AS capability_regions_json,
                   capability.authorization_scope AS capability_authorization_scope,
                   capability.valid_until AS capability_valid_until
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
        "conflict_count": sum(item.verdict == "conflict" for item in items),
        "pending_count": sum(item.verdict == "pending" or item.status == "proposed" for item in items),
    }


def bind_capability_workspace(
    settings: Settings,
    notice_id: str,
    workspace_id: str,
    *,
    actor: str,
) -> None:
    selected = workspace_id.strip() or "default"
    with connection(settings) as conn:
        if conn.execute("SELECT 1 FROM notices WHERE id = ?", (notice_id,)).fetchone() is None:
            raise LookupError("opportunity notice not found")
        if selected != "default" and conn.execute(
            "SELECT 1 FROM organization_workspaces WHERE id = ? AND status = 'active'",
            (selected,),
        ).fetchone() is None:
            raise LookupError("organization workspace not found")
        conn.execute(
            """
            INSERT INTO opportunity_capability_scopes(notice_id, workspace_id, bound_by)
            VALUES (?, ?, ?)
            ON CONFLICT(notice_id) DO UPDATE SET
                workspace_id = excluded.workspace_id,
                bound_by = excluded.bound_by,
                updated_at = datetime('now')
            """,
            (notice_id, selected, actor.strip() or "admin"),
        )


def capability_workspace_id(settings: Settings, notice_id: str) -> str:
    with connection(settings) as conn:
        row = conn.execute(
            "SELECT workspace_id FROM opportunity_capability_scopes WHERE notice_id = ?",
            (notice_id,),
        ).fetchone()
    return str(row["workspace_id"] or "default") if row else "default"


def refresh_capability_validity(settings: Settings, *, workspace_id: str = "default") -> dict[str, int]:
    """Expire credentials by date and put their human-confirmed matches back into review."""
    init_db(settings)
    with connection(settings) as conn:
        expired_ids = [
            str(row["id"])
            for row in conn.execute(
                """
                SELECT id FROM enterprise_capabilities
                WHERE workspace_id = ? AND verification_status = 'verified'
                  AND COALESCE(valid_until, '') <> '' AND date(valid_until) < date('now')
                """,
                (workspace_id.strip() or "default",),
            ).fetchall()
        ]
        if not expired_ids:
            return {"expired_count": 0, "recheck_count": 0}
        placeholders = ",".join("?" for _ in expired_ids)
        conn.execute(
            f"UPDATE enterprise_capabilities SET verification_status = 'expired', updated_at = datetime('now') WHERE id IN ({placeholders})",
            expired_ids,
        )
        cursor = conn.execute(
            f"UPDATE requirement_capability_matches SET status = 'recheck', conflict_code = 'expired', updated_at = datetime('now') WHERE capability_id IN ({placeholders}) AND status = 'confirmed'",
            expired_ids,
        )
        for capability_id in expired_ids:
            conn.execute(
                "INSERT INTO capability_audit_events(id, workspace_id, capability_id, action, actor, payload_json) VALUES (?, ?, ?, 'capability_expired', 'system:validity', '{}')",
                (str(uuid4()), workspace_id.strip() or "default", capability_id),
            )
        return {"expired_count": len(expired_ids), "recheck_count": cursor.rowcount}


def analyze_capability_matches(
    settings: Settings,
    notice_id: str,
    *,
    gateway: ModelGateway | None = None,
    workspace_id: str = "",
) -> dict[str, object]:
    """Create advisory matches using only verified, source-linked capabilities.

    The model is deliberately optional. Its output cannot create a supported claim
    unless it cites one of the capability identifiers provided in the prompt.
    """
    init_db(settings)
    selected_workspace = workspace_id.strip() or capability_workspace_id(settings, notice_id)
    bind_capability_workspace(settings, notice_id, selected_workspace, actor="system:matching")
    refresh_capability_validity(settings, workspace_id=selected_workspace)
    requirements = [
        item
        for item in list_requirements(settings, notice_id)
        if item.status in {"confirmed", "assigned", "in_progress", "review", "completed"}
    ]
    if not requirements:
        raise LookupError("confirmed opportunity requirements not found; confirm requirements first")
    capabilities = list_capabilities(settings, verified_only=True, workspace_id=selected_workspace)
    with connection(settings) as conn:
        notice = conn.execute("SELECT region FROM notices WHERE id = ?", (notice_id,)).fetchone()
    notice_region = str(notice["region"] or "") if notice else ""
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
            proposals = _evidence_only_proposals(requirement, capabilities, notice_region=notice_region)
        for proposal in proposals:
            guarded = _apply_structured_guardrails(
                requirement,
                next((item for item in capabilities if item.id == proposal.get("capability_id")), None),
                proposal,
                notice_region=notice_region,
            )
            _persist_match(settings, notice_id, requirement, guarded, workspace_id=selected_workspace)
            persisted_count += 1
    return {
        "status": "finished",
        "mode": "ai_assisted" if model_used else "evidence_only",
        "scanned_requirement_count": len(requirements),
        "verified_capability_count": len(capabilities),
        "workspace_id": selected_workspace,
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
        if verdict == "supported" and (
            not str(row["capability_id"] or "")
            or not str(row["capability_version_id"] or "")
            or not str(row["project_snapshot_id"] or "")
        ):
            raise ValueError("supported match requires linked enterprise evidence and a project snapshot")
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
        if accept and str(row["project_snapshot_id"] or ""):
            conn.execute(
                """
                UPDATE capability_project_snapshots
                SET confirmation_status = 'confirmed', confirmed_by = ?, confirmed_at = datetime('now')
                WHERE id = ?
                """,
                (actor.strip(), row["project_snapshot_id"]),
            )
        conn.execute(
            """
            INSERT INTO capability_audit_events(
                id, workspace_id, capability_id, notice_id, action, actor, payload_json
            ) VALUES (?, ?, ?, ?, 'match_decided', ?, ?)
            """,
            (
                str(uuid4()),
                str(row["workspace_id"] or "default"),
                str(row["capability_id"] or "") or None,
                notice_id,
                actor.strip(),
                json.dumps({"match_id": match_id, "verdict": verdict, "accepted": accept, "note": note.strip()}, ensure_ascii=False, sort_keys=True),
            ),
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
    *,
    workspace_id: str,
) -> None:
    capability_id = str(proposal.get("capability_id") or "")
    match_id = _match_id(requirement.id, capability_id)
    with connection(settings) as conn:
        capability_version_id = ""
        project_snapshot_id = ""
        if capability_id:
            version = conn.execute(
                "SELECT id FROM capability_versions WHERE capability_id = ? ORDER BY version_number DESC LIMIT 1",
                (capability_id,),
            ).fetchone()
            capability_version_id = str(version["id"] or "") if version else ""
            if capability_version_id:
                project_snapshot_id = hashlib.sha256(
                    f"{notice_id}|{capability_id}|{capability_version_id}".encode()
                ).hexdigest()[:24]
                conn.execute(
                    """
                    INSERT OR IGNORE INTO capability_project_snapshots(
                        id, notice_id, workspace_id, capability_id, capability_version_id
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (project_snapshot_id, notice_id, workspace_id, capability_id, capability_version_id),
                )
        conn.execute(
            """
            INSERT INTO requirement_capability_matches(
                id, notice_id, requirement_id, capability_id, verdict, confidence, rationale, status,
                workspace_id, capability_version_id, project_snapshot_id,
                rule_details_json, conflict_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'proposed', ?, ?, ?, ?, ?)
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
                workspace_id = excluded.workspace_id,
                capability_version_id = excluded.capability_version_id,
                project_snapshot_id = excluded.project_snapshot_id,
                rule_details_json = CASE
                    WHEN requirement_capability_matches.status = 'confirmed'
                    THEN requirement_capability_matches.rule_details_json
                    ELSE excluded.rule_details_json
                END,
                conflict_code = CASE
                    WHEN requirement_capability_matches.status = 'confirmed'
                    THEN requirement_capability_matches.conflict_code
                    ELSE excluded.conflict_code
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
                workspace_id,
                capability_version_id,
                project_snapshot_id,
                json.dumps(proposal.get("rule_details") or {}, ensure_ascii=False, sort_keys=True),
                str(proposal.get("conflict_code") or ""),
            ),
        )


def _evidence_only_proposals(
    requirement: OpportunityRequirement,
    capabilities: list[EnterpriseCapability],
    *,
    notice_region: str,
) -> list[dict[str, object]]:
    if not capabilities:
        return [{"capability_id": "", "verdict": "needs_evidence", "confidence": 0, "rationale": "暂无已核验的企业能力证据，不能判断该要求是否可满足。"}]
    ranked = sorted(
        capabilities,
        key=lambda capability: _capability_relevance(requirement, capability),
        reverse=True,
    )
    return [
        _apply_structured_guardrails(
            requirement,
            capability,
            {
                "capability_id": capability.id,
                "verdict": "pending",
                "confidence": min(85, 35 + _capability_relevance(requirement, capability) * 10),
                "rationale": "确定字段已完成初步核验，语义对应关系仍需人工确认。",
            },
            notice_region=notice_region,
        )
        for capability in ranked
        if _capability_relevance(requirement, capability) > 0
    ] or [{"capability_id": "", "verdict": "needs_evidence", "confidence": 0, "rationale": "没有找到同类企业能力证据，请补充材料或建立缺口行动。"}]


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


def _apply_structured_guardrails(
    requirement: OpportunityRequirement,
    capability: EnterpriseCapability | None,
    proposal: dict[str, object],
    *,
    notice_region: str,
) -> dict[str, object]:
    if capability is None:
        return {**proposal, "rule_details": {"evidence_linked": False}, "conflict_code": ""}
    details: dict[str, object] = {
        "evidence_linked": True,
        "type_compatible": _type_compatible(requirement.requirement_type, capability.capability_type),
        "entity": capability.applicable_entity or "待确认",
        "model": capability.product_model or "未限定",
        "regions": list(capability.regions),
        "authorization_scope": capability.authorization_scope or "待确认",
        "valid_until": capability.valid_until or "长期/待确认",
    }
    verdict = str(proposal.get("verdict") or "pending")
    rationale = str(proposal.get("rationale") or "")
    confidence = _confidence(proposal.get("confidence"))
    conflict_code = ""
    if capability.verification_status == "expired" or _is_expired(capability.valid_until):
        verdict, confidence, conflict_code = "conflict", 100, "expired"
        rationale = "企业证据已经到期，不能作为当前项目的有效能力依据。"
    elif notice_region and capability.regions and not any(
        region in notice_region or notice_region in region for region in capability.regions
    ):
        verdict, confidence, conflict_code = "gap", 96, "region_out_of_scope"
        rationale = f"项目地区为{notice_region}，证据授权地区仅为{'、'.join(capability.regions)}。"
    else:
        required_models = _requirement_models(requirement.evidence_text)
        if required_models and capability.product_model and capability.product_model.casefold() not in {
            item.casefold() for item in required_models
        }:
            verdict, confidence, conflict_code = "conflict", 98, "model_mismatch"
            rationale = f"要求型号为{'、'.join(required_models)}，企业证据型号为{capability.product_model}，禁止相近型号自动拼接。"
        elif capability.capability_type in {"partner_authorization"} and not capability.authorization_scope:
            verdict, confidence, conflict_code = "needs_evidence", 92, "authorization_scope_missing"
            rationale = "合作伙伴材料没有明确授权范围，不能确认覆盖本项目。"
        elif not details["type_compatible"]:
            verdict, confidence, conflict_code = "needs_evidence", min(confidence, 30), "type_mismatch"
            rationale = "证据类别与要求类型不直接对应，需要人工说明关联关系。"
        elif capability.product_model and capability.product_model.casefold() in requirement.evidence_text.casefold():
            verdict, confidence = "supported", max(confidence, 92)
            rationale = f"要求原文与企业证据均明确指向型号 {capability.product_model}；仍需人员确认适用主体和授权范围。"
    return {
        **proposal,
        "verdict": verdict,
        "confidence": confidence,
        "rationale": rationale,
        "rule_details": details,
        "conflict_code": conflict_code,
    }


def _capability_relevance(
    requirement: OpportunityRequirement,
    capability: EnterpriseCapability,
) -> int:
    score = 2 if _type_compatible(requirement.requirement_type, capability.capability_type) else 0
    haystack = f"{capability.title} {capability.evidence_text} {capability.product_model}".casefold()
    for token in _meaningful_tokens(f"{requirement.title} {requirement.evidence_text}"):
        if token.casefold() in haystack:
            score += 1
    return score


def _meaningful_tokens(value: str) -> set[str]:
    words = set(re.findall(r"[A-Za-z][A-Za-z0-9._-]{2,}|[\u4e00-\u9fff]{2,6}", value or ""))
    stop = {"投标人", "供应商", "招标文件", "采购项目", "必须", "应当", "提供", "要求"}
    return {word for word in words if word not in stop}


def _requirement_models(value: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"(?:型号|规格)\s*[:：]?\s*([A-Za-z][A-Za-z0-9._-]{2,})", value or "", re.I)))


def _type_compatible(requirement_type: str, capability_type: str) -> bool:
    normalized = {
        "product": "product_parameter",
        "qualification": "qualification_certificate",
        "delivery": "delivery_service",
        "case": "project_case",
    }.get(capability_type, capability_type)
    allowed = {
        "qualification": {"qualification_certificate", "personnel_skill", "partner_authorization"},
        "technical": {"product_parameter", "delivery_service", "project_case", "partner_authorization"},
        "commercial": {"delivery_service", "project_case", "partner_authorization"},
        "deadline": {"delivery_service", "project_case"},
        "scoring": {"qualification_certificate", "personnel_skill", "project_case", "product_parameter"},
        "disqualification": {"qualification_certificate", "partner_authorization"},
        "attachment": {"qualification_certificate", "personnel_skill", "project_case", "product_parameter", "partner_authorization"},
    }
    return normalized in allowed.get(requirement_type, set())


def _matching_system_prompt() -> str:
    return (
        "You assess tender requirements against an enterprise evidence library. Return strict JSON only: "
        '{"matches":[{"capability_id":"","verdict":"supported|gap|needs_evidence|conflict|pending","confidence":0,"rationale":""}]}. '
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
                    "applicable_entity": item.applicable_entity,
                    "product_model": item.product_model,
                    "regions": list(item.regions),
                    "authorization_scope": item.authorization_scope,
                    "valid_from": item.valid_from,
                    "valid_until": item.valid_until,
                    "version_number": item.version_number,
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
    for field in ("valid_from", "valid_until"):
        if values[field]:
            try:
                date.fromisoformat(values[field])
            except ValueError as exc:
                raise ValueError(f"{field} must use YYYY-MM-DD") from exc
    if values["valid_from"] and values["valid_until"] and values["valid_from"] > values["valid_until"]:
        raise ValueError("valid_from cannot be later than valid_until")


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
        workspace_id=str(row["workspace_id"] or "default"),
        applicable_entity=str(row["applicable_entity"] or ""),
        product_model=str(row["product_model"] or ""),
        regions=tuple(_json_list(row["regions_json"])),
        authorization_scope=str(row["authorization_scope"] or ""),
        source_file_name=str(row["source_file_name"] or ""),
        valid_from=str(row["valid_from"] or ""),
        industry=str(row["industry"] or ""),
        sample_redacted=bool(row["sample_redacted"]),
        content_hash=str(row["content_hash"] or ""),
        version_number=int(row["version_number"] or 1),
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
        capability_applicable_entity=str(row["capability_applicable_entity"] or ""),
        capability_product_model=str(row["capability_product_model"] or ""),
        capability_regions=tuple(_json_list(row["capability_regions_json"])),
        capability_authorization_scope=str(row["capability_authorization_scope"] or ""),
        capability_valid_until=str(row["capability_valid_until"] or ""),
        capability_version_id=str(row["capability_version_id"] or ""),
        project_snapshot_id=str(row["project_snapshot_id"] or ""),
        rule_details=_json_dict(row["rule_details_json"]),
        conflict_code=str(row["conflict_code"] or ""),
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


def _json_list(value: object) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _json_dict(value: object) -> dict[str, object]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


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
