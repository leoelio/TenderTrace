from __future__ import annotations

import json
from pathlib import Path

from tendertrace.bid_memory import archive_project_memory, decide_bid_memory_asset, get_bid_memory_dashboard
from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.opportunity_outcomes import record_outcome
from tendertrace.opportunity_requirements import upsert_requirement
from tendertrace.organization_memory import create_workspace


ROOT = Path(__file__).resolve().parents[1]
TARGET_NOTICE_ID = "demo-bid-memory-target"
HISTORY = (
    ("demo-bid-memory-won-security", "北京市政务云安全与双活容灾扩容项目", "某市政务数据中心（脱敏）", "won"),
    ("demo-bid-memory-lost-auth", "北京市政务云灾备资源采购项目", "某市政务数据中心（脱敏）", "lost"),
    ("demo-bid-memory-won-migration", "北京市政务云迁移与安全服务项目", "某区政务服务中心（脱敏）", "won"),
)


def seed() -> dict[str, object]:
    settings = Settings.load(ROOT)
    init_db(settings)
    workspace = create_workspace(
        settings,
        name="政务云企业投标记忆体（路演演示）",
        feishu_chat_id="oc_demo_bid_memory_20260928",
        members=[
            {"open_id": "demo-memory-owner", "name": "投标总监（脱敏）", "role": "owner"},
            {"open_id": "demo-memory-member", "name": "解决方案经理（脱敏）", "role": "member"},
            {"open_id": "demo-memory-observer", "name": "外部观察员（脱敏）", "role": "observer"},
        ],
        actor="demo-memory-owner",
    )
    other_workspace = create_workspace(
        settings,
        name="隔离事业部（路演验证）",
        feishu_chat_id="oc_demo_bid_memory_isolation_20260928",
        members=[{"open_id": "demo-other-owner", "name": "其他事业部负责人", "role": "owner"}],
        actor="demo-other-owner",
    )
    _reset_demo_memory(settings, workspace.id, other_workspace.id)
    _seed_notices(settings)
    for notice_id, _, _, result in HISTORY:
        _seed_requirements_and_tasks(settings, notice_id)
        record_outcome(
            settings,
            notice_id,
            {
                "result": result,
                "reason_code": "technical_fit" if result == "won" else "qualification",
                "summary": "项目结果与复盘结论已由负责人依据结果公告核验。",
                "lessons": "安全与容灾章节可复用，但客户参数必须重新核对。" if result == "won" else "原厂项目专项授权必须在截标前完成有效期和地域范围双重复核。",
                "evidence_url": f"https://example.com/bid-memory/{notice_id}/result",
            },
            actor="demo-memory-owner",
        )

    archive_project_memory(
        settings,
        HISTORY[0][0],
        workspace_id=workspace.id,
        actor="demo-memory-owner",
        tags=["政务云", "安全", "双活容灾", "北京"],
        materials=[{
            "asset_key": "security-response-template",
            "title": "政务云安全响应模板（脱敏）",
            "content": "复用安全域、等保与双活容灾章节；客户名称、资源规模、RTO/RPO必须逐项更新。",
            "source_url": "https://example.com/bid-memory/security-template",
            "valid_until": "2028-12-31",
            "reuse_status": "reusable",
            "permission_scope": "restricted",
            "sensitivity": "sensitive",
        }],
    )
    archive_project_memory(
        settings,
        HISTORY[1][0],
        workspace_id=workspace.id,
        actor="demo-memory-owner",
        tags=["政务云", "授权", "失败教训", "北京"],
        materials=[{
            "asset_key": "expired-oem-letter",
            "title": "历史原厂授权函",
            "content": "仅用于证明历史缺口，已经过期，严禁直接用于新项目。",
            "source_url": "https://example.com/bid-memory/expired-letter",
            "valid_until": "2025-12-31",
            "reuse_status": "reusable",
        }, {
            "asset_key": "authorization-gap",
            "asset_type": "gap",
            "title": "原厂专项授权缺口",
            "content": "启动阶段就锁定型号、项目名称、地区和授权有效期，截标前执行双人核验。",
            "reuse_status": "reference",
        }],
    )
    third = archive_project_memory(
        settings,
        HISTORY[2][0],
        workspace_id=workspace.id,
        actor="demo-memory-owner",
        tags=["政务云", "迁移", "安全", "北京"],
        materials=[{
            "asset_key": "migration-checklist",
            "title": "政务云迁移核对清单",
            "content": "包含割接窗口、回退机制、数据校验和安全审计四组核对项。",
            "source_url": "https://example.com/bid-memory/migration-checklist",
            "valid_until": "2028-06-30",
            "reuse_status": "update_needed",
        }, {
            "asset_key": "legacy-outline",
            "title": "旧版迁移章节目录",
            "content": "已经被新版迁移核对清单替代。",
            "reuse_status": "reference",
        }],
    )
    checklist = next(item for item in third["assets"] if item["asset_key"] == "migration-checklist")
    decide_bid_memory_asset(
        settings,
        checklist["id"],
        workspace_id=workspace.id,
        action="correct",
        actor="demo-memory-member",
        note="补充割接回退与安全审计适用边界",
        corrections={
            "content": "复用割接窗口、回退机制、数据校验和安全审计四组核对项；资源数量和窗口时间必须按新项目更新。",
            "valid_until": "2028-06-30",
            "reuse_status": "reusable",
        },
    )
    legacy = next(item for item in third["assets"] if item["asset_key"] == "legacy-outline")
    decide_bid_memory_asset(
        settings,
        legacy["id"],
        workspace_id=workspace.id,
        action="withdraw",
        actor="demo-memory-owner",
        note="旧目录已由新版迁移核对清单替代",
    )

    _seed_other_workspace(settings, other_workspace.id)
    owner = get_bid_memory_dashboard(settings, workspace_id=workspace.id, notice_id=TARGET_NOTICE_ID, actor="demo-memory-owner")
    observer = get_bid_memory_dashboard(settings, workspace_id=workspace.id, notice_id=TARGET_NOTICE_ID, actor="demo-memory-observer")
    outsider = get_bid_memory_dashboard(settings, workspace_id=workspace.id, notice_id=TARGET_NOTICE_ID, actor="demo-outsider")
    other_owner = get_bid_memory_dashboard(settings, workspace_id=other_workspace.id, notice_id=TARGET_NOTICE_ID, actor="demo-other-owner")
    expired = next(item for item in owner["assets"] if item["asset_key"] == "expired-oem-letter")
    result = {
        "workspace_id": workspace.id,
        "target_notice_id": TARGET_NOTICE_ID,
        "demo_url": f"http://127.0.0.1:8000/?workspace={workspace.id}&memory_notice={TARGET_NOTICE_ID}",
        "summary": owner["summary"],
        "sample": owner["sample"],
        "recommendations": [{
            "source_notice_id": item["source_notice_id"],
            "result": item["result"],
            "similarity_score": item["similarity_score"],
            "reasons": item["reasons"],
            "reusable_assets": [asset["title"] for asset in item["reusable_assets"]],
            "warnings": [asset["title"] for asset in item["warnings"]],
        } for item in owner["recommendations"]],
        "proof": {
            "three_similar_projects": len(owner["recommendations"]) == 3,
            "wins_and_losses_together": {item["result"] for item in owner["recommendations"]} == {"won", "lost"},
            "sources_and_reasons_present": all(item["source_notice_id"] and item["source_url"] and item["reasons"] for item in owner["recommendations"]),
            "human_audit_present": any(item["action"] in {"asset_correct", "asset_withdraw"} for item in owner["audit"]),
            "expired_never_reusable": expired["effective_status"] == "expired" and all(expired["id"] != asset["id"] for item in owner["recommendations"] for asset in item["reusable_assets"]),
            "observer_cannot_see_sensitive": not any(item["asset_key"] == "security-response-template" for item in observer["assets"]),
            "outsider_denied": not outsider["access"]["granted"],
            "workspace_isolated": not any(item["notice_id"] == "demo-bid-memory-other-secret" for item in owner["projects"]) and len(other_owner["projects"]) == 1,
            "graph_covers_core_relations": {"target", "project", "customer", "region", "category", "requirement", "task", "decision", "outcome"}.issubset({item["type"] for item in owner["graph"]["nodes"]}),
            "no_probability_output": owner["sample"]["probability_output"] is False and owner["rules"]["no_win_probability"] is True,
            "corrected_asset_versioned": next(item for item in owner["assets"] if item["asset_key"] == "migration-checklist")["version_number"] == 2,
        },
    }
    output = ROOT / "docs" / "demo" / "bid_memory_live_demo_20260928.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _reset_demo_memory(settings: Settings, *workspace_ids: str) -> None:
    with connection(settings) as conn:
        for workspace_id in workspace_ids:
            conn.execute("DELETE FROM bid_memory_audit_events WHERE workspace_id = ?", (workspace_id,))
            conn.execute("DELETE FROM bid_memory_assets WHERE workspace_id = ?", (workspace_id,))
            conn.execute("DELETE FROM bid_memory_projects WHERE workspace_id = ?", (workspace_id,))


