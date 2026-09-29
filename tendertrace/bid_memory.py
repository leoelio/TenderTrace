from __future__ import annotations

from datetime import date
import hashlib
import json
import re
from typing import Any
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps
from tendertrace.opportunity import get_opportunity
from tendertrace.opportunity_outcomes import get_outcome
from tendertrace.retrieval import segment_for_fts


ASSET_TYPES = {"requirement", "material", "evidence", "lesson", "gap", "competitor", "decision", "task", "outcome"}
REUSE_STATUSES = {"reusable", "update_needed", "reference", "expired", "invalid"}
PERMISSION_SCOPES = {"workspace", "restricted"}
SENSITIVITY_LEVELS = {"normal", "sensitive"}
PRIVILEGED_ROLES = {"owner", "member"}


def archive_project_memory(
    settings: Settings,
    notice_id: str,
    *,
    workspace_id: str,
    actor: str,
    tags: list[str] | None = None,
    materials: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Archive one completed bid and its reusable facts into an isolated workspace."""
    init_db(settings)
    opportunity = get_opportunity(settings, notice_id)
    if opportunity is None:
        raise LookupError("opportunity not found")
    outcome = get_outcome(settings, notice_id)
    if outcome is None:
        raise ValueError("请先完成投标结果复盘，再进入企业投标记忆体")
    role = _access_role(settings, workspace_id, actor)
    if not role:
        raise PermissionError("当前账号不属于该组织空间")

    project_id = _stable_id("bid-memory-project", workspace_id, notice_id)
    normalized_tags = _unique_texts(tags or [], limit=12)
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO bid_memory_projects(
                id, workspace_id, notice_id, outcome_result, outcome_reason_code,
                summary, lessons, tags_json, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workspace_id, notice_id) DO UPDATE SET
                outcome_result = excluded.outcome_result,
                outcome_reason_code = excluded.outcome_reason_code,
                summary = excluded.summary,
                lessons = excluded.lessons,
                tags_json = excluded.tags_json,
                status = 'active', updated_at = datetime('now')
            """,
            (
                project_id,
                workspace_id,
                notice_id,
                outcome.result,
                outcome.reason_code,
                outcome.summary,
                outcome.lessons,
                json_dumps(normalized_tags),
                actor.strip() or "admin",
            ),
        )
        row = conn.execute(
            "SELECT id FROM bid_memory_projects WHERE workspace_id = ? AND notice_id = ?",
            (workspace_id, notice_id),
        ).fetchone()
        assert row is not None
        project_id = str(row["id"])

    assets = _project_assets(settings, notice_id, opportunity, outcome, materials or [])
    for asset in assets:
        _upsert_asset(settings, project_id, workspace_id, notice_id, asset, actor=actor)
    _record_audit(
        settings,
        workspace_id=workspace_id,
        project_memory_id=project_id,
        action="project_archived",
        actor=actor,
        note=f"归档 {len(assets)} 项要求、材料、缺口、决策和复盘经验",
        after={"notice_id": notice_id, "asset_count": len(assets), "tags": normalized_tags},
    )
    with connection(settings) as conn:
        conn.execute(
            "INSERT INTO opportunity_events(id, notice_id, action, actor_open_id, payload_json) VALUES (?, ?, 'bid_memory_archived', ?, ?)",
            (str(uuid4()), notice_id, actor.strip() or "admin", json_dumps({"workspace_id": workspace_id, "project_memory_id": project_id, "asset_count": len(assets)})),
        )
    return get_bid_memory_dashboard(
        settings,
        workspace_id=workspace_id,
        notice_id=notice_id,
        actor=actor,
    )


