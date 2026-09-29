from __future__ import annotations

from collections import defaultdict
from datetime import date
import hashlib
import json
from pathlib import PurePosixPath
import re
import sqlite3
from typing import Any, Iterable
from urllib.parse import unquote, urlparse
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps
from tendertrace.digital_twin import build_digital_twin


EVIDENCE_STATUS_LABELS = {
    "verified": "已验证",
    "pending": "待确认",
    "expired": "已过期",
    "conflict": "存在冲突",
    "unavailable": "来源不可访问",
}

CLAIM_STATUS_LABELS = {
    "supported": "证据充分",
    "pending": "待确认",
    "recheck": "版本变化待复核",
    "conflict": "存在冲突",
    "rejected": "人工驳回",
}

CLAIM_TYPE_LABELS = {
    "fact": "项目事实",
    "score": "评分判断",
    "requirement": "招标要求",
    "capability_match": "能力匹配",
    "risk": "风险提示",
    "recommendation": "行动建议",
    "agent_opinion": "Agent 意见",
    "decision": "人工决策",
    "attachment": "附件证据",
}

REVIEW_ACTION_STATUS = {
    "confirm": "verified",
    "reject": "conflict",
    "request_more": "pending",
    "mark_unavailable": "unavailable",
}

_DATE_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}[年./-]\s?\d{1,2}[月./-]\s?\d{1,2}日?")
_AMOUNT_RE = re.compile(r"(?<![\d.])(?:人民币\s*)?[\d,]+(?:\.\d+)?\s*(?:亿元|万元|元)(?![A-Za-z0-9])")
_PARAMETER_RE = re.compile(
    r"(?<![\d.])\d+(?:\.\d+)?\s*(?:GB|TB|GHz|MHz|Mbps|Gbps|核|台|套|个|项|%|℃|V|A|W)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_NEGATION_RE = re.compile(r"不得|不接受|禁止|无效|废标|否决|不低于|不高于|至少|至多|必须|须")
_PAGE_RE = re.compile(r"第\s*(\d+)\s*页")
_PARAGRAPH_RE = re.compile(r"第\s*(\d+)\s*(?:段|自然段)")


def build_evidence_microscope(
    settings: Settings,
    notice_id: str,
    *,
    claim_type: str = "",
    claim_key: str = "",
) -> dict[str, object] | None:
    """Build and persist the auditable evidence graph for one opportunity."""
    init_db(settings)
    notice_id = notice_id.strip()
    twin = build_digital_twin(settings, notice_id)
    with connection(settings) as conn:
        notice = conn.execute("SELECT * FROM notices WHERE id = ?", (notice_id,)).fetchone()
        if notice is None:
            return None
        revisions = conn.execute(
            "SELECT * FROM notice_revisions WHERE notice_id = ? ORDER BY created_at, rowid",
            (notice_id,),
        ).fetchall()
        pending_revision_ids = {
            str(row["revision_id"])
            for row in conn.execute(
                "SELECT revision_id FROM notice_change_reviews WHERE notice_id = ? AND status = 'pending'",
                (notice_id,),
            ).fetchall()
        }
        requirements = conn.execute(
            "SELECT * FROM opportunity_requirements WHERE notice_id = ? ORDER BY mandatory DESC, requirement_key",
            (notice_id,),
        ).fetchall()
        matches = conn.execute(
            """
            SELECT matched.*, requirement.requirement_key, requirement.title AS requirement_title,
                   requirement.evidence_text AS requirement_evidence_text,
                   requirement.source_url AS requirement_source_url,
                   requirement.source_locator AS requirement_source_locator,
                   capability.title AS capability_title,
                   capability.capability_type,
                   capability.evidence_text AS capability_evidence_text,
                   capability.source_url AS capability_source_url,
                   capability.source_locator AS capability_source_locator,
                   capability.verification_status AS capability_verification_status,
                   capability.valid_until AS capability_valid_until,
                   capability.updated_at AS capability_updated_at
            FROM requirement_capability_matches matched
            JOIN opportunity_requirements requirement ON requirement.id = matched.requirement_id
            LEFT JOIN enterprise_capabilities capability ON capability.id = matched.capability_id
            WHERE matched.notice_id = ?
            ORDER BY requirement.requirement_key, matched.rowid
            """,
            (notice_id,),
        ).fetchall()
        opinions = conn.execute(
            """
            SELECT opinion.*, requirement.requirement_key, requirement.title AS requirement_title,
                   requirement.evidence_text AS requirement_evidence_text,
                   requirement.source_url AS requirement_source_url,
                   requirement.source_locator AS requirement_source_locator
            FROM requirement_review_opinions opinion
            JOIN opportunity_requirements requirement ON requirement.id = opinion.requirement_id
            WHERE opinion.notice_id = ?
            ORDER BY opinion.review_id, opinion.agent_role
            """,
            (notice_id,),
        ).fetchall()
        attachments = conn.execute(
            "SELECT * FROM attachment_snapshots WHERE notice_id = ? ORDER BY created_at, rowid",
            (notice_id,),
        ).fetchall()
        workflow = conn.execute(
            "SELECT * FROM opportunity_workflows WHERE notice_id = ?",
            (notice_id,),
        ).fetchone()
        page_artifact = conn.execute(
            "SELECT * FROM page_artifacts WHERE notice_id = ? ORDER BY fetched_at DESC, rowid DESC LIMIT 1",
            (notice_id,),
        ).fetchone()

        latest_revision = revisions[-1] if revisions else None
        latest_revision_id = str(latest_revision["id"]) if latest_revision else ""
        latest_changed_fields = set(_json_list(latest_revision["changed_fields_json"])) if latest_revision else set()
        latest_pending = latest_revision_id in pending_revision_ids
        notice_text = _text(notice["content_text"] or notice["core_content"] or notice["title"])
        notice_source_status = "unavailable" if page_artifact is not None and int(page_artifact["blocked"] or 0) else "verified"
        notice_source = _source_spec(
            notice_id=notice_id,
            source_type="webpage",
            source_id=f"notice:{notice_id}",
            source_site=str(notice["source_site"] or ""),
            source_url=str(notice["source_url"] or ""),
            file_name=str(notice["title"] or "公告原文"),
            quote=notice_text[:5000],
            section_path="公告正文",
            selector="document.body",
            parent_content_hash=str(notice["snapshot_sha256"] or (page_artifact["content_sha256"] if page_artifact else "")),
            revision_id=latest_revision_id,
            captured_at=str((page_artifact["fetched_at"] if page_artifact else None) or notice["last_seen_at"] or ""),
            extraction_method="web_snapshot",
            locator_confidence=95 if notice_text else 0,
            verified_status=notice_source_status if notice_text else "unavailable",
        )
        base_id, _, base_changed = _ensure_source(conn, notice_source)

        fields = _json_dict(notice["fields_json"])
        structured = _dict(fields.get("structured_fields"))
        fact_values = {
            "project_no": fields.get("project_no") or structured.get("project_no"),
            "budget": fields.get("budget") or structured.get("budget"),
            "bid_deadline": fields.get("bid_deadline") or structured.get("bid_deadline"),
            "purchaser": notice["purchaser"],
            "publish_time": notice["publish_time"],
        }
        fact_labels = {
            "project_no": "项目编号",
            "budget": "预算金额",
            "bid_deadline": "投标截止",
            "purchaser": "采购主体",
            "publish_time": "发布日期",
        }
        claim_specs: list[dict[str, object]] = []

        for field_name, raw_value in fact_values.items():
            value = _text(raw_value)
            if not value:
                continue
            quote, before, after = _quote_context(notice_text, value)
            forced_pending = latest_pending and field_name in latest_changed_fields
            spec = _source_spec(
                notice_id=notice_id,
                source_type="webpage",
                source_id=f"notice:{notice_id}:{field_name}",
                source_site=str(notice["source_site"] or ""),
                source_url=str(notice["source_url"] or ""),
                file_name=str(notice["title"] or "公告原文"),
                quote=quote or value,
                context_before=before,
                context_after=after,
                section_path=f"公告正文 / {fact_labels[field_name]}",
                selector="document.body",
                parent_content_hash=str(notice["snapshot_sha256"] or ""),
                revision_id=latest_revision_id,
                captured_at=str(notice["last_seen_at"] or ""),
                extraction_method="web_snapshot",
                locator_confidence=98 if value in notice_text else 75,
                verified_status="pending" if forced_pending else notice_source_status,
                force_pending=forced_pending,
            )
            source_id, _, source_changed = _ensure_source(conn, spec)
            claim_specs.append(
                _claim_spec(
                    notice_id,
                    "fact",
                    field_name,
                    fact_labels[field_name],
                    value,
                    [(source_id, "supports", f"原文直接记录{fact_labels[field_name]}")],
                    source_changed,
                )
            )

        requirement_sources: dict[str, str] = {}
        for requirement in requirements:
            requirement_id = str(requirement["id"])
            source_spec = _located_source(
                notice_id=notice_id,
                source_id=f"requirement:{requirement_id}",
                source_site=str(notice["source_site"] or ""),
                source_url=str(requirement["source_url"] or notice["source_url"] or ""),
                locator=str(requirement["source_locator"] or ""),
                quote=str(requirement["evidence_text"] or ""),
                revision_id=latest_revision_id,
                captured_at=str(requirement["updated_at"] or ""),
                verified_status="pending" if str(requirement["status"] or "") in {"pending", "review"} else "verified",
                extraction_method="requirement_extraction",
                locator_confidence=int(requirement["confidence"] or 0),
            )
            evidence_id, _, evidence_changed = _ensure_source(conn, source_spec)
            requirement_sources[requirement_id] = evidence_id
            claim_specs.append(
                _claim_spec(
                    notice_id,
                    "requirement",
                    str(requirement["requirement_key"]),
                    str(requirement["title"]),
                    str(requirement["evidence_text"]),
                    [(evidence_id, "supports", "要求结论来自该原文片段")],
                    evidence_changed,
                )
            )
            if int(requirement["mandatory"] or 0) and str(requirement["status"] or "") in {"pending", "review"}:
                claim_specs.append(
                    _claim_spec(
                        notice_id,
                        "risk",
                        f"mandatory:{requirement_id}",
                        "强制要求尚未确认",
                        f"{requirement['requirement_key']} · {requirement['title']}",
                        [(evidence_id, "supports", "强制条款尚未完成确认")],
                        evidence_changed,
                    )
                )

        capability_sources: dict[str, str] = {}
        for match in matches:
            capability_id = str(match["capability_id"] or "")
            capability_evidence_id = ""
            capability_changed = False
            if capability_id and str(match["capability_evidence_text"] or ""):
                capability_status = _capability_status(
                    str(match["capability_verification_status"] or "draft"),
                    str(match["capability_valid_until"] or ""),
                )
                cap_spec = _located_source(
                    notice_id=notice_id,
                    source_id=f"capability:{capability_id}",
                    source_site="企业材料库",
                    source_url=str(match["capability_source_url"] or ""),
                    locator=str(match["capability_source_locator"] or ""),
                    quote=str(match["capability_evidence_text"] or ""),
                    revision_id="",
                    captured_at=str(match["capability_updated_at"] or ""),
                    verified_status=capability_status,
                    extraction_method="enterprise_material",
                    locator_confidence=100 if capability_status == "verified" else 70,
                    force_source_type="enterprise_material",
                )
                capability_evidence_id, _, capability_changed = _ensure_source(conn, cap_spec)
                capability_sources[capability_id] = capability_evidence_id
            links: list[tuple[str, str, str]] = []
            requirement_evidence_id = requirement_sources.get(str(match["requirement_id"]), "")
            if requirement_evidence_id:
                links.append((requirement_evidence_id, "context", "招标要求原文"))
            if capability_evidence_id:
                stance = "contradicts" if str(match["verdict"]) == "gap" else "supports"
                links.append((capability_evidence_id, stance, "企业材料与要求的对照依据"))
            claim_specs.append(
                _claim_spec(
                    notice_id,
                    "capability_match",
                    str(match["id"]),
                    f"{match['requirement_key']} · {match['capability_title'] or '企业证据待补'}",
                    str(match["rationale"] or "尚未形成可审计判断"),
                    links,
                    capability_changed,
                )
            )

        scores = _dict((twin or {}).get("scores"))
        for score_key, score_value in scores.items():
            score = _dict(score_value)
            if score_key == "opportunity_value":
                score_links = [(base_id, "supports", "机会评分基于公告事实与来源状态")]
            elif score_key == "enterprise_fit":
                score_links = [
                    (evidence_id, "context", "企业适配度引用的招标要求")
                    for evidence_id in requirement_sources.values()
                ] + [
                    (evidence_id, "supports", "企业适配度引用的企业材料")
                    for evidence_id in capability_sources.values()
                ]
            else:
                score_links = [
                    (evidence_id, "context", "投标准备度引用的要求证据")
                    for evidence_id in requirement_sources.values()
                ] or [(base_id, "context", "投标准备度引用的公告版本")]
            components = [
                f"{item.get('label', '维度')} {item.get('score', 0)}分：{item.get('evidence', '依据待补')}"
                for item in score.get("components", [])
                if isinstance(item, dict)
            ]
            claim_specs.append(
                _claim_spec(
                    notice_id,
                    "score",
                    str(score_key),
                    str(score.get("label") or score_key),
                    f"{score.get('score', 0)}分 · {'；'.join(components)}",
                    score_links,
                    base_changed,
                )
            )
            for missing in score.get("missing", []):
                missing_text = _text(missing)
                if not missing_text:
                    continue
                claim_specs.append(
                    _claim_spec(
                        notice_id,
                        "risk",
                        f"score:{score_key}:{hashlib.sha256(missing_text.encode('utf-8')).hexdigest()[:12]}",
                        f"{score.get('label') or score_key}待补",
                        missing_text,
                        score_links,
                        base_changed,
                    )
                )

        for index, action in enumerate((twin or {}).get("next_actions", [])):
            if not isinstance(action, dict):
                continue
            title = _text(action.get("title"))
            claim_specs.append(
                _claim_spec(
                    notice_id,
                    "recommendation",
                    f"digital_twin:{index}:{hashlib.sha256(title.encode('utf-8')).hexdigest()[:12]}",
                    title or "推进建议",
                    str(action.get("reason") or "基于当前档案状态生成"),
                    [(base_id, "context", "建议基于当前项目档案版本")],
                    base_changed,
                )
            )

        attachment_sources: dict[str, str] = {}
        for attachment in attachments:
            attachment_id = str(attachment["id"])
            attachment_type = _attachment_source_type(str(attachment["name"] or ""), str(attachment["url"] or ""))
            quote = str(attachment["text_excerpt"] or "")
            extraction_method = f"{attachment_type}_text" if quote else "ocr_required"
            status = "verified" if str(attachment["status"] or "") == "extracted" and quote else "pending"
            if str(attachment["status"] or "") in {"failed", "blocked"}:
                status = "unavailable"
            spec = _located_source(
                notice_id=notice_id,
                source_id=f"attachment:{attachment_id}",
                source_site=str(notice["source_site"] or ""),
                source_url=str(attachment["url"] or ""),
                locator=str(attachment["name"] or "附件"),
                quote=quote or str(attachment["error"] or "附件正文尚未提取"),
                revision_id=latest_revision_id,
                captured_at=str(attachment["created_at"] or ""),
                verified_status=status,
                extraction_method=extraction_method,
                locator_confidence=90 if quote else 0,
                force_source_type=attachment_type,
                parent_content_hash=str(attachment["sha256"] or ""),
            )
            evidence_id, _, evidence_changed = _ensure_source(conn, spec)
            attachment_sources[attachment_id] = evidence_id
            claim_specs.append(
                _claim_spec(
                    notice_id,
                    "attachment",
                    attachment_id,
                    str(attachment["name"] or "附件证据"),
                    quote[:300] if quote else "正文待 OCR 或人工补录",
                    [(evidence_id, "supports" if status == "verified" else "context", "附件正文与定位信息")],
                    evidence_changed,
                )
            )

        matches_by_requirement: dict[str, list[sqlite3.Row]] = defaultdict(list)
        for match in matches:
            matches_by_requirement[str(match["requirement_id"])].append(match)
        opinion_claim_keys: dict[str, str] = {}
        for opinion in opinions:
            links = []
            requirement_id = str(opinion["requirement_id"])
            decision = str(opinion["decision"])
            if requirement_sources.get(requirement_id):
                links.append((requirement_sources[requirement_id], _opinion_stance(decision), "Agent 审阅的招标原文"))
            requirement_matches = matches_by_requirement.get(requirement_id, [])
            preferred_verdicts = {
                "reject": {"gap"},
                "accept": {"supported"},
                "escalate": {"needs_evidence"},
            }.get(decision, set())
            selected_matches = [
                match for match in requirement_matches
                if str(match["verdict"]) in preferred_verdicts
            ] or requirement_matches
            for match in selected_matches:
                capability_id = str(match["capability_id"] or "")
                if capability_sources.get(capability_id):
                    links.append((capability_sources[capability_id], _opinion_stance(decision), "Agent 审阅的企业材料"))
            opinion_id = str(opinion["id"])
            opinion_claim_keys[opinion_id] = opinion_id
            claim_specs.append(
                _claim_spec(
                    notice_id,
                    "agent_opinion",
                    opinion_id,
                    f"{_agent_label(str(opinion['agent_role']))} · {opinion['requirement_key']}",
                    str(opinion["rationale"] or "未提供判断依据"),
                    links,
                    False,
                )
            )

        if workflow is not None and (str(workflow["decision"] or "pending") != "pending" or str(workflow["decision_reason"] or "")):
            decision_links = [
                (evidence_id, "context", "人工决策参考的已登记要求")
                for evidence_id in list(requirement_sources.values())[:12]
            ] or [(base_id, "context", "人工决策参考的公告原文")]
            claim_specs.append(
                _claim_spec(
                    notice_id,
                    "decision",
                    "bid_decision",
                    "投标决策",
                    f"{workflow['decision']} · {workflow['decision_reason'] or '未填写理由'}",
                    decision_links,
                    False,
                )
            )
        if workflow is not None and str(workflow["next_action"] or ""):
            claim_specs.append(
                _claim_spec(
                    notice_id,
                    "recommendation",
                    "next_action",
                    "下一步行动",
                    str(workflow["next_action"]),
                    [(base_id, "context", "行动建议基于当前项目版本")],
                    base_changed,
                )
            )

        _sync_revision_evidence(conn, notice, revisions)
        for spec in claim_specs:
            _ensure_claim(conn, spec)

    return _load_payload(settings, notice_id, claim_type=claim_type, claim_key=claim_key)


def review_evidence(
    settings: Settings,
    notice_id: str,
    evidence_id: str,
    *,
    action: str,
    actor: str,
    reason: str,
) -> dict[str, object]:
    if action not in REVIEW_ACTION_STATUS:
        raise ValueError(f"unsupported evidence action: {action}")
    actor = actor.strip()
    reason = reason.strip()
    if not actor or not reason:
        raise ValueError("actor and reason are required")
    with connection(settings) as conn:
        source = conn.execute(
            "SELECT * FROM evidence_sources WHERE id = ? AND notice_id = ?",
            (evidence_id, notice_id),
        ).fetchone()
        if source is None:
            raise LookupError("evidence source not found")
        previous_status = str(source["verified_status"])
        new_status = REVIEW_ACTION_STATUS[action]
        conn.execute(
            """
            UPDATE evidence_sources
            SET verified_status = ?, confirmed_by = ?, confirmed_at = datetime('now'),
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (new_status, actor, evidence_id),
        )
        claim_rows = conn.execute(
            "SELECT claim_id FROM evidence_claim_links WHERE evidence_id = ?",
            (evidence_id,),
        ).fetchall()
        claim_ids = [str(row["claim_id"]) for row in claim_rows]
        for claim_id in claim_ids:
            _refresh_claim_status(conn, claim_id)
            conn.execute(
                """
                INSERT INTO evidence_audit_events(
                    id, notice_id, evidence_id, claim_id, action, actor, reason,
                    previous_status, new_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()), notice_id, evidence_id, claim_id, action,
                    actor, reason, previous_status, new_status,
                ),
            )
        if not claim_ids:
            conn.execute(
                """
                INSERT INTO evidence_audit_events(
                    id, notice_id, evidence_id, action, actor, reason,
                    previous_status, new_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid4()), notice_id, evidence_id, action, actor, reason, previous_status, new_status),
            )
    payload = build_evidence_microscope(settings, notice_id)
    assert payload is not None
    return payload


def invalidate_evidence_for_revision(
    conn: sqlite3.Connection,
    *,
    notice_id: str,
    revision_id: str,
    changed_fields: Iterable[str],
) -> int:
    """Expire evidence identities affected by a newly recorded notice version."""
    fields = set(changed_fields)
    source_ids = {f"notice:{notice_id}", *(f"notice:{notice_id}:{field}" for field in fields)}
    clauses = ["source_id IN ({})".format(",".join("?" for _ in source_ids))]
    params: list[object] = [notice_id, *sorted(source_ids)]
    if fields & {"content_text", "core_content", "attachments", "attachment_fingerprints"}:
        clauses.extend(("source_id LIKE 'requirement:%'", "source_id LIKE 'attachment:%'"))
    rows = conn.execute(
        f"""
        SELECT * FROM evidence_sources
        WHERE notice_id = ? AND verified_status <> 'expired'
          AND ({' OR '.join(clauses)})
        """,
        params,
    ).fetchall()
    for source in rows:
        conn.execute(
            "UPDATE evidence_sources SET verified_status = 'expired', updated_at = datetime('now') WHERE id = ?",
            (source["id"],),
        )
        claims = conn.execute(
            "SELECT claim_id FROM evidence_claim_links WHERE evidence_id = ?",
            (source["id"],),
        ).fetchall()
        for claim in claims:
            conn.execute(
                "UPDATE evidence_claims SET status = 'recheck', updated_at = datetime('now') WHERE id = ?",
                (claim["claim_id"],),
            )
            conn.execute(
                """
                INSERT INTO evidence_audit_events(
                    id, notice_id, evidence_id, claim_id, action, actor, reason,
                    previous_status, new_status
                ) VALUES (?, ?, ?, ?, 'source_invalidated', 'system:notice_revision', ?, ?, 'expired')
                """,
                (
                    str(uuid4()), notice_id, source["id"], claim["claim_id"],
                    f"公告版本 {revision_id} 变更字段：{', '.join(sorted(fields))}",
                    source["verified_status"],
                ),
            )
    return len(rows)


def _load_payload(
    settings: Settings,
    notice_id: str,
    *,
    claim_type: str,
    claim_key: str,
) -> dict[str, object]:
    with connection(settings) as conn:
        notice = conn.execute("SELECT * FROM notices WHERE id = ?", (notice_id,)).fetchone()
        claims = conn.execute(
            "SELECT * FROM evidence_claims WHERE notice_id = ? ORDER BY claim_type, created_at, rowid",
            (notice_id,),
        ).fetchall()
        links = conn.execute(
            """
            SELECT link.*, source.*
            FROM evidence_claim_links link
            JOIN evidence_sources source ON source.id = link.evidence_id
            JOIN evidence_claims claim ON claim.id = link.claim_id
            WHERE claim.notice_id = ?
            ORDER BY source.created_at, source.rowid
            """,
            (notice_id,),
        ).fetchall()
        events = conn.execute(
            "SELECT * FROM evidence_audit_events WHERE notice_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 100",
            (notice_id,),
        ).fetchall()
        opinions = conn.execute(
            """
            SELECT opinion.*, requirement.requirement_key
            FROM requirement_review_opinions opinion
            JOIN opportunity_requirements requirement ON requirement.id = opinion.requirement_id
            WHERE opinion.notice_id = ?
            ORDER BY opinion.review_id, opinion.agent_role
            """,
            (notice_id,),
        ).fetchall()
    assert notice is not None
    links_by_claim: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in links:
        item = _source_dict(row)
        item["stance"] = str(row["stance"])
        item["stance_label"] = {"supports": "支持", "contradicts": "反驳", "context": "上下文"}.get(str(row["stance"]), str(row["stance"]))
        item["link_rationale"] = str(row["rationale"] or "")
        links_by_claim[str(row["claim_id"])].append(item)
    claim_items = []
    selected_id = ""
    for row in claims:
        evidence = links_by_claim.get(str(row["id"]), [])
        item = {
            "id": str(row["id"]),
            "claim_type": str(row["claim_type"]),
            "claim_type_label": CLAIM_TYPE_LABELS.get(str(row["claim_type"]), str(row["claim_type"])),
            "claim_key": str(row["claim_key"]),
            "title": str(row["title"]),
            "conclusion": str(row["conclusion"]),
            "status": str(row["status"]),
            "status_label": CLAIM_STATUS_LABELS.get(str(row["status"]), str(row["status"])),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "evidence": evidence,
            "comparison": _comparison(evidence),
        }
        claim_items.append(item)
        if claim_type and claim_key and item["claim_type"] == claim_type and item["claim_key"] == claim_key:
            selected_id = str(item["id"])
    if not selected_id and claim_items:
        selected_id = str(claim_items[0]["id"])
    unique_sources = {
        str(item["id"]): item
        for values in links_by_claim.values()
        for item in values
    }
    source_count = len(unique_sources)
    status_counts = {
        status: sum(
            1
            for item in unique_sources.values()
            if item["verified_status"] == status
        )
        for status in EVIDENCE_STATUS_LABELS
    }
    definitive_without_valid_evidence = sum(
        item["status"] == "supported"
        and not any(source["verified_status"] == "verified" for source in item["evidence"])
        for item in claim_items
    )
    return {
        "notice_id": notice_id,
        "title": str(notice["title"] or ""),
        "source_site": str(notice["source_site"] or ""),
        "source_url": str(notice["source_url"] or ""),
        "selected_claim_id": selected_id,
        "claims": claim_items,
        "disagreements": _agent_disagreements(opinions, claim_items),
        "audit_events": [_event_dict(row) for row in events],
        "summary": {
            "claim_count": len(claim_items),
            "source_count": source_count,
            "verified_count": status_counts["verified"],
            "pending_count": status_counts["pending"],
            "expired_count": status_counts["expired"],
            "conflict_count": status_counts["conflict"],
            "unavailable_count": status_counts["unavailable"],
            "recheck_claim_count": sum(item["status"] == "recheck" for item in claim_items),
            "definitive_without_valid_evidence": definitive_without_valid_evidence,
            "audit_complete": definitive_without_valid_evidence == 0,
        },
    }


def _ensure_source(conn: sqlite3.Connection, spec: dict[str, object]) -> tuple[str, str, bool]:
    exact = conn.execute(
        """
        SELECT * FROM evidence_sources
        WHERE notice_id = ? AND source_type = ? AND source_id = ? AND content_hash = ?
        """,
        (spec["notice_id"], spec["source_type"], spec["source_id"], spec["content_hash"]),
    ).fetchone()
    prior_rows = conn.execute(
        """
        SELECT * FROM evidence_sources
        WHERE notice_id = ? AND source_type = ? AND source_id = ?
          AND content_hash <> ?
        ORDER BY updated_at DESC, rowid DESC
        """,
        (spec["notice_id"], spec["source_type"], spec["source_id"], spec["content_hash"]),
    ).fetchall()
    active_previous = [row for row in prior_rows if str(row["verified_status"]) != "expired"]
    changed = bool(active_previous) if exact is not None else bool(prior_rows)
    for old in active_previous:
        conn.execute(
            "UPDATE evidence_sources SET verified_status = 'expired', updated_at = datetime('now') WHERE id = ?",
            (old["id"],),
        )
        linked_claims = conn.execute(
            "SELECT claim_id FROM evidence_claim_links WHERE evidence_id = ?",
            (old["id"],),
        ).fetchall()
        for claim in linked_claims:
            conn.execute(
                "UPDATE evidence_claims SET status = 'recheck', updated_at = datetime('now') WHERE id = ?",
                (claim["claim_id"],),
            )
            conn.execute(
                """
                INSERT INTO evidence_audit_events(
                    id, notice_id, evidence_id, claim_id, action, actor, reason,
                    previous_status, new_status
                ) VALUES (?, ?, ?, ?, 'source_invalidated', 'system:content_hash', ?, ?, 'expired')
                """,
                (
                    str(uuid4()), spec["notice_id"], old["id"], claim["claim_id"],
                    "证据内容哈希发生变化，保留旧版本并要求重新确认",
                    old["verified_status"],
                ),
            )
    if exact is not None:
        status = str(exact["verified_status"])
        if spec.get("force_pending") and not str(exact["confirmed_by"] or "") and status == "verified":
            status = "pending"
            conn.execute(
                "UPDATE evidence_sources SET verified_status = 'pending', updated_at = datetime('now') WHERE id = ?",
                (exact["id"],),
            )
        return str(exact["id"]), status, changed
    evidence_id = _stable_id("evidence", spec["notice_id"], spec["source_type"], spec["source_id"], spec["content_hash"])
    status = "pending" if changed else str(spec["verified_status"])
    conn.execute(
        """
        INSERT INTO evidence_sources(
            id, notice_id, source_type, source_id, source_site, source_url,
            file_name, page_number, section_path, paragraph_index, selector,
            text_coordinates_json, quote, context_before, context_after,
            content_hash, parent_content_hash, revision_id, captured_at,
            extraction_method, locator_confidence, verified_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            evidence_id, spec["notice_id"], spec["source_type"], spec["source_id"],
            spec["source_site"], spec["source_url"], spec["file_name"], spec["page_number"],
            spec["section_path"], spec["paragraph_index"], spec["selector"],
            json_dumps(spec["text_coordinates"]), spec["quote"], spec["context_before"],
            spec["context_after"], spec["content_hash"], spec["parent_content_hash"],
            spec["revision_id"], spec["captured_at"], spec["extraction_method"],
            spec["locator_confidence"], status,
        ),
    )
    return evidence_id, status, changed