def _seed_notices(settings: Settings) -> None:
    notices = list(HISTORY) + [
        (TARGET_NOTICE_ID, "北京市政务云安全与容灾一体化采购项目", "某市政务数据中心（脱敏）", "target"),
        ("demo-bid-memory-other-secret", "其他事业部涉密云项目", "某单位（脱敏）", "won"),
    ]
    with connection(settings) as conn:
        for notice_id, title, purchaser, _ in notices:
            fields = {"structured_fields": {"category": "政务云", "project_no": notice_id.upper(), "bid_deadline": "2026-11-18 17:00"}}
            conn.execute(
                """
                INSERT INTO notices(id, source_site, source_url, canonical_url, title, purchaser, publish_time, region, content_text, core_content, fields_json, updated_at, last_seen_at)
                VALUES (?, 'demo', ?, ?, ?, ?, '2026-09-28', '北京', ?, ?, ?, datetime('now'), datetime('now'))
                ON CONFLICT(id) DO UPDATE SET title=excluded.title, purchaser=excluded.purchaser, region=excluded.region,
                    content_text=excluded.content_text, core_content=excluded.core_content, fields_json=excluded.fields_json,
                    updated_at=datetime('now'), last_seen_at=datetime('now')
                """,
                (notice_id, f"https://example.com/bid-memory/{notice_id}", f"https://example.com/bid-memory/{notice_id}", title, purchaser, f"{title}，要求政务云安全、双活容灾、原厂授权、迁移实施与审计交付。", "政务云安全与双活容灾建设。", json.dumps(fields, ensure_ascii=False)),
            )


