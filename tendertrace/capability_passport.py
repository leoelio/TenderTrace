from __future__ import annotations

from datetime import date
import hashlib
import json
from typing import Any
from uuid import uuid4

from tendertrace.capability_matching import (
    CAPABILITY_TYPE_LABELS,
    MATCH_VERDICT_LABELS,
    capability_match_summary,
    capability_workspace_id,
    list_capabilities,
    list_requirement_capability_matches,
)
from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.opportunity_requirements import REQUIREMENT_TYPE_LABELS, list_requirements


ACTION_LABELS = {
    "supplement_material": "补充材料",
    "internal_confirmation": "内部确认",
    "partner_support": "伙伴协同",
    "abandon_requirement": "放弃要求",
}


def build_capability_passport(
    settings: Settings,
    notice_id: str,
    *,
    workspace_id: str = "",
) -> dict[str, object]:
    init_db(settings)
    selected_workspace = workspace_id.strip() or capability_workspace_id(settings, notice_id)
    requirements = [item for item in list_requirements(settings, notice_id) if item.status != "superseded"]
    matches = list_requirement_capability_matches(settings, notice_id)
    capabilities = list_capabilities(settings, workspace_id=selected_workspace)
    with connection(settings) as conn:
        actions = _rows(
            conn,
            """
            SELECT action.*, requirement.requirement_key, requirement.title AS requirement_title,
                   task.feishu_task_guid, task.feishu_task_status
            FROM capability_gap_actions action
            JOIN opportunity_requirements requirement ON requirement.id = action.requirement_id
            LEFT JOIN bid_plan_tasks task ON task.id = action.bid_plan_task_id
            WHERE action.notice_id = ? ORDER BY action.status, action.created_at DESC
            """,
            (notice_id,),
        )
        versions = _rows(
            conn,
            """
            SELECT version.id, version.capability_id, capability.title, version.version_number,
                   version.content_hash, version.actor, version.created_at
            FROM capability_versions version
            JOIN enterprise_capabilities capability ON capability.id = version.capability_id
            WHERE capability.workspace_id = ?
            ORDER BY version.created_at DESC, version.version_number DESC LIMIT 100
            """,
            (selected_workspace,),
        )
        audits = _rows(
            conn,
            """
            SELECT action, actor, capability_id, notice_id, payload_json, created_at
            FROM capability_audit_events
            WHERE workspace_id = ? AND (notice_id IS NULL OR notice_id = ?)
            ORDER BY created_at DESC, rowid DESC LIMIT 80
            """,
            (selected_workspace, notice_id),
        )
    for action in actions:
        action["action_type_label"] = ACTION_LABELS.get(str(action["action_type"]), str(action["action_type"]))
    for audit in audits:
        audit["payload"] = _json_dict(audit.pop("payload_json", "{}"))
    requirement_tree = [
        {
            "type": kind,
            "label": label,
            "items": [item.to_dict() for item in requirements if item.requirement_type == kind],
        }
        for kind, label in REQUIREMENT_TYPE_LABELS.items()
        if any(item.requirement_type == kind for item in requirements)
    ]
    passports = [
        {
            "type": kind,
            "label": CAPABILITY_TYPE_LABELS.get(kind, kind),
            "items": [item.to_dict() for item in capabilities if _canonical_type(item.capability_type) == kind],
        }
        for kind in (
            "product_parameter",
            "qualification_certificate",
            "personnel_skill",
            "delivery_service",
            "project_case",
            "partner_authorization",
        )
    ]
    matrix = []
    for requirement in requirements:
        linked = [item.to_dict() for item in matches if item.requirement_id == requirement.id]
        matrix.append(
            {
                "requirement": requirement.to_dict(),
                "matches": linked,
                "best_verdict": _best_verdict(linked),
                "best_verdict_label": MATCH_VERDICT_LABELS[_best_verdict(linked)],
            }
        )
    alerts = _alerts(capabilities, matches)
    summary = {
        **capability_match_summary(settings, notice_id),
        "passport_count": len(capabilities),
        "verified_passport_count": sum(item.verification_status == "verified" for item in capabilities),
        "alert_count": len(alerts),
        "open_gap_action_count": sum(item["status"] == "open" for item in actions),
        "confirmed_snapshot_count": sum(item.status == "confirmed" and bool(item.project_snapshot_id) for item in matches),
    }
    return {
        "notice_id": notice_id,
        "workspace_id": selected_workspace,
        "summary": summary,
        "requirement_tree": requirement_tree,
        "passports": passports,
        "matrix": matrix,
        "alerts": alerts,
        "gap_actions": actions,
        "similar_cases": similar_case_rankings(settings, notice_id, workspace_id=selected_workspace),
        "versions": versions,
        "audit_events": audits,
        "rules": {
            "verdicts": MATCH_VERDICT_LABELS,
            "human_confirmation_required": True,
            "project_version_snapshot_required": True,
            "action_types": ACTION_LABELS,
        },
    }