def _ensure_claim(conn: sqlite3.Connection, spec: dict[str, object]) -> None:
    claim_id = _stable_id("claim", spec["notice_id"], spec["claim_type"], spec["claim_key"])
    existing = conn.execute("SELECT conclusion FROM evidence_claims WHERE id = ?", (claim_id,)).fetchone()
    conclusion_changed = existing is not None and str(existing["conclusion"]) != str(spec["conclusion"])
    conn.execute(
        """
        INSERT INTO evidence_claims(id, notice_id, claim_type, claim_key, title, conclusion, status)
        VALUES (?, ?, ?, ?, ?, ?, 'pending')
        ON CONFLICT(notice_id, claim_type, claim_key) DO UPDATE SET
            title = excluded.title, conclusion = excluded.conclusion, updated_at = datetime('now')
        """,
        (
            claim_id, spec["notice_id"], spec["claim_type"], spec["claim_key"],
            spec["title"], spec["conclusion"],
        ),
    )
    active_ids = []
    for evidence_id, stance, rationale in spec["links"]:
        if not evidence_id:
            continue
        active_ids.append(evidence_id)
        conn.execute(
            """
            INSERT INTO evidence_claim_links(claim_id, evidence_id, stance, rationale)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(claim_id, evidence_id) DO UPDATE SET
                stance = excluded.stance, rationale = excluded.rationale
            """,
            (claim_id, evidence_id, stance, rationale),
        )
    _refresh_claim_status(
        conn,
        claim_id,
        active_evidence_ids=active_ids,
        force_recheck=bool(spec["source_changed"] or conclusion_changed),
    )


