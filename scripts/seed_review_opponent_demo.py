from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from tendertrace.capability_matching import analyze_capability_matches, refresh_capability_validity, upsert_capability
from tendertrace.config import ModelMode, Settings
from tendertrace.db import connection, init_db
from tendertrace.digital_twin import build_digital_twin
from tendertrace.llm.gateway import ModelCallResult
from tendertrace.opportunity_requirements import upsert_requirement
from tendertrace.requirement_review_agents import (
    AGENT_PERSONAS,
    list_review_agent_runs,
    list_review_opinions,
    retry_review_agent,
    review_agent_suggestions,
    run_review_agents,
)
from tendertrace.requirement_review_board import (
    list_requirement_review_cases,
    resolve_requirement_review_case,
    sync_requirement_review_cases,
)


ROOT = Path(__file__).resolve().parents[1]
NOTICE_ID = "demo-review-opponent"


class DemoGateway:
    def __init__(self, *, fail_roles: set[str] | None = None, technical_decision: str = "accept"):
        self.fail_roles = fail_roles or set()
        self.technical_decision = technical_decision

    def generate_json(self, *, system: str, user: str) -> ModelCallResult:
        role = next(key for key in AGENT_PERSONAS if f"（{key}）" in system)
        if role in self.fail_roles:
            return ModelCallResult(mode="local", provider="demo", model="opponent-demo", status="failed", error=f"{role} simulated timeout")
        payload = json.loads(user)
        requirement_id = payload["requirement"]["evidence_id"]
        capability_items = payload.get("enterprise_capability_matches", [])
        product = next((item["evidence_id"] for item in capability_items if "TT-X100" in item.get("capability_title", "")), requirement_id)
        certificate = next((item["evidence_id"] for item in capability_items if "认证" in item.get("capability_title", "")), requirement_id)
        if role == "technical":
            parsed = {"decision": self.technical_decision, "confidence": 94, "rationale": "TT-X100 产品规格与招标参数一致，技术路径可实施。", "evidence_ids": [requirement_id, product], "risks": [], "pending_items": [], "recommended_actions": ["进入技术响应编制"]}
        elif role == "evidence_audit":
            parsed = {"decision": "reject", "confidence": 98, "rationale": "企业认证材料已过有效期，当前不能支撑资格与技术结论。", "evidence_ids": [requirement_id, certificate], "risks": ["认证证书过期"], "pending_items": ["更新有效认证证书"], "recommended_actions": ["退回补证并由人员裁决"]}
        elif role == "project_control":
            parsed = {"decision": "escalate", "confidence": 78, "rationale": "补证时间可能影响内部终审窗口。", "evidence_ids": [requirement_id, certificate], "risks": ["补证时序风险"], "pending_items": ["证书更新时间"], "recommended_actions": ["设置补证截止节点"]}
        else:
            parsed = {"decision": "accept", "confidence": 82, "rationale": f"{role} 未发现本专业范围内的新冲突。", "evidence_ids": [requirement_id], "risks": [], "pending_items": [], "recommended_actions": ["保留人工终审"]}
        return ModelCallResult(mode="local", provider="demo", model="opponent-demo", status="ok", parsed=parsed)


