from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path

from tendertrace.company_due_diligence import (
    add_company_evidence,
    add_company_relationship,
    aggregate_existing_company_data,
    ask_company_due_diligence,
    create_company_due_diligence_task,
    create_company_entity,
    evaluate_company_risks,
    get_company_due_diligence_profile,
    list_company_due_diligence_tasks,
    list_company_entities,
    review_company_evidence,
    save_company_due_diligence_snapshot,
    submit_due_diligence_review,
    subscribe_company_changes,
)
from tendertrace.config import Settings
from tendertrace.db import connection
from tendertrace.integrations.feishu_company_due_diligence import (
    sync_company_due_diligence_task,
)
from tendertrace.organization_memory import create_workspace


ROOT = Path(__file__).resolve().parents[1]
REAL_WORKSPACE_ID = "b9e56ca6-c5f1-58fc-b79e-58b26e053f16"
REAL_NOTICE_ID = "ggzy:0051eddfc588cedd4da698903cec566821e7"
REAL_COMPANY_NAME = "成都华东电脑系统集成有限公司"
REAL_ASSIGNEE = "ou_7c7bf0b2fea7bcea1f17988437ac25d9"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sync-feishu", action="store_true")
    args = parser.parse_args()
    settings = Settings.load(ROOT)
    real_case = _seed_real_demo(settings, sync_feishu=args.sync_feishu)
    gold_cases = _seed_gold_cases(settings)
    demo_path = ROOT / "docs" / "demo" / "company_due_diligence_live_demo_20260929.json"
    gold_path = ROOT / "docs" / "demo" / "company_due_diligence_gold_cases_20260929.json"
    demo_path.write_text(json.dumps(real_case, ensure_ascii=False, indent=2), encoding="utf-8")
    gold_path.write_text(json.dumps(gold_cases, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"demo": str(demo_path), "gold": str(gold_path), "feishu": args.sync_feishu}, ensure_ascii=False))