def _refresh_claim_status(
    conn: sqlite3.Connection,
    claim_id: str,
    *,
    active_evidence_ids: Iterable[str] | None = None,
    force_recheck: bool = False,
) -> None:
    if active_evidence_ids is None:
        rows = conn.execute(
            """
            SELECT source.verified_status, link.stance
            FROM evidence_claim_links link
            JOIN evidence_sources source ON source.id = link.evidence_id
            WHERE link.claim_id = ? AND source.verified_status <> 'expired'
            """,
            (claim_id,),
        ).fetchall()
    else:
        ids = list(active_evidence_ids)
        if not ids:
            rows = []
        else:
            placeholders = ",".join("?" for _ in ids)
            rows = conn.execute(
                f"""
                SELECT source.verified_status, link.stance
                FROM evidence_claim_links link
                JOIN evidence_sources source ON source.id = link.evidence_id
                WHERE link.claim_id = ? AND source.id IN ({placeholders})
                """,
                (claim_id, *ids),
            ).fetchall()
    statuses = {str(row["verified_status"]) for row in rows}
    stances = {str(row["stance"]) for row in rows if str(row["verified_status"]) == "verified"}
    if force_recheck:
        status = "recheck"
    elif "conflict" in statuses or ({"supports", "contradicts"} <= stances):
        status = "conflict"
    elif rows and statuses == {"verified"}:
        status = "supported"
    else:
        status = "pending"
    conn.execute(
        "UPDATE evidence_claims SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (status, claim_id),
    )


