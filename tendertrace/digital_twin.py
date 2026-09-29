from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import re
from typing import Any
from uuid import uuid4

from tendertrace.capability_matching import (
    capability_match_summary,
    list_requirement_capability_matches,
)
from tendertrace.capability_passport import build_capability_passport
from tendertrace.bid_workplan import get_bid_workplan
from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps
from tendertrace.notice_changes import list_notice_revisions
from tendertrace.opportunity import get_opportunity
from tendertrace.opportunity_requirements import list_requirements, requirement_summary
from tendertrace.requirement_review_actions import review_action_summary
from tendertrace.requirement_review_board import requirement_review_summary
from tendertrace.requirement_review_agents import review_agent_runtime_summary
from tendertrace.retrieval import parse_date
from tendertrace.source_relation_graph import build_source_relation_graph


RULE_VERSION = "tendertrace_digital_twin_v1"

EVENT_LABELS = {
    "claim": "负责人认领机会",
    "pursue": "进入机会确认",
    "approve_bid": "批准投标",
    "prepare_bid": "进入投标准备",
    "hold": "机会暂缓",
    "reject": "机会 No-Go",
    "acknowledge_notice_change": "公告变更已复核",
    "requirement_upserted": "要求账本已更新",
    "requirement_review_resolved": "要求会审已裁决",
    "requirement_review_action_created": "会审行动已创建",
    "capability_match_decided": "能力匹配已确认",
    "team_member_added": "协作成员已加入",
    "stakeholder_upserted": "客户关键人已更新",
    "relationship_action_upserted": "关系行动已更新",
    "feishu_task_sync": "飞书任务状态已同步",
    "war_room_launched": "飞书项目战情室已启动",
    "war_room_step_retried": "战情室失败步骤已单独重试",
    "war_room_task_status_synced": "飞书团队状态已回写",
    "war_room_changes_dispatched": "受影响行动已增量推送",
    "war_room_archived": "投标战情室已归档",
    "bid_requirement_confirmed": "拆标要求已人工确认",
    "bid_requirement_split": "复杂要求已拆分",
    "bid_requirements_merged": "重复要求已合并",
    "bid_workplan_built": "履约作战计划已生成",
    "bid_plan_task_completed": "作战任务已完成",
    "decision_sandbox_suggestion_decided": "沙盘建议已人工裁决",
    "bid_memory_archived": "项目经验已进入企业投标记忆体",
}