def _seed_real_demo(settings: Settings, *, sync_feishu: bool) -> dict[str, object]:
    entity = _get_or_create_entity(settings, REAL_WORKSPACE_ID, REAL_COMPANY_NAME, "成都")
    entity_id = str(entity["id"])
    aggregation = aggregate_existing_company_data(
        settings, entity_id, workspace_id=REAL_WORKSPACE_ID, actor="admin"
    )
    cooperation = add_company_evidence(
        settings,
        entity_id,
        workspace_id=REAL_WORKSPACE_ID,
        actor="admin",
        evidence_type="cooperation_record",
        title="脱敏合作访谈纪要（路演演示材料）",
        content_text=(
            "路演演示用脱敏材料，不代表对真实企业的事实判断。访谈记录显示交付联系人已建立，"
            "但验收口径和重大事项持续披露机制仍需在签约前确认。"
        ),
        redacted_content=(
            "路演演示用脱敏材料。交付联系人已建立；验收口径和重大事项持续披露机制待确认。"
        ),
        source_type="manual_upload",
        source_name="路演脱敏合作材料",
        source_license="authorized_demo_material",
        access_policy="workspace",
        access_frequency="manual",
        occurred_at="2026-09-29",
        valid_until="2027-03-31",
        confidence=80,
        sensitive=True,
        notice_id=REAL_NOTICE_ID,
    )
    review_company_evidence(
        settings,
        str(cooperation["id"]),
        workspace_id=REAL_WORKSPACE_ID,
        actor="admin",
        status="verified",
        reason="仅确认材料来源和脱敏状态，不把演示材料扩张为真实企业负面事实",
    )
    award_evidence = next(
        (
            item
            for item in aggregation["evidence"]
            if item["notice_id"] == REAL_NOTICE_ID and item["source_type"] == "notice"
        ),
        None,
    )
    if award_evidence:
        review_company_evidence(
            settings,
            str(award_evidence["id"]),
            workspace_id=REAL_WORKSPACE_ID,
            actor="admin",
            status="verified",
            reason="核对本地已固化公共资源交易公告快照",
        )
        _ensure_relationship(
            settings,
            entity_id,
            workspace_id=REAL_WORKSPACE_ID,
            evidence_id=str(award_evidence["id"]),
        )
    risks = evaluate_company_risks(
        settings, entity_id, workspace_id=REAL_WORKSPACE_ID, actor="admin"
    )
    due = (date.today() + timedelta(days=7)).isoformat()
    task_specs = (
        ("法务核验主体与司法合规", "请补充当前有效的主体登记、司法执行和行政处罚核验结果。", "legal"),
        ("交付确认同类项目验收口径", "请核对历史服务器项目的交付范围、验收标准和客户证明。", "delivery"),
    )
    existing_tasks = {
        item["title"]: item
        for item in list_company_due_diligence_tasks(
            settings, entity_id, workspace_id=REAL_WORKSPACE_ID, actor="admin"
        )
    }
    tasks = []
    for title, question, task_type in task_specs:
        task = existing_tasks.get(title) or create_company_due_diligence_task(
            settings,
            entity_id,
            workspace_id=REAL_WORKSPACE_ID,
            actor="admin",
            title=title,
            question=question,
            task_type=task_type,
            assignee_open_id=REAL_ASSIGNEE,
            due_at=due,
            notice_id=REAL_NOTICE_ID,
        )
        sync_result: dict[str, object] = {"status": "not_requested"}
        if sync_feishu:
            try:
                sync_result = sync_company_due_diligence_task(settings, str(task["id"]))
            except Exception as exc:
                sync_result = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
        tasks.append({"task": task, "sync": sync_result})
    profile = get_company_due_diligence_profile(
        settings, entity_id, workspace_id=REAL_WORKSPACE_ID, actor="admin"
    )
    current = profile.get("current_review")
    if not current or current.get("recommendation") != "conditional":
        review = submit_due_diligence_review(
            settings,
            entity_id,
            workspace_id=REAL_WORKSPACE_ID,
            actor="admin",
            recommendation="conditional",
            reason="已核验真实服务器项目公告和脱敏合作材料；主体、司法合规与验收证明仍需在签约前补齐。",
            valid_until=(date.today() + timedelta(days=180)).isoformat(),
            conditions=["补齐官方主体及司法合规核验", "合同写明验收标准、重大事项披露与退出条款"],
            notice_id=REAL_NOTICE_ID,
        )
    else:
        review = current
    subscription = subscribe_company_changes(
        settings,
        entity_id,
        workspace_id=REAL_WORKSPACE_ID,
        actor="admin",
        event_types=["subject", "operations", "judicial", "performance", "relationships"],
    )
    answer = ask_company_due_diligence(
        settings,
        entity_id,
        workspace_id=REAL_WORKSPACE_ID,
        actor="admin",
        question="如果合作，合同里最需要约束什么？",
    )
    snapshot = save_company_due_diligence_snapshot(
        settings,
        entity_id,
        workspace_id=REAL_WORKSPACE_ID,
        actor="admin",
        verified=True,
    )
    profile = get_company_due_diligence_profile(
        settings, entity_id, workspace_id=REAL_WORKSPACE_ID, actor="admin"
    )
    return {
        "workspace_id": REAL_WORKSPACE_ID,
        "entity_id": entity_id,
        "notice_id": REAL_NOTICE_ID,
        "source_fact": "真实公开服务器采购合同公告中的成交供应商；其他合作材料均明确标为脱敏路演材料",
        "aggregation": {"imported_count": aggregation["imported_count"], "source_counts": aggregation["source_counts"]},
        "risk_summary": risks,
        "answer": answer,
        "review": review,
        "subscription": subscription,
        "tasks": tasks,
        "snapshot": {key: snapshot[key] for key in ("id", "state_hash", "verified", "verified_at")},
        "profile_summary": profile["summary"],
        "url": f"http://127.0.0.1:8000/?view=partnerView&workspace={REAL_WORKSPACE_ID}&partner={entity_id}",
    }