def _sync_revision_evidence(conn: sqlite3.Connection, notice: sqlite3.Row, revisions: list[sqlite3.Row]) -> None:
    for revision in revisions:
        before = _json_dict(revision["before_json"])
        for field_name in _json_list(revision["changed_fields_json"]):
            value = before.get(field_name)
            if value in (None, "", [], {}):
                continue
            quote = _text(value if not isinstance(value, dict) else value.get("excerpt") or json_dumps(value))
            spec = _source_spec(
                notice_id=str(notice["id"]),
                source_type="webpage",
                source_id=f"revision:{revision['id']}:{field_name}:before",
                source_site=str(notice["source_site"] or ""),
                source_url=str(notice["source_url"] or ""),
                file_name=str(notice["title"] or "公告原文"),
                quote=quote,
                section_path=f"历史版本 / {field_name}",
                selector="document.body",
                parent_content_hash=str(revision["change_hash"] or ""),
                revision_id=str(revision["id"]),
                captured_at=str(revision["created_at"] or ""),
                extraction_method="revision_snapshot",
                locator_confidence=100,
                verified_status="expired",
            )
            _ensure_source(conn, spec)


def _source_spec(
    *,
    notice_id: str,
    source_type: str,
    source_id: str,
    source_site: str,
    source_url: str,
    file_name: str,
    quote: str,
    page_number: int | None = None,
    section_path: str = "",
    paragraph_index: int | None = None,
    selector: str = "",
    text_coordinates: dict[str, object] | None = None,
    context_before: str = "",
    context_after: str = "",
    parent_content_hash: str = "",
    revision_id: str = "",
    captured_at: str = "",
    extraction_method: str,
    locator_confidence: int,
    verified_status: str,
    force_pending: bool = False,
) -> dict[str, object]:
    normalized_quote = _text(quote)
    return {
        "notice_id": notice_id,
        "source_type": source_type,
        "source_id": source_id,
        "source_site": source_site,
        "source_url": source_url,
        "file_name": file_name,
        "page_number": page_number,
        "section_path": section_path,
        "paragraph_index": paragraph_index,
        "selector": selector,
        "text_coordinates": text_coordinates or {},
        "quote": normalized_quote,
        "context_before": _text(context_before),
        "context_after": _text(context_after),
        "content_hash": hashlib.sha256(normalized_quote.encode("utf-8")).hexdigest(),
        "parent_content_hash": parent_content_hash,
        "revision_id": revision_id,
        "captured_at": captured_at,
        "extraction_method": extraction_method,
        "locator_confidence": max(0, min(100, int(locator_confidence))),
        "verified_status": verified_status if verified_status in EVIDENCE_STATUS_LABELS else "pending",
        "force_pending": force_pending,
    }