def build_digital_twin(settings: Settings, notice_id: str) -> dict[str, object] | None:
    """Build and persist a traceable, current-state project dossier."""
    init_db(settings)
    opportunity = get_opportunity(settings, notice_id)
    if opportunity is None:
        return None
    source_relations = build_source_relation_graph(settings, notice_id) or {}
    source_relation_summary = _mapping(source_relations.get("summary"))

    requirements = list_requirements(settings, notice_id)
    requirement_state = requirement_summary(settings, notice_id)
    matches = list_requirement_capability_matches(settings, notice_id)
    match_state = capability_match_summary(settings, notice_id)
    review_state = requirement_review_summary(settings, notice_id)
    review_agents = review_agent_runtime_summary(settings, notice_id)
    review_actions = review_action_summary(settings, notice_id)
    revisions = list_notice_revisions(settings, notice_id=notice_id, limit=30)
    raw = _raw_counts(settings, notice_id)
    workplan = get_bid_workplan(settings, notice_id)
    passport = build_capability_passport(settings, notice_id)

    opportunity_value = _opportunity_value_score(opportunity)
    enterprise_fit = _enterprise_fit_score(requirements, matches, requirement_state, match_state)
    bid_readiness = _bid_readiness_score(
        opportunity,
        requirement_state=requirement_state,
        enterprise_fit=enterprise_fit,
        review_state=review_state,
        review_actions=review_actions,
        workplan_summary=_mapping(workplan.get("summary")),
    )
    scores = {
        "opportunity_value": opportunity_value,
        "enterprise_fit": enterprise_fit,
        "bid_readiness": bid_readiness,
    }
    counts = {
        "revisions": len(revisions),
        "attachments": raw["attachments"],
        "evidence_items": raw["evidence_items"],
        "requirements": int(requirement_state.get("total_count") or 0),
        "capability_matches": int(match_state.get("total_count") or 0),
        "review_items": int(review_state.get("total_count") or 0),
        "pending_reviews": int(review_state.get("pending_count") or 0),
        "open_review_actions": int(review_actions.get("open_count") or 0),
        "review_agent_runs": int(review_agents.get("run_count") or 0),
        "review_agent_disagreements": int(review_agents.get("disagreement_count") or 0),
        "review_agent_failures": int(review_agents.get("failed_role_count") or 0),
        "team_members": int(_mapping(opportunity.get("team")).get("member_count") or 0),
        "stakeholders": int(_mapping(opportunity.get("stakeholder_map")).get("stakeholder_count") or 0),
        "relationship_actions": int(_mapping(opportunity.get("relationship_actions")).get("total_count") or 0),
        "collaboration_notes": raw["collaboration_notes"],
        "bid_plan_tasks": int(_mapping(workplan.get("summary")).get("task_count") or 0),
        "bid_plan_tasks_completed": int(_mapping(workplan.get("summary")).get("completed_task_count") or 0),
        "capability_passports": int(_mapping(passport.get("summary")).get("passport_count") or 0),
        "capability_alerts": int(_mapping(passport.get("summary")).get("alert_count") or 0),
        "open_capability_gap_actions": int(_mapping(passport.get("summary")).get("open_gap_action_count") or 0),
        "decision_scenarios": int(raw.get("decision_scenarios") or 0),
        "pending_sandbox_suggestions": int(raw.get("pending_sandbox_suggestions") or 0),
        "war_room_resources": int(raw.get("war_room_resources") or 0),
        "war_room_failed_steps": int(raw.get("war_room_failed_steps") or 0),
        "bid_memory_projects": int(raw.get("bid_memory_projects") or 0),
        "bid_memory_assets": int(raw.get("bid_memory_assets") or 0),
        "confirmed_source_relations": int(source_relation_summary.get("confirmed_count") or 0),
        "source_relation_conflicts": int(source_relation_summary.get("conflict_count") or 0),
    }
    source_sync = _source_sync(opportunity, raw)
    summary = {
        "rule_version": RULE_VERSION,
        "title": opportunity.get("title"),
        "workflow_stage": _mapping(opportunity.get("workflow")).get("stage"),
        "decision": _mapping(opportunity.get("workflow")).get("decision"),
        "project_facts": {
            key: opportunity.get(key)
            for key in ("purchaser", "project_no", "budget", "region", "bid_deadline", "source_url")
        },
        "scores": {key: value["score"] for key, value in scores.items()},
        "score_statuses": {key: value["status"] for key, value in scores.items()},
        "score_rules": {
            key: [
                {
                    "key": component["key"],
                    "score": component["score"],
                    "weight": component["weight"],
                }
                for component in value["components"]
            ]
            for key, value in scores.items()
        },
        "counts": counts,
        "change_review_pending": int(_mapping(opportunity.get("change_review")).get("pending_count") or 0),
        "state_markers": raw["state_markers"],
        "source_relation_state": {
            "confirmed": counts["confirmed_source_relations"],
            "conflicts": counts["source_relation_conflicts"],
            "timeline_items": int(source_relation_summary.get("timeline_item_count") or 0),
        },
    }
    state_hash = hashlib.sha256(json_dumps(summary).encode("utf-8")).hexdigest()
    snapshot_state = _persist_snapshot(settings, notice_id, state_hash, summary)
    timeline = _timeline(settings, notice_id, opportunity, revisions)
    for item in source_relations.get("confirmed_timeline", []):
        if not isinstance(item, dict) or str(item.get("notice_id") or "") == notice_id:
            continue
        timeline.append({
            "type": "source_relation",
            "title": f"已确认关联：{item.get('type_label') or '关联公告'}",
            "detail": f"{item.get('source_site') or '未知来源'} · {item.get('title') or ''}",
            "at": item.get("at") or "",
            "severity": "normal",
            "source_url": item.get("source_url") or "",
        })
    timeline = sorted(timeline, key=lambda item: str(item.get("at") or ""), reverse=True)[:30]
    actions = _next_actions(opportunity, scores, requirement_state, review_state, review_actions)
    change_review = _mapping(opportunity.get("change_review"))

    return {
        "notice_id": notice_id,
        "title": opportunity.get("title"),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule_version": RULE_VERSION,
        "refresh": {
            "mode": "on_read_plus_30s_polling",
            "label": "打开即同步，档案页每 30 秒自动刷新",
            "data_as_of": source_sync["last_seen_at"] or raw["notice_updated_at"],
        },
        "source_sync": source_sync,
        "project": {
            key: opportunity.get(key)
            for key in (
                "notice_id",
                "title",
                "purchaser",
                "project_no",
                "budget",
                "region",
                "publish_time",
                "bid_deadline",
                "source_site",
                "source_url",
            )
        },
        "workflow": opportunity.get("workflow") or {},
        "change_review": change_review,
        "scores": scores,
        "counts": counts,
        "timeline": timeline,
        "source_relations": {
            "summary": source_relation_summary,
            "placement": source_relations.get("placement"),
            "rule_version": source_relations.get("rule_version"),
        },
        "next_actions": actions,
        "bid_workplan": {
            "summary": workplan.get("summary") or {},
            "gap_lanes": workplan.get("gap_lanes") or {},
            "redlines": workplan.get("redlines") or [],
        },
        "capability_passport": {
            "summary": passport.get("summary") or {},
            "alerts": passport.get("alerts") or [],
            "gap_actions": passport.get("gap_actions") or [],
        },
        "review_opponent": {
            "summary": review_agents,
            "human_decision_required": True,
            "aggregation_rule": "仅合并一致且有证据的事实；分歧由人员裁决",
        },
        "snapshot": snapshot_state,
        "dossier_sections": [
            {"key": "source", "label": "公告、关联与附件", "count": 1 + counts["attachments"] + counts["revisions"] + counts["confirmed_source_relations"]},
            {"key": "requirements", "label": "要求与证据", "count": counts["requirements"] + counts["evidence_items"]},
            {"key": "capabilities", "label": "企业能力匹配", "count": counts["capability_matches"]},
            {"key": "review", "label": "会审与行动", "count": counts["review_items"] + counts["open_review_actions"]},
            {"key": "collaboration", "label": "团队与飞书协同", "count": counts["team_members"] + counts["collaboration_notes"] + counts["war_room_resources"]},
            {"key": "memory", "label": "企业投标记忆体", "count": counts["bid_memory_projects"] + counts["bid_memory_assets"]},
        ],
    }


