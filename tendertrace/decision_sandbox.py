from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any
from uuid import uuid4

from tendertrace.bid_workplan import get_bid_workplan
from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps
from tendertrace.digital_twin import build_digital_twin
from tendertrace.opportunity_requirements import list_requirements


RULES_VERSION = "decision_sandbox_v1"
SCENARIO_MODES = {"self_bid": "自投", "joint_bid": "联合伙伴投标"}
TECHNICAL_STATES = {"unchanged", "met", "gap"}
PARTNER_STATES = {"unchanged", "complete", "missing"}
DELIVERY_STATES = {"unchanged", "covered", "uncovered"}


def get_decision_sandbox(settings: Settings, notice_id: str) -> dict[str, object]:
    baseline = build_sandbox_baseline(settings, notice_id)
    with connection(settings) as conn:
        scenarios = [_scenario_from_row(row) for row in conn.execute(
            "SELECT * FROM decision_scenarios WHERE notice_id = ? ORDER BY created_at DESC, rowid DESC",
            (notice_id,),
        ).fetchall()]
        suggestions = [_suggestion_from_row(row) for row in conn.execute(
            "SELECT * FROM decision_scenario_suggestions WHERE notice_id = ? ORDER BY created_at DESC, rowid DESC",
            (notice_id,),
        ).fetchall()]
    return {
        "notice_id": notice_id,
        "baseline": baseline,
        "scenarios": scenarios,
        "suggestions": suggestions,
        "rules": {
            "version": RULES_VERSION,
            "formal_data_is_read_only": True,
            "no_win_probability": True,
            "scenario_modes": SCENARIO_MODES,
            "responsible_confirmation_required": True,
        },
    }


def build_sandbox_baseline(settings: Settings, notice_id: str) -> dict[str, object]:
    init_db(settings)
    twin = build_digital_twin(settings, notice_id)
    if twin is None:
        raise LookupError("opportunity not found")
    workplan = get_bid_workplan(settings, notice_id)
    requirements = [item.to_dict() for item in list_requirements(settings, notice_id) if item.status != "superseded"]
    sample_count = _sample_count(settings)
    project = twin.get("project") if isinstance(twin.get("project"), dict) else {}
    scores = twin.get("scores") if isinstance(twin.get("scores"), dict) else {}
    baseline = {
        "formal_state_hash": formal_project_state_hash(settings, notice_id),
        "digital_twin_state_hash": str((twin.get("snapshot") or {}).get("state_hash") or ""),
        "rule_version": str(twin.get("rule_version") or ""),
        "project": {
            "title": project.get("title"),
            "budget": project.get("budget"),
            "region": project.get("region"),
            "bid_deadline": project.get("bid_deadline"),
        },
        "scores": {
            key: int((scores.get(key) or {}).get("score") or 0)
            for key in ("opportunity_value", "enterprise_fit", "bid_readiness")
        },
        "requirements": requirements,
        "task_load": {
            "formal_task_count": int((workplan.get("summary") or {}).get("task_count") or 0),
            "completed_task_count": int((workplan.get("summary") or {}).get("completed_task_count") or 0),
            "team_member_count": int((twin.get("counts") or {}).get("team_members") or 0),
        },
        "sample": {
            "count": sample_count,
            "sufficient_for_probability": False,
            "message": f"当前仅有 {sample_count} 个结果/履约样本，只展示条件变化和风险方向，不计算中标概率。",
        },
        "captured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    return baseline


def simulate_scenario(
    settings: Settings,
    notice_id: str,
    *,
    name: str,
    params: dict[str, object],
    actor: str,
) -> dict[str, object]:
    if not name.strip() or not actor.strip():
        raise ValueError("scenario name and actor are required")
    normalized = _normalize_params(params)
    baseline = build_sandbox_baseline(settings, notice_id)
    output = _calculate_scenario(baseline, normalized)
    scenario_id = str(uuid4())
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO decision_scenarios(
                id, notice_id, name, scenario_mode, params_json, baseline_hash,
                baseline_json, rules_version, output_json, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scenario_id, notice_id, name.strip(), normalized["scenario_mode"],
                json_dumps(normalized), str(baseline["formal_state_hash"]), json_dumps(baseline),
                RULES_VERSION, json_dumps(output), actor.strip(),
            ),
        )
        _event(conn, notice_id, scenario_id, "scenario_saved", actor, {"name": name.strip(), "params": normalized})
    return get_scenario(settings, notice_id, scenario_id)


