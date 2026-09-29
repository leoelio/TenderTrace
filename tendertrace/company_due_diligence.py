from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import re
from typing import Any
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps


USCC_PATTERN = re.compile(r"^[0-9A-HJ-NPQRTUWXY]{18}$")
PRIVILEGED_ROLES = {"system_admin", "owner", "member"}
SENSITIVE_VIEW_ROLES = {"system_admin", "owner"}
PORTRAIT_DIMENSIONS = {
    "subject": "主体与股权",
    "operations": "经营与信用",
    "judicial": "司法与合规",
    "performance": "历史项目与履约",
    "relationships": "关系与冲突",
    "public_opinion": "舆情与外部事件",
}
EVIDENCE_DIMENSIONS = {
    "subject_registration": "subject",
    "business_license": "subject",
    "shareholding": "subject",
    "operating_status": "operations",
    "operating_abnormal": "operations",
    "finance": "operations",
    "tax": "operations",
    "cooperation_record": "operations",
    "judicial_case": "judicial",
    "administrative_penalty": "judicial",
    "sanction": "judicial",
    "historical_project": "performance",
    "award_result": "performance",
    "delivery_record": "performance",
    "stakeholder_relation": "relationships",
    "relationship_action": "relationships",
    "ownership_relation": "relationships",
    "conflict": "relationships",
    "organization_memory": "relationships",
    "adverse_public_opinion": "public_opinion",
    "public_event": "public_opinion",
    "uploaded_material": "operations",
}
NEGATIVE_EVIDENCE_RULES = {
    "operating_abnormal": (
        "经营异常记录",
        "可能影响持续履约或授信",
        "请确认异常原因、移出状态和整改证明，并在合同中设置持续经营承诺。",
        "核验官方最新状态；必要时增加履约保证或分期验收。",
        "warning",
    ),
    "judicial_case": (
        "司法案件记录",
        "可能带来资产执行、声誉或交付中断风险",
        "案件当前阶段、涉案金额、责任归属和对本项目交付有何影响？",
        "由法务复核裁判/执行状态并设置重大诉讼披露条款。",
        "warning",
    ),
    "administrative_penalty": (
        "行政处罚记录",
        "可能影响合规准入、声誉或项目验收",
        "处罚是否已履行、整改是否闭环、是否影响本项目所需资质？",
        "核验处罚决定与整改证明，在合同中设置合规承诺和退出条款。",
        "critical",
    ),
    "sanction": (
        "制裁或禁入记录",
        "可能直接导致合作准入失败或供应中断",
        "主体是否仍在有效限制名单，适用范围是否覆盖本次交易？",
        "法务确认适用范围前暂停签约，并准备替代供应方案。",
        "critical",
    ),
    "conflict": (
        "潜在利益冲突",
        "可能影响采购公正、审批或合同执行",
        "关联关系是否已完整披露，是否需要回避或独立审批？",
        "完成利益冲突声明并由合规负责人确认回避方案。",
        "critical",
    ),
    "adverse_public_opinion": (
        "负面外部事件",
        "可能影响品牌、客户接受度或合作稳定性",
        "事件事实、来源可信度、当前状态和公司的正式回应是什么？",
        "交叉核验权威来源，不以单一媒体报道直接下结论。",
        "warning",
    ),
}


def create_company_entity(
    settings: Settings,
    *,
    workspace_id: str,
    legal_name: object,
    actor: str,
    unified_credit_code: object = "",
    region: object = "",
    legal_representative: object = "",
    entity_type: object = "company",
    aliases: list[object] | None = None,
) -> dict[str, object]:
    init_db(settings)
    role = _require_workspace_access(settings, workspace_id, actor)
    if role not in PRIVILEGED_ROLES:
        raise PermissionError("只有空间负责人或正式成员可以建立合作方主体")
    name = _controlled_text(legal_name, "legal_name", 180)
    credit_code = _credit_code(unified_credit_code, required=False)
    region_text = _controlled_text(region, "region", 80, required=False)
    representative = _controlled_text(
        legal_representative, "legal_representative", 100, required=False
    )
    type_text = _choice(entity_type, "entity_type", {"company", "institution", "person"})
    with connection(settings) as conn:
        if credit_code:
            existing = conn.execute(
                """
                SELECT id FROM company_entities
                WHERE workspace_id = ? AND unified_credit_code = ?
                """,
                (workspace_id, credit_code),
            ).fetchone()
            if existing is not None:
                return _entity_payload(conn, str(existing["id"]), role=role)
        entity_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO company_entities(
                id, workspace_id, legal_name, unified_credit_code, region,
                legal_representative, entity_type, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity_id,
                workspace_id,
                name,
                credit_code,
                region_text,
                representative,
                type_text,
                actor.strip() or "admin",
            ),
        )
        _insert_alias(conn, workspace_id, entity_id, name, "legal_name", "manual", actor, True)
        for alias in aliases or []:
            alias_text = _controlled_text(alias, "alias", 180, required=False)
            if alias_text:
                _insert_alias(
                    conn, workspace_id, entity_id, alias_text, "name", "manual", actor, False
                )
        _audit(
            conn,
            workspace_id,
            entity_id,
            "company_entity_created",
            actor,
            {"legal_name": name, "credit_code_present": bool(credit_code)},
        )
        return _entity_payload(conn, entity_id, role=role)


def resolve_company_candidates(
    settings: Settings,
    *,
    workspace_id: str,
    query: object,
    actor: str,
    unified_credit_code: object = "",
    region: object = "",
    legal_representative: object = "",
) -> dict[str, object]:
    init_db(settings)
    role = _require_workspace_access(settings, workspace_id, actor)
    query_text = _controlled_text(query, "query", 180, required=False)
    credit_code = _credit_code(unified_credit_code, required=False)
    region_text = _controlled_text(region, "region", 80, required=False)
    representative = _controlled_text(
        legal_representative, "legal_representative", 100, required=False
    )
    if not query_text and not credit_code:
        raise ValueError("query or unified_credit_code is required")
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT entity.*
            FROM company_entities entity
            LEFT JOIN company_aliases alias ON alias.entity_id = entity.id
            WHERE entity.workspace_id = ?
              AND (
                (? <> '' AND entity.unified_credit_code = ?)
                OR (? <> '' AND (
                    lower(entity.legal_name) = lower(?)
                    OR lower(alias.alias) = lower(?)
                    OR instr(lower(entity.legal_name), lower(?)) > 0
                    OR instr(lower(alias.alias), lower(?)) > 0
                ))
              )
            """,
            (
                workspace_id,
                credit_code,
                credit_code,
                query_text,
                query_text,
                query_text,
                query_text,
                query_text,
            ),
        ).fetchall()
        candidates = []
        for row in rows:
            exact_credit = bool(credit_code and row["unified_credit_code"] == credit_code)
            exact_name = _normalize_name(str(row["legal_name"])) == _normalize_name(query_text)
            score = 100 if exact_credit else 70 if exact_name else 50
            reasons = ["统一社会信用代码精确匹配"] if exact_credit else [
                "法定名称精确匹配" if exact_name else "名称或别名相似"
            ]
            if region_text and _normalize_name(str(row["region"])) == _normalize_name(region_text):
                score += 10
                reasons.append("地区一致")
            if representative and _normalize_name(
                str(row["legal_representative"])
            ) == _normalize_name(representative):
                score += 10
                reasons.append("法定代表人一致")
            payload = _entity_payload(conn, str(row["id"]), role=role)
            payload.update(
                {
                    "candidate_score": min(score, 100),
                    "match_reasons": reasons,
                    "match_status": "confirmed" if exact_credit else "candidate",
                    "requires_human_confirmation": not exact_credit,
                }
            )
            candidates.append(payload)
        candidates.sort(
            key=lambda item: (int(item["candidate_score"]), str(item["legal_name"])),
            reverse=True,
        )
        return {
            "query": query_text,
            "workspace_id": workspace_id,
            "credit_code_provided": bool(credit_code),
            "candidates": candidates,
            "resolution": "confirmed"
            if len(candidates) == 1 and candidates[0]["match_status"] == "confirmed"
            else "needs_confirmation"
            if candidates
            else "not_found",
            "rules": {
                "credit_code_exact_match_can_confirm": True,
                "name_region_representative_only_create_candidates": True,
                "same_name_never_auto_merges": True,
            },
        }


def confirm_company_identity(
    settings: Settings,
    entity_id: str,
    *,
    workspace_id: str,
    actor: str,
    unified_credit_code: object,
    reason: object,
) -> dict[str, object]:
    init_db(settings)
    role = _require_workspace_access(settings, workspace_id, actor)
    if role not in {"system_admin", "owner"}:
        raise PermissionError("只有空间负责人可以确认合作方主体")
    credit_code = _credit_code(unified_credit_code, required=True)
    reason_text = _controlled_text(reason, "reason", 800)
    with connection(settings) as conn:
        row = conn.execute(
            "SELECT * FROM company_entities WHERE id = ? AND workspace_id = ?",
            (entity_id, workspace_id),
        ).fetchone()
        if row is None:
            raise LookupError("company entity not found")
        collision = conn.execute(
            """
            SELECT id FROM company_entities
            WHERE workspace_id = ? AND unified_credit_code = ? AND id <> ?
            """,
            (workspace_id, credit_code, entity_id),
        ).fetchone()
        if collision is not None:
            raise ValueError("unified_credit_code already belongs to another entity")
        conn.execute(
            """
            UPDATE company_entities
            SET unified_credit_code = ?, identity_status = 'confirmed',
                verification_status = 'manually_confirmed',
                last_verified_at = datetime('now'), updated_at = datetime('now')
            WHERE id = ? AND workspace_id = ?
            """,
            (credit_code, entity_id, workspace_id),
        )
        _audit(
            conn,
            workspace_id,
            entity_id,
            "company_identity_confirmed",
            actor,
            {"reason": reason_text, "credit_code_suffix": credit_code[-4:]},
        )
        return _entity_payload(conn, entity_id, role=role)


def list_company_entities(
    settings: Settings,
    *,
    workspace_id: str,
    actor: str,
    query: str = "",
    limit: int = 100,
) -> list[dict[str, object]]:
    init_db(settings)
    role = _require_workspace_access(settings, workspace_id, actor)
    safe_limit = max(1, min(int(limit), 200))
    query_text = query.strip()
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT entity.id
            FROM company_entities entity
            LEFT JOIN company_aliases alias ON alias.entity_id = entity.id
            WHERE entity.workspace_id = ?
              AND (? = '' OR instr(lower(entity.legal_name), lower(?)) > 0
                   OR instr(lower(alias.alias), lower(?)) > 0)
            ORDER BY entity.updated_at DESC, entity.legal_name LIMIT ?
            """,
            (workspace_id, query_text, query_text, query_text, safe_limit),
        ).fetchall()
        return [_entity_payload(conn, str(row["id"]), role=role) for row in rows]