def _opportunity_value_score(opportunity: dict[str, object]) -> dict[str, object]:
    intelligence = _mapping(opportunity.get("intelligence"))
    raw_scores = _mapping(intelligence.get("scores"))
    action_state = _mapping(opportunity.get("action_state"))
    components = [
        _component("quality", "机会质量", _score(intelligence.get("score")), 30, "综合公告完整度、时效和项目要素", "intelligence.score"),
        _component("credibility", "来源可信", _score(raw_scores.get("credibility")), 25, _trust_basis(intelligence), "intelligence.scores.credibility"),
        _component("window", "投标窗口", _score(raw_scores.get("freshness")), 25, _deadline_basis(opportunity, action_state), "intelligence.scores.freshness"),
        _component("completeness", "信息完整", _score(raw_scores.get("completeness")), 20, _missing_basis(intelligence), "intelligence.scores.completeness"),
    ]
    return _score_result(
        "opportunity_value",
        "机会价值",
        components,
        "衡量项目是否值得优先投入，依据机会质量、来源可信、投标窗口和信息完整度。",
    )


def _enterprise_fit_score(
    requirements: list[Any],
    matches: list[Any],
    requirement_state: dict[str, object],
    match_state: dict[str, object],
) -> dict[str, object]:
    total_requirements = len(requirements)
    confirmed_supported = sum(
        item.verdict == "supported" and item.status == "confirmed" for item in matches
    )
    confirmed_matches = int(match_state.get("confirmed_count") or 0)
    total_matches = len(matches)
    gaps = sum(item.verdict == "gap" for item in matches)
    requirements_with_evidence = sum(
        bool(item.evidence_text and item.source_url and item.source_locator) for item in requirements
    )
    gap_control_score = (
        _ratio(max(total_requirements - gaps, 0), total_requirements)
        if total_matches
        else 0
    )
    components = [
        _component(
            "supported_requirements",
            "已证实能力覆盖",
            _ratio(confirmed_supported, total_requirements),
            50,
            f"{confirmed_supported}/{total_requirements} 条要求已有经人工确认的能力支持",
            "capability_matches.supported_confirmed",
        ),
        _component(
            "match_confirmation",
            "匹配确认质量",
            _ratio(confirmed_matches, total_matches),
            20,
            f"{confirmed_matches}/{total_matches} 条匹配建议已确认",
            "capability_matches.confirmed_count",
        ),
        _component(
            "gap_control",
            "能力缺口控制",
            gap_control_score,
            20,
            (
                f"发现 {gaps} 条明确能力缺口"
                if total_matches
                else "尚无已确认匹配，不能判定没有能力缺口"
            ),
            "capability_matches.gap_count",
        ),
        _component(
            "requirement_evidence",
            "要求证据清晰度",
            _ratio(requirements_with_evidence, total_requirements),
            10,
            f"{requirements_with_evidence}/{total_requirements} 条要求具备原文、链接和定位",
            "requirements.evidence",
        ),
    ]
    missing = []
    if not total_requirements:
        missing.append("尚未形成要求账本")
    if total_requirements and not total_matches:
        missing.append("尚未生成并确认企业能力匹配")
    result = _score_result(
        "enterprise_fit",
        "企业匹配度",
        components,
        "衡量企业是否有可核验的能力满足本项目要求，只承认有来源且经人工确认的能力证据。",
        force_status="insufficient" if missing else "",
    )
    result["missing"] = missing
    result["requirement_coverage_score"] = int(requirement_state.get("coverage_score") or 0)
    return result