def _seed_requirements_and_tasks(settings: Settings, notice_id: str) -> None:
    requirement = upsert_requirement(
        settings,
        notice_id=notice_id,
        requirement_key="TECH-MEMORY-01",
        requirement_type="technical",
        title="政务云双活容灾与安全响应",
        evidence_text="采购文件要求提供双活容灾、安全域划分、迁移回退与审计交付方案。",
        source_url=f"https://example.com/bid-memory/{notice_id}",
        source_locator="技术规格第18-26页",
        mandatory=True,
        confidence=96,
        status="confirmed",
        actor="demo-memory-owner",
    )
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO bid_plan_tasks(id, notice_id, requirement_id, task_key, title, milestone_type, due_at, status, formal, completed_at)
            VALUES (?, ?, ?, 'MEMORY-TASK-01', '完成安全与容灾响应章节复核', 'document', '2026-09-20 17:00', 'completed', 1, '2026-09-18 16:30')
            ON CONFLICT(notice_id, task_key) DO UPDATE SET title=excluded.title, status='completed', completed_at=excluded.completed_at, updated_at=datetime('now')
            """,
            (f"task-{notice_id}", notice_id, requirement.id),
        )


def _seed_other_workspace(settings: Settings, workspace_id: str) -> None:
    notice_id = "demo-bid-memory-other-secret"
    record_outcome(settings, notice_id, {"result": "won", "reason_code": "technical_fit", "summary": "其他事业部项目结果。", "lessons": "仅允许本事业部访问。", "evidence_url": "https://example.com/bid-memory/other/result"}, actor="demo-other-owner")
    archive_project_memory(settings, notice_id, workspace_id=workspace_id, actor="demo-other-owner", materials=[{"asset_key": "secret", "title": "其他事业部敏感经验", "content": "不得跨组织访问。", "permission_scope": "restricted", "sensitivity": "sensitive"}])


if __name__ == "__main__":
    print(json.dumps(seed(), ensure_ascii=False, indent=2))