def get_bid_memory_dashboard(
    settings: Settings,
    *,
    workspace_id: str,
    notice_id: str = "",
    actor: str = "admin",
) -> dict[str, object]:
    init_db(settings)
    role = _access_role(settings, workspace_id, actor)
    if not role:
        return {
            "access": {"granted": False, "role": "none", "message": "当前账号无权查看该组织空间的投标记忆"},
            "workspace_id": workspace_id,
            "notice_id": notice_id,
            "summary": _empty_summary(),
            "sample": _sample_boundary([]),
            "recommendations": [],
            "assets": [],
            "projects": [],
            "graph": {"nodes": [], "edges": [], "legend": _graph_legend()},
            "audit": [],
            "rules": _rules(),
        }
    _refresh_expired_assets(settings, workspace_id)
    with connection(settings) as conn:
        project_rows = conn.execute(
            """
            SELECT p.*, n.title, n.purchaser, n.region, n.source_url, n.fields_json,
                   n.publish_time, o.finalized_at
            FROM bid_memory_projects p
            JOIN notices n ON n.id = p.notice_id
            LEFT JOIN opportunity_outcomes o ON o.notice_id = p.notice_id
            WHERE p.workspace_id = ? AND p.status = 'active'
            ORDER BY COALESCE(o.finalized_at, p.updated_at) DESC
            """,
            (workspace_id,),
        ).fetchall()
        asset_rows = conn.execute(
            "SELECT * FROM bid_memory_assets WHERE workspace_id = ? ORDER BY updated_at DESC, rowid DESC",
            (workspace_id,),
        ).fetchall()
        audit_rows = conn.execute(
            "SELECT * FROM bid_memory_audit_events WHERE workspace_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 80",
            (workspace_id,),
        ).fetchall()

    projects = [_project_payload(row) for row in project_rows]
    visible_assets = [
        _asset_payload(row)
        for row in asset_rows
        if _asset_visible(row, role)
    ]
    hidden_count = len(asset_rows) - len(visible_assets)
    target = _target_profile(settings, notice_id) if notice_id else None
    recommendations = _recommendations(settings, target, projects, visible_assets) if target else []
    comparable = [item for item in recommendations if float(item["similarity_score"]) >= 20]
    sample = _sample_boundary(comparable)
    graph = _relationship_graph(settings, target, projects, visible_assets, recommendations)
    summary = {
        "project_count": len(projects),
        "asset_count": len(visible_assets),
        "reusable_count": sum(item["effective_status"] == "reusable" for item in visible_assets),
        "update_needed_count": sum(item["effective_status"] == "update_needed" for item in visible_assets),
        "reference_count": sum(item["effective_status"] == "reference" for item in visible_assets),
        "expired_count": sum(item["effective_status"] == "expired" for item in visible_assets),
        "invalid_count": sum(item["effective_status"] == "invalid" for item in visible_assets),
        "won_count": sum(item["outcome_result"] == "won" for item in projects),
        "lost_count": sum(item["outcome_result"] == "lost" for item in projects),
        "hidden_sensitive_count": hidden_count,
        "recommendation_count": len(recommendations),
    }
    return {
        "access": {"granted": True, "role": role, "message": "仅返回当前组织空间与当前账号可见的经验"},
        "workspace_id": workspace_id,
        "notice_id": notice_id,
        "target": target or {},
        "summary": summary,
        "sample": sample,
        "recommendations": recommendations,
        "assets": visible_assets,
        "projects": projects,
        "graph": graph,
        "audit": [_audit_payload(row) for row in audit_rows],
        "rules": _rules(),
    }


