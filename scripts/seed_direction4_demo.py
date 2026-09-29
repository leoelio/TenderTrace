from __future__ import annotations

import json
from pathlib import Path

from tendertrace.bid_workplan import (
    build_bid_workplan,
    complete_bid_task,
    export_bid_workplan,
    get_bid_workplan,
    split_requirement,
    upsert_pricing_item,
)
from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.digital_twin import build_digital_twin
from tendertrace.opportunity_requirements import list_requirements, upsert_requirement
from tendertrace.opportunity_team import upsert_team_member


ROOT = Path(__file__).resolve().parents[1]
NOTICE_ID = "demo-direction4-public-gold"


def seed() -> dict[str, object]:
    settings = Settings.load(ROOT)
    init_db(settings)
    fixture = json.loads((ROOT / "docs" / "demo" / "direction4_requirement_gold_cases.json").read_text(encoding="utf-8"))
    text = "\n".join(str(case["text"]) for case in fixture["cases"])
    fields = {
        "structured_fields": {
            "project_no": "TT-D4-PUBLIC-GOLD-20260927",
            "budget": "公开样本验收，不作为真实报价",
            "bid_deadline": "2026-10-20 17:00",
        },
        "demo_scope": "三份政府采购公开文档的联合金标验收，逐条保留各自来源链接",
    }
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(
                id, source_site, source_url, canonical_url, title, purchaser,
                publish_time, region, content_text, core_content, fields_json,
                updated_at, last_seen_at
            ) VALUES (?, 'ccgp', ?, ?, ?, ?, '2026-09-27', '全国', ?, ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title, purchaser = excluded.purchaser,
                content_text = excluded.content_text, core_content = excluded.core_content,
                fields_json = excluded.fields_json, updated_at = datetime('now'), last_seen_at = datetime('now')
            """,
            (
                NOTICE_ID,
                fixture["cases"][0]["source_url"],
                fixture["cases"][0]["source_url"],
                "方向四｜三份政府采购公开文档联合验收作战图",
                "中国政府采购网公开样本（演示）",
                text,
                "五类高价值要求联合金标验证：资格、截止、评分、废标、附件。",
                json.dumps(fields, ensure_ascii=False),
            ),
        )
    members = {
        "solution": upsert_team_member(settings, notice_id=NOTICE_ID, member_name="方案负责人", role="solution", responsibility="技术响应与评分策略", actor="demo"),
        "commercial": upsert_team_member(settings, notice_id=NOTICE_ID, member_name="商务负责人", role="commercial", responsibility="报价与递交计划", actor="demo"),
        "delivery": upsert_team_member(settings, notice_id=NOTICE_ID, member_name="交付负责人", role="delivery", responsibility="交付可行性与计划", actor="demo"),
        "legal": upsert_team_member(settings, notice_id=NOTICE_ID, member_name="合规负责人", role="legal", responsibility="资格与废标红线", actor="demo"),
    }
    role_by_type = {
        "qualification": "legal",
        "deadline": "commercial",
        "scoring": "solution",
        "disqualification": "legal",
        "attachment": "commercial",
    }
    counters: dict[str, int] = {}
    for case in fixture["cases"]:
        for gold in case["gold"]:
            requirement_type = str(gold["type"])
            counters[requirement_type] = counters.get(requirement_type, 0) + 1
            prefix = {"qualification": "QUAL", "deadline": "DEADLINE", "scoring": "SCORE", "disqualification": "DISQ", "attachment": "ATTACH"}[requirement_type]
            key = f"{prefix}-D4-{counters[requirement_type]:02d}"
            upsert_requirement(
                settings,
                notice_id=NOTICE_ID,
                requirement_key=key,
                requirement_type=requirement_type,
                title=str(gold["text"]),
                evidence_text=str(gold["text"]),
                source_url=str(case["source_url"]),
                source_locator=str(case["source_locator"]),
                mandatory=requirement_type in {"qualification", "deadline", "disqualification", "attachment"},
                confidence=96 if requirement_type in {"deadline", "disqualification"} else 90,
                weight=_score_weight(str(gold["text"])),
                status="confirmed",
                assignee_member_id=members[role_by_type[requirement_type]].id,
                due_at="2026-10-16T17:00",
                note="三份公开文档联合金标验收；人工确认后进入正式计划。",
                source_revision_id=f"gold:{case['case_id']}",
                extraction_mode="rules",
                actor="demo:gold-reviewer",
            )
    complex_requirement = upsert_requirement(
        settings,
        notice_id=NOTICE_ID,
        requirement_key="TECH-D4-COMPLEX",
        requirement_type="technical",
        title="统一门户与政务云部署综合要求",
        evidence_text="支持统一门户一次登录多系统跳转，并提供政务云部署架构、网络架构和资源需求清单。",
        source_url="https://www.ccgp.gov.cn/cggg/dfgg/gzgg/202503/t20250331_24373397.htm",
        source_locator="更正公告正文第50-51行",
        mandatory=True,
        confidence=93,
        status="confirmed",
        assignee_member_id=members["solution"].id,
        due_at="2026-10-16T17:00",
        source_revision_id="public:20250331",
        extraction_mode="rules",
        actor="demo:gold-reviewer",
    )
    current = {item.id: item for item in list_requirements(settings, NOTICE_ID)}
    if current[complex_requirement.id].status != "superseded":
        split_requirement(
            settings,
            NOTICE_ID,
            complex_requirement.id,
            [
                {"title": "统一门户一次登录与多系统跳转响应", "assignee_member_id": members["solution"].id},
                {"title": "政务云部署架构与资源清单", "assignee_member_id": members["delivery"].id},
            ],
            actor="demo:solution-owner",
        )
    build_bid_workplan(settings, NOTICE_ID, actor="demo:project-owner")
    with connection(settings) as conn:
        conn.execute(
            """
            UPDATE bid_deliverables
            SET evidence_ref = CASE
                WHEN evidence_ref = '' THEN '演示证据包/' || deliverable_key || '.pdf'
                ELSE evidence_ref
            END,
                updated_at = datetime('now')
            WHERE notice_id = ? AND deliverable_key IN (
                SELECT deliverable_key FROM bid_deliverables WHERE notice_id = ? ORDER BY deliverable_key LIMIT 6
            )
            """,
            (NOTICE_ID, NOTICE_ID),
        )
    upsert_pricing_item(
        settings,
        NOTICE_ID,
        item_key="PRICE-D4-PLATFORM",
        title="平台许可与实施服务（演示）",
        quantity=1,
        unit="项",
        unit_price=880000,
        cost=610000,
        tax_rate=6,
        owner_member_id=members["commercial"].id,
        status="review",
        note="演示报价，仅用于展示报价计划和毛利计算。",
    )
    twin_before = build_digital_twin(settings, NOTICE_ID)
    refreshed = get_bid_workplan(settings, NOTICE_ID)
    open_prep = next((item for item in refreshed["tasks"] if item["requirement_id"] and item["status"] != "completed"), None)
    if open_prep:
        complete_bid_task(settings, NOTICE_ID, str(open_prep["id"]), actor="demo:owner")
    twin_after = build_digital_twin(settings, NOTICE_ID)
    final_plan = get_bid_workplan(settings, NOTICE_ID)
    export_path = export_bid_workplan(settings, NOTICE_ID)
    result = {
        "notice_id": NOTICE_ID,
        "title": "方向四｜三份政府采购公开文档联合验收作战图",
        "source_case_count": 3,
        "source_urls": [case["source_url"] for case in fixture["cases"]],
        "requirements": final_plan["summary"]["requirement_count"],
        "deliverables": final_plan["summary"]["deliverable_count"],
        "tasks": final_plan["summary"]["task_count"],
        "completed_tasks": final_plan["summary"]["completed_task_count"],
        "execution_readiness_before": twin_before["bid_workplan"]["summary"]["execution_readiness"] if twin_before else 0,
        "execution_readiness_after": twin_after["bid_workplan"]["summary"]["execution_readiness"] if twin_after else 0,
        "digital_twin_bid_readiness_after": twin_after["scores"]["bid_readiness"]["score"] if twin_after else 0,
        "export_path": str(export_path),
    }
    output = ROOT / "docs" / "demo" / "direction4_live_demo_20260927.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _score_weight(text: str) -> float:
    import re
    match = re.search(r"(?:得|占|满分)\s*(\d+(?:\.\d+)?)\s*分", text)
    return min(float(match.group(1)), 100) if match else 0


if __name__ == "__main__":
    print(json.dumps(seed(), ensure_ascii=False, indent=2))