def get_scenario(settings: Settings, notice_id: str, scenario_id: str) -> dict[str, object]:
    with connection(settings) as conn:
        row = conn.execute(
            "SELECT * FROM decision_scenarios WHERE id = ? AND notice_id = ?",
            (scenario_id, notice_id),
        ).fetchone()
    if row is None:
        raise LookupError("decision scenario not found")
    return _scenario_from_row(row)


def recompute_scenario(settings: Settings, notice_id: str, scenario_id: str) -> dict[str, object]:
    scenario = get_scenario(settings, notice_id, scenario_id)
    recomputed = _calculate_scenario(dict(scenario["baseline"]), dict(scenario["params"]))
    previous_hash = _stable_hash(scenario["output"])
    recomputed_hash = _stable_hash(recomputed)
    current_formal_hash = formal_project_state_hash(settings, notice_id)
    with connection(settings) as conn:
        _event(conn, notice_id, scenario_id, "scenario_recomputed", "system:recompute", {
            "identical": previous_hash == recomputed_hash,
            "baseline_is_current": current_formal_hash == scenario["baseline_hash"],
        })
    return {
        "scenario_id": scenario_id,
        "identical": previous_hash == recomputed_hash,
        "baseline_is_current": current_formal_hash == scenario["baseline_hash"],
        "stored_output_hash": previous_hash,
        "recomputed_output_hash": recomputed_hash,
        "output": recomputed,
    }


def compare_scenarios(settings: Settings, notice_id: str, left_id: str, right_id: str) -> dict[str, object]:
    left = get_scenario(settings, notice_id, left_id)
    right = get_scenario(settings, notice_id, right_id)
    left_scores = (left["output"] or {}).get("scores") or {}
    right_scores = (right["output"] or {}).get("scores") or {}
    metrics = []
    for key, label in (("opportunity_value", "机会价值"), ("enterprise_fit", "企业匹配"), ("bid_readiness", "投标准备")):
        left_value = int(left_scores.get(key) or 0)
        right_value = int(right_scores.get(key) or 0)
        metrics.append({"key": key, "label": label, "left": left_value, "right": right_value, "difference": right_value - left_value})
    return {
        "left": {"id": left["id"], "name": left["name"], "mode": left["scenario_mode"], "output": left["output"]},
        "right": {"id": right["id"], "name": right["name"], "mode": right["scenario_mode"], "output": right["output"]},
        "metrics": metrics,
        "interpretation": _comparison_interpretation(metrics, left, right),
        "no_win_probability": True,
    }