def _located_source(
    *,
    notice_id: str,
    source_id: str,
    source_site: str,
    source_url: str,
    locator: str,
    quote: str,
    revision_id: str,
    captured_at: str,
    verified_status: str,
    extraction_method: str,
    locator_confidence: int,
    force_source_type: str = "",
    parent_content_hash: str = "",
) -> dict[str, object]:
    source_type = force_source_type or _source_type(source_url, locator)
    page_match = _PAGE_RE.search(locator)
    paragraph_match = _PARAGRAPH_RE.search(locator)
    return _source_spec(
        notice_id=notice_id,
        source_type=source_type,
        source_id=source_id,
        source_site=source_site,
        source_url=source_url,
        file_name=_file_name(source_url, locator),
        page_number=int(page_match.group(1)) if page_match else None,
        section_path=locator,
        paragraph_index=int(paragraph_match.group(1)) if paragraph_match else None,
        selector="document.body" if source_type == "webpage" else "",
        quote=quote,
        parent_content_hash=parent_content_hash,
        revision_id=revision_id,
        captured_at=captured_at,
        extraction_method=extraction_method,
        locator_confidence=locator_confidence,
        verified_status=verified_status,
    )


def _claim_spec(
    notice_id: str,
    claim_type: str,
    claim_key: str,
    title: str,
    conclusion: str,
    links: list[tuple[str, str, str]],
    source_changed: bool,
) -> dict[str, object]:
    return {
        "notice_id": notice_id,
        "claim_type": claim_type,
        "claim_key": claim_key,
        "title": _text(title),
        "conclusion": _text(conclusion),
        "links": links,
        "source_changed": source_changed,
    }