def add_company_evidence(
    settings: Settings,
    entity_id: str,
    *,
    workspace_id: str,
    actor: str,
    evidence_type: object,
    title: object,
    content_text: object,
    source_type: object = "manual_upload",
    source_name: object = "人工提交材料",
    source_url: object = "",
    source_locator: object = "",
    source_license: object = "authorized_manual",
    access_policy: object = "workspace",
    access_frequency: object = "on_demand",
    snapshot_sha256: object = "",
    occurred_at: object = "",
    valid_from: object = "",
    valid_until: object = "",
    confidence: int = 70,
    subject_match_basis: dict[str, object] | None = None,
    redacted_content: object = "",
    sensitive: bool = False,
    notice_id: str = "",
) -> dict[str, object]:
    """Store one traceable, workspace-scoped company evidence item."""
    init_db(settings)
    role = _require_workspace_access(settings, workspace_id, actor)
    type_text = _controlled_text(evidence_type, "evidence_type", 80)
    title_text = _controlled_text(title, "title", 240)
    content = _controlled_text(content_text, "content_text", 12000)
    redacted = _controlled_text(
        redacted_content, "redacted_content", 12000, required=False
    )
    if sensitive and not redacted:
        raise ValueError("redacted_content is required for sensitive evidence")
    source_type_text = _controlled_text(source_type, "source_type", 80)
    access = _choice(
        access_policy,
        "access_policy",
        {"public", "workspace", "restricted", "authorized_interface"},
    )
    frequency = _choice(
        access_frequency,
        "access_frequency",
        {"manual", "on_demand", "hourly", "daily", "weekly", "monthly"},
    )
    snapshot = _snapshot_hash(snapshot_sha256, content)
    score = max(0, min(int(confidence), 100))
    with connection(settings) as conn:
        _require_entity(conn, workspace_id, entity_id)
        if notice_id:
            _require_notice(conn, notice_id)
        content_hash = hashlib.sha256(
            f"{source_type_text}|{title_text}|{content}|{notice_id}".encode()
        ).hexdigest()
        evidence_id = content_hash[:32]
        conn.execute(
            """
            INSERT INTO company_evidence(
                id, workspace_id, entity_id, notice_id, evidence_type, title,
                source_type, source_name, source_url, source_locator,
                source_license, access_policy, access_frequency, snapshot_sha256,
                occurred_at, valid_from,
                valid_until, evidence_status, confidence,
                subject_match_basis_json, content_text, redacted_content,
                content_hash, sensitive, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workspace_id, entity_id, content_hash) DO UPDATE SET
                title = excluded.title,
                valid_until = excluded.valid_until,
                evidence_status = excluded.evidence_status,
                confidence = excluded.confidence,
                redacted_content = excluded.redacted_content,
                updated_at = datetime('now')
            """,
            (
                evidence_id,
                workspace_id,
                entity_id,
                notice_id or None,
                type_text,
                title_text,
                source_type_text,
                _controlled_text(source_name, "source_name", 180, required=False),
                _controlled_text(source_url, "source_url", 2000, required=False),
                _controlled_text(source_locator, "source_locator", 500, required=False),
                _controlled_text(source_license, "source_license", 120, required=False),
                access,
                frequency,
                snapshot,
                _date_text(occurred_at, "occurred_at"),
                _date_text(valid_from, "valid_from"),
                _date_text(valid_until, "valid_until"),
                "verified" if source_type_text in {"notice", "award_result"} else "pending",
                score,
                json_dumps(subject_match_basis or {}),
                content,
                redacted,
                content_hash,
                int(bool(sensitive)),
                actor.strip() or "admin",
            ),
        )
        _audit(
            conn,
            workspace_id,
            entity_id,
            "company_evidence_added",
            actor,
            {"evidence_id": evidence_id, "source_type": source_type_text},
        )
        row = conn.execute("SELECT * FROM company_evidence WHERE id = ?", (evidence_id,)).fetchone()
        assert row is not None
        return _evidence_payload(row, role=role)


def add_authorized_external_evidence(
    settings: Settings,
    entity_id: str,
    *,
    workspace_id: str,
    actor: str,
    evidence_type: object,
    title: object,
    content_text: object,
    source_type: object,
    source_name: object,
    source_url: object,
    source_license: object,
    access_frequency: object,
    occurred_at: object = "",
    valid_until: object = "",
    confidence: int = 80,
) -> dict[str, object]:
    """Accept external evidence only through recorded lawful access paths."""
    source_type_text = _choice(
        source_type,
        "source_type",
        {
            "official_api",
            "authorized_interface",
            "official_public_snapshot",
            "manual_upload",
        },
    )
    license_text = _controlled_text(source_license, "source_license", 120)
    source_url_text = _controlled_text(source_url, "source_url", 2000)
    if not source_url_text.lower().startswith("https://"):
        raise ValueError("external source_url must use https")
    frequency = _choice(
        access_frequency,
        "access_frequency",
        {"manual", "on_demand", "hourly", "daily", "weekly", "monthly"},
    )
    if source_type_text == "manual_upload" and frequency != "manual":
        raise ValueError("manual_upload access_frequency must be manual")
    if source_type_text == "authorized_interface" and "author" not in license_text.lower():
        raise ValueError("authorized_interface requires an authorization reference")
    content = _controlled_text(content_text, "content_text", 12000)
    return add_company_evidence(
        settings,
        entity_id,
        workspace_id=workspace_id,
        actor=actor,
        evidence_type=evidence_type,
        title=title,
        content_text=content,
        source_type=source_type_text,
        source_name=source_name,
        source_url=source_url_text,
        source_license=license_text,
        access_policy="authorized_interface"
        if source_type_text in {"official_api", "authorized_interface"}
        else "public"
        if source_type_text == "official_public_snapshot"
        else "workspace",
        access_frequency=frequency,
        snapshot_sha256=hashlib.sha256(content.encode()).hexdigest(),
        occurred_at=occurred_at,
        valid_until=valid_until,
        confidence=confidence,
        subject_match_basis={"method": "external_source_subject_match", "requires_review": True},
    )


def verify_company_subject_from_official_evidence(
    settings: Settings,
    entity_id: str,
    *,
    workspace_id: str,
    actor: str,
    evidence_id: str,
    unified_credit_code: object,
    reason: object,
) -> dict[str, object]:
    """Confirm subject identity from an official, lawfully captured evidence snapshot."""
    role = _require_workspace_access(settings, workspace_id, actor)
    if role not in {"system_admin", "owner"}:
        raise PermissionError("只有空间负责人可以完成官方主体核验")
    credit_code = _credit_code(unified_credit_code, required=True)
    reason_text = _controlled_text(reason, "reason", 800)
    with connection(settings) as conn:
        _require_entity(conn, workspace_id, entity_id)
        evidence = conn.execute(
            """
            SELECT * FROM company_evidence
            WHERE id = ? AND entity_id = ? AND workspace_id = ?
            """,
            (evidence_id, entity_id, workspace_id),
        ).fetchone()
        if evidence is None:
            raise LookupError("company evidence not found")
        if str(evidence["source_type"]) not in {"official_api", "official_public_snapshot"}:
            raise ValueError("official subject verification requires an official source")
        if not str(evidence["source_license"] or "").strip():
            raise ValueError("official evidence license is required")
        if credit_code not in re.sub(r"\s+", "", str(evidence["content_text"]).upper()):
            raise ValueError("credit code does not match the official evidence snapshot")
        collision = conn.execute(
            """
            SELECT id FROM company_entities
            WHERE workspace_id = ? AND unified_credit_code = ? AND id <> ?
            """,
            (workspace_id, credit_code, entity_id),
        ).fetchone()
        if collision is not None:
            raise ValueError("unified_credit_code already belongs to another entity")
        conn.execute(
            """
            UPDATE company_evidence SET evidence_status = 'verified', updated_at = datetime('now')
            WHERE id = ?
            """,
            (evidence_id,),
        )
        conn.execute(
            """
            UPDATE company_entities
            SET unified_credit_code = ?, identity_status = 'confirmed',
                verification_status = 'official_verified',
                verification_evidence_id = ?, last_verified_at = datetime('now'),
                updated_at = datetime('now')
            WHERE id = ? AND workspace_id = ?
            """,
            (credit_code, evidence_id, entity_id, workspace_id),
        )
        _audit(
            conn,
            workspace_id,
            entity_id,
            "company_subject_officially_verified",
            actor,
            {
                "evidence_id": evidence_id,
                "credit_code_suffix": credit_code[-4:],
                "reason": reason_text,
                "access_rule": "no_captcha_login_or_access_control_bypass",
            },
        )
        return _entity_payload(conn, entity_id, role=role)