def promote_scenario(settings: Settings, notice_id: str, scenario_id: str, *, actor: str) -> dict[str, object]:
    if not actor.strip():
        raise ValueError("actor is required")
    scenario = get_scenario(settings, notice_id, scenario_id)
    actions = list((scenario["output"] or {}).get("suggested_actions") or [])
    suggestion_id = hashlib.sha256(f"{scenario_id}|suggestion".encode()).hexdigest()[:24]
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO decision_scenario_suggestions(id, scenario_id, notice_id, actions_json, requested_by)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(scenario_id) DO UPDATE SET
                actions_json = excluded.actions_json, requested_by = excluded.requested_by,
                status = CASE WHEN decision_scenario_suggestions.status = 'pending' THEN 'pending' ELSE decision_scenario_suggestions.status END,
                updated_at = datetime('now')
            """,
            (suggestion_id, scenario_id, notice_id, json_dumps(actions), actor.strip()),
        )
        conn.execute("UPDATE decision_scenarios SET status = 'pending_suggestion', updated_at = datetime('now') WHERE id = ?", (scenario_id,))
        _event(conn, notice_id, scenario_id, "scenario_promoted", actor, {"suggestion_id": suggestion_id, "action_count": len(actions)})
        row = conn.execute("SELECT * FROM decision_scenario_suggestions WHERE id = ?", (suggestion_id,)).fetchone()
    assert row is not None
    return _suggestion_from_row(row)


def decide_scenario_suggestion(
    settings: Settings,
    notice_id: str,
    suggestion_id: str,
    *,
    accept: bool,
    actor: str,
    note: str,
) -> dict[str, object]:
    if not actor.strip() or not note.strip():
        raise ValueError("decision actor and note are required")
    with connection(settings) as conn:
        row = conn.execute(
            "SELECT * FROM decision_scenario_suggestions WHERE id = ? AND notice_id = ?",
            (suggestion_id, notice_id),
        ).fetchone()
        if row is None:
            raise LookupError("scenario suggestion not found")
        if str(row["status"]) != "pending":
            raise ValueError("scenario suggestion is already decided")
        status = "accepted" if accept else "rejected"
        actions = _json_list(row["actions_json"])
        created_task_ids: list[str] = []
        if accept:
            for index, action in enumerate(actions, start=1):
                if not isinstance(action, dict):
                    continue
                task_key = f"SANDBOX-{suggestion_id[:8].upper()}-{index:02d}"
                task_id = hashlib.sha256(f"{notice_id}|task|{task_key}".encode()).hexdigest()[:24]
                conn.execute(
                    """
                    INSERT INTO bid_plan_tasks(
                        id, notice_id, requirement_id, task_key, title, milestone_type,
                        dependency_keys_json, formal
                    ) VALUES (?, ?, ?, ?, ?, 'sandbox_suggestion', '[]', 1)
                    ON CONFLICT(notice_id, task_key) DO NOTHING
                    """,
                    (task_id, notice_id, str(action.get("requirement_id") or "") or None, task_key, str(action.get("title") or "落实沙盘建议")),
                )
                created_task_ids.append(task_id)
        conn.execute(
            """
            UPDATE decision_scenario_suggestions
            SET status = ?, decided_by = ?, decision_note = ?, decided_at = datetime('now'), updated_at = datetime('now')
            WHERE id = ?
            """,
            (status, actor.strip(), note.strip(), suggestion_id),
        )
        conn.execute("UPDATE decision_scenarios SET status = ?, updated_at = datetime('now') WHERE id = ?", (status, row["scenario_id"]))
        conn.execute(
            "INSERT INTO opportunity_events(id, notice_id, action, actor_open_id, payload_json) VALUES (?, ?, 'decision_sandbox_suggestion_decided', ?, ?)",
            (str(uuid4()), notice_id, actor.strip(), json_dumps({"suggestion_id": suggestion_id, "status": status, "note": note.strip(), "task_ids": created_task_ids})),
        )
        _event(conn, notice_id, str(row["scenario_id"]), "suggestion_decided", actor, {"suggestion_id": suggestion_id, "status": status, "task_ids": created_task_ids})
        updated = conn.execute("SELECT * FROM decision_scenario_suggestions WHERE id = ?", (suggestion_id,)).fetchone()
    assert updated is not None
    result = _suggestion_from_row(updated)
    result["created_task_ids"] = created_task_ids
    return result


def formal_project_state_hash(settings: Settings, notice_id: str) -> str:
    tables = {
        "notice": ("SELECT * FROM notices WHERE id = ?", (notice_id,)),
        "requirements": ("SELECT * FROM opportunity_requirements WHERE notice_id = ? ORDER BY id", (notice_id,)),
        "matches": ("SELECT * FROM requirement_capability_matches WHERE notice_id = ? ORDER BY id", (notice_id,)),
        "review_cases": ("SELECT * FROM requirement_review_cases WHERE notice_id = ? ORDER BY id", (notice_id,)),
        "tasks": ("SELECT * FROM bid_plan_tasks WHERE notice_id = ? ORDER BY id", (notice_id,)),
        "outcome": ("SELECT * FROM opportunity_outcomes WHERE notice_id = ?", (notice_id,)),
    }
    snapshot: dict[str, object] = {}
    with connection(settings) as conn:
        for key, (sql, params) in tables.items():
            snapshot[key] = [dict(row) for row in conn.execute(sql, params).fetchall()]
    return _stable_hash(snapshot)


def _calculate_scenario(baseline: dict[str, object], params: dict[str, object]) -> dict[str, object]:
    base_scores = dict(baseline.get("scores") or {})
    scores = {key: int(base_scores.get(key) or 0) for key in ("opportunity_value", "enterprise_fit", "bid_readiness")}
    changes: list[dict[str, object]] = []
    risks: list[dict[str, object]] = []
    actions: list[dict[str, object]] = []
    requirements = list(baseline.get("requirements") or [])
    affected: dict[str, dict[str, object]] = {}

    def adjust(metric: str, delta: int, reason: str, rule: str) -> None:
        before = scores[metric]
        after = _clamp(before + delta)
        scores[metric] = after
        changes.append({
            "metric": metric,
            "before": before,
            "after": after,
            "delta": after - before,
            "input": reason,
            "reason": reason,
            "rule": rule,
        })

    deadline_shift = int(params["deadline_shift_days"])
    if deadline_shift:
        delta = -min(30, abs(deadline_shift) * 4) if deadline_shift < 0 else min(12, deadline_shift * 2)
        adjust("bid_readiness", delta, f"投标截止{'提前' if deadline_shift < 0 else '延后'} {abs(deadline_shift)} 天", "每提前1天准备度-4，延后1天+2，上下限保护")
        _affect(requirements, affected, {"deadline", "attachment", "technical", "commercial"}, "截止窗口变化")
        if deadline_shift < 0:
            risks.append(_risk("high" if deadline_shift <= -3 else "medium", "交付窗口压缩", "内部终审、签章与上传节点需要同步前移。", "deadline_shift_days"))
            actions.append(_action("重排内部终审与递交节点", "project_control", _first_requirement_id(requirements, {"deadline"})))

    budget_change = float(params["budget_change_percent"])
    if budget_change:
        delta = round(max(-20, min(15, budget_change * 0.3)))
        adjust("opportunity_value", delta, f"预算相对基准变化 {budget_change:+g}%", "预算每变化1%影响机会价值0.3分，限制在-20至+15")
        _affect(requirements, affected, {"commercial", "scoring"}, "预算条件变化")
        if budget_change < 0:
            risks.append(_risk("medium", "预算压缩", "需要重新核对成本、毛利和报价边界。", "budget_change_percent"))
            actions.append(_action("复核成本与报价边界", "commercial", _first_requirement_id(requirements, {"commercial", "scoring"})))

    technical = str(params["critical_technical_status"])
    if technical == "met":
        adjust("enterprise_fit", 15, "关键技术参数材料补齐并确认满足", "关键技术满足：企业匹配+15")
        adjust("bid_readiness", 5, "技术响应可进入正式编制", "关键技术满足：投标准备+5")
        _affect(requirements, affected, {"technical"}, "关键技术参数已满足")
    elif technical == "gap":
        adjust("enterprise_fit", -25, "关键技术参数存在明确缺口", "关键技术缺口：企业匹配-25")
        adjust("bid_readiness", -15, "技术缺口阻塞响应编制", "关键技术缺口：投标准备-15")
        _affect(requirements, affected, {"technical"}, "关键技术参数存在缺口")
        risks.append(_risk("high", "关键技术不满足", "在补齐产品、方案或伙伴能力前不应形成满足结论。", "critical_technical_status"))
        actions.append(_action("补齐关键技术能力或形成偏离决策", "technical", _first_requirement_id(requirements, {"technical"})))

    people_delta = int(params["available_people_delta"])
    if people_delta:
        adjust("bid_readiness", max(-24, min(16, people_delta * (4 if people_delta > 0 else 6))), f"可用人员变化 {people_delta:+d} 人", "增加1人准备度+4，减少1人-6，上下限保护")
        if people_delta < 0:
            risks.append(_risk("high" if people_delta <= -2 else "medium", "关键人员不足", "现有任务负荷可能超过团队可用容量。", "available_people_delta"))
            actions.append(_action("重新分配任务或补充项目成员", "project_control", ""))

    partner = str(params["partner_material_status"])
    if partner == "complete":
        adjust("enterprise_fit", 12, "伙伴授权材料补齐", "伙伴材料完整：企业匹配+12")
        adjust("bid_readiness", 6, "伙伴缺口解除", "伙伴材料完整：投标准备+6")
        _affect(requirements, affected, {"qualification", "commercial", "technical"}, "伙伴授权材料补齐")
        actions.append(_action("归档伙伴授权并锁定联合响应分工", "commercial", _first_requirement_id(requirements, {"qualification", "commercial"})))
    elif partner == "missing":
        adjust("enterprise_fit", -15, "伙伴授权材料缺失", "伙伴材料缺失：企业匹配-15")
        adjust("bid_readiness", -8, "伙伴缺口尚未解除", "伙伴材料缺失：投标准备-8")
        _affect(requirements, affected, {"qualification", "commercial", "technical"}, "伙伴授权材料缺失")
        risks.append(_risk("high", "伙伴授权不足", "专项授权的主体、区域或产品范围尚未覆盖。", "partner_material_status"))
        actions.append(_action("取得项目专项授权并核验范围", "commercial", _first_requirement_id(requirements, {"qualification", "commercial"})))

    delivery = str(params["delivery_region_status"])
    if delivery == "covered":
        adjust("enterprise_fit", 8, "交付区域已纳入服务范围", "交付区域覆盖：企业匹配+8")
        adjust("bid_readiness", 4, "区域交付风险下降", "交付区域覆盖：投标准备+4")
        _affect(requirements, affected, {"technical", "deadline", "commercial"}, "交付区域已覆盖")
    elif delivery == "uncovered":
        adjust("enterprise_fit", -20, "交付区域超出当前服务范围", "交付区域不覆盖：企业匹配-20")
        adjust("bid_readiness", -12, "区域交付能力形成阻塞", "交付区域不覆盖：投标准备-12")
        _affect(requirements, affected, {"technical", "deadline", "commercial"}, "交付区域未覆盖")
        risks.append(_risk("high", "交付区域不覆盖", "需要新增本地交付资源或联合伙伴。", "delivery_region_status"))
        actions.append(_action("确认本地交付资源或伙伴方案", "delivery", _first_requirement_id(requirements, {"technical", "commercial"})))

    if params["scenario_mode"] == "joint_bid" and partner == "complete":
        adjust("enterprise_fit", 3, "联合伙伴模式且授权材料完整", "联合投标协同加成：企业匹配+3")

    task_load = dict(baseline.get("task_load") or {})
    base_tasks = int(task_load.get("formal_task_count") or 0)
    base_people = int(task_load.get("team_member_count") or 0)
    scenario_people = max(0, base_people + people_delta)
    unique_actions = _dedupe_actions(actions)
    scenario_tasks = base_tasks + len(unique_actions)
    output = {
        "scores": scores,
        "score_changes": changes,
        "affected_requirements": list(affected.values()),
        "task_load": {
            "baseline_task_count": base_tasks,
            "scenario_task_count": scenario_tasks,
            "additional_action_count": len(unique_actions),
            "baseline_people": base_people,
            "scenario_people": scenario_people,
            "tasks_per_person": round(scenario_tasks / max(1, scenario_people), 1),
        },
        "risks": risks,
        "suggested_actions": unique_actions,
        "improvements": [item for item in changes if int(item["delta"]) > 0],
        "deteriorations": [item for item in changes if int(item["delta"]) < 0],
        "uncertainty": baseline.get("sample") or {},
        "formal_write_performed": False,
        "rules_version": RULES_VERSION,
        "calculation_basis": "确定性条件规则；不输出中标概率",
    }
    return output


def _normalize_params(params: dict[str, object]) -> dict[str, object]:
    mode = str(params.get("scenario_mode") or "self_bid")
    technical = str(params.get("critical_technical_status") or "unchanged")
    partner = str(params.get("partner_material_status") or "unchanged")
    delivery = str(params.get("delivery_region_status") or "unchanged")
    if mode not in SCENARIO_MODES:
        raise ValueError("unsupported scenario_mode")
    if technical not in TECHNICAL_STATES or partner not in PARTNER_STATES or delivery not in DELIVERY_STATES:
        raise ValueError("unsupported scenario condition")
    deadline = _bounded_int(params.get("deadline_shift_days"), -30, 30, "deadline_shift_days")
    budget = _bounded_float(params.get("budget_change_percent"), -50, 100, "budget_change_percent")
    people = _bounded_int(params.get("available_people_delta"), -20, 20, "available_people_delta")
    return {
        "scenario_mode": mode,
        "deadline_shift_days": deadline,
        "budget_change_percent": budget,
        "critical_technical_status": technical,
        "available_people_delta": people,
        "partner_material_status": partner,
        "delivery_region_status": delivery,
    }


def _scenario_from_row(row: Any) -> dict[str, object]:
    return {
        "id": str(row["id"]), "notice_id": str(row["notice_id"]), "name": str(row["name"]),
        "scenario_mode": str(row["scenario_mode"]), "scenario_mode_label": SCENARIO_MODES.get(str(row["scenario_mode"]), str(row["scenario_mode"])),
        "params": _json_dict(row["params_json"]), "baseline_hash": str(row["baseline_hash"]),
        "baseline": _json_dict(row["baseline_json"]), "rules_version": str(row["rules_version"]),
        "output": _json_dict(row["output_json"]), "status": str(row["status"]),
        "created_by": str(row["created_by"]), "created_at": str(row["created_at"]), "updated_at": str(row["updated_at"]),
    }


def _suggestion_from_row(row: Any) -> dict[str, object]:
    return {
        "id": str(row["id"]), "scenario_id": str(row["scenario_id"]), "notice_id": str(row["notice_id"]),
        "status": str(row["status"]), "actions": _json_list(row["actions_json"]),
        "requested_by": str(row["requested_by"]), "decided_by": str(row["decided_by"] or ""),
        "decision_note": str(row["decision_note"] or ""), "decided_at": str(row["decided_at"] or ""),
        "created_at": str(row["created_at"]), "updated_at": str(row["updated_at"]),
    }


def _affect(requirements: list[object], affected: dict[str, dict[str, object]], types: set[str], reason: str) -> None:
    for raw in requirements:
        if not isinstance(raw, dict) or str(raw.get("requirement_type") or "") not in types:
            continue
        rid = str(raw.get("id") or "")
        item = affected.setdefault(rid, {"id": rid, "requirement_key": raw.get("requirement_key"), "title": raw.get("title"), "reasons": []})
        if reason not in item["reasons"]:
            item["reasons"].append(reason)


def _first_requirement_id(requirements: list[object], types: set[str]) -> str:
    return next((str(item.get("id") or "") for item in requirements if isinstance(item, dict) and item.get("requirement_type") in types), "")


def _risk(severity: str, title: str, detail: str, source_param: str) -> dict[str, object]:
    return {"severity": severity, "title": title, "detail": detail, "source_param": source_param}


def _action(title: str, owner_role: str, requirement_id: str) -> dict[str, object]:
    return {"title": title, "owner_role": owner_role, "requirement_id": requirement_id}


def _dedupe_actions(actions: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[str] = set()
    result = []
    for action in actions:
        key = str(action["title"])
        if key not in seen:
            seen.add(key)
            result.append(action)
    return result


def _comparison_interpretation(metrics: list[dict[str, object]], left: dict[str, object], right: dict[str, object]) -> list[str]:
    notes = [
        f"{item['label']}：{right['name']} 相对 {left['name']} {int(item['difference']):+d} 分。"
        for item in metrics if int(item["difference"])
    ]
    left_risks = len((left["output"] or {}).get("risks") or [])
    right_risks = len((right["output"] or {}).get("risks") or [])
    notes.append(f"风险项：{left['name']} {left_risks} 项，{right['name']} {right_risks} 项。")
    notes.append("比较结果只说明条件变化，不代表中标概率或最终决策。")
    return notes


def _sample_count(settings: Settings) -> int:
    with connection(settings) as conn:
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT notice_id) AS count FROM (
                SELECT notice_id FROM opportunity_outcomes
                UNION ALL
                SELECT notice_id FROM capability_performance_records
            )
            """
        ).fetchone()
    return int(row["count"] or 0) if row else 0


def _bounded_int(value: object, lower: int, upper: int, name: str) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not lower <= parsed <= upper:
        raise ValueError(f"{name} must be between {lower} and {upper}")
    return parsed


def _bounded_float(value: object, lower: float, upper: float, name: str) -> float:
    try:
        parsed = float(value or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not lower <= parsed <= upper:
        raise ValueError(f"{name} must be between {lower} and {upper}")
    return round(parsed, 2)


def _clamp(value: int) -> int:
    return max(0, min(100, int(round(value))))


def _stable_hash(value: object) -> str:
    return hashlib.sha256(json_dumps(value).encode()).hexdigest()


def _json_dict(value: object) -> dict[str, object]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: object) -> list[object]:
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _event(conn: Any, notice_id: str, scenario_id: str, action: str, actor: str, payload: dict[str, object]) -> None:
    conn.execute(
        "INSERT INTO decision_sandbox_events(id, notice_id, scenario_id, action, actor, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid4()), notice_id, scenario_id, action, actor.strip(), json_dumps(payload)),
    )
