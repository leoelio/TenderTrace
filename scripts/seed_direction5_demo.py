from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tendertrace.capability_matching import (
    analyze_capability_matches,
    decide_capability_match,
    list_requirement_capability_matches,
    refresh_capability_validity,
    upsert_capability,
)
from tendertrace.capability_passport import build_capability_passport, create_gap_action
from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.digital_twin import build_digital_twin
from tendertrace.opportunity_requirements import upsert_requirement


ROOT = Path(__file__).resolve().parents[1]
NOTICE_ID = "demo-direction5-capability-passport"


def seed() -> dict[str, object]:
    settings = Settings.load(ROOT)
    init_db(settings)
    fields = {"structured_fields": {"project_no": "TT-D5-20260927", "budget": 2600000, "bid_deadline": "2026-10-20 17:00"}, "demo_scope": "企业能力护照脱敏验收样本"}
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(id, source_site, source_url, canonical_url, title, purchaser,
                publish_time, region, content_text, core_content, fields_json, updated_at, last_seen_at)
            VALUES (?, 'demo', ?, ?, ?, ?, '2026-09-27', '北京', ?, ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(id) DO UPDATE SET title = excluded.title, purchaser = excluded.purchaser,
                region = excluded.region, content_text = excluded.content_text,
                core_content = excluded.core_content, fields_json = excluded.fields_json,
                updated_at = datetime('now'), last_seen_at = datetime('now')
            """,
            (NOTICE_ID, "https://example.com/direction5", "https://example.com/direction5", "政务云企业能力护照与逐项匹配矩阵", "某政务单位（脱敏）", "营业执照、行业认证、TT-X100服务器、同类案例与原厂授权要求。", "能力护照验收演示。", json.dumps(fields, ensure_ascii=False)),
        )
    requirements = {
        "license": _requirement(settings, "QUAL-D5-01", "qualification", "投标主体营业执照", "投标主体须提供有效营业执照。", "第12页 资格条件"),
        "cert": _requirement(settings, "QUAL-D5-02", "qualification", "行业服务认证", "投标人须具备有效的行业服务认证。", "第13页 资格条件"),
        "technical": _requirement(settings, "TECH-D5-01", "technical", "核心服务器指定型号", "投标产品型号：TT-X100，配置参数不得低于技术规格。", "第28页 技术参数"),
        "case": _requirement(settings, "SCORE-D5-01", "scoring", "同类项目案例", "提供近三年政府行业同类项目案例并附中标证明。", "第46页 评分表"),
        "partner": _requirement(settings, "COMM-D5-01", "commercial", "原厂项目授权", "须提供原厂针对本项目及北京地区的授权函。", "第18页 商务要求"),
    }
    capabilities = {
        "license": _capability(settings, "D5-LICENSE", "示例科技营业执照", "qualification_certificate", "统一社会信用代码及经营范围已核验。", entity="示例科技有限公司", valid_until="2032-12-31", source="营业执照.pdf"),
        "cert": _capability(settings, "D5-CERT", "行业服务认证证书", "qualification_certificate", "证书覆盖政务信息化服务。", entity="示例科技有限公司", valid_until="2027-06-30", source="行业服务认证.pdf"),
        "product": _capability(settings, "D5-PRODUCT-X100", "TT-X100 产品规格", "product_parameter", "TT-X100 CPU、内存、存储与安全参数清单。", entity="示例科技有限公司", model="TT-X100", valid_until="2028-12-31", source="TT-X100规格书.pdf"),
        "near_product": _capability(settings, "D5-PRODUCT-X90", "TT-X90 产品规格", "product_parameter", "TT-X90 为上一代相近型号，不可替代本项目型号。", entity="示例科技有限公司", model="TT-X90", valid_until="2028-12-31", source="TT-X90规格书.pdf"),
        "personnel": _capability(settings, "D5-PERSON", "高级项目经理能力", "personnel_skill", "项目经理证书及政务项目履历。", entity="示例科技有限公司", valid_until="2028-08-31", source="人员证书包.pdf"),
        "delivery": _capability(settings, "D5-DELIVERY", "7×24交付服务", "delivery_service", "北京地区4小时响应及备件服务。", entity="示例科技有限公司", valid_until="2028-12-31", source="服务SLA.pdf"),
        "case": _capability(settings, "D5-CASE", "某市政务云服务器项目（脱敏）", "project_case", "同型号服务器项目已完成验收并保留中标通知书。", entity="示例科技有限公司", model="TT-X100", valid_until="2029-12-31", source="脱敏案例证明.pdf"),
        "partner": _capability(settings, "D5-PARTNER", "原厂合作伙伴证明", "partner_authorization", "已建立合作伙伴关系，但尚缺本项目专项授权范围。", entity="示例科技有限公司", valid_until="2027-12-31", source="伙伴证明.pdf", authorization_scope=""),
    }
    analyze_capability_matches(settings, NOTICE_ID)
    matches = list_requirement_capability_matches(settings, NOTICE_ID)
    for requirement_name, capability_name in (("license", "license"), ("cert", "cert"), ("technical", "product"), ("case", "case")):
        match = next(item for item in matches if item.requirement_id == requirements[requirement_name].id and item.capability_id == capabilities[capability_name].id)
        decide_capability_match(settings, NOTICE_ID, match.id, verdict="supported", actor="demo:评审负责人", note="已核对要求原文、企业原件、适用主体和有效期。", accept=True)
    partner_match = next(item for item in matches if item.requirement_id == requirements["partner"].id and item.capability_id == capabilities["partner"].id)
    passport_before_action = build_capability_passport(settings, NOTICE_ID)
    existing_action = next((item for item in passport_before_action["gap_actions"] if item["match_id"] == partner_match.id and item["status"] == "open"), None)
    if existing_action is None:
        create_gap_action(settings, NOTICE_ID, partner_match.id, action_type="partner_support", actor="demo:项目经理", due_at="2026-10-05T17:00", title="取得TT-X100本项目及北京地区原厂授权函")
    _capability(settings, "D5-CERT", "行业服务认证证书", "qualification_certificate", "证书覆盖政务信息化服务。", entity="示例科技有限公司", valid_until="2026-08-31", source="行业服务认证.pdf")
    refresh_capability_validity(settings)
    _seed_similar_cases(settings, capabilities["case"].id)
    passport = build_capability_passport(settings, NOTICE_ID)
    twin = build_digital_twin(settings, NOTICE_ID)
    result = {
        "notice_id": NOTICE_ID,
        "title": "政务云企业能力护照与逐项匹配矩阵",
        "passport_count": passport["summary"]["passport_count"],
        "verified_passport_count": passport["summary"]["verified_passport_count"],
        "supported_count": passport["summary"]["supported_count"],
        "conflict_count": passport["summary"]["conflict_count"],
        "recheck_count": passport["summary"]["recheck_count"],
        "alert_count": passport["summary"]["alert_count"],
        "open_gap_action_count": passport["summary"]["open_gap_action_count"],
        "similar_case_count": len(passport["similar_cases"]),
        "digital_twin_passport_count": twin["counts"]["capability_passports"] if twin else 0,
        "proof": {
            "exact_model_supported": any(
                item["requirement"]["requirement_key"] == "TECH-D5-01"
                and any(match["capability_id"] == capabilities["product"].id and match["verdict"] == "supported" for match in item["matches"])
                for item in passport["matrix"]
            ),
            "near_model_conflict": any(alert["code"] == "model_mismatch" for alert in passport["alerts"]),
            "expired_certificate_recheck": passport["summary"]["recheck_count"] >= 1,
            "gap_action_in_workplan": passport["summary"]["open_gap_action_count"] >= 1,
            "six_evidence_classes": sum(bool(group["items"]) for group in passport["passports"]) == 6,
        },
    }
    output = ROOT / "docs" / "demo" / "direction5_live_demo_20260927.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _requirement(settings: Settings, key: str, kind: str, title: str, evidence: str, locator: str):
    return upsert_requirement(settings, notice_id=NOTICE_ID, requirement_key=key, requirement_type=kind, title=title, evidence_text=evidence, source_url="https://example.com/direction5", source_locator=locator, mandatory=True, confidence=96, status="confirmed", extraction_mode="rules", actor="demo:需求负责人")


def _capability(settings: Settings, key: str, title: str, kind: str, evidence: str, *, entity: str, model: str = "", valid_until: str, source: str, authorization_scope: str = "全国政务项目"):
    return upsert_capability(settings, capability_key=key, title=title, capability_type=kind, evidence_text=evidence, source_url=f"https://example.com/evidence/{key.lower()}", source_locator=f"{source} 第1-3页", verification_status="verified", owner="企业能力管理员", valid_from="2025-01-01", valid_until=valid_until, applicable_entity=entity, product_model=model, regions=["北京", "全国"], authorization_scope=authorization_scope, source_file_name=source, industry="政府", sample_redacted=True, actor="demo:证据管理员")


def _seed_similar_cases(settings: Settings, capability_id: str) -> None:
    rows = [
        ("d5-history-1", "某市政务云扩容（脱敏）", "北京", 2450000, "TT-X100", "won", "2026-06-30"),
        ("d5-history-2", "某区数据中心更新（脱敏）", "北京", 3100000, "TT-X100", "won", "2026-03-15"),
        ("d5-history-3", "某事业单位算力平台（脱敏）", "天津", 2200000, "TT-X100", "lost", "2025-12-20"),
    ]
    with connection(settings) as conn:
        for notice_id, title, region, amount, model, result, occurred_at in rows:
            conn.execute("INSERT OR IGNORE INTO notices(id, source_site, source_url, canonical_url, title, region) VALUES (?, 'demo', ?, ?, ?, ?)", (notice_id, f"https://example.com/{notice_id}", f"https://example.com/{notice_id}", title, region))
            record_id = hashlib.sha256(f"{capability_id}|{notice_id}".encode()).hexdigest()[:24]
            conn.execute("""
                INSERT INTO capability_performance_records(id, capability_id, notice_id, project_title, industry, region, amount, product_model, result, evidence_url, occurred_at)
                VALUES (?, ?, ?, ?, '政府', ?, ?, ?, ?, ?, ?)
                ON CONFLICT(capability_id, notice_id) DO UPDATE SET result = excluded.result, amount = excluded.amount
            """, (record_id, capability_id, notice_id, title, region, amount, model, result, f"https://example.com/evidence/{notice_id}", occurred_at))


if __name__ == "__main__":
    print(json.dumps(seed(), ensure_ascii=False, indent=2))