def _source_dict(row: sqlite3.Row) -> dict[str, object]:
    quote = str(row["quote"] or "")
    return {
        "id": str(row["id"]),
        "source_type": str(row["source_type"]),
        "source_id": str(row["source_id"]),
        "source_site": str(row["source_site"] or ""),
        "source_url": str(row["source_url"] or ""),
        "file_name": str(row["file_name"] or ""),
        "page_number": row["page_number"],
        "section_path": str(row["section_path"] or ""),
        "paragraph_index": row["paragraph_index"],
        "selector": str(row["selector"] or ""),
        "text_coordinates": _json_dict(row["text_coordinates_json"]),
        "quote": quote,
        "context_before": str(row["context_before"] or ""),
        "context_after": str(row["context_after"] or ""),
        "content_hash": str(row["content_hash"]),
        "parent_content_hash": str(row["parent_content_hash"] or ""),
        "revision_id": str(row["revision_id"] or ""),
        "captured_at": str(row["captured_at"] or ""),
        "extraction_method": str(row["extraction_method"] or ""),
        "locator_confidence": int(row["locator_confidence"] or 0),
        "verified_status": str(row["verified_status"]),
        "verified_status_label": EVIDENCE_STATUS_LABELS.get(str(row["verified_status"]), str(row["verified_status"])),
        "confirmed_by": str(row["confirmed_by"] or ""),
        "confirmed_at": str(row["confirmed_at"] or ""),
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
        "highlights": _highlights(quote),
    }