def seed() -> dict[str, object]:
    base = Settings.load(ROOT)
    init_db(base)
    fields = {"structured_fields": {"project_no": "TT-REVIEW-20260927", "budget": 3200000, "bid_deadline": "2026-10-18 17:00"}, "demo_scope": "可质询多角色会审脱敏样本"}
    with connection(base) as conn:
        conn.execute(
            """
            INSERT INTO notices(id, source_site, source_url, canonical_url, title, purchaser,
                publish_time, region, content_text, core_content, fields_json, snapshot_sha256,
                updated_at, last_seen_at)
            VALUES (?, 'demo', ?, ?, ?, ?, '2026-09-27', '北京', ?, ?, ?, 'review-opponent-snapshot', datetime('now'), datetime('now'))
            ON CONFLICT(id) DO UPDATE SET title = excluded.title, purchaser = excluded.purchaser,
                content_text = excluded.content_text, core_content = excluded.core_content,
                fields_json = excluded.fields_json, snapshot_sha256 = excluded.snapshot_sha256,
                updated_at = datetime('now'), last_seen_at = datetime('now')
            """,
            (NOTICE_ID, "https://example.com/review-opponent", "https://example.com/review-opponent", "政务云投标专业对手盘", "某政务单位（脱敏）", "TT-X100 技术参数与有效行业认证要求。", "同一证据集上的五角色独立审查和人工裁决。", json.dumps(fields, ensure_ascii=False)),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO notice_revisions(id, notice_id, change_hash, changed_fields_json, before_json, after_json)
            VALUES ('review-opponent-rev-1', ?, 'review-change-1', '["content_text"]', '{}', '{"content_text":"TT-X100 与有效认证要求"}')
            """,
            (NOTICE_ID,),
        )
    requirement = upsert_requirement(
        base,
        notice_id=NOTICE_ID,
        requirement_key="TECH-REVIEW-01",
        requirement_type="technical",
        title="TT-X100 参数与有效认证联合要求",
        evidence_text="投标产品型号：TT-X100，技术参数须符合附件；配套行业认证在投标截止日必须有效。",
        source_url="https://example.com/review-opponent",
        source_locator="招标文件第28页、第31页",
        mandatory=True,
        confidence=58,
        status="review",
        source_revision_id="review-opponent-rev-1",
        extraction_mode="rules",
        actor="demo:需求负责人",
    )
    upsert_capability(base, capability_key="REVIEW-PRODUCT-X100", title="TT-X100 产品规格", capability_type="product_parameter", evidence_text="TT-X100 处理器、内存、存储和接口满足附件参数。", source_url="https://example.com/review/product", source_locator="TT-X100规格书第3-8页", verification_status="verified", applicable_entity="示例科技有限公司", product_model="TT-X100", regions=["北京"], authorization_scope="北京政务项目", valid_until="2028-12-31", source_file_name="TT-X100规格书.pdf", actor="demo:证据管理员")
    upsert_capability(base, capability_key="REVIEW-EXPIRED-CERT", title="行业服务认证证书", capability_type="qualification_certificate", evidence_text="证书覆盖政务云产品交付与服务。", source_url="https://example.com/review/cert", source_locator="行业认证证书第1页", verification_status="verified", applicable_entity="示例科技有限公司", regions=["北京"], authorization_scope="全国政务项目", valid_until="2027-06-30", source_file_name="行业服务认证.pdf", actor="demo:证据管理员")
    analyze_capability_matches(base, NOTICE_ID)
    upsert_capability(base, capability_key="REVIEW-EXPIRED-CERT", title="行业服务认证证书", capability_type="qualification_certificate", evidence_text="证书覆盖政务云产品交付与服务。", source_url="https://example.com/review/cert", source_locator="行业认证证书第1页", verification_status="verified", applicable_entity="示例科技有限公司", regions=["北京"], authorization_scope="全国政务项目", valid_until="2026-08-31", source_file_name="行业服务认证.pdf", actor="demo:证据管理员")
    refresh_capability_validity(base)
    sync_requirement_review_cases(base, NOTICE_ID)
    cases = list_requirement_review_cases(base, NOTICE_ID)
    primary = next(item for item in cases if item.requirement_id == requirement.id and item.reason == "requirement_marked_for_review")
    if primary.status == "resolved":
        with connection(base) as conn:
            conn.execute("UPDATE requirement_review_cases SET status = 'pending', decision = NULL, decision_note = NULL, decided_by = NULL, decided_at = NULL WHERE id = ?", (primary.id,))
    settings = replace(base, model_mode=ModelMode.LOCAL, model_enhancement_enabled=True, ollama_base_url="http://127.0.0.1:11434", ollama_model="opponent-demo")
    first = run_review_agents(settings, NOTICE_ID, gateway=DemoGateway(fail_roles={"commercial"}), review_ids=[primary.id], actor="demo:会审主持人")
    retry = retry_review_agent(settings, NOTICE_ID, primary.id, "commercial", gateway=DemoGateway(), actor="demo:恢复操作员")
    opinions_before = list_review_opinions(settings, NOTICE_ID)
    decision = resolve_requirement_review_case(settings, NOTICE_ID, primary.id, decision="returned", actor="demo:总负责人", note="技术参数满足，但认证证书已过期；退回补证后再进入终审。")
    rerun = run_review_agents(settings, NOTICE_ID, gateway=DemoGateway(technical_decision="reject"), review_ids=[primary.id], actor="demo:二次运行")
    opinions_after = list_review_opinions(settings, NOTICE_ID)
    change_case = next((item for item in list_requirement_review_cases(base, NOTICE_ID) if item.reason.startswith("notice_change_impact") and item.status == "pending"), None)
    affected = run_review_agents(settings, NOTICE_ID, gateway=DemoGateway(), review_ids=[change_case.id], actor="demo:公告变更复核") if change_case else {"review_run_ids": []}
    suggestions = review_agent_suggestions(settings, NOTICE_ID)
    runs = list_review_agent_runs(settings, NOTICE_ID)
    twin = build_digital_twin(base, NOTICE_ID)
    primary_suggestion = next(item for item in suggestions if item["review_id"] == primary.id)
    result = {
        "notice_id": NOTICE_ID,
        "title": "政务云投标专业对手盘",
        "primary_review_id": primary.id,
        "notice_revision_id": "review-opponent-rev-1",
        "first_run": {"opinion_count": first["opinion_count"], "failed_count": first["failed_count"]},
        "retry": {"opinion_count": retry["opinion_count"], "failed_count": retry["failed_count"]},
        "final_opinion_count": len([item for item in opinions_after if item.review_id == primary.id]),
        "human_decision": decision.decision,
        "human_decision_note": decision.decision_note,
        "rerun_after_decision_scanned": rerun["scanned_case_count"],
        "affected_role_run_ids": affected.get("review_run_ids", []),
        "run_count": len(runs),
        "digital_twin_disagreements": twin["counts"]["review_agent_disagreements"] if twin else 0,
        "proof": {
            "real_disagreement": primary_suggestion["disagreement"],
            "conclusion_conflict": "conclusion_conflict" in primary_suggestion["conflict_types"],
            "evidence_linked": all(item.evidence_ids and item.notice_revision_id for item in opinions_after if item.review_id == primary.id),
            "failure_preserved_other_results": first["failed_count"] == 1 and len([item for item in opinions_before if item.review_id == primary.id]) == 5,
            "single_role_retry_succeeded": retry["failed_count"] == 0,
            "human_decision_preserved": rerun["scanned_case_count"] == 0 and decision.decision == "returned",
            "affected_roles_only": any(run["requested_roles"] == ["technical", "evidence_audit"] for run in runs),
        },
    }
    output = ROOT / "docs" / "demo" / "review_opponent_live_demo_20260927.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(seed(), ensure_ascii=False, indent=2))