def create_gap_action(
    settings: Settings,
    notice_id: str,
    match_id: str,
    *,
    action_type: str,
    actor: str,
    assignee_member_id: str = "",
    due_at: str = "",
    title: str = "",
) -> dict[str, object]:
    if action_type not in ACTION_LABELS:
        raise ValueError(f"unsupported gap action type: {action_type}")
    if not actor.strip():
        raise ValueError("actor is required")
    init_db(settings)
    with connection(settings) as conn:
        match = conn.execute(
            """
            SELECT matched.*, requirement.title AS requirement_title
            FROM requirement_capability_matches matched
            JOIN opportunity_requirements requirement ON requirement.id = matched.requirement_id
            WHERE matched.id = ? AND matched.notice_id = ?
            """,
            (match_id, notice_id),
        ).fetchone()
        if match is None:
            raise LookupError("capability match not found")
        if assignee_member_id and conn.execute(
            "SELECT 1 FROM opportunity_team_members WHERE id = ? AND notice_id = ? AND status = 'active'",
            (assignee_member_id, notice_id),
        ).fetchone() is None:
            raise ValueError("assignee must be an active opportunity member")
        action_id = str(uuid4())
        task_key = f"CAP-GAP-{action_id[:8].upper()}"
        task_id = hashlib.sha256(f"{notice_id}|task|{task_key}".encode()).hexdigest()[:24]
        action_title = title.strip() or f"{ACTION_LABELS[action_type]}：{match['requirement_title']}"
        conn.execute(
            """
            INSERT INTO bid_plan_tasks(
                id, notice_id, requirement_id, task_key, title, milestone_type,
                due_at, dependency_keys_json, formal
            ) VALUES (?, ?, ?, ?, ?, 'capability_gap', ?, '[]', 1)
            """,
            (task_id, notice_id, match["requirement_id"], task_key, action_title, due_at or None),
        )
        conn.execute(
            """
            INSERT INTO capability_gap_actions(
                id, notice_id, requirement_id, match_id, action_type, title,
                assignee_member_id, due_at, bid_plan_task_id, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (action_id, notice_id, match["requirement_id"], match_id, action_type, action_title, assignee_member_id or None, due_at or None, task_id, actor.strip()),
        )
        _audit(conn, str(match["workspace_id"] or "default"), notice_id, str(match["capability_id"] or ""), "gap_action_created", actor, {"action_id": action_id, "action_type": action_type, "task_id": task_id})
    return next(item for item in build_capability_passport(settings, notice_id)["gap_actions"] if item["id"] == action_id)


def complete_gap_action(
    settings: Settings,
    notice_id: str,
    action_id: str,
    *,
    actor: str,
    note: str,
) -> dict[str, object]:
    if not actor.strip() or not note.strip():
        raise ValueError("actor and completion note are required")
    with connection(settings) as conn:
        action = conn.execute(
            """
            SELECT action.*, matched.workspace_id, matched.capability_id
            FROM capability_gap_actions action
            JOIN requirement_capability_matches matched ON matched.id = action.match_id
            WHERE action.id = ? AND action.notice_id = ?
            """,
            (action_id, notice_id),
        ).fetchone()
        if action is None:
            raise LookupError("capability gap action not found")
        conn.execute(
            """
            UPDATE capability_gap_actions SET status = 'completed', completed_by = ?,
                completion_note = ?, completed_at = datetime('now'), updated_at = datetime('now')
            WHERE id = ?
            """,
            (actor.strip(), note.strip(), action_id),
        )
        if action["bid_plan_task_id"]:
            conn.execute(
                "UPDATE bid_plan_tasks SET status = 'completed', completed_at = datetime('now'), updated_at = datetime('now') WHERE id = ?",
                (action["bid_plan_task_id"],),
            )
        _audit(conn, str(action["workspace_id"] or "default"), notice_id, str(action["capability_id"] or ""), "gap_action_completed", actor, {"action_id": action_id, "note": note.strip()})
    return next(item for item in build_capability_passport(settings, notice_id)["gap_actions"] if item["id"] == action_id)


def sync_project_results_to_passport(settings: Settings, notice_id: str) -> dict[str, int]:
    init_db(settings)
    with connection(settings) as conn:
        outcome = conn.execute(
            """
            SELECT outcome.*, notice.title, notice.region
            FROM opportunity_outcomes outcome JOIN notices notice ON notice.id = outcome.notice_id
            WHERE outcome.notice_id = ?
            """,
            (notice_id,),
        ).fetchone()
        if outcome is None:
            raise LookupError("project outcome not found")
        matches = conn.execute(
            """
            SELECT DISTINCT matched.capability_id, capability.industry, capability.product_model
            FROM requirement_capability_matches matched
            JOIN enterprise_capabilities capability ON capability.id = matched.capability_id
            WHERE matched.notice_id = ? AND matched.status = 'confirmed' AND matched.verdict = 'supported'
            """,
            (notice_id,),
        ).fetchall()
        for item in matches:
            record_id = hashlib.sha256(f"{item['capability_id']}|{notice_id}".encode()).hexdigest()[:24]
            conn.execute(
                """
                INSERT INTO capability_performance_records(
                    id, capability_id, notice_id, project_title, industry, region, amount,
                    product_model, result, evidence_url, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(capability_id, notice_id) DO UPDATE SET
                    result = excluded.result, amount = excluded.amount,
                    evidence_url = excluded.evidence_url, occurred_at = excluded.occurred_at
                """,
                (record_id, item["capability_id"], notice_id, outcome["title"], item["industry"] or "", outcome["region"] or "", outcome["award_amount"] or 0, item["product_model"] or "", outcome["result"], outcome["evidence_url"] or "", outcome["finalized_at"]),
            )
    return {"synced_count": len(matches)}


def similar_case_rankings(settings: Settings, notice_id: str, *, workspace_id: str = "default") -> list[dict[str, object]]:
    with connection(settings) as conn:
        notice = conn.execute("SELECT title, region, fields_json FROM notices WHERE id = ?", (notice_id,)).fetchone()
        if notice is None:
            return []
        rows = _rows(
            conn,
            """
            SELECT record.*, capability.title AS capability_title, capability.sample_redacted
            FROM capability_performance_records record
            JOIN enterprise_capabilities capability ON capability.id = record.capability_id
            WHERE capability.workspace_id = ? AND record.notice_id <> ?
            """,
            (workspace_id, notice_id),
        )
    target_region = str(notice["region"] or "")
    fields = _json_dict(notice["fields_json"])
    structured = fields.get("structured_fields") if isinstance(fields.get("structured_fields"), dict) else {}
    try:
        target_amount = float(structured.get("budget") or fields.get("budget") or 0)
    except (TypeError, ValueError):
        target_amount = 0
    for row in rows:
        score = 0
        dimensions = []
        if target_region and row["region"] and (target_region in str(row["region"]) or str(row["region"]) in target_region):
            score += 30
            dimensions.append("同地区")
        if target_amount and row["amount"]:
            ratio = min(float(row["amount"]), target_amount) / max(float(row["amount"]), target_amount)
            if ratio >= .7:
                score += 20
                dimensions.append("金额相近")
        if row["product_model"]:
            score += 20
            dimensions.append("型号可核验")
        if row["industry"]:
            score += 15
            dimensions.append("行业已标注")
        if row["result"] == "won":
            score += 15
            dimensions.append("中标案例")
        row["similarity_score"] = score
        row["matched_dimensions"] = dimensions
        row["sample_count"] = 1
        row["sample_redacted"] = bool(row["sample_redacted"])
    return sorted(rows, key=lambda item: (int(item["similarity_score"]), str(item["occurred_at"] or "")), reverse=True)[:12]


def _alerts(capabilities: list[Any], matches: list[Any]) -> list[dict[str, object]]:
    alerts: list[dict[str, object]] = []
    today = date.today()
    for capability in capabilities:
        if capability.verification_status == "expired":
            alerts.append(_alert("expired", "高", capability.id, f"{capability.title} 已失效"))
        elif capability.valid_until:
            remaining = (date.fromisoformat(capability.valid_until) - today).days
            if remaining <= 60:
                alerts.append(_alert("expiring", "高" if remaining <= 30 else "中", capability.id, f"{capability.title} 将在 {remaining} 天后到期"))
        if not capability.applicable_entity:
            alerts.append(_alert("entity_missing", "中", capability.id, f"{capability.title} 尚未标注适用主体"))
        if capability.capability_type == "partner_authorization" and not capability.authorization_scope:
            alerts.append(_alert("authorization_scope_missing", "高", capability.id, f"{capability.title} 缺少授权范围"))
    seen = {str(item["code"]) + str(item["ref_id"]) for item in alerts}
    for match in matches:
        if match.conflict_code and match.conflict_code + match.id not in seen:
            alerts.append(_alert(match.conflict_code, "高", match.id, match.rationale))
    return alerts


def _alert(code: str, severity: str, ref_id: str, message: str) -> dict[str, object]:
    return {"code": code, "severity": severity, "ref_id": ref_id, "message": message}


def _best_verdict(matches: list[dict[str, object]]) -> str:
    if not matches:
        return "needs_evidence"
    if any(item.get("verdict") == "supported" and item.get("status") == "confirmed" for item in matches):
        return "supported"
    rank = {"conflict": 5, "gap": 4, "needs_evidence": 3, "pending": 2, "supported": 1}
    return max((str(item.get("verdict") or "pending") for item in matches), key=lambda value: rank.get(value, 0))


def _canonical_type(value: str) -> str:
    return {"product": "product_parameter", "qualification": "qualification_certificate", "delivery": "delivery_service", "case": "project_case"}.get(value, value)


def _rows(conn: Any, sql: str, params: tuple[object, ...]) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _json_dict(value: object) -> dict[str, object]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _audit(conn: Any, workspace_id: str, notice_id: str, capability_id: str, action: str, actor: str, payload: dict[str, object]) -> None:
    conn.execute(
        "INSERT INTO capability_audit_events(id, workspace_id, capability_id, notice_id, action, actor, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(uuid4()), workspace_id or "default", capability_id or None, notice_id, action, actor.strip(), json.dumps(payload, ensure_ascii=False, sort_keys=True)),
    )