def _event_dict(row: sqlite3.Row) -> dict[str, object]:
    return {
        "id": str(row["id"]),
        "evidence_id": str(row["evidence_id"] or ""),
        "claim_id": str(row["claim_id"] or ""),
        "action": str(row["action"]),
        "actor": str(row["actor"]),
        "reason": str(row["reason"]),
        "previous_status": str(row["previous_status"] or ""),
        "new_status": str(row["new_status"] or ""),
        "created_at": str(row["created_at"]),
    }


def _highlights(text: str) -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    for kind, pattern in (("amount", _AMOUNT_RE), ("date", _DATE_RE), ("parameter", _PARAMETER_RE), ("negation", _NEGATION_RE)):
        for match in pattern.finditer(text):
            matches.append({"kind": kind, "value": match.group(0), "start": match.start(), "end": match.end()})
    matches.sort(key=lambda item: (int(item["start"]), -int(item["end"])))
    kept: list[dict[str, object]] = []
    cursor = -1
    for item in matches:
        if int(item["start"]) < cursor:
            continue
        kept.append(item)
        cursor = int(item["end"])
    return kept


def _comparison(evidence: list[dict[str, object]]) -> dict[str, object]:
    active = [item for item in evidence if item["verified_status"] != "expired"]
    if len(active) < 2:
        return {"status": "single_source", "items": []}
    tokens: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for item in active:
        quote = str(item["quote"])
        for kind, pattern in (("金额", _AMOUNT_RE), ("日期", _DATE_RE), ("参数", _PARAMETER_RE), ("限制词", _NEGATION_RE)):
            for match in pattern.finditer(quote):
                tokens[kind].append((str(item["id"]), match.group(0)))
    items = []
    conflict = False
    for label, values in tokens.items():
        distinct = sorted({value for _, value in values})
        source_values: dict[str, set[str]] = defaultdict(set)
        for source_id, value in values:
            source_values[source_id].add(value)
        field_conflict = len(source_values) > 1 and len({tuple(sorted(items)) for items in source_values.values()}) > 1
        if field_conflict:
            conflict = True
        items.append(
            {
                "field": label,
                "values": [{"evidence_id": source_id, "value": value} for source_id, value in values],
                "distinct_values": distinct,
                "conflict": field_conflict,
            }
        )
    return {"status": "different" if conflict else "aligned", "items": items}


