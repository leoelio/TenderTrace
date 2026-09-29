from __future__ import annotations

import csv
from datetime import datetime, time, timedelta, timezone
import hashlib
from io import StringIO
import json
from pathlib import Path
import re
from typing import Any
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.opportunity_requirements import (
    REQUIREMENT_TYPE_LABELS,
    list_requirements,
    upsert_requirement,
)
from tendertrace.retrieval import parse_date


CONFIRMED_STATUSES = {"confirmed", "assigned", "in_progress", "review", "completed"}
RESPONSIBILITY_LABELS = {"R": "执行", "A": "批准", "C": "会签", "I": "知会"}
DELIVERABLE_TEMPLATES = {
    "qualification": ("资格证明与核验清单", "qualification_pack"),
    "deadline": ("递交时间与渠道确认单", "deadline_check"),
    "scoring": ("评分响应与得分证据", "scoring_response"),
    "disqualification": ("废标红线核验表", "redline_check"),
    "attachment": ("附件文件与签章检查", "attachment"),
    "technical": ("技术偏离与响应表", "technical_response"),
    "commercial": ("商务偏离与报价依据", "commercial_response"),
}
ROLE_BY_TYPE = {
    "qualification": "legal",
    "deadline": "commercial",
    "scoring": "solution",
    "disqualification": "legal",
    "attachment": "commercial",
    "technical": "solution",
    "commercial": "commercial",
}
ROLE_LABELS = {
    "solution": "方案技术",
    "commercial": "商务报价",
    "delivery": "交付实施",
    "legal": "法务合规",
}


def get_bid_workplan(settings: Settings, notice_id: str) -> dict[str, object]:
    init_db(settings)
    requirements = [item for item in list_requirements(settings, notice_id) if item.status != "superseded"]
    with connection(settings) as conn:
        if conn.execute("SELECT 1 FROM notices WHERE id = ?", (notice_id,)).fetchone() is None:
            raise LookupError("opportunity notice not found")
        deliverables = _rows(conn, "SELECT * FROM bid_deliverables WHERE notice_id = ? ORDER BY due_at, deliverable_key", notice_id)
        responsibilities = _rows(conn, "SELECT * FROM bid_responsibility_assignments WHERE notice_id = ? ORDER BY requirement_id, responsibility_type", notice_id)
        tasks = _rows(conn, "SELECT * FROM bid_plan_tasks WHERE notice_id = ? ORDER BY due_at, task_key", notice_id)
        pricing = _rows(conn, "SELECT * FROM bid_pricing_items WHERE notice_id = ? ORDER BY item_key", notice_id)
        history = _rows(conn, "SELECT * FROM bid_requirement_history WHERE notice_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 80", notice_id)
        matches = _rows(
            conn,
            "SELECT requirement_id, verdict, status, confidence FROM requirement_capability_matches WHERE notice_id = ?",
            notice_id,
        )
    for task in tasks:
        task["dependency_keys"] = _json_list(task.pop("dependency_keys_json", "[]"))
        task["formal"] = bool(task.get("formal"))
    for item in history:
        item["before"] = _json_dict(item.pop("before_json", "{}"))
        item["after"] = _json_dict(item.pop("after_json", "{}"))
    gaps = _gap_lanes(requirements, deliverables, matches)
    redlines = [
        item.to_dict()
        for item in requirements
        if item.requirement_type in {"disqualification", "deadline"}
        or bool(re.search(r"(?:签字|盖章|密封|格式|拒收|无效|废标|否决)", item.evidence_text))
    ]
    pricing_summary = _pricing_summary(pricing)
    formal_tasks = [item for item in tasks if item.get("formal")]
    completed_tasks = [item for item in formal_tasks if item.get("status") == "completed"]
    summary = {
        "requirement_count": len(requirements),
        "confirmed_count": sum(item.status in CONFIRMED_STATUSES for item in requirements),
        "deliverable_count": len(deliverables),
        "task_count": len(formal_tasks),
        "completed_task_count": len(completed_tasks),
        "execution_readiness": round(len(completed_tasks) / len(formal_tasks) * 100) if formal_tasks else 0,
        "redline_count": len(redlines),
        "gap_count": sum(len(items) for items in gaps.values()),
        **pricing_summary,
    }
    tree = [
        {
            "type": requirement_type,
            "label": label,
            "items": [item.to_dict() for item in requirements if item.requirement_type == requirement_type],
        }
        for requirement_type, label in REQUIREMENT_TYPE_LABELS.items()
        if any(item.requirement_type == requirement_type for item in requirements)
    ]
    return {
        "notice_id": notice_id,
        "summary": summary,
        "requirement_tree": tree,
        "deliverables": deliverables,
        "responsibilities": responsibilities,
        "tasks": tasks,
        "pricing": pricing,
        "pricing_summary": pricing_summary,
        "gap_lanes": gaps,
        "redlines": redlines,
        "history": history,
        "rules": {
            "formal_tasks_require_confirmation": True,
            "source_trace_required": True,
            "readiness_formula": "已完成正式任务数 / 正式任务总数",
        },
    }


def confirm_requirement(
    settings: Settings,
    notice_id: str,
    requirement_id: str,
    *,
    actor: str,
    assignee_member_id: str = "",
    due_at: str = "",
) -> dict[str, object]:
    init_db(settings)
    with connection(settings) as conn:
        row = conn.execute(
            "SELECT * FROM opportunity_requirements WHERE id = ? AND notice_id = ?",
            (requirement_id, notice_id),
        ).fetchone()
        if row is None:
            raise LookupError("requirement not found")
        if assignee_member_id and conn.execute(
            "SELECT 1 FROM opportunity_team_members WHERE id = ? AND notice_id = ? AND status = 'active'",
            (assignee_member_id, notice_id),
        ).fetchone() is None:
            raise ValueError("assignee_member_id must be an active member of this opportunity")
        before = dict(row)
        conn.execute(
            """
            UPDATE opportunity_requirements
            SET status = 'confirmed',
                assignee_member_id = CASE WHEN ? = '' THEN assignee_member_id ELSE ? END,
                due_at = CASE WHEN ? = '' THEN due_at ELSE ? END,
                confirmed_at = COALESCE(confirmed_at, datetime('now')),
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (assignee_member_id, assignee_member_id, due_at, due_at, requirement_id),
        )
        after = dict(conn.execute("SELECT * FROM opportunity_requirements WHERE id = ?", (requirement_id,)).fetchone())
        _history(conn, notice_id, requirement_id, "confirmed", before, after, actor)
        _event(conn, notice_id, "bid_requirement_confirmed", actor, {"requirement_id": requirement_id})
    return after


def split_requirement(
    settings: Settings,
    notice_id: str,
    requirement_id: str,
    parts: list[dict[str, object]],
    *,
    actor: str,
) -> list[dict[str, object]]:
    if len(parts) < 2:
        raise ValueError("split requires at least two parts")
    init_db(settings)
    with connection(settings) as conn:
        parent = conn.execute(
            "SELECT * FROM opportunity_requirements WHERE id = ? AND notice_id = ?",
            (requirement_id, notice_id),
        ).fetchone()
    if parent is None:
        raise LookupError("requirement not found")
    if str(parent["status"]) == "superseded":
        raise ValueError("superseded requirement cannot be split again")
    child_status = "confirmed" if str(parent["status"]) in CONFIRMED_STATUSES else "pending"
    children = []
    for index, part in enumerate(parts, start=1):
        title = str(part.get("title") or "").strip()
        if not title:
            raise ValueError("every split part requires a title")
        child = upsert_requirement(
            settings,
            notice_id=notice_id,
            requirement_key=str(part.get("requirement_key") or f"{parent['requirement_key']}.{index}"),
            requirement_type=str(part.get("requirement_type") or parent["requirement_type"]),
            title=title,
            evidence_text=str(part.get("evidence_text") or parent["evidence_text"]),
            source_url=str(parent["source_url"]),
            source_locator=str(part.get("source_locator") or parent["source_locator"]),
            mandatory=bool(part.get("mandatory", parent["mandatory"])),
            confidence=int(part.get("confidence") or parent["confidence"]),
            weight=float(part.get("weight") or 0),
            status=child_status,
            assignee_member_id=str(part.get("assignee_member_id") or parent["assignee_member_id"] or ""),
            due_at=str(part.get("due_at") or parent["due_at"] or ""),
            note=str(part.get("note") or "由复杂要求拆分"),
            source_revision_id=str(parent["source_revision_id"] or ""),
            parent_requirement_id=requirement_id,
            extraction_mode="manual",
            actor=actor,
        )
        children.append(child.to_dict())
    with connection(settings) as conn:
        before = dict(conn.execute("SELECT * FROM opportunity_requirements WHERE id = ?", (requirement_id,)).fetchone())
        conn.execute("UPDATE opportunity_requirements SET status = 'superseded', updated_at = datetime('now') WHERE id = ?", (requirement_id,))
        after = dict(conn.execute("SELECT * FROM opportunity_requirements WHERE id = ?", (requirement_id,)).fetchone())
        _history(conn, notice_id, requirement_id, "split", before, {**after, "child_ids": [item["id"] for item in children]}, actor)
        _event(conn, notice_id, "bid_requirement_split", actor, {"requirement_id": requirement_id, "child_ids": [item["id"] for item in children]})
    return children


def merge_requirements(
    settings: Settings,
    notice_id: str,
    requirement_ids: list[str],
    *,
    requirement_key: str,
    title: str,
    actor: str,
) -> dict[str, object]:
    unique_ids = list(dict.fromkeys(value.strip() for value in requirement_ids if value.strip()))
    if len(unique_ids) < 2:
        raise ValueError("merge requires at least two requirements")
    with connection(settings) as conn:
        placeholders = ",".join("?" for _ in unique_ids)
        rows = conn.execute(
            f"SELECT * FROM opportunity_requirements WHERE notice_id = ? AND id IN ({placeholders})",
            (notice_id, *unique_ids),
        ).fetchall()
    if len(rows) != len(unique_ids):
        raise LookupError("one or more requirements were not found")
    if any(str(row["status"]) == "superseded" for row in rows):
        raise ValueError("superseded requirements cannot be merged")
    first = rows[0]
    merged = upsert_requirement(
        settings,
        notice_id=notice_id,
        requirement_key=requirement_key,
        requirement_type=str(first["requirement_type"]),
        title=title,
        evidence_text="\n".join(str(row["evidence_text"]) for row in rows),
        source_url=str(first["source_url"]),
        source_locator="；".join(dict.fromkeys(str(row["source_locator"]) for row in rows)),
        mandatory=any(bool(row["mandatory"]) for row in rows),
        confidence=min(int(row["confidence"] or 0) for row in rows),
        weight=min(sum(float(row["weight"] or 0) for row in rows), 100),
        status="confirmed" if all(str(row["status"]) in CONFIRMED_STATUSES for row in rows) else "pending",
        note="由多条要求合并，原始要求与来源保留在编辑历史中。",
        source_revision_id=str(first["source_revision_id"] or ""),
        parent_requirement_id=",".join(unique_ids),
        extraction_mode="manual",
        actor=actor,
    )
    with connection(settings) as conn:
        for row in rows:
            before = dict(row)
            conn.execute("UPDATE opportunity_requirements SET status = 'superseded', updated_at = datetime('now') WHERE id = ?", (row["id"],))
            after = dict(conn.execute("SELECT * FROM opportunity_requirements WHERE id = ?", (row["id"],)).fetchone())
            _history(conn, notice_id, str(row["id"]), "merged", before, {**after, "merged_into": merged.id}, actor)
        _event(conn, notice_id, "bid_requirements_merged", actor, {"source_ids": unique_ids, "merged_id": merged.id})
    return merged.to_dict()


def build_bid_workplan(settings: Settings, notice_id: str, *, actor: str) -> dict[str, object]:
    init_db(settings)
    requirements = [item for item in list_requirements(settings, notice_id) if item.status in CONFIRMED_STATUSES]
    if not requirements:
        raise ValueError("请先人工确认至少一条要求，再生成正式作战计划")
    deadline = _bid_deadline(settings, notice_id)
    content_due = deadline - timedelta(days=4) if deadline else None
    team = _team_members(settings, notice_id)
    prep_keys: list[str] = []
    with connection(settings) as conn:
        for requirement in requirements:
            template_title, file_type = DELIVERABLE_TEMPLATES[requirement.requirement_type]
            deliverable_key = f"{requirement.requirement_key}-D1"
            deliverable_id = _stable_id(notice_id, "deliverable", deliverable_key)
            conn.execute(
                """
                INSERT INTO bid_deliverables(
                    id, notice_id, requirement_id, deliverable_key, title, file_type,
                    status, owner_member_id, due_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                ON CONFLICT(notice_id, deliverable_key) DO UPDATE SET
                    title = excluded.title, file_type = excluded.file_type,
                    owner_member_id = COALESCE(bid_deliverables.owner_member_id, excluded.owner_member_id),
                    due_at = excluded.due_at, updated_at = datetime('now')
                """,
                (
                    deliverable_id,
                    notice_id,
                    requirement.id,
                    deliverable_key,
                    f"{requirement.requirement_key} · {template_title}",
                    file_type,
                    requirement.assignee_member_id or None,
                    _iso(content_due),
                ),
            )
            _upsert_raci(conn, notice_id, requirement.to_dict(), team)
            prep_key = f"{requirement.requirement_key}-PREP"
            prep_keys.append(prep_key)
            _upsert_task(
                conn,
                notice_id,
                requirement.id,
                prep_key,
                f"完成 {requirement.requirement_key} 交付物",
                "requirement_delivery",
                content_due,
                [],
                True,
            )
            if requirement.requirement_type in {"commercial", "technical"}:
                _upsert_default_pricing(conn, notice_id, requirement.to_dict())
        milestones = [
            ("MILESTONE-REVIEW", "内部终审", "review", deadline - timedelta(days=2) if deadline else None, prep_keys),
            ("MILESTONE-SEAL", "签字盖章与格式复核", "seal", deadline - timedelta(days=1) if deadline else None, ["MILESTONE-REVIEW"]),
            ("MILESTONE-LOCK", "终版锁定与上传预检", "package", deadline - timedelta(hours=8) if deadline else None, ["MILESTONE-SEAL"]),
            ("MILESTONE-SUBMIT", "正式递交并留存回执", "submission", deadline - timedelta(hours=2) if deadline else None, ["MILESTONE-LOCK"]),
        ]
        for key, title, milestone_type, due_at, dependencies in milestones:
            _upsert_task(conn, notice_id, None, key, title, milestone_type, due_at, dependencies, True)
        _event(conn, notice_id, "bid_workplan_built", actor, {"requirement_count": len(requirements), "deadline": _iso(deadline)})
    return get_bid_workplan(settings, notice_id)


def complete_bid_task(
    settings: Settings,
    notice_id: str,
    task_id: str,
    *,
    actor: str,
) -> dict[str, object]:
    init_db(settings)
    with connection(settings) as conn:
        task = conn.execute("SELECT * FROM bid_plan_tasks WHERE id = ? AND notice_id = ?", (task_id, notice_id)).fetchone()
        if task is None:
            raise LookupError("bid plan task not found")
        dependencies = _json_list(task["dependency_keys_json"])
        if dependencies:
            placeholders = ",".join("?" for _ in dependencies)
            open_dependency = conn.execute(
                f"SELECT task_key FROM bid_plan_tasks WHERE notice_id = ? AND task_key IN ({placeholders}) AND status <> 'completed' LIMIT 1",
                (notice_id, *dependencies),
            ).fetchone()
            if open_dependency is not None:
                raise ValueError(f"前置任务尚未完成：{open_dependency['task_key']}")
        conn.execute(
            "UPDATE bid_plan_tasks SET status = 'completed', completed_at = datetime('now'), updated_at = datetime('now') WHERE id = ?",
            (task_id,),
        )
        requirement_id = str(task["requirement_id"] or "")
        if requirement_id:
            conn.execute(
                "UPDATE bid_deliverables SET status = 'completed', updated_at = datetime('now') WHERE requirement_id = ?",
                (requirement_id,),
            )
            conn.execute(
                "UPDATE opportunity_requirements SET status = 'completed', updated_at = datetime('now') WHERE id = ?",
                (requirement_id,),
            )
        _event(conn, notice_id, "bid_plan_task_completed", actor, {"task_id": task_id, "requirement_id": requirement_id})
    return get_bid_workplan(settings, notice_id)


def upsert_pricing_item(
    settings: Settings,
    notice_id: str,
    *,
    item_key: str,
    title: str,
    requirement_id: str = "",
    quantity: float = 1,
    unit: str = "项",
    unit_price: float = 0,
    cost: float = 0,
    tax_rate: float = 0,
    owner_member_id: str = "",
    status: str = "draft",
    note: str = "",
) -> dict[str, object]:
    if not item_key.strip() or not title.strip():
        raise ValueError("item_key and title are required")
    if any(value < 0 for value in (quantity, unit_price, cost, tax_rate)):
        raise ValueError("pricing values cannot be negative")
    if status not in {"draft", "review", "approved"}:
        raise ValueError("unsupported pricing status")
    init_db(settings)
    item_id = _stable_id(notice_id, "pricing", item_key)
    with connection(settings) as conn:
        if requirement_id and conn.execute(
            "SELECT 1 FROM opportunity_requirements WHERE id = ? AND notice_id = ?",
            (requirement_id, notice_id),
        ).fetchone() is None:
            raise LookupError("requirement not found")
        conn.execute(
            """
            INSERT INTO bid_pricing_items(
                id, notice_id, requirement_id, item_key, title, quantity, unit,
                unit_price, cost, tax_rate, owner_member_id, status, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(notice_id, item_key) DO UPDATE SET
                requirement_id = excluded.requirement_id, title = excluded.title,
                quantity = excluded.quantity, unit = excluded.unit,
                unit_price = excluded.unit_price, cost = excluded.cost,
                tax_rate = excluded.tax_rate, owner_member_id = excluded.owner_member_id,
                status = excluded.status, note = excluded.note, updated_at = datetime('now')
            """,
            (item_id, notice_id, requirement_id or None, item_key.strip(), title.strip(), float(quantity), unit.strip() or "项", float(unit_price), float(cost), float(tax_rate), owner_member_id or None, status, note.strip()),
        )
        row = conn.execute("SELECT * FROM bid_pricing_items WHERE id = ?", (item_id,)).fetchone()
    return dict(row)


def export_bid_workplan(settings: Settings, notice_id: str) -> Path:
    plan = get_bid_workplan(settings, notice_id)
    output_dir = settings.outputs_dir / "bid_workplans"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{notice_id}-bid-workplan.zip"
    requirements = [item for group in plan["requirement_tree"] for item in group["items"]]
    gaps = [
        {"lane": lane, "requirement_id": item.get("requirement_id", ""), "requirement_key": item.get("requirement_key", ""), "reason": item.get("reason", "")}
        for lane, items in plan["gap_lanes"].items()
        for item in items
    ]
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("01_要求目录.csv", _csv(requirements, ["id", "requirement_key", "requirement_type_label", "title", "mandatory", "weight", "status_label", "source_locator", "source_url"]))
        archive.writestr("02_交付物.csv", _csv(plan["deliverables"], ["requirement_id", "deliverable_key", "title", "file_type", "status", "owner_member_id", "due_at", "evidence_ref"]))
        archive.writestr("03_RACI责任矩阵.csv", _csv(plan["responsibilities"], ["requirement_id", "responsibility_type", "person_label", "member_id"]))
        archive.writestr("04_倒排计划.csv", _csv(plan["tasks"], ["requirement_id", "task_key", "title", "milestone_type", "due_at", "status", "dependency_keys", "feishu_task_guid"]))
        archive.writestr("05_缺口清单.csv", _csv(gaps, ["lane", "requirement_id", "requirement_key", "reason"]))
        archive.writestr("06_报价计划.csv", _csv(plan["pricing"], ["requirement_id", "item_key", "title", "quantity", "unit", "unit_price", "cost", "tax_rate", "status"]))
        archive.writestr("feishu_bitable_rows.json", json.dumps({"requirements": requirements, "deliverables": plan["deliverables"], "raci": plan["responsibilities"], "tasks": plan["tasks"], "gaps": gaps, "pricing": plan["pricing"]}, ensure_ascii=False, indent=2, default=str))
    return path


def _gap_lanes(requirements: list[Any], deliverables: list[dict[str, Any]], matches: list[dict[str, Any]]) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {
        "material_missing": [],
        "capability_gap": [],
        "evidence_insufficient": [],
        "conflict": [],
        "awaiting_confirmation": [],
    }
    deliverable_by_requirement = {str(item["requirement_id"]): item for item in deliverables}
    matches_by_requirement: dict[str, list[dict[str, Any]]] = {}
    for match in matches:
        matches_by_requirement.setdefault(str(match["requirement_id"]), []).append(match)
    for requirement in requirements:
        base = {"requirement_id": requirement.id, "requirement_key": requirement.requirement_key}
        if requirement.status == "pending":
            result["awaiting_confirmation"].append({**base, "reason": "要求尚未人工确认"})
        deliverable = deliverable_by_requirement.get(requirement.id)
        if requirement.status in CONFIRMED_STATUSES and (not deliverable or not str(deliverable.get("evidence_ref") or "")):
            result["material_missing"].append({**base, "reason": "交付物尚未绑定材料或成稿证据"})
        requirement_matches = matches_by_requirement.get(requirement.id, [])
        if requirement_matches and any(item.get("verdict") == "gap" for item in requirement_matches):
            result["capability_gap"].append({**base, "reason": "能力匹配已确认存在缺口"})
        elif requirement.status in CONFIRMED_STATUSES and not any(item.get("status") == "confirmed" for item in requirement_matches):
            result["evidence_insufficient"].append({**base, "reason": "尚无经人工确认的能力证据"})
        if requirement.status == "review":
            result["conflict"].append({**base, "reason": "公告变化或会审冲突待处理"})
    return result


def _pricing_summary(items: list[dict[str, Any]]) -> dict[str, object]:
    total = sum(float(item.get("quantity") or 0) * float(item.get("unit_price") or 0) for item in items)
    cost = sum(float(item.get("cost") or 0) for item in items)
    return {
        "quoted_total": round(total, 2),
        "estimated_cost": round(cost, 2),
        "gross_margin": round((total - cost) / total * 100, 2) if total else 0,
        "approved_pricing_count": sum(item.get("status") == "approved" for item in items),
    }


def _team_members(settings: Settings, notice_id: str) -> list[dict[str, Any]]:
    with connection(settings) as conn:
        return _rows(conn, "SELECT * FROM opportunity_team_members WHERE notice_id = ? AND status = 'active' ORDER BY created_at", notice_id)


def _upsert_raci(conn, notice_id: str, requirement: dict[str, Any], team: list[dict[str, Any]]) -> None:
    role = ROLE_BY_TYPE[str(requirement["requirement_type"])]
    matching = next((item for item in team if item.get("id") == requirement.get("assignee_member_id")), None)
    if matching is None:
        matching = next((item for item in team if item.get("role") == role), None)
    labels = {
        "R": str(matching.get("member_name")) if matching else f"待指派·{ROLE_LABELS[role]}",
        "A": "项目负责人（待确认）",
        "C": "法务/商务会签人（待确认）",
        "I": "投标协同组",
    }
    for responsibility_type, person_label in labels.items():
        member_id = str(matching.get("id")) if responsibility_type == "R" and matching else None
        assignment_id = _stable_id(requirement["id"], responsibility_type, person_label)
        conn.execute(
            """
            INSERT INTO bid_responsibility_assignments(
                id, notice_id, requirement_id, responsibility_type, member_id, person_label
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(requirement_id, responsibility_type, person_label) DO UPDATE SET
                member_id = excluded.member_id, updated_at = datetime('now')
            """,
            (assignment_id, notice_id, requirement["id"], responsibility_type, member_id, person_label),
        )


def _upsert_task(conn, notice_id: str, requirement_id: str | None, task_key: str, title: str, milestone_type: str, due_at: datetime | None, dependencies: list[str], formal: bool) -> None:
    task_id = _stable_id(notice_id, "task", task_key)
    conn.execute(
        """
        INSERT INTO bid_plan_tasks(
            id, notice_id, requirement_id, task_key, title, milestone_type,
            due_at, dependency_keys_json, formal
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(notice_id, task_key) DO UPDATE SET
            requirement_id = excluded.requirement_id, title = excluded.title,
            milestone_type = excluded.milestone_type, due_at = excluded.due_at,
            dependency_keys_json = excluded.dependency_keys_json,
            formal = excluded.formal, updated_at = datetime('now')
        """,
        (task_id, notice_id, requirement_id, task_key, title, milestone_type, _iso(due_at), json.dumps(dependencies, ensure_ascii=False), int(formal)),
    )


def _upsert_default_pricing(conn, notice_id: str, requirement: dict[str, Any]) -> None:
    key = f"{requirement['requirement_key']}-PRICE"
    conn.execute(
        """
        INSERT INTO bid_pricing_items(id, notice_id, requirement_id, item_key, title)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(notice_id, item_key) DO NOTHING
        """,
        (_stable_id(notice_id, "pricing", key), notice_id, requirement["id"], key, requirement["title"]),
    )


def _bid_deadline(settings: Settings, notice_id: str) -> datetime | None:
    with connection(settings) as conn:
        row = conn.execute("SELECT fields_json, content_text FROM notices WHERE id = ?", (notice_id,)).fetchone()
    if row is None:
        raise LookupError("opportunity notice not found")
    fields = _json_dict(row["fields_json"])
    structured = fields.get("structured_fields") if isinstance(fields.get("structured_fields"), dict) else {}
    raw = str(structured.get("bid_deadline") or fields.get("bid_deadline") or row["content_text"] or "")
    parsed = parse_date(raw)
    if parsed is None:
        return None
    clock = time(17, 0)
    match = re.search(r"(\d{1,2})\s*[:：时]\s*(\d{1,2})?", raw)
    if match:
        clock = time(min(int(match.group(1)), 23), min(int(match.group(2) or 0), 59))
    return datetime.combine(parsed, clock, tzinfo=timezone(timedelta(hours=8)))


def _history(conn, notice_id: str, requirement_id: str, action: str, before: dict[str, Any], after: dict[str, Any], actor: str) -> None:
    conn.execute(
        "INSERT INTO bid_requirement_history(id, notice_id, requirement_id, action, before_json, after_json, actor) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (uuid4().hex, notice_id, requirement_id, action, json.dumps(before, ensure_ascii=False, sort_keys=True), json.dumps(after, ensure_ascii=False, sort_keys=True), actor.strip() or "admin"),
    )


def _event(conn, notice_id: str, action: str, actor: str, payload: dict[str, object]) -> None:
    conn.execute(
        "INSERT INTO opportunity_events(id, notice_id, action, actor_open_id, payload_json) VALUES (?, ?, ?, ?, ?)",
        (uuid4().hex[:24], notice_id, action, actor.strip() or "admin", json.dumps(payload, ensure_ascii=False, sort_keys=True)),
    )


def _rows(conn, query: str, notice_id: str) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(query, (notice_id,)).fetchall()]


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]


def _json_dict(value: object) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: object) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="minutes") if value else None


def _csv(rows: list[dict[str, Any]], fields: list[str]) -> str:
    buffer = StringIO()
    buffer.write("\ufeff")
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        normalized = {key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value for key, value in row.items()}
        writer.writerow(normalized)
    return buffer.getvalue()