def decide_bid_memory_asset(
    settings: Settings,
    asset_id: str,
    *,
    workspace_id: str,
    action: str,
    actor: str,
    note: str,
    corrections: dict[str, object] | None = None,
) -> dict[str, object]:
    role = _access_role(settings, workspace_id, actor)
    if role not in PRIVILEGED_ROLES and role != "system_admin":
        raise PermissionError("只有空间负责人或正式成员可以修改企业投标记忆")
    action = action.strip()
    note = " ".join(note.split())
    if action not in {"confirm", "correct", "withdraw"}:
        raise ValueError("unsupported bid memory decision")
    if not note:
        raise ValueError("人工处理说明不能为空")
    with connection(settings) as conn:
        row = conn.execute(
            "SELECT * FROM bid_memory_assets WHERE id = ? AND workspace_id = ?",
            (asset_id, workspace_id),
        ).fetchone()
        if row is None:
            raise LookupError("bid memory asset not found")
        before = dict(row)
        effective = _effective_status(row)
        if action == "confirm":
            if effective == "expired":
                raise ValueError("过期材料不能确认为可直接使用，请先纠正有效期或更新材料")
            conn.execute(
                "UPDATE bid_memory_assets SET reuse_status = 'reusable', confirmed_by = ?, confirmed_at = datetime('now'), withdrawn_at = NULL, updated_at = datetime('now') WHERE id = ?",
                (actor, asset_id),
            )
        elif action == "withdraw":
            conn.execute(
                "UPDATE bid_memory_assets SET reuse_status = 'invalid', withdrawn_at = datetime('now'), updated_at = datetime('now') WHERE id = ?",
                (asset_id,),
            )
        else:
            values = corrections or {}
            title = " ".join(str(values.get("title") or row["title"]).split())[:240]
            content = " ".join(str(values.get("content") or row["content"]).split())[:8000]
            valid_until = str(values.get("valid_until") if "valid_until" in values else row["valid_until"] or "").strip()
            reuse_status = str(values.get("reuse_status") or row["reuse_status"] or "reference")
            if reuse_status not in REUSE_STATUSES - {"invalid", "expired"}:
                raise ValueError("unsupported reuse status")
            if not title or not content:
                raise ValueError("标题和内容不能为空")
            conn.execute(
                """
                UPDATE bid_memory_assets
                SET title = ?, content = ?, valid_until = NULLIF(?, ''),
                    reuse_status = ?, version_number = version_number + 1,
                    confirmed_by = ?, confirmed_at = datetime('now'),
                    withdrawn_at = NULL, updated_at = datetime('now')
                WHERE id = ?
                """,
                (title, content, valid_until, reuse_status, actor, asset_id),
            )
        after_row = conn.execute("SELECT * FROM bid_memory_assets WHERE id = ?", (asset_id,)).fetchone()
        assert after_row is not None
        after = dict(after_row)
    _record_audit(
        settings,
        workspace_id=workspace_id,
        project_memory_id=str(before["project_memory_id"]),
        asset_id=asset_id,
        action=f"asset_{action}",
        actor=actor,
        note=note,
        before=before,
        after=after,
    )
    return _asset_payload(after)