def _seed_gold_cases(settings: Settings) -> dict[str, object]:
    workspace = create_workspace(
        settings,
        name="合作方尽调金标空间（脱敏）",
        feishu_chat_id="oc_demo_company_due_diligence_20260929",
        members=[
            {"open_id": "ou_gold_owner", "name": "尽调负责人（脱敏）", "role": "owner"},
            {"open_id": "ou_gold_member", "name": "业务成员（脱敏）", "role": "member"},
        ],
        actor="admin",
    )
    definitions = [
        {
            "case_id": "gold-clean-history",
            "legal_name": "云岭交付服务有限公司（脱敏）",
            "evidence": [("award_result", "历史中标结果", "已完成同类项目并取得验收证明。")],
            "expected_rules": [],
        },
        {
            "case_id": "gold-penalty",
            "legal_name": "华兴科技有限公司（脱敏A）",
            "evidence": [("administrative_penalty", "行政处罚快照", "处罚已履行，整改材料仍需法务核验。")],
            "expected_rules": ["evidence:administrative_penalty"],
        },
        {
            "case_id": "gold-conflict-judicial",
            "legal_name": "安衡联合服务有限公司（脱敏）",
            "evidence": [
                ("conflict", "利益冲突声明", "存在待披露的关联关系，需独立审批。"),
                ("judicial_case", "司法案件快照", "执行状态和涉案金额需法务复核。"),
            ],
            "expected_rules": ["evidence:conflict", "evidence:judicial_case"],
        },
    ]
    cases = []
    for definition in definitions:
        entity = _get_or_create_entity(settings, workspace.id, definition["legal_name"], "已脱敏")
        for evidence_type, title, content in definition["evidence"]:
            evidence = add_company_evidence(
                settings,
                str(entity["id"]),
                workspace_id=workspace.id,
                actor="ou_gold_owner",
                evidence_type=evidence_type,
                title=title,
                content_text=content,
                source_type="manual_upload",
                source_name="脱敏金标材料",
                source_license="authorized_gold_case",
                access_policy="workspace",
                access_frequency="manual",
                valid_until="2027-06-30",
                confidence=95,
            )
            review_company_evidence(
                settings,
                str(evidence["id"]),
                workspace_id=workspace.id,
                actor="ou_gold_owner",
                status="verified",
                reason="金标评审确认",
            )
        result = evaluate_company_risks(
            settings,
            str(entity["id"]),
            workspace_id=workspace.id,
            actor="ou_gold_owner",
        )
        actual_rules = _active_rule_keys(settings, str(entity["id"]))
        cases.append(
            {
                **definition,
                "entity_id": entity["id"],
                "workspace_id": workspace.id,
                "actual_rules": actual_rules,
                "risk_count": len(result["risks"]),
                "missing_is_separate": all(item["signal_kind"] == "missing" for item in result["missing"]),
            }
        )
    return {
        "version": "direction16-gold-v1",
        "redacted": True,
        "workspace_id": workspace.id,
        "cases": cases,
        "evaluation_command": ".venv\\Scripts\\python.exe scripts\\evaluate_company_due_diligence.py",
    }


def _get_or_create_entity(settings: Settings, workspace_id: str, legal_name: str, region: str) -> dict[str, object]:
    items = list_company_entities(settings, workspace_id=workspace_id, actor="admin", query=legal_name)
    existing = next((item for item in items if item["legal_name"] == legal_name), None)
    return existing or create_company_entity(
        settings, workspace_id=workspace_id, legal_name=legal_name, region=region, actor="admin"
    )


def _ensure_relationship(
    settings: Settings,
    entity_id: str,
    *,
    workspace_id: str,
    evidence_id: str,
) -> None:
    profile = get_company_due_diligence_profile(
        settings, entity_id, workspace_id=workspace_id, actor="admin"
    )
    if any(item["related_object_id"] == REAL_NOTICE_ID for item in profile["relationships"]):
        return
    add_company_relationship(
        settings,
        entity_id,
        workspace_id=workspace_id,
        actor="admin",
        related_label="成都市自然资源调查利用研究院机架式服务器采购合同",
        relationship_type="award",
        basis_type="factual",
        confidence=95,
        evidence_id=evidence_id,
        related_object_type="notice",
        related_object_id=REAL_NOTICE_ID,
    )


def _active_rule_keys(settings: Settings, entity_id: str) -> list[str]:
    with connection(settings) as conn:
        return [
            str(row["rule_key"])
            for row in conn.execute(
                """
                SELECT rule_key FROM company_risk_signals
                WHERE entity_id = ? AND signal_kind = 'risk' AND signal_status = 'active'
                ORDER BY rule_key
                """,
                (entity_id,),
            ).fetchall()
        ]


if __name__ == "__main__":
    main()