def _bid_readiness_score(
    opportunity: dict[str, object],
    *,
    requirement_state: dict[str, object],
    enterprise_fit: dict[str, object],
    review_state: dict[str, object],
    review_actions: dict[str, int],
    workplan_summary: dict[str, object],
) -> dict[str, object]:
    qualification = _mapping(opportunity.get("qualification"))
    gates = qualification.get("gates") if isinstance(qualification.get("gates"), list) else []
    compliance_gates = [
        gate for gate in gates
        if isinstance(gate, dict) and gate.get("key") in {"purchaser", "credibility", "completeness", "deadline"}
    ]
    compliance_passed = sum(gate.get("status") == "passed" for gate in compliance_gates)
    team = _mapping(opportunity.get("team"))
    stakeholder = _mapping(opportunity.get("stakeholder_map"))
    relations = _mapping(opportunity.get("relationship_actions"))
    intelligence = _mapping(opportunity.get("intelligence"))
    raw_scores = _mapping(intelligence.get("scores"))
    action_state = _mapping(opportunity.get("action_state"))
    change_review = _mapping(opportunity.get("change_review"))
    commercial = round(
        (_score(stakeholder.get("coverage_score")) + _score(relations.get("completion_rate"))) / 2
    )
    evidence = round(
        (_score(requirement_state.get("coverage_score")) + _score(raw_scores.get("credibility"))) / 2
    )
    time_window = 0 if action_state.get("overdue") else _score(raw_scores.get("freshness"))
    if int(change_review.get("pending_count") or 0):
        time_window = min(time_window, 40)
    technical_score = (
        _score(enterprise_fit.get("score"))
        if enterprise_fit.get("status") != "insufficient"
        else 0
    )
    execution_score = _score(workplan_summary.get("execution_readiness"))
    components = [
        _component("compliance", "资质合规", _ratio(compliance_passed, len(compliance_gates)), 20, f"{compliance_passed}/{len(compliance_gates)} 项基础准入门禁通过", "qualification.gates"),
        _component("technical", "技术匹配", technical_score, 20, "采用企业匹配度的可核验证据结果；数据待补时不计分", "scores.enterprise_fit"),
        _component("commercial", "商务策略", commercial, 15, f"关键关系覆盖 {stakeholder.get('coverage_score') or 0}%，行动闭环 {relations.get('completion_rate') or 0}%", "stakeholder_and_relationship_actions"),
        _component("evidence", "证据完整", evidence, 15, f"要求账本覆盖 {requirement_state.get('coverage_score') or 0}%，来源可信 {raw_scores.get('credibility') or 0} 分", "requirements_and_source_trust"),
        _component("team", "团队协同", _score(team.get("coverage_score")), 10, f"核心角色覆盖 {team.get('coverage_score') or 0}%", "team.coverage_score"),
        _component("execution", "作战执行", execution_score, 10, f"正式任务完成 {workplan_summary.get('completed_task_count') or 0}/{workplan_summary.get('task_count') or 0}，按真实任务完成率计分", "bid_workplan.summary.execution_readiness"),
        _component("time", "时间窗口", time_window, 10, _deadline_basis(opportunity, action_state), "deadline_and_change_review"),
    ]
    result = _score_result(
        "bid_readiness",
        "投标准备度",
        components,
        "衡量当前是否具备启动和交付投标文件的条件，覆盖合规、技术、商务、证据、团队和时间六个维度。",
    )
    blockers = _mapping(qualification.get("blockers")).get("approve_bid")
    result["blockers"] = [str(value) for value in blockers] if isinstance(blockers, list) else []
    result["pending_reviews"] = int(review_state.get("pending_count") or 0)
    result["open_review_actions"] = int(review_actions.get("open_count") or 0)
    return result


def _score_result(
    key: str,
    label: str,
    components: list[dict[str, object]],
    explanation: str,
    *,
    force_status: str = "",
) -> dict[str, object]:
    score = round(sum(float(item["weighted_score"]) for item in components))
    status = force_status or ("ready" if score >= 80 else "attention" if score >= 60 else "risk")
    return {
        "key": key,
        "label": label,
        "score": max(0, min(score, 100)),
        "status": status,
        "status_label": {
            "ready": "良好",
            "attention": "需提升",
            "risk": "风险",
            "insufficient": "数据待补",
        }[status],
        "explanation": explanation,
        "components": components,
        "rule_version": RULE_VERSION,
        "evaluated_at": date.today().isoformat(),
    }


def _component(
    key: str,
    label: str,
    score: int,
    weight: int,
    evidence: str,
    source_path: str,
) -> dict[str, object]:
    normalized = max(0, min(int(score), 100))
    return {
        "key": key,
        "label": label,
        "score": normalized,
        "weight": weight,
        "weighted_score": round(normalized * weight / 100, 2),
        "evidence": evidence,
        "source_path": source_path,
    }


def _raw_counts(settings: Settings, notice_id: str) -> dict[str, Any]:
    with connection(settings) as conn:
        notice = conn.execute(
            "SELECT updated_at, last_seen_at FROM notices WHERE id = ?", (notice_id,)
        ).fetchone()
        counts: dict[str, Any] = {}
        for key, table in (
            ("attachments", "attachment_snapshots"),
            ("evidence_items", "evidence_items"),
            ("collaboration_notes", "opportunity_collaboration_notes"),
        ):
            counts[key] = int(
                conn.execute(f"SELECT COUNT(*) FROM {table} WHERE notice_id = ?", (notice_id,)).fetchone()[0]
            )
        counts["notice_updated_at"] = str(notice["updated_at"] or "") if notice else ""
        counts["last_seen_at"] = str(notice["last_seen_at"] or "") if notice else ""
        counts["decision_scenarios"] = int(conn.execute(
            "SELECT COUNT(*) FROM decision_scenarios WHERE notice_id = ?", (notice_id,)
        ).fetchone()[0])
        counts["pending_sandbox_suggestions"] = int(conn.execute(
            "SELECT COUNT(*) FROM decision_scenario_suggestions WHERE notice_id = ? AND status = 'pending'",
            (notice_id,),
        ).fetchone()[0])
        counts["war_room_resources"] = int(conn.execute(
            "SELECT COUNT(*) FROM feishu_war_room_steps WHERE notice_id = ? AND resource_id <> ''",
            (notice_id,),
        ).fetchone()[0])
        counts["war_room_failed_steps"] = int(conn.execute(
            "SELECT COUNT(*) FROM feishu_war_room_steps WHERE notice_id = ? AND status = 'failed'",
            (notice_id,),
        ).fetchone()[0])
        counts["bid_memory_projects"] = int(conn.execute(
            "SELECT COUNT(*) FROM bid_memory_projects WHERE notice_id = ?", (notice_id,)
        ).fetchone()[0])
        counts["bid_memory_assets"] = int(conn.execute(
            "SELECT COUNT(*) FROM bid_memory_assets WHERE source_notice_id = ?", (notice_id,)
        ).fetchone()[0])
        marker_specs = (
            ("requirements", "opportunity_requirements", "updated_at"),
            ("capability_matches", "requirement_capability_matches", "updated_at"),
            ("review_cases", "requirement_review_cases", "updated_at"),
            ("review_actions", "requirement_review_actions", "updated_at"),
            ("workflow", "opportunity_workflows", "updated_at"),
            ("team", "opportunity_team_members", "updated_at"),
            ("stakeholders", "opportunity_stakeholders", "updated_at"),
            ("relationship_actions", "opportunity_relationship_actions", "updated_at"),
            ("events", "opportunity_events", "created_at"),
            ("collaboration_notes", "opportunity_collaboration_notes", "created_at"),
            ("revisions", "notice_revisions", "created_at"),
            ("attachments", "attachment_snapshots", "created_at"),
            ("evidence", "evidence_items", "created_at"),
            ("bid_deliverables", "bid_deliverables", "updated_at"),
            ("bid_plan_tasks", "bid_plan_tasks", "updated_at"),
            ("bid_pricing", "bid_pricing_items", "updated_at"),
            ("decision_scenarios", "decision_scenarios", "updated_at"),
            ("decision_suggestions", "decision_scenario_suggestions", "updated_at"),
            ("war_room", "feishu_war_rooms", "updated_at"),
            ("war_room_steps", "feishu_war_room_steps", "updated_at"),
        )
        counts["state_markers"] = {
            key: _table_state_marker(conn, table, timestamp, notice_id)
            for key, table, timestamp in marker_specs
        }
        counts["state_markers"]["bid_memory_projects"] = _table_state_marker(conn, "bid_memory_projects", "updated_at", notice_id)
        counts["state_markers"]["bid_memory_assets"] = _table_state_marker(conn, "bid_memory_assets", "updated_at", notice_id, id_column="source_notice_id")
        return counts


