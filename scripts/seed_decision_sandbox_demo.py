from __future__ import annotations

import json
from pathlib import Path

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.decision_sandbox import (
    compare_scenarios,
    decide_scenario_suggestion,
    formal_project_state_hash,
    get_decision_sandbox,
    promote_scenario,
    recompute_scenario,
    simulate_scenario,
)
from tendertrace.opportunity_requirements import upsert_requirement


ROOT = Path(__file__).resolve().parents[1]
NOTICE_ID = "demo-decision-sandbox"


def seed() -> dict[str, object]:
    settings = Settings.load(ROOT)
    init_db(settings)
    fields = {
        "structured_fields": {
            "project_no": "TT-SIM-20260928",
            "budget": 5800000,
            "bid_deadline": "2026-10-16 17:00",
        },
        "demo_scope": "投标决策沙盘脱敏样本",
    }
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(
                id, source_site, source_url, canonical_url, title, purchaser,
                publish_time, region, content_text, core_content, fields_json,
                updated_at, last_seen_at
            ) VALUES (?, 'demo', ?, ?, ?, ?, '2026-09-28', '北京', ?, ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title, purchaser = excluded.purchaser,
                region = excluded.region, content_text = excluded.content_text,
                core_content = excluded.core_content, fields_json = excluded.fields_json,
                updated_at = datetime('now'), last_seen_at = datetime('now')
            """,
            (
                NOTICE_ID,
                "https://example.com/decision-sandbox",
                "https://example.com/decision-sandbox",
                "政务云投标决策沙盘",
                "某政务单位（脱敏）",
                "政务云平台采购，包含截止时间、关键技术参数、伙伴授权与北京区域交付要求。",
                "通过只读基准与临时参数比较自主投标和联合伙伴投标方案。",
                json.dumps(fields, ensure_ascii=False),
            ),
        )
        conn.execute(
            """
            INSERT INTO opportunity_team_members(
                id, notice_id, member_key, member_open_id, member_name, role,
                responsibility, added_by
            ) VALUES ('sandbox-member-manager', ?, 'bid-manager', 'demo-bid-manager',
                '李经理（脱敏）', 'bid_manager', '统筹投标决策与资源安排', 'demo')
            ON CONFLICT(notice_id, member_key, role) DO UPDATE SET
                member_name = excluded.member_name, responsibility = excluded.responsibility,
                status = 'active', updated_at = datetime('now')
            """,
            (NOTICE_ID,),
        )
        conn.execute("DELETE FROM decision_sandbox_events WHERE notice_id = ?", (NOTICE_ID,))
        conn.execute("DELETE FROM decision_scenario_suggestions WHERE notice_id = ?", (NOTICE_ID,))
        conn.execute("DELETE FROM decision_scenarios WHERE notice_id = ?", (NOTICE_ID,))
        conn.execute("DELETE FROM bid_plan_tasks WHERE notice_id = ? AND milestone_type = 'sandbox_suggestion'", (NOTICE_ID,))

    requirements = []
    for key, kind, title, locator in (
        ("DEADLINE-SIM-01", "deadline", "投标截止时间与上传窗口", "采购文件第6页"),
        ("TECH-SIM-01", "technical", "政务云安全与容灾参数", "技术规格第18-26页"),
        ("QUAL-SIM-01", "qualification", "原厂项目专项授权", "资格条件第9页"),
        ("COMM-SIM-01", "commercial", "北京区域交付承诺", "商务条款第31页"),
        ("SCORE-SIM-01", "scoring", "报价与实施方案评分", "评分表第42页"),
    ):
        requirements.append(upsert_requirement(
            settings,
            notice_id=NOTICE_ID,
            requirement_key=key,
            requirement_type=kind,
            title=title,
            evidence_text=f"采购文件明确要求：{title}。",
            source_url="https://example.com/decision-sandbox",
            source_locator=locator,
            mandatory=True,
            confidence=96,
            status="confirmed",
            extraction_mode="rules",
            actor="demo:需求负责人",
        ))
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO bid_plan_tasks(
                id, notice_id, requirement_id, task_key, title, milestone_type,
                due_at, status, formal
            ) VALUES ('sandbox-baseline-task', ?, ?, 'BASELINE-01', '完成政务云技术响应初稿',
                'draft', '2026-10-10 17:00', 'open', 1)
            ON CONFLICT(notice_id, task_key) DO UPDATE SET title = excluded.title,
                due_at = excluded.due_at, status = 'open', formal = 1, updated_at = datetime('now')
            """,
            (NOTICE_ID, requirements[1].id),
        )

    formal_before = formal_project_state_hash(settings, NOTICE_ID)
    deadline = simulate_scenario(
        settings,
        NOTICE_ID,
        name="截止提前三天",
        params={"deadline_shift_days": -3},
        actor="demo:项目负责人",
    )
    partner = simulate_scenario(
        settings,
        NOTICE_ID,
        name="联合伙伴补齐材料",
        params={
            "scenario_mode": "joint_bid",
            "partner_material_status": "complete",
            "delivery_region_status": "covered",
        },
        actor="demo:项目负责人",
    )
    formal_after_simulation = formal_project_state_hash(settings, NOTICE_ID)
    deadline_recompute = recompute_scenario(settings, NOTICE_ID, deadline["id"])
    comparison = compare_scenarios(settings, NOTICE_ID, deadline["id"], partner["id"])

    pending = promote_scenario(settings, NOTICE_ID, deadline["id"], actor="demo:项目负责人")
    partner_suggestion = promote_scenario(settings, NOTICE_ID, partner["id"], actor="demo:项目负责人")
    formal_after_pending = formal_project_state_hash(settings, NOTICE_ID)
    accepted = decide_scenario_suggestion(
        settings,
        NOTICE_ID,
        partner_suggestion["id"],
        accept=True,
        actor="demo:投标总监",
        note="伙伴授权、区域交付条件改善，确认将归档与分工行动纳入正式计划。",
    )
    formal_after_accept = formal_project_state_hash(settings, NOTICE_ID)
    sandbox = get_decision_sandbox(settings, NOTICE_ID)
    result = {
        "notice_id": NOTICE_ID,
        "title": "政务云投标决策沙盘",
        "scenario_ids": [deadline["id"], partner["id"]],
        "pending_suggestion_id": pending["id"],
        "accepted_suggestion_id": accepted["id"],
        "accepted_task_ids": accepted["created_task_ids"],
        "comparison": comparison["interpretation"],
        "proof": {
            "simulation_kept_formal_state": formal_before == formal_after_simulation,
            "pending_suggestion_kept_formal_state": formal_before == formal_after_pending,
            "human_acceptance_changed_formal_state": formal_after_accept != formal_before,
            "same_parameters_recompute_identically": deadline_recompute["identical"],
            "baseline_was_current_during_recompute": deadline_recompute["baseline_is_current"],
            "two_saved_scenarios": len(sandbox["scenarios"]) == 2,
            "no_win_probability": sandbox["rules"]["no_win_probability"] and comparison["no_win_probability"],
            "all_changes_explainable": all(
                item.get("input") and item.get("reason") and item.get("rule")
                for scenario in sandbox["scenarios"]
                for item in scenario["output"].get("score_changes", [])
            ),
            "responsible_confirmation_required": sandbox["rules"]["responsible_confirmation_required"],
        },
        "formal_hashes": {
            "before": formal_before,
            "after_simulation": formal_after_simulation,
            "after_pending": formal_after_pending,
            "after_accept": formal_after_accept,
        },
    }
    output = ROOT / "docs" / "demo" / "decision_sandbox_live_demo_20260928.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(seed(), ensure_ascii=False, indent=2))