def company_external_access_policy() -> dict[str, object]:
    return {
        "allowed": [
            "official_api",
            "authorized_interface",
            "official_public_snapshot",
            "manual_upload",
        ],
        "forbidden": [
            "绕过验证码",
            "复用未经授权的登录会话",
            "突破访问频率或访问控制",
            "抓取禁止自动访问的页面",
        ],
        "fallback": "无法合法、稳定获取时，仅允许人工上传或经授权接口接入",
    }


def review_company_evidence(
    settings: Settings,
    evidence_id: str,
    *,
    workspace_id: str,
    actor: str,
    status: object,
    reason: object,
) -> dict[str, object]:
    role = _require_workspace_access(settings, workspace_id, actor)
    if role not in PRIVILEGED_ROLES:
        raise PermissionError("当前角色无权复核企业证据")
    status_text = _choice(
        status,
        "status",
        {"verified", "withdrawn", "mismatched", "rejected", "pending"},
    )
    reason_text = _controlled_text(reason, "reason", 800)
    with connection(settings) as conn:
        row = conn.execute(
            "SELECT * FROM company_evidence WHERE id = ? AND workspace_id = ?",
            (evidence_id, workspace_id),
        ).fetchone()
        if row is None:
            raise LookupError("company evidence not found")
        conn.execute(
            "UPDATE company_evidence SET evidence_status = ?, updated_at = datetime('now') WHERE id = ?",
            (status_text, evidence_id),
        )
        if status_text in {"withdrawn", "mismatched", "rejected"}:
            conn.execute(
                """
                UPDATE company_risk_signals
                SET signal_status = 'invalidated', updated_at = datetime('now')
                WHERE evidence_id = ?
                """,
                (evidence_id,),
            )
        _audit(
            conn,
            workspace_id,
            str(row["entity_id"]),
            "company_evidence_reviewed",
            actor,
            {"evidence_id": evidence_id, "status": status_text, "reason": reason_text},
        )
        updated = conn.execute(
            "SELECT * FROM company_evidence WHERE id = ?", (evidence_id,)
        ).fetchone()
        assert updated is not None
        return _evidence_payload(updated, role=role)


def confirm_company_risk_signal(
    settings: Settings,
    signal_id: str,
    *,
    workspace_id: str,
    actor: str,
    status: object,
    reason: object,
) -> dict[str, object]:
    role = _require_workspace_access(settings, workspace_id, actor)
    if role not in {"system_admin", "owner"}:
        raise PermissionError("只有空间负责人可以确认风险信号")
    status_text = _choice(status, "status", {"active", "dismissed", "needs_review"})
    reason_text = _controlled_text(reason, "reason", 800)
    with connection(settings) as conn:
        row = conn.execute(
            "SELECT * FROM company_risk_signals WHERE id = ? AND workspace_id = ?",
            (signal_id, workspace_id),
        ).fetchone()
        if row is None:
            raise LookupError("company risk signal not found")
        if row["evidence_id"]:
            evidence = conn.execute(
                "SELECT evidence_status, valid_until FROM company_evidence WHERE id = ?",
                (row["evidence_id"],),
            ).fetchone()
            if evidence is None or not _evidence_is_current(evidence):
                status_text = "needs_review"
        conn.execute(
            """
            UPDATE company_risk_signals
            SET signal_status = ?, manually_confirmed_by = ?,
                manually_confirmed_at = datetime('now'), updated_at = datetime('now')
            WHERE id = ?
            """,
            (status_text, actor.strip() or "admin", signal_id),
        )
        _audit(
            conn,
            workspace_id,
            str(row["entity_id"]),
            "company_risk_signal_confirmed",
            actor,
            {"signal_id": signal_id, "status": status_text, "reason": reason_text},
        )
        return _risk_summary(conn, str(row["entity_id"]), role=role)


def ask_company_due_diligence(
    settings: Settings,
    entity_id: str,
    *,
    workspace_id: str,
    actor: str,
    question: object,
) -> dict[str, object]:
    """Answer from current company evidence and expose risks, gaps, and mitigations."""
    role = _require_workspace_access(settings, workspace_id, actor)
    question_text = _controlled_text(question, "question", 1000)
    with connection(settings) as conn:
        entity = _require_entity(conn, workspace_id, entity_id)
        summary = _risk_summary(conn, entity_id, role=role)
        risks = [
            item
            for item in summary["risks"]
            if item["signal_status"] in {"active", "needs_review"}
        ]
        missing = [
            item
            for item in summary["missing"]
            if item["signal_status"] in {"needs_evidence", "needs_review"}
        ]
        ranked = sorted(
            risks,
            key=lambda item: (
                {"critical": 3, "warning": 2, "info": 1}.get(str(item["severity"]), 0),
                int(item["confidence"]),
            ),
            reverse=True,
        )[:3]
        evidence_ids = [str(item["evidence_id"]) for item in ranked if item["evidence_id"]]
        risk_lines = []
        for item in ranked:
            citation = f"[企业证据:{item['evidence_id']}]" if item["evidence_id"] else ""
            review_note = "（已核验）" if item["deterministic"] else "（待复核）"
            risk_lines.append(
                f"{item['risk_interpretation']}{review_note}：{item['business_impact']} {citation}".strip()
            )
        missing_items = [str(item["fact_signal"]) for item in missing[:6]]
        if risk_lines:
            answer_text = (
                f"针对“{question_text}”，{entity['legal_name']}当前最需要关注："
                + "；".join(risk_lines)
                + "。"
            )
        else:
            answer_text = (
                f"针对“{question_text}”，当前没有已核验的负面风险证据；"
                "这不等于无风险，仍需先补齐缺失信息。"
            )
        if missing_items:
            answer_text += " 尚缺：" + "；".join(missing_items) + "。"
        worst_impact = (
            str(ranked[0]["business_impact"])
            if ranked
            else "证据不足可能导致在签约前遗漏关键准入、履约或合规问题"
        )
        mitigations = list(
            dict.fromkeys(str(item["mitigation"]) for item in ranked if item["mitigation"])
        )
        if missing_items:
            mitigations.append("将未覆盖维度列为签约前置条件，补证后重新评估。")
        mitigation = "；".join(mitigations) or "完成六维尽调并由负责人确认后再作合作决定。"
        answer_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO company_due_diligence_answers(
                id, workspace_id, entity_id, question, answer,
                evidence_ids_json, missing_items_json, worst_impact,
                mitigation, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                answer_id,
                workspace_id,
                entity_id,
                question_text,
                answer_text,
                json_dumps(evidence_ids),
                json_dumps(missing_items),
                worst_impact,
                mitigation,
                actor.strip() or "admin",
            ),
        )
        _audit(
            conn,
            workspace_id,
            entity_id,
            "company_due_diligence_question_answered",
            actor,
            {"answer_id": answer_id, "evidence_ids": evidence_ids},
        )
        return {
            "id": answer_id,
            "entity_id": entity_id,
            "question": question_text,
            "answer": answer_text,
            "evidence_ids": evidence_ids,
            "missing_items": missing_items,
            "worst_impact": worst_impact,
            "mitigation": mitigation,
            "basis": "仅基于当前工作区证据；待复核材料不会表述为确定事实",
        }