def _table_state_marker(conn, table: str, timestamp: str, notice_id: str, *, id_column: str = "notice_id") -> dict[str, object]:
    rows = conn.execute(
        f"SELECT * FROM {table} WHERE {id_column} = ? ORDER BY rowid",
        (notice_id,),
    ).fetchall()
    latest = max((str(row[timestamp] or "") for row in rows), default="")
    content = [
        {key: _stable_db_value(row[key]) for key in row.keys()}
        for row in rows
    ]
    return {
        "count": len(rows),
        "latest_at": latest,
        "content_hash": hashlib.sha256(json_dumps(content).encode("utf-8")).hexdigest()
        if rows
        else "",
    }


def _stable_db_value(value: object) -> object:
    if isinstance(value, bytes):
        return value.hex()
    return value


def _source_sync(opportunity: dict[str, object], raw: dict[str, Any]) -> dict[str, object]:
    intelligence = _mapping(opportunity.get("intelligence"))
    trust = _mapping(intelligence.get("trust_assessment"))
    last_seen = str(raw.get("last_seen_at") or "")
    age_days = _age_days(last_seen)
    if not last_seen:
        status, label = "unknown", "采集时间待确认"
    elif age_days is not None and age_days <= 1:
        status, label = "fresh", "24 小时内已同步"
    elif age_days is not None and age_days <= 7:
        status, label = "normal", f"{age_days} 天内已同步"
    else:
        status, label = "stale", f"已 {age_days} 天未见新采集" if age_days is not None else "同步时间待确认"
    return {
        "status": status,
        "status_label": label,
        "source_site": opportunity.get("source_site"),
        "authority": trust.get("authority") or opportunity.get("source_site"),
        "verification_status": trust.get("verification_status") or "unverified",
        "verification_label": trust.get("verification_label") or "待核验",
        "last_seen_at": last_seen,
        "notice_updated_at": raw.get("notice_updated_at") or "",
        "sync_scope": "页面打开时读取数据库最新状态；上游采集频率由数据源调度决定",
    }