def _project_assets(settings: Settings, notice_id: str, opportunity: dict[str, object], outcome: Any, materials: list[dict[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = [
        {"asset_key": "outcome", "asset_type": "outcome", "title": "项目最终结果", "content": outcome.summary, "source_url": outcome.evidence_url, "reuse_status": "reference"},
        {"asset_key": "lesson", "asset_type": "lesson", "title": "项目复盘经验", "content": outcome.lessons, "source_url": outcome.evidence_url, "reuse_status": "reusable"},
        {"asset_key": "decision", "asset_type": "decision", "title": "最终投标决策", "content": _decision_content(opportunity), "source_url": str(opportunity.get("source_url") or ""), "reuse_status": "reference"},
    ]
    with connection(settings) as conn:
        requirements = conn.execute(
            "SELECT id, requirement_key, requirement_type, title, evidence_text, source_url, status FROM opportunity_requirements WHERE notice_id = ? ORDER BY requirement_key",
            (notice_id,),
        ).fetchall()
        matches = conn.execute(
            """
            SELECT m.id, m.verdict, m.status, m.rationale, r.requirement_key,
                   c.id capability_id, c.title, c.evidence_text, c.source_url, c.valid_until,
                   c.verification_status
            FROM requirement_capability_matches m
            JOIN opportunity_requirements r ON r.id = m.requirement_id
            LEFT JOIN enterprise_capabilities c ON c.id = m.capability_id
            WHERE m.notice_id = ?
            """,
            (notice_id,),
        ).fetchall()
        gaps = conn.execute(
            "SELECT id, title, action_type, status, completion_note FROM capability_gap_actions WHERE notice_id = ?",
            (notice_id,),
        ).fetchall()
        memories = conn.execute(
            "SELECT id, memory_type, title, content, evidence_url FROM organization_memories WHERE related_notice_id = ? AND memory_type IN ('competitor', 'risk')",
            (notice_id,),
        ).fetchall()
        tasks = conn.execute(
            "SELECT id, task_key, title, milestone_type, due_at, status, completed_at FROM bid_plan_tasks WHERE notice_id = ? ORDER BY updated_at DESC",
            (notice_id,),
        ).fetchall()
    for row in requirements:
        result.append({
            "asset_key": f"requirement:{row['id']}", "asset_type": "requirement",
            "title": str(row["title"]), "content": str(row["evidence_text"] or ""),
            "source_url": str(row["source_url"] or ""),
            "reuse_status": "reusable" if str(row["status"]) in {"confirmed", "completed"} else "reference",
        })
    for row in matches:
        if row["capability_id"] and str(row["status"]) == "confirmed" and str(row["verdict"]) == "supported":
            result.append({
                "asset_key": f"capability:{row['capability_id']}", "asset_type": "material",
                "title": str(row["title"]), "content": str(row["evidence_text"] or row["rationale"] or ""),
                "source_url": str(row["source_url"] or ""), "valid_until": str(row["valid_until"] or ""),
                "reuse_status": "reusable" if str(row["verification_status"]) == "verified" else "update_needed",
                "permission_scope": "restricted", "sensitivity": "sensitive",
            })
        elif str(row["verdict"]) in {"gap", "conflict"}:
            result.append({
                "asset_key": f"match-gap:{row['id']}", "asset_type": "gap",
                "title": f"历史能力缺口：{row['requirement_key']}", "content": str(row["rationale"] or "能力缺口待补齐"),
                "reuse_status": "reference",
            })
    for row in gaps:
        result.append({
            "asset_key": f"gap:{row['id']}", "asset_type": "gap", "title": str(row["title"]),
            "content": str(row["completion_note"] or f"{row['action_type']} · {row['status']}"), "reuse_status": "reference",
        })
    for row in memories:
        result.append({
            "asset_key": f"organization-memory:{row['id']}",
            "asset_type": "competitor" if str(row["memory_type"]) == "competitor" else "gap",
            "title": str(row["title"]), "content": str(row["content"]),
            "source_url": str(row["evidence_url"] or ""), "reuse_status": "reference",
        })
    for row in tasks:
        status = str(row["status"] or "open")
        result.append({
            "asset_key": f"task:{row['id']}", "asset_type": "task", "title": str(row["title"]),
            "content": " · ".join(part for part in (
                f"里程碑 {row['milestone_type']}", f"状态 {status}",
                f"截止 {row['due_at']}" if row["due_at"] else "",
                f"完成 {row['completed_at']}" if row["completed_at"] else "",
            ) if part),
            "source_url": str(opportunity.get("source_url") or ""),
            "reuse_status": "reusable" if status == "completed" else "reference",
        })
    for index, raw in enumerate(materials):
        asset_type = str(raw.get("asset_type") or "material")
        if asset_type not in ASSET_TYPES:
            raise ValueError("unsupported bid memory asset type")
        result.append({
            "asset_key": str(raw.get("asset_key") or f"manual:{index}"),
            "asset_type": asset_type,
            "title": str(raw.get("title") or "可复用投标材料"),
            "content": str(raw.get("content") or ""),
            "source_url": str(raw.get("source_url") or opportunity.get("source_url") or ""),
            "valid_until": str(raw.get("valid_until") or ""),
            "reuse_status": str(raw.get("reuse_status") or "update_needed"),
            "permission_scope": str(raw.get("permission_scope") or "workspace"),
            "sensitivity": str(raw.get("sensitivity") or "normal"),
        })
    return [item for item in result if str(item.get("content") or "").strip()]


def _upsert_asset(settings: Settings, project_id: str, workspace_id: str, notice_id: str, asset: dict[str, object], *, actor: str) -> None:
    asset_type = str(asset.get("asset_type") or "")
    reuse_status = str(asset.get("reuse_status") or "reference")
    permission_scope = str(asset.get("permission_scope") or "workspace")
    sensitivity = str(asset.get("sensitivity") or "normal")
    if asset_type not in ASSET_TYPES or reuse_status not in REUSE_STATUSES or permission_scope not in PERMISSION_SCOPES or sensitivity not in SENSITIVITY_LEVELS:
        raise ValueError("invalid bid memory asset")
    asset_key = str(asset.get("asset_key") or "")[:240]
    title = " ".join(str(asset.get("title") or "").split())[:240]
    content = " ".join(str(asset.get("content") or "").split())[:8000]
    if not asset_key or not title or not content:
        raise ValueError("bid memory asset requires key, title and content")
    asset_id = _stable_id("bid-memory-asset", project_id, asset_key)
    valid_until = str(asset.get("valid_until") or "").strip()
    with connection(settings) as conn:
        existing = conn.execute(
            "SELECT * FROM bid_memory_assets WHERE project_memory_id = ? AND asset_key = ?",
            (project_id, asset_key),
        ).fetchone()
        version = int(existing["version_number"] or 1) + 1 if existing and (str(existing["content"]) != content or str(existing["title"]) != title or str(existing["valid_until"] or "") != valid_until) else int(existing["version_number"] or 1) if existing else 1
        conn.execute(
            """
            INSERT INTO bid_memory_assets(
                id, project_memory_id, workspace_id, source_notice_id, asset_key,
                asset_type, title, content, source_url, version_number, valid_until,
                reuse_status, permission_scope, sensitivity, confirmed_by, confirmed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULLIF(?, ''), ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(project_memory_id, asset_key) DO UPDATE SET
                asset_type = excluded.asset_type, title = excluded.title, content = excluded.content,
                source_url = excluded.source_url, version_number = excluded.version_number,
                valid_until = excluded.valid_until, reuse_status = CASE
                    WHEN bid_memory_assets.reuse_status = 'invalid' THEN bid_memory_assets.reuse_status
                    ELSE excluded.reuse_status END,
                permission_scope = excluded.permission_scope, sensitivity = excluded.sensitivity,
                updated_at = datetime('now')
            """,
            (asset_id, project_id, workspace_id, notice_id, asset_key, asset_type, title, content, str(asset.get("source_url") or "")[:2000], version, valid_until, reuse_status, permission_scope, sensitivity, actor.strip() or "admin"),
        )


def _recommendations(settings: Settings, target: dict[str, object] | None, projects: list[dict[str, object]], assets: list[dict[str, object]]) -> list[dict[str, object]]:
    if not target:
        return []
    result = []
    for project in projects:
        if project["notice_id"] == target["notice_id"]:
            continue
        reasons: list[str] = []
        score = 0.0
        if target.get("region") and project.get("region") == target.get("region"):
            score += 22
            reasons.append(f"同地区：{target['region']}")
        if target.get("purchaser") and project.get("purchaser") == target.get("purchaser"):
            score += 18
            reasons.append("同一采购主体")
        if target.get("category") and project.get("category") == target.get("category"):
            score += 15
            reasons.append(f"同品类：{target['category']}")
        target_tokens = set(target.get("tokens") or [])
        project_tokens = set(project.get("tokens") or [])
        overlap = target_tokens & project_tokens
        union = target_tokens | project_tokens
        lexical = len(overlap) / len(union) if union else 0.0
        score += min(45, lexical * 100)
        if overlap:
            reasons.append("标题/内容共同词：" + "、".join(sorted(overlap)[:5]))
        target_types = set(target.get("requirement_types") or [])
        project_types = set(_requirement_types(settings, str(project["notice_id"])))
        common_types = target_types & project_types
        if common_types:
            score += min(15, len(common_types) * 5)
            reasons.append("共同要求类型：" + "、".join(sorted(common_types)))
        project_assets = [item for item in assets if item["source_notice_id"] == project["notice_id"] and item["effective_status"] != "invalid"]
        reusable = [item for item in project_assets if item["effective_status"] == "reusable"]
        warnings = [item for item in project_assets if item["asset_type"] == "gap" or item["effective_status"] in {"update_needed", "expired"}]
        if score < 12:
            continue
        result.append({
            "project_memory_id": project["id"], "source_notice_id": project["notice_id"],
            "source_title": project["title"], "source_url": project["source_url"],
            "result": project["outcome_result"], "finalized_at": project["finalized_at"],
            "similarity_score": round(min(score, 100), 1), "reasons": reasons or ["文本主题存在弱相关"],
            "reusable_assets": reusable[:6], "warnings": warnings[:6],
            "human_confirmed_count": sum(bool(item["confirmed_by"]) for item in project_assets),
        })
    return sorted(result, key=lambda item: (-float(item["similarity_score"]), str(item["source_title"])))[:8]


def _relationship_graph(settings: Settings, target: dict[str, object] | None, projects: list[dict[str, object]], assets: list[dict[str, object]], recommendations: list[dict[str, object]]) -> dict[str, object]:
    nodes: list[dict[str, object]] = []
    edges: list[dict[str, object]] = []
    seen: set[str] = set()

    def node(node_id: str, node_type: str, label: str, **extra: object) -> None:
        if node_id in seen:
            return
        seen.add(node_id)
        nodes.append({"id": node_id, "type": node_type, "label": label, **extra})

    if target:
        target_id = f"target:{target['notice_id']}"
        node(target_id, "target", str(target["title"]), subtitle="当前机会")
    else:
        target_id = "memory:center"
        node(target_id, "target", "企业投标记忆体", subtitle="组织经验中心")
    recommended_ids = {str(item["project_memory_id"]): item for item in recommendations}
    graph_projects = [item for item in projects if not recommendations or item["id"] in recommended_ids][:8]
    for project in graph_projects:
        project_id = f"project:{project['id']}"
        node(project_id, "project", str(project["title"]), subtitle="中标" if project["outcome_result"] == "won" else "未中标", source_notice_id=project["notice_id"])
        recommendation = recommended_ids.get(str(project["id"]))
        edges.append({"source": project_id, "target": target_id, "type": "similar", "label": f"相似 {recommendation['similarity_score']}" if recommendation else "历史项目"})
        for relation_type, value in (("customer", project.get("purchaser")), ("region", project.get("region")), ("category", project.get("category"))):
            if value:
                relation_id = f"{relation_type}:{_stable_id(str(value))}"
                node(relation_id, relation_type, str(value))
                edges.append({"source": project_id, "target": relation_id, "type": relation_type, "label": {"customer": "采购主体", "region": "地区", "category": "品类"}[relation_type]})
        decision_id = f"decision:{project['id']}"
        node(decision_id, "decision", str(project.get("decision") or "结果已复盘"))
        edges.append({"source": project_id, "target": decision_id, "type": "decision", "label": "决策"})
        outcome_id = f"outcome:{project['id']}"
        node(outcome_id, "outcome", "中标" if project["outcome_result"] == "won" else "未中标")
        edges.append({"source": project_id, "target": outcome_id, "type": "outcome", "label": "结果"})
        for asset in [item for item in assets if item["source_notice_id"] == project["notice_id"] and item["effective_status"] != "invalid"][:8]:
            asset_id = f"asset:{asset['id']}"
            node(asset_id, str(asset["asset_type"]), str(asset["title"]), status=asset["effective_status"], source_notice_id=project["notice_id"])
            edges.append({"source": project_id, "target": asset_id, "type": "contains", "label": _asset_type_label(str(asset["asset_type"]))})
    return {"nodes": nodes[:44], "edges": [edge for edge in edges if edge["source"] in seen and edge["target"] in seen][:60], "legend": _graph_legend()}


def _project_payload(row: Any) -> dict[str, object]:
    fields = _json_object(row["fields_json"])
    structured = fields.get("structured_fields") if isinstance(fields.get("structured_fields"), dict) else {}
    title = str(row["title"] or "")
    return {
        "id": str(row["id"]), "workspace_id": str(row["workspace_id"]), "notice_id": str(row["notice_id"]),
        "title": title, "purchaser": str(row["purchaser"] or ""), "region": str(row["region"] or ""),
        "category": str(structured.get("category") or fields.get("category") or ""),
        "source_url": str(row["source_url"] or ""), "publish_time": str(row["publish_time"] or ""),
        "outcome_result": str(row["outcome_result"]), "outcome_reason_code": str(row["outcome_reason_code"] or ""),
        "summary": str(row["summary"]), "lessons": str(row["lessons"]), "tags": _json_list(row["tags_json"]),
        "finalized_at": str(row["finalized_at"] or row["updated_at"] or ""),
        "decision": str(structured.get("decision") or ""),
        "tokens": _tokens(" ".join((title, str(row["purchaser"] or ""), str(row["summary"] or ""), str(row["lessons"] or "")))),
    }


def _asset_payload(row: Any) -> dict[str, object]:
    return {
        "id": str(row["id"]), "project_memory_id": str(row["project_memory_id"]),
        "workspace_id": str(row["workspace_id"]), "source_notice_id": str(row["source_notice_id"]),
        "asset_key": str(row["asset_key"]), "asset_type": str(row["asset_type"]),
        "asset_type_label": _asset_type_label(str(row["asset_type"])), "title": str(row["title"]),
        "content": str(row["content"]), "source_url": str(row["source_url"] or ""),
        "version_number": int(row["version_number"] or 1), "valid_until": str(row["valid_until"] or ""),
        "reuse_status": str(row["reuse_status"]), "effective_status": _effective_status(row),
        "permission_scope": str(row["permission_scope"]), "sensitivity": str(row["sensitivity"]),
        "confirmed_by": str(row["confirmed_by"] or ""), "confirmed_at": str(row["confirmed_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }


def _target_profile(settings: Settings, notice_id: str) -> dict[str, object] | None:
    opportunity = get_opportunity(settings, notice_id)
    if opportunity is None:
        raise LookupError("opportunity not found")
    with connection(settings) as conn:
        row = conn.execute("SELECT fields_json, core_content, content_text FROM notices WHERE id = ?", (notice_id,)).fetchone()
    fields = _json_object(row["fields_json"]) if row else {}
    structured = fields.get("structured_fields") if isinstance(fields.get("structured_fields"), dict) else {}
    category = str(structured.get("category") or fields.get("category") or "")
    text = " ".join(str(opportunity.get(key) or "") for key in ("title", "purchaser", "region"))
    if row:
        text += " " + str(row["core_content"] or row["content_text"] or "")
    return {
        "notice_id": notice_id, "title": str(opportunity.get("title") or notice_id),
        "purchaser": str(opportunity.get("purchaser") or ""), "region": str(opportunity.get("region") or ""),
        "category": category,
        "source_url": str(opportunity.get("source_url") or ""), "tokens": _tokens(text),
        "requirement_types": _requirement_types(settings, notice_id),
    }


def _requirement_types(settings: Settings, notice_id: str) -> list[str]:
    with connection(settings) as conn:
        rows = conn.execute("SELECT DISTINCT requirement_type FROM opportunity_requirements WHERE notice_id = ?", (notice_id,)).fetchall()
    return [str(row["requirement_type"]) for row in rows if row["requirement_type"]]


def _sample_boundary(recommendations: list[dict[str, object]]) -> dict[str, object]:
    count = len(recommendations)
    won = sum(item.get("result") == "won" for item in recommendations)
    lost = sum(item.get("result") == "lost" for item in recommendations)
    reliable = count >= 2 and won > 0 and lost > 0
    return {
        "count": count, "won_count": won, "lost_count": lost, "reliable": reliable,
        "label": "经验样本可供交叉参考" if reliable else "暂无可靠经验",
        "message": f"已找到 {count} 个相似历史项目（中标 {won}、未中标 {lost}）；只提供可追溯参考，不生成胜率。" if count else "当前组织空间暂无足够相似历史项目，不生成胜率。",
        "probability_output": False,
    }


def _access_role(settings: Settings, workspace_id: str, actor: str) -> str:
    actor = actor.strip() or "admin"
    with connection(settings) as conn:
        workspace = conn.execute("SELECT 1 FROM organization_workspaces WHERE id = ? AND status = 'active'", (workspace_id,)).fetchone()
        if workspace is None:
            raise LookupError("organization workspace not found")
        if actor in {"admin", "system", "web:admin"}:
            return "system_admin"
        row = conn.execute("SELECT role FROM organization_members WHERE workspace_id = ? AND member_open_id = ? AND status = 'active'", (workspace_id, actor)).fetchone()
    return str(row["role"]) if row else ""


def _asset_visible(row: Any, role: str) -> bool:
    if role in {"system_admin", "owner", "member"}:
        return True
    return str(row["permission_scope"]) == "workspace" and str(row["sensitivity"]) == "normal"


def _refresh_expired_assets(settings: Settings, workspace_id: str) -> None:
    today = date.today().isoformat()
    with connection(settings) as conn:
        conn.execute(
            "UPDATE bid_memory_assets SET reuse_status = 'expired', updated_at = datetime('now') WHERE workspace_id = ? AND valid_until IS NOT NULL AND valid_until <> '' AND substr(valid_until, 1, 10) < ? AND reuse_status NOT IN ('invalid', 'expired')",
            (workspace_id, today),
        )


def _effective_status(row: Any) -> str:
    status = str(row["reuse_status"] or "reference")
    valid_until = str(row["valid_until"] or "")[:10]
    if status == "invalid" or row["withdrawn_at"]:
        return "invalid"
    if valid_until and valid_until < date.today().isoformat():
        return "expired"
    return status


def _record_audit(settings: Settings, *, workspace_id: str, action: str, actor: str, note: str, project_memory_id: str = "", asset_id: str = "", before: dict[str, object] | None = None, after: dict[str, object] | None = None) -> None:
    with connection(settings) as conn:
        conn.execute(
            "INSERT INTO bid_memory_audit_events(id, workspace_id, project_memory_id, asset_id, action, actor_open_id, note, before_json, after_json) VALUES (?, ?, NULLIF(?, ''), NULLIF(?, ''), ?, ?, ?, ?, ?)",
            (str(uuid4()), workspace_id, project_memory_id, asset_id, action, actor.strip() or "admin", note[:1000], json_dumps(before or {}), json_dumps(after or {})),
        )


def _audit_payload(row: Any) -> dict[str, object]:
    return {"id": str(row["id"]), "project_memory_id": str(row["project_memory_id"] or ""), "asset_id": str(row["asset_id"] or ""), "action": str(row["action"]), "actor": str(row["actor_open_id"]), "note": str(row["note"] or ""), "created_at": str(row["created_at"] or "")}


def _decision_content(opportunity: dict[str, object]) -> str:
    workflow = opportunity.get("workflow") if isinstance(opportunity.get("workflow"), dict) else {}
    return " · ".join(value for value in (f"阶段 {workflow.get('stage_label') or workflow.get('stage') or '已结束'}", f"决策 {workflow.get('decision') or '待记录'}", str(workflow.get("decision_reason") or "")) if value)


def _tokens(text: str) -> list[str]:
    segmented = segment_for_fts(text)
    tokens = [token.lower() for token in segmented.split() if len(token.strip()) >= 2 and re.search(r"[\w\u4e00-\u9fff]", token)]
    return list(dict.fromkeys(tokens))[:80]


def _asset_type_label(value: str) -> str:
    return {"requirement": "历史要求", "material": "可复用材料", "evidence": "能力证据", "lesson": "复盘经验", "gap": "历史缺口", "competitor": "竞争经验", "decision": "投标决策", "task": "执行任务", "outcome": "项目结果"}.get(value, value)


def _graph_legend() -> list[dict[str, str]]:
    return [{"type": key, "label": label} for key, label in (("target", "当前机会"), ("project", "历史项目"), ("customer", "客户"), ("region", "地区"), ("category", "品类"), ("requirement", "要求"), ("material", "材料"), ("task", "任务"), ("gap", "缺口"), ("competitor", "竞争"), ("decision", "决策"), ("outcome", "结果"))]


def _rules() -> dict[str, object]:
    return {"rule_version": "enterprise_bid_memory_v1", "no_win_probability": True, "workspace_isolation": True, "expired_never_reusable": True, "human_confirmation_audited": True}


def _empty_summary() -> dict[str, int]:
    return {key: 0 for key in ("project_count", "asset_count", "reusable_count", "update_needed_count", "reference_count", "expired_count", "invalid_count", "won_count", "lost_count", "hidden_sensitive_count", "recommendation_count")}


def _unique_texts(values: list[str], *, limit: int) -> list[str]:
    return list(dict.fromkeys(" ".join(str(value).split())[:80] for value in values if str(value).strip()))[:limit]


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]


def _json_object(value: object) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: object) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []
