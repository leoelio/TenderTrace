from __future__ import annotations

from datetime import datetime, timezone
from difflib import SequenceMatcher
import hashlib
import json
import re
from typing import Any
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps
from tendertrace.pipeline.dedup import normalize_title
from tendertrace.source_trust import source_trust_profiles


RULE_VERSION = "tendertrace_source_relation_v1"
DECISION_ACTIONS = {"merge", "split", "lock"}
FIELD_LABELS = {
    "project_no": "项目编号",
    "purchaser": "采购人",
    "title": "标题",
    "budget": "预算",
    "region": "地区",
    "publish_time": "发布时间",
}


def build_source_relation_graph(settings: Settings, notice_id: str) -> dict[str, object] | None:
    """Build a local, explainable relation graph without changing notice facts."""
    init_db(settings)
    with connection(settings) as conn:
        current = conn.execute("SELECT * FROM notices WHERE id = ?", (notice_id,)).fetchone()
        if current is None:
            return None
        rows = conn.execute(
            "SELECT * FROM notices WHERE id <> ? AND source_site <> 'demo' ORDER BY updated_at DESC",
            (notice_id,),
        ).fetchall()
        decisions = _decisions_for_notice(conn, notice_id)
        profiles = source_trust_profiles(settings)
        current_notice = _notice_payload(current, profiles)
        relations: list[dict[str, object]] = []
        blocked: list[dict[str, object]] = []
        for row in rows:
            other = _notice_payload(row, profiles)
            pair_key = _pair_key(notice_id, str(row["id"]))
            match = _match(current_notice, other)
            decision = decisions.get(pair_key)
            relation = _relation_payload(current_notice, other, match, decision)
            if decision or int(match["score"]) >= 55:
                relations.append(relation)
            elif int(match["title_similarity_percent"]) >= 86 and match["conflicts"]:
                relation["status"] = "blocked"
                relation["status_label"] = "已阻止误合并"
                blocked.append(relation)

        relations.sort(key=_relation_sort_key, reverse=True)
        blocked.sort(key=lambda item: int(item.get("score") or 0), reverse=True)
        relations = relations[:8]
        blocked = blocked[:3]
        graph = _graph_payload(conn, current_notice, relations)
        conflicts = [
            conflict
            for relation in relations
            if relation.get("status") != "rejected"
            for conflict in relation.get("conflicts", [])
        ]
        confirmed = [item for item in relations if item.get("status") == "confirmed"]
        candidates = [item for item in relations if item.get("status") == "candidate"]
        rejected = [item for item in relations if item.get("status") == "rejected"]
        timeline = _confirmed_timeline(conn, current_notice, confirmed)

    return {
        "notice_id": notice_id,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule_version": RULE_VERSION,
        "mode": "local_incremental",
        "placement": "digital_twin_source_evidence",
        "summary": {
            "related_count": len(relations),
            "confirmed_count": len(confirmed),
            "candidate_count": len(candidates),
            "rejected_count": len(rejected),
            "blocked_false_merge_count": len(blocked),
            "conflict_count": len(conflicts),
            "source_count": len({current_notice["source_site"], *[str(item["source_site"]) for item in confirmed]}),
            "timeline_item_count": len(timeline),
        },
        "current": current_notice,
        "relations": relations,
        "blocked_candidates": blocked,
        "conflicts": conflicts,
        "graph": graph,
        "confirmed_timeline": timeline,
        "rules": {
            "deterministic_and_similarity_separated": True,
            "manual_decisions_override_incremental_matching": True,
            "conflicts_never_auto_resolved": True,
            "network_fetch_performed": False,
            "incremental_scope": "current_notice_candidates_only",
        },
    }


def decide_source_relation(
    settings: Settings,
    notice_id: str,
    related_notice_id: str,
    *,
    action: str,
    actor: str,
    reason: str,
) -> dict[str, object]:
    action = action.strip().lower()
    actor = actor.strip()
    reason = reason.strip()
    if action not in DECISION_ACTIONS:
        raise ValueError("action must be merge, split, or lock")
    if not actor:
        raise ValueError("actor is required")
    if not reason:
        raise ValueError("reason is required")
    if notice_id == related_notice_id:
        raise ValueError("cannot relate a notice to itself")
    init_db(settings)
    pair_key = _pair_key(notice_id, related_notice_id)
    left_id, right_id = sorted((notice_id, related_notice_id))
    decision = "rejected" if action == "split" else "confirmed"
    locked = 1 if action in {"split", "lock"} else 0
    with connection(settings) as conn:
        found = conn.execute(
            "SELECT id FROM notices WHERE id IN (?, ?)", (notice_id, related_notice_id)
        ).fetchall()
        if len(found) != 2:
            raise LookupError("notice relation target not found")
        previous_row = conn.execute(
            "SELECT * FROM notice_relation_decisions WHERE pair_key = ?", (pair_key,)
        ).fetchone()
        previous = dict(previous_row) if previous_row is not None else {}
        conn.execute(
            """
            INSERT INTO notice_relation_decisions(
                pair_key, left_notice_id, right_notice_id, decision, locked, actor, reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(pair_key) DO UPDATE SET
                decision = excluded.decision,
                locked = excluded.locked,
                actor = excluded.actor,
                reason = excluded.reason,
                updated_at = datetime('now')
            """,
            (pair_key, left_id, right_id, decision, locked, actor, reason),
        )
        current_row = conn.execute(
            "SELECT * FROM notice_relation_decisions WHERE pair_key = ?", (pair_key,)
        ).fetchone()
        current = dict(current_row) if current_row is not None else {}
        conn.execute(
            """
            INSERT INTO notice_relation_audit_events(
                id, pair_key, action, actor, reason, before_json, after_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (str(uuid4()), pair_key, action, actor, reason, json_dumps(previous), json_dumps(current)),
        )
    graph = build_source_relation_graph(settings, notice_id)
    if graph is None:
        raise LookupError("notice not found")
    graph["decision_result"] = {
        "pair_key": pair_key,
        "action": action,
        "decision": decision,
        "locked": bool(locked),
        "actor": actor,
        "reason": reason,
    }
    return graph


def _notice_payload(row: Any, profiles: dict[str, dict[str, object]]) -> dict[str, object]:
    fields = _json_mapping(row["fields_json"])
    structured = _mapping(fields.get("structured_fields"))
    site = str(row["source_site"] or "")
    profile = profiles.get(site, {})
    source_class = str(profile.get("source_class") or "")
    if site in {"manual_upload", "manual", "upload"}:
        source_kind = "manual"
        source_label = "人工上传"
    elif source_class == "official_primary":
        source_kind = "official"
        source_label = "官方来源"
    else:
        source_kind = "repost"
        source_label = "转载/其他来源"
    purchaser = _actual_purchaser(str(row["purchaser"] or ""), str(row["content_text"] or ""))
    project_no = _text(fields.get("project_no") or structured.get("project_no"))
    budget = _text(fields.get("budget") or structured.get("budget"))
    return {
        "id": str(row["id"]),
        "source_site": site,
        "source_url": str(row["source_url"] or ""),
        "source_kind": source_kind,
        "source_kind_label": source_label,
        "authority": str(profile.get("authority") or site or "来源未分类"),
        "title": str(row["title"] or ""),
        "title_norm": normalize_title(str(row["title"] or "")),
        "notice_type": str(row["notice_type"] or fields.get("notice_type") or "other"),
        "notice_type_label": str(row["notice_type_label"] or fields.get("notice_type") or "其他"),
        "project_no": project_no,
        "purchaser": purchaser,
        "budget": budget,
        "budget_amount": _money_amount(budget or str(row["content_text"] or "")),
        "region": str(row["region"] or ""),
        "publish_time": str(row["publish_time"] or ""),
        "updated_at": str(row["updated_at"] or ""),
        "snapshot_sha256": str(row["snapshot_sha256"] or ""),
    }


def _match(left: dict[str, object], right: dict[str, object]) -> dict[str, object]:
    score = 0
    deterministic: list[dict[str, object]] = []
    similarity: list[dict[str, object]] = []
    conflicts: list[dict[str, object]] = []

    project_left, project_right = _texts(left, right, "project_no")
    if project_left and project_right:
        if _norm(project_left) == _norm(project_right):
            score += 50
            deterministic.append(_basis("project_no", project_left, project_right, "matched", 50))
        else:
            score -= 45
            conflicts.append(_conflict("project_no", left, right))
            deterministic.append(_basis("project_no", project_left, project_right, "conflict", -45))

    title_similarity = SequenceMatcher(
        None, str(left.get("title_norm") or ""), str(right.get("title_norm") or "")
    ).ratio()
    title_points = 25 if title_similarity >= 0.92 else 18 if title_similarity >= 0.75 else 10 if title_similarity >= 0.55 else 0
    score += title_points
    similarity.append(
        _basis("title", str(left.get("title") or ""), str(right.get("title") or ""), "matched" if title_points else "weak", title_points, confidence=round(title_similarity * 100))
    )

    purchaser_left, purchaser_right = _texts(left, right, "purchaser")
    if purchaser_left and purchaser_right:
        purchaser_similarity = SequenceMatcher(None, _norm(purchaser_left), _norm(purchaser_right)).ratio()
        if purchaser_similarity >= 0.86:
            score += 15
            deterministic.append(_basis("purchaser", purchaser_left, purchaser_right, "matched", 15))
        elif purchaser_similarity < 0.45:
            score -= 20
            conflicts.append(_conflict("purchaser", left, right))
            deterministic.append(_basis("purchaser", purchaser_left, purchaser_right, "conflict", -20))

    region_left, region_right = _texts(left, right, "region")
    if region_left and region_right and _region(region_left) == _region(region_right):
        score += 5
        deterministic.append(_basis("region", region_left, region_right, "matched", 5))

    amount_left = left.get("budget_amount")
    amount_right = right.get("budget_amount")
    if isinstance(amount_left, (int, float)) and isinstance(amount_right, (int, float)) and amount_left and amount_right:
        delta = abs(float(amount_left) - float(amount_right)) / max(float(amount_left), float(amount_right))
        if delta <= 0.02:
            score += 10
            deterministic.append(_basis("budget", str(left.get("budget") or amount_left), str(right.get("budget") or amount_right), "matched", 10))
        elif delta >= 0.2:
            score -= 15
            conflicts.append(_conflict("budget", left, right))
            deterministic.append(_basis("budget", str(left.get("budget") or amount_left), str(right.get("budget") or amount_right), "conflict", -15))

    days = _date_distance(str(left.get("publish_time") or ""), str(right.get("publish_time") or ""))
    if days is not None:
        points = 5 if days <= 1 else 3 if days <= 30 else 0
        score += points
        if points:
            deterministic.append(_basis("publish_time", str(left.get("publish_time") or ""), str(right.get("publish_time") or ""), "near", points))

    return {
        "score": max(0, min(99, score)),
        "title_similarity_percent": round(title_similarity * 100),
        "deterministic_basis": deterministic,
        "similarity_basis": similarity,
        "conflicts": conflicts,
    }


def _relation_payload(
    current: dict[str, object],
    other: dict[str, object],
    match: dict[str, object],
    decision: dict[str, object] | None,
) -> dict[str, object]:
    if decision:
        status = "confirmed" if decision["decision"] == "confirmed" else "rejected"
        status_label = "已锁定合并" if status == "confirmed" and decision["locked"] else "已人工确认" if status == "confirmed" else "已拆分并锁定"
        confidence_source = "human_locked" if decision["locked"] else "human_confirmed"
    else:
        status = "candidate"
        status_label = "待人工确认"
        confidence_source = "rules_and_similarity"
    return {
        "pair_key": _pair_key(str(current["id"]), str(other["id"])),
        "related_notice_id": other["id"],
        "source_site": other["source_site"],
        "source_url": other["source_url"],
        "source_kind": other["source_kind"],
        "source_kind_label": other["source_kind_label"],
        "authority": other["authority"],
        "title": other["title"],
        "notice_type": other["notice_type"],
        "notice_type_label": other["notice_type_label"],
        "project_no": other["project_no"],
        "purchaser": other["purchaser"],
        "budget": other["budget"],
        "region": other["region"],
        "publish_time": other["publish_time"],
        "score": match["score"],
        "status": status,
        "status_label": status_label,
        "confidence_source": confidence_source,
        "deterministic_basis": match["deterministic_basis"],
        "similarity_basis": match["similarity_basis"],
        "conflicts": match["conflicts"],
        "decision": decision or {},
    }


def _graph_payload(conn: Any, current: dict[str, object], relations: list[dict[str, object]]) -> dict[str, object]:
    nodes = [{
        "id": current["id"], "type": "notice", "role": "current", "label": current["title"],
        "subtitle": f"{current['notice_type_label']} · {current['authority']}", "source_kind": current["source_kind"],
        "source_url": current["source_url"],
    }]
    edges: list[dict[str, object]] = []
    included_notice_ids = [str(current["id"])]
    for relation in relations:
        if relation["status"] == "rejected":
            continue
        related_id = str(relation["related_notice_id"])
        included_notice_ids.append(related_id)
        nodes.append({
            "id": related_id, "type": "notice", "role": "related", "label": relation["title"],
            "subtitle": f"{relation['notice_type_label']} · {relation['authority']}", "source_kind": relation["source_kind"],
            "source_url": relation["source_url"], "status": relation["status"],
        })
        matched = [item["label"] for item in relation["deterministic_basis"] if item["status"] in {"matched", "near"}]
        edges.append({
            "from": current["id"], "to": related_id, "type": "relation", "status": relation["status"],
            "score": relation["score"], "label": "、".join(matched[:3]) or "标题相似度",
        })
    placeholders = ",".join("?" for _ in included_notice_ids)
    if included_notice_ids:
        revisions = conn.execute(
            f"SELECT id, notice_id, changed_fields_json, created_at FROM notice_revisions WHERE notice_id IN ({placeholders}) ORDER BY created_at",
            included_notice_ids,
        ).fetchall()
        attachments = conn.execute(
            f"SELECT id, notice_id, name, url, status, created_at FROM attachment_snapshots WHERE notice_id IN ({placeholders}) ORDER BY created_at",
            included_notice_ids,
        ).fetchall()
        for row in revisions:
            node_id = f"revision:{row['id']}"
            fields = _json_list(row["changed_fields_json"])
            nodes.append({"id": node_id, "type": "revision", "role": "evidence", "label": "公告修订", "subtitle": "、".join(fields) or "内容变化", "source_kind": "revision"})
            edges.append({"from": row["notice_id"], "to": node_id, "type": "revision", "status": "traceable", "score": 100, "label": "版本变化"})
        for row in attachments:
            node_id = f"attachment:{row['id']}"
            nodes.append({"id": node_id, "type": "attachment", "role": "evidence", "label": row["name"], "subtitle": row["status"], "source_kind": "attachment", "source_url": row["url"]})
            edges.append({"from": row["notice_id"], "to": node_id, "type": "attachment", "status": "traceable", "score": 100, "label": "附件"})
    return {"nodes": nodes[:18], "edges": edges[:24], "legend": [
        {"kind": "official", "label": "官方来源"}, {"kind": "repost", "label": "转载/其他"},
        {"kind": "manual", "label": "人工上传"}, {"kind": "revision", "label": "更正/版本"},
        {"kind": "attachment", "label": "附件"},
    ]}


def _confirmed_timeline(conn: Any, current: dict[str, object], confirmed: list[dict[str, object]]) -> list[dict[str, object]]:
    notices = [{
        "notice_id": current["id"], "type": current["notice_type"], "type_label": current["notice_type_label"],
        "title": current["title"], "source_site": current["source_site"], "source_url": current["source_url"],
        "at": current["publish_time"], "relation_status": "current",
    }]
    for item in confirmed:
        notices.append({
            "notice_id": item["related_notice_id"], "type": item["notice_type"], "type_label": item["notice_type_label"],
            "title": item["title"], "source_site": item["source_site"], "source_url": item["source_url"],
            "at": item["publish_time"], "relation_status": "confirmed",
        })
    unique = {str(item["notice_id"]): item for item in notices}
    return sorted(unique.values(), key=lambda item: str(item.get("at") or ""), reverse=True)


def _decisions_for_notice(conn: Any, notice_id: str) -> dict[str, dict[str, object]]:
    rows = conn.execute(
        "SELECT * FROM notice_relation_decisions WHERE left_notice_id = ? OR right_notice_id = ?",
        (notice_id, notice_id),
    ).fetchall()
    return {str(row["pair_key"]): {**dict(row), "locked": bool(row["locked"])} for row in rows}


def _relation_sort_key(item: dict[str, object]) -> tuple[int, int]:
    status_rank = {"confirmed": 3, "candidate": 2, "rejected": 1}.get(str(item.get("status")), 0)
    return (status_rank, int(item.get("score") or 0))


def _pair_key(left: str, right: str) -> str:
    value = "\x1f".join(sorted((left, right)))
    return "relation:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _basis(field: str, left: str, right: str, status: str, weight: int, *, confidence: int = 100) -> dict[str, object]:
    return {"field": field, "label": FIELD_LABELS[field], "left": left, "right": right, "status": status, "weight": weight, "confidence": confidence}


def _conflict(field: str, left: dict[str, object], right: dict[str, object]) -> dict[str, object]:
    left_value = left.get(field)
    right_value = right.get(field)
    if field == "budget":
        left_value = left.get("budget") or left.get("budget_amount")
        right_value = right.get("budget") or right.get("budget_amount")
    return {
        "id": hashlib.sha1(f"{left['id']}:{right['id']}:{field}".encode("utf-8")).hexdigest()[:18],
        "field": field,
        "field_label": FIELD_LABELS[field],
        "status": "pending_review",
        "left": {"notice_id": left["id"], "value": left_value, "source_url": left["source_url"], "authority": left["authority"]},
        "right": {"notice_id": right["id"], "value": right_value, "source_url": right["source_url"], "authority": right["authority"]},
        "resolution": "人工复核后决定，不自动覆盖",
    }


def _actual_purchaser(value: str, content: str) -> str:
    value = value.strip()
    if value and not re.search(r"政府采购网|公共资源|采购中心|交易中心|采购平台", value):
        return value
    match = re.search(r"采购人(?:名称)?\s*[:：]?\s*([^\n；;，,]{2,80})", content)
    if match:
        candidate = re.split(r"中标|成交|供应商|项目", match.group(1), maxsplit=1)[0].strip()
        if len(candidate) >= 2:
            return candidate
    return value


def _money_amount(value: str) -> float | None:
    match = re.search(r"(?:预算(?:金额)?|合同金额|最高限价)?\s*[:：]?\s*([0-9][0-9,]*(?:\.\d+)?)\s*(亿元|万元|元)?", value)
    if not match:
        return None
    amount = float(match.group(1).replace(",", ""))
    unit = match.group(2) or "元"
    if unit == "万元":
        amount *= 10000
    elif unit == "亿元":
        amount *= 100000000
    return amount


def _date_distance(left: str, right: str) -> int | None:
    try:
        return abs((datetime.fromisoformat(left[:10]) - datetime.fromisoformat(right[:10])).days)
    except ValueError:
        return None


def _texts(left: dict[str, object], right: dict[str, object], key: str) -> tuple[str, str]:
    return str(left.get(key) or "").strip(), str(right.get(key) or "").strip()


def _norm(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", value.lower())


def _region(value: str) -> str:
    return re.sub(r"省|市|自治区|壮族|维吾尔|回族", "", value)


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _json_mapping(value: object) -> dict[str, Any]:
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


def _text(value: object) -> str:
    return str(value or "").strip()