def _agent_disagreements(opinions: list[sqlite3.Row], claims: list[dict[str, object]]) -> list[dict[str, object]]:
    claims_by_key = {str(item["claim_key"]): item for item in claims if item["claim_type"] == "agent_opinion"}
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for opinion in opinions:
        grouped[str(opinion["review_id"])].append(opinion)
    result = []
    for review_id, items in grouped.items():
        if len({str(item["decision"]) for item in items}) < 2:
            continue
        result.append(
            {
                "review_id": review_id,
                "requirement_key": str(items[0]["requirement_key"]),
                "opinions": [
                    {
                        "agent_role": str(item["agent_role"]),
                        "agent_label": _agent_label(str(item["agent_role"])),
                        "decision": str(item["decision"]),
                        "confidence": int(item["confidence"] or 0),
                        "rationale": str(item["rationale"] or ""),
                        "model_status": str(item["model_status"] or ""),
                        "claim_id": str(claims_by_key.get(str(item["id"]), {}).get("id", "")),
                        "evidence": claims_by_key.get(str(item["id"]), {}).get("evidence", []),
                    }
                    for item in items
                ],
            }
        )
    return result


def _quote_context(text: str, value: str) -> tuple[str, str, str]:
    index = text.find(value)
    if index < 0:
        return value, "", ""
    start = max(0, index - 140)
    end = min(len(text), index + len(value) + 180)
    return text[start:end], text[start:index], text[index + len(value):end]


def _source_type(url: str, locator: str) -> str:
    lowered = f"{url} {locator}".lower()
    if ".pdf" in lowered:
        return "pdf"
    if ".docx" in lowered or ".doc " in lowered:
        return "docx"
    return "webpage"


def _attachment_source_type(name: str, url: str) -> str:
    return _source_type(url, name)


def _file_name(url: str, locator: str) -> str:
    path_name = unquote(PurePosixPath(urlparse(url).path).name) if url else ""
    if path_name:
        return path_name
    return locator.split("第", 1)[0].strip(" ：:，,") or "来源材料"


def _capability_status(status: str, valid_until: str) -> str:
    if status == "expired":
        return "expired"
    if valid_until:
        try:
            if date.fromisoformat(valid_until) < date.today():
                return "expired"
        except ValueError:
            return "pending"
    return "verified" if status == "verified" else "pending"


def _opinion_stance(decision: str) -> str:
    return {"accept": "supports", "reject": "contradicts"}.get(decision, "context")


def _agent_label(role: str) -> str:
    return {
        "project_control": "项目统筹审查",
        "compliance": "合规审查",
        "technical": "技术评审",
        "commercial": "商务评审",
        "evidence_audit": "证据审计",
    }.get(role, role)


def _stable_id(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:32]


def _text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, ValueError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