def _persist_snapshot(
    settings: Settings,
    notice_id: str,
    state_hash: str,
    summary: dict[str, object],
) -> dict[str, object]:
    snapshot_id = str(uuid4())
    with connection(settings) as conn:
        # Serialize the compare-and-append step so concurrent readers cannot
        # record the same state transition twice.
        conn.execute("BEGIN IMMEDIATE")
        latest = conn.execute(
            """
            SELECT state_hash FROM opportunity_digital_twin_history
            WHERE notice_id = ?
            ORDER BY created_at DESC, rowid DESC
            LIMIT 1
            """,
            (notice_id,),
        ).fetchone()
        changed = latest is None or str(latest["state_hash"]) != state_hash
        conn.execute(
            """
            INSERT OR IGNORE INTO opportunity_digital_twin_snapshots(
                id, notice_id, state_hash, summary_json
            ) VALUES (?, ?, ?, ?)
            """,
            (snapshot_id, notice_id, state_hash, json_dumps(summary)),
        )
        if changed:
            conn.execute(
                """
                INSERT INTO opportunity_digital_twin_history(
                    id, notice_id, state_hash, summary_json
                ) VALUES (?, ?, ?, ?)
                """,
                (snapshot_id, notice_id, state_hash, json_dumps(summary)),
            )
        rows = conn.execute(
            """
            SELECT id, state_hash, summary_json, created_at
            FROM opportunity_digital_twin_history
            WHERE notice_id = ?
            ORDER BY created_at DESC, rowid DESC
            LIMIT 8
            """,
            (notice_id,),
        ).fetchall()
    history = [
        {
            "id": str(row["id"]),
            "state_hash": str(row["state_hash"]),
            "created_at": str(row["created_at"]),
            "summary": _json_mapping(row["summary_json"]),
        }
        for row in rows
    ]
    previous = next((item for item in history if item["state_hash"] != state_hash), None)
    return {
        "status": "changed" if changed else "unchanged",
        "state_hash": state_hash,
        "current_id": next((item["id"] for item in history if item["state_hash"] == state_hash), snapshot_id),
        "changes_since_previous": _snapshot_changes(summary, _mapping(previous.get("summary")) if previous else {}),
        "history": history,
    }


def _snapshot_changes(current: dict[str, object], previous: dict[str, object]) -> list[dict[str, object]]:
    if not previous:
        return [{"label": "数字档案基线", "before": "无", "after": "已建立"}]
    changes: list[dict[str, object]] = []
    current_scores = _mapping(current.get("scores"))
    previous_scores = _mapping(previous.get("scores"))
    score_labels = {
        "opportunity_value": "机会价值",
        "enterprise_fit": "企业匹配度",
        "bid_readiness": "投标准备度",
    }
    for key, label in score_labels.items():
        if current_scores.get(key) != previous_scores.get(key):
            changes.append({"label": label, "before": previous_scores.get(key, 0), "after": current_scores.get(key, 0)})
    current_counts = _mapping(current.get("counts"))
    previous_counts = _mapping(previous.get("counts"))
    for key, label in (
        ("revisions", "公告修订"),
        ("requirements", "要求账本"),
        ("capability_matches", "能力匹配"),
        ("review_items", "会审项"),
        ("team_members", "团队成员"),
        ("bid_plan_tasks_completed", "作战任务完成数"),
    ):
        if current_counts.get(key) != previous_counts.get(key):
            changes.append({"label": label, "before": previous_counts.get(key, 0), "after": current_counts.get(key, 0)})
    if current.get("workflow_stage") != previous.get("workflow_stage"):
        changes.append({"label": "推进阶段", "before": previous.get("workflow_stage") or "未开始", "after": current.get("workflow_stage") or "未开始"})
    if not changes and current.get("state_markers") != previous.get("state_markers"):
        changes.append({"label": "档案内容", "before": "上一状态", "after": "已更新并留痕"})
    return changes[:8]