def create_company_due_diligence_task(
    settings: Settings,
    entity_id: str,
    *,
    workspace_id: str,
    actor: str,
    title: object,
    question: object,
    task_type: object,
    assignee_open_id: object,
    due_at: object,
    risk_signal_id: str = "",
    notice_id: str = "",
) -> dict[str, object]:
    role = _require_workspace_access(settings, workspace_id, actor)
    if role not in PRIVILEGED_ROLES:
        raise PermissionError("当前角色无权创建尽调任务")
    title_text = _controlled_text(title, "title", 240)
    question_text = _controlled_text(question, "question", 1000)
    type_text = _choice(
        task_type,
        "task_type",
        {"legal", "finance", "sales", "delivery", "verification"},
    )
    assignee = _controlled_text(
        assignee_open_id, "assignee_open_id", 160, required=False
    )
    due = _due_at_text(due_at)
    with connection(settings) as conn:
        _require_entity(conn, workspace_id, entity_id)
        if notice_id:
            _require_notice(conn, notice_id)
        member_name = ""
        if assignee:
            member = conn.execute(
                """
                SELECT member_name FROM organization_members
                WHERE workspace_id = ? AND member_open_id = ? AND status = 'active'
                """,
                (workspace_id, assignee),
            ).fetchone()
            if member is None:
                raise ValueError("assignee must be an active workspace member")
            member_name = str(member["member_name"] or "")
        if risk_signal_id:
            risk = conn.execute(
                """
                SELECT 1 FROM company_risk_signals
                WHERE id = ? AND workspace_id = ? AND entity_id = ?
                """,
                (risk_signal_id, workspace_id, entity_id),
            ).fetchone()
            if risk is None:
                raise ValueError("risk_signal_id does not belong to this entity")
        task_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO company_due_diligence_tasks(
                id, workspace_id, entity_id, notice_id, risk_signal_id,
                title, question, task_type, assignee_open_id, assignee_name,
                due_at, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                workspace_id,
                entity_id,
                notice_id or None,
                risk_signal_id or None,
                title_text,
                question_text,
                type_text,
                assignee,
                member_name,
                due,
                actor.strip() or "admin",
            ),
        )
        _audit(
            conn,
            workspace_id,
            entity_id,
            "company_due_diligence_task_created",
            actor,
            {"task_id": task_id, "task_type": type_text, "due_at": due},
        )
        row = conn.execute(
            "SELECT * FROM company_due_diligence_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        assert row is not None
        return _task_payload(row)


def list_company_due_diligence_tasks(
    settings: Settings,
    entity_id: str,
    *,
    workspace_id: str,
    actor: str,
) -> list[dict[str, object]]:
    _require_workspace_access(settings, workspace_id, actor)
    with connection(settings) as conn:
        _require_entity(conn, workspace_id, entity_id)
        rows = conn.execute(
            """
            SELECT * FROM company_due_diligence_tasks
            WHERE workspace_id = ? AND entity_id = ? ORDER BY due_at, created_at
            """,
            (workspace_id, entity_id),
        ).fetchall()
        return [_task_payload(row) for row in rows]


def get_company_evidence(
    settings: Settings,
    evidence_id: str,
    *,
    workspace_id: str,
    actor: str,
) -> dict[str, object]:
    role = _require_workspace_access(settings, workspace_id, actor)
    with connection(settings) as conn:
        row = conn.execute(
            "SELECT * FROM company_evidence WHERE id = ? AND workspace_id = ?",
            (evidence_id, workspace_id),
        ).fetchone()
        if row is None:
            raise LookupError("company evidence not found")
        sensitive = bool(row["sensitive"])
        access_mode = "full" if not sensitive or role in SENSITIVE_VIEW_ROLES else "redacted"
        if sensitive:
            _audit(
                conn,
                workspace_id,
                str(row["entity_id"]),
                "sensitive_company_evidence_accessed",
                actor,
                {"evidence_id": evidence_id, "access_mode": access_mode},
            )
        return _evidence_payload(row, role=role)


def record_company_task_feishu_receipt(
    settings: Settings,
    task_id: str,
    *,
    task_guid: str = "",
    status: str,
    receipt: dict[str, object] | None = None,
    error: str = "",
) -> dict[str, object]:
    status_text = _choice(
        status,
        "status",
        {"not_created", "open", "completed", "overdue", "failed"},
    )
    with connection(settings) as conn:
        row = conn.execute(
            "SELECT * FROM company_due_diligence_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise LookupError("company due diligence task not found")
        conn.execute(
            """
            UPDATE company_due_diligence_tasks
            SET feishu_task_guid = CASE WHEN ? <> '' THEN ? ELSE feishu_task_guid END,
                feishu_task_status = ?, feishu_receipt_json = ?,
                feishu_sync_error = ?, feishu_task_synced_at = datetime('now'),
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                task_guid,
                task_guid,
                status_text,
                json_dumps(receipt or {}),
                error[:1000],
                task_id,
            ),
        )
        updated = conn.execute(
            "SELECT * FROM company_due_diligence_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        assert updated is not None
        return _task_payload(updated)


def add_company_relationship(
    settings: Settings,
    entity_id: str,
    *,
    workspace_id: str,
    actor: str,
    related_label: object,
    relationship_type: object,
    basis_type: object,
    confidence: int,
    evidence_id: str = "",
    to_entity_id: str = "",
    related_object_type: object = "company",
    related_object_id: object = "",
) -> dict[str, object]:
    _require_workspace_access(settings, workspace_id, actor)
    label = _controlled_text(related_label, "related_label", 200)
    relationship = _choice(
        relationship_type,
        "relationship_type",
        {
            "parent",
            "subsidiary",
            "shareholder",
            "executive",
            "award",
            "purchaser",
            "partner",
            "competitor",
            "joint_bidder",
            "other",
        },
    )
    basis = _choice(basis_type, "basis_type", {"factual", "inferred", "manual"})
    object_type = _choice(
        related_object_type,
        "related_object_type",
        {"company", "person", "project", "notice"},
    )
    score = max(0, min(int(confidence), 100))
    with connection(settings) as conn:
        _require_entity(conn, workspace_id, entity_id)
        if to_entity_id:
            _require_entity(conn, workspace_id, to_entity_id)
        if evidence_id:
            evidence = conn.execute(
                "SELECT 1 FROM company_evidence WHERE id = ? AND entity_id = ? AND workspace_id = ?",
                (evidence_id, entity_id, workspace_id),
            ).fetchone()
            if evidence is None:
                raise ValueError("evidence_id does not belong to this entity")
        relationship_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO company_relationships(
                id, workspace_id, from_entity_id, to_entity_id,
                related_object_type, related_object_id, related_label,
                relationship_type, basis_type, evidence_id, confidence,
                relationship_status, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                relationship_id,
                workspace_id,
                entity_id,
                to_entity_id or None,
                object_type,
                _controlled_text(
                    related_object_id, "related_object_id", 240, required=False
                ),
                label,
                relationship,
                basis,
                evidence_id or None,
                score,
                "confirmed" if basis in {"factual", "manual"} else "candidate",
                actor.strip() or "admin",
            ),
        )
        _audit(
            conn,
            workspace_id,
            entity_id,
            "company_relationship_added",
            actor,
            {"relationship_id": relationship_id, "basis_type": basis},
        )
        row = conn.execute(
            "SELECT * FROM company_relationships WHERE id = ?", (relationship_id,)
        ).fetchone()
        assert row is not None
        return _relationship_payload(row)


def submit_due_diligence_review(
    settings: Settings,
    entity_id: str,
    *,
    workspace_id: str,
    actor: str,
    recommendation: object,
    reason: object,
    valid_until: object,
    conditions: list[object] | None = None,
    notice_id: str = "",
) -> dict[str, object]:
    role = _require_workspace_access(settings, workspace_id, actor)
    if role not in {"system_admin", "owner"}:
        raise PermissionError("只有空间负责人可以确认合作结论")
    recommendation_text = _choice(
        recommendation,
        "recommendation",
        {"cooperate", "conditional", "pause", "reject"},
    )
    reason_text = _controlled_text(reason, "reason", 2000)
    valid = _date_text(valid_until, "valid_until")
    assert valid is not None
    if valid < _today():
        raise ValueError("valid_until cannot be in the past")
    condition_list = [
        _controlled_text(item, "condition", 500)
        for item in (conditions or [])
        if str(item or "").strip()
    ]
    if recommendation_text == "conditional" and not condition_list:
        raise ValueError("conditional recommendation requires at least one condition")
    with connection(settings) as conn:
        _require_entity(conn, workspace_id, entity_id)
        if notice_id:
            _require_notice(conn, notice_id)
        previous = conn.execute(
            """
            SELECT id FROM due_diligence_reviews
            WHERE workspace_id = ? AND entity_id = ?
            ORDER BY confirmed_at DESC LIMIT 1
            """,
            (workspace_id, entity_id),
        ).fetchone()
        review_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO due_diligence_reviews(
                id, workspace_id, entity_id, notice_id, recommendation,
                reason, conditions_json, valid_until, review_status,
                previous_review_id, confirmed_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'confirmed', ?, ?)
            """,
            (
                review_id,
                workspace_id,
                entity_id,
                notice_id or None,
                recommendation_text,
                reason_text,
                json_dumps(condition_list),
                valid,
                str(previous["id"]) if previous else None,
                actor.strip() or "admin",
            ),
        )
        _audit(
            conn,
            workspace_id,
            entity_id,
            "due_diligence_review_confirmed",
            actor,
            {
                "review_id": review_id,
                "recommendation": recommendation_text,
                "valid_until": valid,
            },
        )
        row = conn.execute(
            "SELECT * FROM due_diligence_reviews WHERE id = ?", (review_id,)
        ).fetchone()
        assert row is not None
        return _review_payload(row)


def subscribe_company_changes(
    settings: Settings,
    entity_id: str,
    *,
    workspace_id: str,
    actor: str,
    event_types: list[object],
) -> dict[str, object]:
    _require_workspace_access(settings, workspace_id, actor)
    allowed = {"subject", "operations", "judicial", "performance", "relationships", "public_opinion"}
    normalized = sorted({_choice(item, "event_type", allowed) for item in event_types})
    if not normalized:
        raise ValueError("at least one event_type is required")
    with connection(settings) as conn:
        _require_entity(conn, workspace_id, entity_id)
        subscription_id = hashlib.sha256(
            f"{workspace_id}|{entity_id}|company-change".encode()
        ).hexdigest()[:32]
        conn.execute(
            """
            INSERT INTO company_change_subscriptions(
                id, workspace_id, entity_id, event_types_json, created_by
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(workspace_id, entity_id) DO UPDATE SET
                event_types_json = excluded.event_types_json,
                status = 'active', updated_at = datetime('now')
            """,
            (subscription_id, workspace_id, entity_id, json_dumps(normalized), actor),
        )
        return {
            "id": subscription_id,
            "entity_id": entity_id,
            "event_types": normalized,
            "status": "active",
            "review_policy": "仅受变化影响的结论重新进入复核；不覆盖已确认结论",
        }


def get_company_due_diligence_profile(
    settings: Settings,
    entity_id: str,
    *,
    workspace_id: str,
    actor: str,
) -> dict[str, object]:
    role = _require_workspace_access(settings, workspace_id, actor)
    with connection(settings) as conn:
        return _profile_payload(conn, entity_id, workspace_id=workspace_id, role=role)


def save_company_due_diligence_snapshot(
    settings: Settings,
    entity_id: str,
    *,
    workspace_id: str,
    actor: str,
    verified: bool = False,
) -> dict[str, object]:
    role = _require_workspace_access(settings, workspace_id, actor)
    if verified and role not in {"system_admin", "owner"}:
        raise PermissionError("只有空间负责人可以保存已核验快照")
    with connection(settings) as conn:
        profile = _profile_payload(conn, entity_id, workspace_id=workspace_id, role=role)
        serialized = json_dumps(profile)
        state_hash = hashlib.sha256(serialized.encode()).hexdigest()
        snapshot_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO company_due_diligence_snapshots(
                id, workspace_id, entity_id, state_hash, snapshot_json,
                verified, verified_by, verified_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, CASE WHEN ? THEN datetime('now') END)
            ON CONFLICT(workspace_id, entity_id, state_hash) DO UPDATE SET
                verified = MAX(company_due_diligence_snapshots.verified, excluded.verified),
                verified_by = CASE WHEN excluded.verified = 1 THEN excluded.verified_by ELSE company_due_diligence_snapshots.verified_by END,
                verified_at = CASE WHEN excluded.verified = 1 THEN datetime('now') ELSE company_due_diligence_snapshots.verified_at END
            """,
            (
                snapshot_id,
                workspace_id,
                entity_id,
                state_hash,
                serialized,
                int(verified),
                actor if verified else None,
                int(verified),
            ),
        )
        row = conn.execute(
            """
            SELECT * FROM company_due_diligence_snapshots
            WHERE workspace_id = ? AND entity_id = ? AND state_hash = ?
            """,
            (workspace_id, entity_id, state_hash),
        ).fetchone()
        assert row is not None
        return _snapshot_payload(row)


def latest_verified_company_snapshot(
    settings: Settings,
    entity_id: str,
    *,
    workspace_id: str,
    actor: str,
) -> dict[str, object]:
    _require_workspace_access(settings, workspace_id, actor)
    with connection(settings) as conn:
        row = conn.execute(
            """
            SELECT * FROM company_due_diligence_snapshots
            WHERE workspace_id = ? AND entity_id = ? AND verified = 1
            ORDER BY verified_at DESC, created_at DESC LIMIT 1
            """,
            (workspace_id, entity_id),
        ).fetchone()
        if row is None:
            raise LookupError("verified company snapshot not found")
        return _snapshot_payload(row)


def aggregate_existing_company_data(
    settings: Settings,
    entity_id: str,
    *,
    workspace_id: str,
    actor: str,
) -> dict[str, object]:
    """Import only already-held project and workspace data into the company portrait."""
    role = _require_workspace_access(settings, workspace_id, actor)
    with connection(settings) as conn:
        entity = _require_entity(conn, workspace_id, entity_id)
        legal_name = str(entity["legal_name"])
        aliases = [
            str(row["alias"])
            for row in conn.execute(
                "SELECT alias FROM company_aliases WHERE entity_id = ?", (entity_id,)
            ).fetchall()
        ]
        names = sorted({name for name in [legal_name, *aliases] if name})
        imported_ids: list[str] = []
        source_counts: dict[str, int] = {}

        def import_row(
            *,
            evidence_type: str,
            title: str,
            content: str,
            source_type: str,
            source_name: str,
            source_url: str = "",
            locator: str = "",
            occurred_at: str = "",
            notice_id: str = "",
            match_field: str,
            sensitive: bool = False,
        ) -> None:
            if not _matches_company(names, title, content):
                return
            evidence = _upsert_evidence(
                conn,
                entity_id=entity_id,
                workspace_id=workspace_id,
                actor=actor,
                evidence_type=evidence_type,
                title=title,
                content=content,
                source_type=source_type,
                source_name=source_name,
                source_url=source_url,
                locator=locator,
                occurred_at=occurred_at,
                notice_id=notice_id,
                match_basis={"method": "exact_name_or_alias", "field": match_field},
                access_policy="workspace" if sensitive else "public",
                sensitive=sensitive,
            )
            imported_ids.append(evidence)
            source_counts[source_type] = source_counts.get(source_type, 0) + 1

        for row in conn.execute(
            """
            SELECT id, title, purchaser, content_text, source_site, source_url, publish_time
            FROM notices ORDER BY publish_time DESC, id LIMIT 1000
            """
        ).fetchall():
            excerpt = _matching_excerpt(
                names,
                " ".join(
                    [str(row["purchaser"] or ""), str(row["content_text"] or "")]
                ),
            )
            import_row(
                evidence_type="historical_project",
                title=str(row["title"]),
                content=excerpt,
                source_type="notice",
                source_name=str(row["source_site"]),
                source_url=str(row["source_url"]),
                occurred_at=str(row["publish_time"] or ""),
                notice_id=str(row["id"]),
                match_field="notice_title_purchaser_or_content",
            )

        for row in conn.execute(
            """
            SELECT o.notice_id, o.winner_name, o.summary, o.evidence_url,
                   o.evidence_text, o.finalized_at, n.title
            FROM opportunity_outcomes o JOIN notices n ON n.id = o.notice_id
            ORDER BY o.finalized_at DESC
            """
        ).fetchall():
            content = " ".join(
                [str(row["winner_name"] or ""), str(row["summary"] or ""), str(row["evidence_text"] or "")]
            )
            import_row(
                evidence_type="award_result",
                title=f"中标/成交结果：{row['title']}",
                content=content,
                source_type="award_result",
                source_name="项目复盘结果",
                source_url=str(row["evidence_url"] or ""),
                occurred_at=str(row["finalized_at"] or "")[:10],
                notice_id=str(row["notice_id"]),
                match_field="winner_name_or_result",
            )

        for row in conn.execute(
            """
            SELECT s.notice_id, s.stakeholder_name, s.organization_name, s.role,
                   s.evidence_url, s.evidence_text, n.title
            FROM opportunity_stakeholders s JOIN notices n ON n.id = s.notice_id
            WHERE s.status = 'active'
            """
        ).fetchall():
            content = " ".join(
                [str(row["organization_name"] or ""), str(row["stakeholder_name"]), str(row["evidence_text"] or "")]
            )
            import_row(
                evidence_type="stakeholder_relation",
                title=f"客户干系人：{row['stakeholder_name']}（{row['role']}）",
                content=content,
                source_type="stakeholder",
                source_name="客户干系人图谱",
                source_url=str(row["evidence_url"] or ""),
                notice_id=str(row["notice_id"]),
                match_field="stakeholder_organization",
                sensitive=True,
            )

        for row in conn.execute(
            """
            SELECT a.notice_id, a.title, a.outcome_note, a.source_ref,
                   s.organization_name, s.stakeholder_name, n.title project_title
            FROM opportunity_relationship_actions a
            JOIN notices n ON n.id = a.notice_id
            LEFT JOIN opportunity_stakeholders s ON s.id = a.stakeholder_id
            """
        ).fetchall():
            content = " ".join(
                [str(row["organization_name"] or ""), str(row["stakeholder_name"] or ""), str(row["title"]), str(row["outcome_note"] or "")]
            )
            import_row(
                evidence_type="relationship_action",
                title=f"关系动作：{row['title']}",
                content=content,
                source_type="relationship_action",
                source_name="客户关系动作",
                locator=str(row["source_ref"] or ""),
                notice_id=str(row["notice_id"]),
                match_field="relationship_action",
                sensitive=True,
            )

        for row in conn.execute(
            """
            SELECT id, title, content, source_type, evidence_url, related_notice_id, created_at
            FROM organization_memories WHERE workspace_id = ?
            """,
            (workspace_id,),
        ).fetchall():
            import_row(
                evidence_type="organization_memory",
                title=str(row["title"]),
                content=str(row["content"]),
                source_type="organization_memory",
                source_name=str(row["source_type"]),
                source_url=str(row["evidence_url"] or ""),
                occurred_at=str(row["created_at"] or "")[:10],
                notice_id=str(row["related_notice_id"] or ""),
                match_field="workspace_memory",
                sensitive=True,
            )

        for row in conn.execute(
            """
            SELECT title, content, asset_type, source_url, source_notice_id,
                   valid_until, sensitivity
            FROM bid_memory_assets
            WHERE workspace_id = ? AND withdrawn_at IS NULL
            """,
            (workspace_id,),
        ).fetchall():
            import_row(
                evidence_type="uploaded_material",
                title=str(row["title"]),
                content=str(row["content"]),
                source_type="bid_memory_asset",
                source_name=str(row["asset_type"]),
                source_url=str(row["source_url"] or ""),
                notice_id=str(row["source_notice_id"] or ""),
                match_field="workspace_upload_or_memory_asset",
                sensitive=str(row["sensitivity"] or "normal") != "normal",
            )

        _audit(
            conn,
            workspace_id,
            entity_id,
            "existing_company_data_aggregated",
            actor,
            {"source_counts": source_counts, "evidence_count": len(set(imported_ids))},
        )
        rows = conn.execute(
            "SELECT * FROM company_evidence WHERE entity_id = ? ORDER BY occurred_at DESC, created_at DESC",
            (entity_id,),
        ).fetchall()
        return {
            "entity": _entity_payload(conn, entity_id, role=role),
            "source_counts": source_counts,
            "imported_count": len(set(imported_ids)),
            "evidence": [_evidence_payload(row, role=role) for row in rows],
            "policy": "仅聚合本工作区已有数据；未调用外部受限数据源",
        }


def evaluate_company_risks(
    settings: Settings,
    entity_id: str,
    *,
    workspace_id: str,
    actor: str,
) -> dict[str, object]:
    """Create explainable signals without collapsing them into an opaque score."""
    role = _require_workspace_access(settings, workspace_id, actor)
    with connection(settings) as conn:
        entity = _require_entity(conn, workspace_id, entity_id)
        conn.execute(
            """
            DELETE FROM company_risk_signals
            WHERE entity_id = ? AND workspace_id = ? AND manually_confirmed_by IS NULL
            """,
            (entity_id, workspace_id),
        )
        evidence_rows = conn.execute(
            """
            SELECT * FROM company_evidence
            WHERE entity_id = ? AND workspace_id = ?
            ORDER BY occurred_at DESC, captured_at DESC
            """,
            (entity_id, workspace_id),
        ).fetchall()
        covered_dimensions: set[str] = set()
        for evidence in evidence_rows:
            evidence_type = str(evidence["evidence_type"])
            dimension = EVIDENCE_DIMENSIONS.get(evidence_type)
            if not dimension:
                continue
            if _evidence_expired(evidence):
                conn.execute(
                    "UPDATE company_evidence SET evidence_status = 'expired', updated_at = datetime('now') WHERE id = ?",
                    (evidence["id"],),
                )
            current = _evidence_is_current(evidence)
            if str(evidence["evidence_status"]) in {
                "withdrawn",
                "mismatched",
                "rejected",
                "expired",
            } or _evidence_expired(evidence):
                continue
            if current:
                covered_dimensions.add(dimension)
            if evidence_type in NEGATIVE_EVIDENCE_RULES:
                interpretation, impact, question, mitigation, severity = NEGATIVE_EVIDENCE_RULES[
                    evidence_type
                ]
                _insert_risk_signal(
                    conn,
                    workspace_id=workspace_id,
                    entity_id=entity_id,
                    evidence_id=str(evidence["id"]),
                    rule_key=f"evidence:{evidence_type}",
                    dimension=dimension,
                    signal_kind="risk",
                    fact_signal=_fact_excerpt(str(evidence["content_text"])),
                    interpretation=interpretation,
                    impact=impact,
                    question=question,
                    mitigation=mitigation,
                    severity=severity,
                    confidence=int(evidence["confidence"]),
                    status="active" if current else "needs_review",
                    valid_until=str(evidence["valid_until"] or ""),
                )
            elif evidence_type in {"award_result", "delivery_record", "cooperation_record"}:
                _insert_risk_signal(
                    conn,
                    workspace_id=workspace_id,
                    entity_id=entity_id,
                    evidence_id=str(evidence["id"]),
                    rule_key=f"fact:{evidence_type}",
                    dimension=dimension,
                    signal_kind="fact",
                    fact_signal=_fact_excerpt(str(evidence["content_text"])),
                    interpretation="已发现可核验的历史合作或履约事实",
                    impact="可作为合作经验参考，仍需核验项目相似度与当前有效性",
                    question="该项目与本次合作在规模、范围和交付条件上有哪些可比性？",
                    mitigation="由业务负责人复核相似度，不直接等同于本次履约能力。",
                    severity="info",
                    confidence=int(evidence["confidence"]),
                    status="active" if current else "needs_review",
                    valid_until=str(evidence["valid_until"] or ""),
                )

        if str(entity["identity_status"]) != "confirmed":
            _insert_missing_signal(
                conn,
                workspace_id,
                entity_id,
                "subject",
                "主体身份尚未用统一社会信用代码确认",
                "请核验营业执照原件并确认统一社会信用代码。",
            )
        elif "subject" not in covered_dimensions:
            _insert_missing_signal(
                conn,
                workspace_id,
                entity_id,
                "subject",
                "缺少当前有效的登记或股权证据",
                "请补充官方登记快照、股权结构和最终受益人确认材料。",
            )
        for dimension, label in PORTRAIT_DIMENSIONS.items():
            if dimension == "subject" or dimension in covered_dimensions:
                continue
            _insert_missing_signal(
                conn,
                workspace_id,
                entity_id,
                dimension,
                f"{label}信息尚未覆盖",
                _missing_question(dimension),
            )
        _audit(
            conn,
            workspace_id,
            entity_id,
            "company_risks_evaluated",
            actor,
            {"covered_dimensions": sorted(covered_dimensions)},
        )
        return _risk_summary(conn, entity_id, role=role)


def _entity_payload(conn: Any, entity_id: str, *, role: str) -> dict[str, object]:
    row = conn.execute("SELECT * FROM company_entities WHERE id = ?", (entity_id,)).fetchone()
    if row is None:
        raise LookupError("company entity not found")
    aliases = [
        {
            "alias": str(alias["alias"]),
            "alias_type": str(alias["alias_type"]),
            "confirmed": bool(alias["confirmed"]),
        }
        for alias in conn.execute(
            """
            SELECT alias, alias_type, confirmed FROM company_aliases
            WHERE entity_id = ? ORDER BY confirmed DESC, alias
            """,
            (entity_id,),
        ).fetchall()
    ]
    credit_code = str(row["unified_credit_code"] or "")
    return {
        "id": str(row["id"]),
        "workspace_id": str(row["workspace_id"]),
        "legal_name": str(row["legal_name"]),
        "unified_credit_code": credit_code if role in PRIVILEGED_ROLES else "",
        "unified_credit_code_masked": _mask_credit_code(credit_code),
        "region": str(row["region"] or ""),
        "legal_representative": str(row["legal_representative"] or "")
        if role in PRIVILEGED_ROLES
        else _mask_person(str(row["legal_representative"] or "")),
        "entity_type": str(row["entity_type"]),
        "identity_status": str(row["identity_status"]),
        "verification_status": str(row["verification_status"]),
        "last_verified_at": str(row["last_verified_at"] or ""),
        "aliases": aliases,
        "updated_at": str(row["updated_at"]),
    }


def _require_entity(conn: Any, workspace_id: str, entity_id: str) -> Any:
    row = conn.execute(
        "SELECT * FROM company_entities WHERE id = ? AND workspace_id = ?",
        (entity_id, workspace_id),
    ).fetchone()
    if row is None:
        raise LookupError("company entity not found")
    return row


def _require_notice(conn: Any, notice_id: str) -> None:
    if conn.execute("SELECT 1 FROM notices WHERE id = ?", (notice_id,)).fetchone() is None:
        raise LookupError("notice not found")


def _upsert_evidence(
    conn: Any,
    *,
    entity_id: str,
    workspace_id: str,
    actor: str,
    evidence_type: str,
    title: str,
    content: str,
    source_type: str,
    source_name: str,
    source_url: str,
    locator: str,
    occurred_at: str,
    notice_id: str,
    match_basis: dict[str, object],
    access_policy: str,
    sensitive: bool,
) -> str:
    safe_content = _controlled_text(content, "content", 12000)
    content_hash = hashlib.sha256(
        f"{source_type}|{title}|{safe_content}|{notice_id}".encode()
    ).hexdigest()
    evidence_id = content_hash[:32]
    conn.execute(
        """
        INSERT INTO company_evidence(
            id, workspace_id, entity_id, notice_id, evidence_type, title,
            source_type, source_name, source_url, source_locator,
            source_license, access_policy, access_frequency, snapshot_sha256,
            occurred_at, evidence_status,
            confidence, subject_match_basis_json, content_text,
            redacted_content, content_hash, sensitive, created_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'on_demand', ?, ?, 'verified', ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(workspace_id, entity_id, content_hash) DO UPDATE SET
            evidence_status = excluded.evidence_status,
            confidence = excluded.confidence,
            updated_at = datetime('now')
        """,
        (
            evidence_id,
            workspace_id,
            entity_id,
            notice_id or None,
            evidence_type,
            title[:240],
            source_type,
            source_name[:180],
            source_url[:2000],
            locator[:500],
            "existing_workspace_data",
            access_policy,
            content_hash,
            _date_text(occurred_at, "occurred_at"),
            90 if source_type in {"notice", "award_result"} else 75,
            json_dumps(match_basis),
            safe_content,
            _redact_text(safe_content) if sensitive else safe_content,
            content_hash,
            int(sensitive),
            actor.strip() or "admin",
        ),
    )
    return evidence_id


def _evidence_payload(row: Any, *, role: str) -> dict[str, object]:
    sensitive = bool(row["sensitive"])
    content = str(row["content_text"] or "")
    if sensitive and role not in SENSITIVE_VIEW_ROLES:
        content = str(row["redacted_content"] or "")
    return {
        "id": str(row["id"]),
        "entity_id": str(row["entity_id"]),
        "notice_id": str(row["notice_id"] or ""),
        "evidence_type": str(row["evidence_type"]),
        "title": str(row["title"]),
        "source_type": str(row["source_type"]),
        "source_name": str(row["source_name"] or ""),
        "source_url": str(row["source_url"] or ""),
        "source_locator": str(row["source_locator"] or ""),
        "source_license": str(row["source_license"] or ""),
        "access_policy": str(row["access_policy"]),
        "access_frequency": str(row["access_frequency"]),
        "snapshot_sha256": str(row["snapshot_sha256"]),
        "occurred_at": str(row["occurred_at"] or ""),
        "valid_from": str(row["valid_from"] or ""),
        "valid_until": str(row["valid_until"] or ""),
        "evidence_status": str(row["evidence_status"]),
        "confidence": int(row["confidence"]),
        "subject_match_basis": _json_object(row["subject_match_basis_json"]),
        "content_text": content,
        "sensitive": sensitive,
        "captured_at": str(row["captured_at"]),
    }


def _matches_company(names: list[str], *values: str) -> bool:
    normalized_values = [_normalize_name(value) for value in values]
    return any(
        normalized_name and any(normalized_name in value for value in normalized_values)
        for normalized_name in (_normalize_name(name) for name in names)
    )


def _matching_excerpt(names: list[str], content: str, radius: int = 240) -> str:
    normalized_content = _normalize_name(content)
    for name in names:
        if _normalize_name(name) in normalized_content:
            index = content.find(name)
            if index >= 0:
                return " ".join(content[max(0, index - radius) : index + len(name) + radius].split())
    return " ".join(content[: radius * 2].split())


def _redact_text(value: str) -> str:
    text = re.sub(r"(?<!\d)1\d{10}(?!\d)", "1**********", value)
    text = re.sub(r"(?<!\d)\d{17}[0-9Xx](?!\d)", "****已脱敏统一代码****", text)
    text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "***@***", text)
    return text


def _insert_risk_signal(
    conn: Any,
    *,
    workspace_id: str,
    entity_id: str,
    evidence_id: str,
    rule_key: str,
    dimension: str,
    signal_kind: str,
    fact_signal: str,
    interpretation: str,
    impact: str,
    question: str,
    mitigation: str,
    severity: str,
    confidence: int,
    status: str,
    valid_until: str,
) -> None:
    signal_id = hashlib.sha256(
        f"{workspace_id}|{entity_id}|{rule_key}|{fact_signal}".encode()
    ).hexdigest()[:32]
    conn.execute(
        """
        INSERT INTO company_risk_signals(
            id, workspace_id, entity_id, evidence_id, rule_key, dimension,
            signal_kind, fact_signal, risk_interpretation, business_impact,
            due_diligence_question, mitigation, severity, confidence,
            signal_status, valid_until
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(workspace_id, entity_id, rule_key, fact_signal) DO UPDATE SET
            evidence_id = excluded.evidence_id,
            risk_interpretation = excluded.risk_interpretation,
            business_impact = excluded.business_impact,
            due_diligence_question = excluded.due_diligence_question,
            mitigation = excluded.mitigation,
            severity = excluded.severity,
            confidence = excluded.confidence,
            signal_status = excluded.signal_status,
            valid_until = excluded.valid_until,
            updated_at = datetime('now')
        WHERE company_risk_signals.manually_confirmed_by IS NULL
        """,
        (
            signal_id,
            workspace_id,
            entity_id,
            evidence_id or None,
            rule_key,
            dimension,
            signal_kind,
            fact_signal,
            interpretation,
            impact,
            question,
            mitigation,
            severity,
            max(0, min(confidence, 100)),
            status,
            valid_until or None,
        ),
    )


def _insert_missing_signal(
    conn: Any,
    workspace_id: str,
    entity_id: str,
    dimension: str,
    fact: str,
    question: str,
) -> None:
    _insert_risk_signal(
        conn,
        workspace_id=workspace_id,
        entity_id=entity_id,
        evidence_id="",
        rule_key=f"missing:{dimension}",
        dimension=dimension,
        signal_kind="missing",
        fact_signal=fact,
        interpretation="这是信息缺口，不代表负面事实",
        impact="在证据补齐前，该维度无法形成确定结论",
        question=question,
        mitigation="补充权威来源或经授权材料后重新评估。",
        severity="info",
        confidence=100,
        status="needs_evidence",
        valid_until="",
    )


def _risk_summary(conn: Any, entity_id: str, *, role: str) -> dict[str, object]:
    rows = conn.execute(
        """
        SELECT signal.*, evidence.title evidence_title, evidence.source_url,
               evidence.occurred_at, evidence.evidence_status
        FROM company_risk_signals signal
        LEFT JOIN company_evidence evidence ON evidence.id = signal.evidence_id
        WHERE signal.entity_id = ?
        ORDER BY CASE signal.severity WHEN 'critical' THEN 3 WHEN 'warning' THEN 2 ELSE 1 END DESC,
                 signal.dimension, signal.created_at
        """,
        (entity_id,),
    ).fetchall()
    signals = [
        {
            "id": str(row["id"]),
            "evidence_id": str(row["evidence_id"] or ""),
            "evidence_title": str(row["evidence_title"] or ""),
            "source_url": str(row["source_url"] or ""),
            "occurred_at": str(row["occurred_at"] or ""),
            "dimension": str(row["dimension"]),
            "dimension_label": PORTRAIT_DIMENSIONS.get(
                str(row["dimension"]), str(row["dimension"])
            ),
            "signal_kind": str(row["signal_kind"]),
            "fact_signal": str(row["fact_signal"]),
            "risk_interpretation": str(row["risk_interpretation"]),
            "business_impact": str(row["business_impact"]),
            "due_diligence_question": str(row["due_diligence_question"]),
            "mitigation": str(row["mitigation"]),
            "severity": str(row["severity"]),
            "confidence": int(row["confidence"]),
            "signal_status": str(row["signal_status"]),
            "evidence_status": str(row["evidence_status"] or ""),
            "valid_until": str(row["valid_until"] or ""),
            "manually_confirmed_by": str(row["manually_confirmed_by"] or ""),
            "deterministic": bool(
                row["evidence_id"]
                and str(row["evidence_status"] or "") == "verified"
                and str(row["signal_status"]) == "active"
                and (
                    not str(row["valid_until"] or "")
                    or str(row["valid_until"] or "") >= _today()
                )
            ),
        }
        for row in rows
    ]
    return {
        "dimensions": [
            {"key": key, "label": label} for key, label in PORTRAIT_DIMENSIONS.items()
        ],
        "risks": [item for item in signals if item["signal_kind"] == "risk"],
        "facts": [item for item in signals if item["signal_kind"] == "fact"],
        "missing": [item for item in signals if item["signal_kind"] == "missing"],
        "has_opaque_overall_score": False,
        "visibility": "full" if role in PRIVILEGED_ROLES else "redacted",
    }


def _fact_excerpt(value: str, limit: int = 360) -> str:
    text = " ".join(value.split())
    return text[:limit] + ("…" if len(text) > limit else "")


def _missing_question(dimension: str) -> str:
    questions = {
        "operations": "请补充经营状态、纳税/财务和信用记录的有效证明。",
        "judicial": "请核验当前司法、执行、行政处罚及行业禁入状态。",
        "performance": "请补充可核验的同类项目、交付验收和客户证明。",
        "relationships": "请披露股东、高管、联合体、客户及潜在利益冲突关系。",
        "public_opinion": "请核验近期重大舆情、事故和对外公告，并确认事件状态。",
    }
    return questions.get(dimension, "请补充该维度的有效证据。")


def _evidence_expired(row: Any) -> bool:
    valid_until = str(row["valid_until"] or "")
    return bool(valid_until and valid_until < _today())


def _evidence_is_current(row: Any) -> bool:
    return str(row["evidence_status"] or "") == "verified" and not _evidence_expired(row)


def _due_at_text(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("due_at is required")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("due_at must be an ISO date or datetime") from exc
    if "T" not in text and " " not in text:
        return parsed.date().isoformat() + "T18:00:00"
    return parsed.isoformat(timespec="seconds")


def _task_payload(row: Any) -> dict[str, object]:
    return {
        "id": str(row["id"]),
        "workspace_id": str(row["workspace_id"]),
        "entity_id": str(row["entity_id"]),
        "notice_id": str(row["notice_id"] or ""),
        "risk_signal_id": str(row["risk_signal_id"] or ""),
        "title": str(row["title"]),
        "question": str(row["question"]),
        "task_type": str(row["task_type"]),
        "assignee_open_id": str(row["assignee_open_id"] or ""),
        "assignee_name": str(row["assignee_name"] or ""),
        "due_at": str(row["due_at"]),
        "status": str(row["status"]),
        "feishu_task_guid": str(row["feishu_task_guid"] or ""),
        "feishu_task_status": str(row["feishu_task_status"]),
        "feishu_receipt": _json_object(row["feishu_receipt_json"]),
        "feishu_sync_error": str(row["feishu_sync_error"] or ""),
        "feishu_task_synced_at": str(row["feishu_task_synced_at"] or ""),
    }


def _profile_payload(
    conn: Any,
    entity_id: str,
    *,
    workspace_id: str,
    role: str,
) -> dict[str, object]:
    entity = _require_entity(conn, workspace_id, entity_id)
    evidence_rows = conn.execute(
        """
        SELECT * FROM company_evidence WHERE workspace_id = ? AND entity_id = ?
        ORDER BY occurred_at DESC, captured_at DESC
        """,
        (workspace_id, entity_id),
    ).fetchall()
    evidence = [_evidence_payload(row, role=role) for row in evidence_rows]
    risk_summary = _risk_summary(conn, entity_id, role=role)
    relationship_rows = conn.execute(
        """
        SELECT * FROM company_relationships
        WHERE workspace_id = ? AND from_entity_id = ?
        ORDER BY basis_type, relationship_type, related_label
        """,
        (workspace_id, entity_id),
    ).fetchall()
    review_rows = conn.execute(
        """
        SELECT * FROM due_diligence_reviews
        WHERE workspace_id = ? AND entity_id = ?
        ORDER BY confirmed_at DESC
        """,
        (workspace_id, entity_id),
    ).fetchall()
    task_rows = conn.execute(
        """
        SELECT * FROM company_due_diligence_tasks
        WHERE workspace_id = ? AND entity_id = ? ORDER BY due_at, created_at
        """,
        (workspace_id, entity_id),
    ).fetchall()
    subscription = conn.execute(
        """
        SELECT * FROM company_change_subscriptions
        WHERE workspace_id = ? AND entity_id = ?
        """,
        (workspace_id, entity_id),
    ).fetchone()
    active_risks = [
        item
        for item in risk_summary["risks"]
        if item["signal_status"] in {"active", "needs_review"}
    ]
    dimensions = []
    for key, label in PORTRAIT_DIMENSIONS.items():
        dimension_risks = [item for item in active_risks if item["dimension"] == key]
        dimension_missing = [
            item for item in risk_summary["missing"] if item["dimension"] == key
        ]
        evidence_count = sum(
            EVIDENCE_DIMENSIONS.get(str(item["evidence_type"])) == key for item in evidence
        )
        state = (
            "risk"
            if dimension_risks
            else "missing"
            if dimension_missing
            else "covered"
            if evidence_count
            else "missing"
        )
        dimensions.append(
            {
                "key": key,
                "label": label,
                "state": state,
                "evidence_count": evidence_count,
                "risk_count": len(dimension_risks),
                "missing_count": len(dimension_missing),
            }
        )
    reviews = [_review_payload(row) for row in review_rows]
    current_review = reviews[0] if reviews else None
    if current_review and str(current_review["valid_until"]) < _today():
        current_review = {**current_review, "review_status": "expired"}
    risk_level = (
        "critical"
        if any(item["severity"] == "critical" for item in active_risks)
        else "warning"
        if active_risks
        else "pending"
        if risk_summary["missing"]
        else "clear"
    )
    return {
        "entity": _entity_payload(conn, entity_id, role=role),
        "summary": {
            "recommendation": current_review["recommendation"] if current_review else "pending",
            "risk_level": risk_level,
            "evidence_completeness": round(
                100 * sum(item["state"] != "missing" for item in dimensions) / len(dimensions)
            ),
            "evidence_count": len(evidence),
            "manual_review_status": current_review["review_status"] if current_review else "pending",
            "last_updated_at": max(
                [str(entity["updated_at"])]
                + [str(row["updated_at"]) for row in evidence_rows]
            ),
        },
        "dimensions": dimensions,
        "evidence": evidence,
        "risk_summary": risk_summary,
        "relationships": [_relationship_payload(row) for row in relationship_rows],
        "relationship_graph": {
            "nodes": [
                {"id": entity_id, "label": str(entity["legal_name"]), "type": "company"}
            ]
            + [
                {
                    "id": str(row["to_entity_id"] or row["related_object_id"] or row["id"]),
                    "label": str(row["related_label"]),
                    "type": str(row["related_object_type"]),
                }
                for row in relationship_rows
            ],
            "edges": [_relationship_payload(row) for row in relationship_rows],
            "basis_legend": {
                "factual": "事实关系",
                "inferred": "推断关系",
                "manual": "人工确认关系",
            },
        },
        "reviews": reviews,
        "current_review": current_review,
        "tasks": [_task_payload(row) for row in task_rows],
        "change_subscription": {
            "id": str(subscription["id"]),
            "event_types": json.loads(str(subscription["event_types_json"])),
            "status": str(subscription["status"]),
        }
        if subscription
        else None,
        "integration": {
            "capability_passport_boundary": "企业能力护照继续评估本企业投标能力；本画像只评估外部合作方",
            "relation_graph_grammar": "沿用可信关系图的证据ID、事实/推断/人工关系和统一状态语言",
        },
    }


def _relationship_payload(row: Any) -> dict[str, object]:
    return {
        "id": str(row["id"]),
        "from_entity_id": str(row["from_entity_id"]),
        "to_entity_id": str(row["to_entity_id"] or ""),
        "related_object_type": str(row["related_object_type"]),
        "related_object_id": str(row["related_object_id"] or ""),
        "related_label": str(row["related_label"]),
        "relationship_type": str(row["relationship_type"]),
        "basis_type": str(row["basis_type"]),
        "evidence_id": str(row["evidence_id"] or ""),
        "confidence": int(row["confidence"]),
        "relationship_status": str(row["relationship_status"]),
        "valid_from": str(row["valid_from"] or ""),
        "valid_until": str(row["valid_until"] or ""),
    }


def _review_payload(row: Any) -> dict[str, object]:
    return {
        "id": str(row["id"]),
        "entity_id": str(row["entity_id"]),
        "notice_id": str(row["notice_id"] or ""),
        "recommendation": str(row["recommendation"]),
        "reason": str(row["reason"]),
        "conditions": json.loads(str(row["conditions_json"] or "[]")),
        "valid_until": str(row["valid_until"]),
        "review_status": str(row["review_status"]),
        "previous_review_id": str(row["previous_review_id"] or ""),
        "confirmed_by": str(row["confirmed_by"]),
        "confirmed_at": str(row["confirmed_at"]),
    }


def _snapshot_payload(row: Any) -> dict[str, object]:
    return {
        "id": str(row["id"]),
        "entity_id": str(row["entity_id"]),
        "state_hash": str(row["state_hash"]),
        "verified": bool(row["verified"]),
        "verified_by": str(row["verified_by"] or ""),
        "verified_at": str(row["verified_at"] or ""),
        "created_at": str(row["created_at"]),
        "profile": _json_object(row["snapshot_json"]),
        "offline_ready": True,
    }


def _require_workspace_access(settings: Settings, workspace_id: str, actor: str) -> str:
    workspace = workspace_id.strip()
    if not workspace:
        raise ValueError("workspace_id is required")
    actor_text = actor.strip() or "admin"
    with connection(settings) as conn:
        exists = conn.execute(
            "SELECT 1 FROM organization_workspaces WHERE id = ? AND status = 'active'",
            (workspace,),
        ).fetchone()
        if exists is None:
            raise LookupError("organization workspace not found")
        if actor_text in {"admin", "system", "web:admin"}:
            return "system_admin"
        member = conn.execute(
            """
            SELECT role FROM organization_members
            WHERE workspace_id = ? AND member_open_id = ? AND status = 'active'
            """,
            (workspace, actor_text),
        ).fetchone()
    if member is None:
        raise PermissionError("当前账号不属于该组织空间")
    return str(member["role"])


def _insert_alias(
    conn: Any,
    workspace_id: str,
    entity_id: str,
    alias: str,
    alias_type: str,
    source_type: str,
    actor: str,
    confirmed: bool,
) -> None:
    alias_id = hashlib.sha256(
        f"{workspace_id}|{entity_id}|{alias_type}|{_normalize_name(alias)}".encode()
    ).hexdigest()[:24]
    conn.execute(
        """
        INSERT INTO company_aliases(
            id, workspace_id, entity_id, alias, alias_type, source_type,
            confirmed, created_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(entity_id, alias, alias_type) DO UPDATE SET
            confirmed = MAX(company_aliases.confirmed, excluded.confirmed)
        """,
        (
            alias_id,
            workspace_id,
            entity_id,
            alias,
            alias_type,
            source_type,
            int(confirmed),
            actor.strip() or "admin",
        ),
    )


def _audit(
    conn: Any,
    workspace_id: str,
    entity_id: str,
    action: str,
    actor: str,
    payload: dict[str, object],
) -> None:
    conn.execute(
        """
        INSERT INTO company_due_diligence_audit_events(
            id, workspace_id, entity_id, action, actor, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid4()),
            workspace_id,
            entity_id or None,
            action,
            actor.strip() or "admin",
            json_dumps(payload),
        ),
    )


def _credit_code(value: object, *, required: bool) -> str:
    text = re.sub(r"\s+", "", str(value or "").upper())
    if not text and not required:
        return ""
    if not USCC_PATTERN.fullmatch(text):
        raise ValueError("unified_credit_code must be a valid 18-character code")
    return text


def _controlled_text(
    value: object,
    field: str,
    max_length: int,
    *,
    required: bool = True,
) -> str:
    text = " ".join(str(value or "").split())
    if required and not text:
        raise ValueError(f"{field} is required")
    if len(text) > max_length:
        raise ValueError(f"{field} is too long")
    if any(ord(char) < 32 for char in text):
        raise ValueError(f"{field} contains control characters")
    return text


def _choice(value: object, field: str, choices: set[str]) -> str:
    text = str(value or "").strip()
    if text not in choices:
        raise ValueError(f"{field} must be one of: {', '.join(sorted(choices))}")
    return text


def _date_text(value: object, field: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidate = text[:10]
    try:
        date.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD") from exc
    return candidate


def _snapshot_hash(value: object, content: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return hashlib.sha256(content.encode()).hexdigest()
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        raise ValueError("snapshot_sha256 must be a 64-character hexadecimal hash")
    return text


def _normalize_name(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", value.lower())


def _mask_credit_code(value: str) -> str:
    return f"{value[:4]}**********{value[-4:]}" if len(value) == 18 else ""


def _mask_person(value: str) -> str:
    if not value:
        return ""
    return value[0] + "*" * max(1, len(value) - 1)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today() -> str:
    return date.today().isoformat()


def _json_object(value: object) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