def _timeline(
    settings: Settings,
    notice_id: str,
    opportunity: dict[str, object],
    revisions: list[Any],
) -> list[dict[str, object]]:
    items = [
        {
            "type": "source",
            "title": "公告进入项目档案",
            "detail": f"{opportunity.get('source_site') or '未知来源'} · {opportunity.get('project_no') or '项目编号待确认'}",
            "at": opportunity.get("publish_time") or "",
            "severity": "normal",
        }
    ]
    for revision in revisions:
        fields = "、".join(revision.changed_fields)
        items.append({
            "type": "revision",
            "title": "公告或附件发生变化",
            "detail": fields or "内容已更新",
            "at": revision.created_at,
            "severity": "attention",
        })
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT action, from_stage, to_stage, actor_open_id, payload_json, created_at
            FROM opportunity_events WHERE notice_id = ?
            ORDER BY created_at DESC, rowid DESC LIMIT 30
            """,
            (notice_id,),
        ).fetchall()
    for row in rows:
        payload = _json_mapping(row["payload_json"])
        items.append({
            "type": "event",
            "title": EVENT_LABELS.get(str(row["action"]), _humanize_action(str(row["action"]))),
            "detail": _event_detail(row, payload),
            "at": str(row["created_at"] or ""),
            "severity": "normal",
        })
    return sorted(items, key=lambda item: str(item.get("at") or ""), reverse=True)[:30]


def _next_actions(
    opportunity: dict[str, object],
    scores: dict[str, dict[str, object]],
    requirement_state: dict[str, object],
    review_state: dict[str, object],
    review_actions: dict[str, int],
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    change_review = _mapping(opportunity.get("change_review"))
    workflow = _mapping(opportunity.get("workflow"))
    if int(change_review.get("pending_count") or 0):
        actions.append({"priority": "urgent", "title": "复核公告重大变更", "reason": f"有 {change_review.get('pending_count')} 条变更使旧结论待复核", "target": "opportunityChangeSection"})
    if not workflow.get("owner_name") and not workflow.get("owner_open_id"):
        actions.append({"priority": "high", "title": "认领项目负责人", "reason": "负责人缺失会阻断投标准入和飞书任务闭环", "target": "opportunityCollaborationSection"})
    if not int(requirement_state.get("total_count") or 0):
        actions.append({"priority": "high", "title": "提取投标要求账本", "reason": "尚无逐条要求，企业匹配度无法形成可靠结论", "target": "opportunityRequirementsSection"})
    elif scores["enterprise_fit"]["status"] == "insufficient":
        actions.append({"priority": "high", "title": "生成并确认能力匹配", "reason": "要求已有，但企业能力尚未完成证据匹配", "target": "opportunityCapabilitySection"})
    if int(review_state.get("pending_count") or 0):
        actions.append({"priority": "normal", "title": "完成人工会审裁决", "reason": f"仍有 {review_state.get('pending_count')} 项等待裁决", "target": "opportunityReviewSection"})
    if int(review_actions.get("open_count") or 0):
        actions.append({"priority": "normal", "title": "闭环会审行动", "reason": f"仍有 {review_actions.get('open_count')} 项行动未完成", "target": "opportunityReviewSection"})
    if not actions:
        actions.append({"priority": "normal", "title": workflow.get("next_action") or "保持档案更新", "reason": "当前关键门禁无新增阻断", "target": "opportunityCollaborationSection"})
    return actions[:5]


def _deadline_basis(opportunity: dict[str, object], action_state: dict[str, object]) -> str:
    deadline = str(opportunity.get("bid_deadline") or "")
    if not deadline:
        return "投标截止时间尚未确认"
    if action_state.get("overdue"):
        return f"投标截止 {deadline}，窗口已关闭"
    days = action_state.get("days_to_deadline")
    return f"投标截止 {deadline}" + (f"，剩余 {days} 天" if days is not None else "")


def _trust_basis(intelligence: dict[str, object]) -> str:
    trust = _mapping(intelligence.get("trust_assessment"))
    return f"{trust.get('authority') or '来源待核验'} · {trust.get('verification_label') or '待核验'}"


def _missing_basis(intelligence: dict[str, object]) -> str:
    missing = intelligence.get("missing_fields")
    values = [str(value) for value in missing] if isinstance(missing, list) else []
    return "关键字段已齐全" if not values else f"仍缺：{'、'.join(values[:5])}"


def _event_detail(row: Any, payload: dict[str, object]) -> str:
    actor = str(row["actor_open_id"] or "系统")
    stage = ""
    if row["from_stage"] or row["to_stage"]:
        stage = f" · {row['from_stage'] or '-'} → {row['to_stage'] or '-'}"
    subject = payload.get("title") or payload.get("requirement_key") or payload.get("member_name") or ""
    return f"{actor}{stage}" + (f" · {subject}" if subject else "")


def _humanize_action(action: str) -> str:
    return re.sub(r"[_-]+", " ", action).strip() or "项目状态已更新"


def _age_days(value: str) -> int | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max((datetime.now(timezone.utc) - parsed).days, 0)
    except ValueError:
        parsed_date = parse_date(value)
        return max((date.today() - parsed_date).days, 0) if parsed_date else None


def _ratio(numerator: int, denominator: int) -> int:
    return round(numerator / denominator * 100) if denominator else 0


def _score(value: object) -> int:
    try:
        return max(0, min(round(float(value or 0)), 100))
    except (TypeError, ValueError):
        return 0


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _json_mapping(value: object) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
