from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
import json
import re
from statistics import median
from typing import Any

from tendertrace.adapters.ccgp import Attachment, Notice
from tendertrace.config import Settings
from tendertrace.db import connection
from tendertrace.intent.topic import extract_topic
from tendertrace.retrieval import parse_date


LEVELS = (
    (80, "A", "优先跟进"),
    (65, "B", "重点观察"),
    (45, "C", "信息补全"),
    (0, "D", "低优先级"),
)


@dataclass(frozen=True)
class OpportunityResult:
    notices: list[Notice]
    stats: dict[str, object]


def enrich_opportunity_intelligence(
    notices: list[Notice],
    *,
    as_of: datetime | date | None = None,
) -> OpportunityResult:
    enriched = [_with_intelligence(notice, as_of=as_of) for notice in notices]
    market = build_market_context(enriched, as_of=as_of)
    levels = {level: 0 for _threshold, level, _label in LEVELS}
    scores: list[int] = []
    for notice in enriched:
        intelligence = notice.fields.get("opportunity_intelligence")
        if not isinstance(intelligence, dict):
            continue
        intelligence["market_context"] = {
            "benchmark": market_benchmark_for_notice(notice, market),
            "signals": list(market.get("signals") or [])[:3],
        }
        level = str(intelligence.get("level") or "D")
        levels[level] = levels.get(level, 0) + 1
        scores.append(int(intelligence.get("score") or 0))
    return OpportunityResult(
        notices=enriched,
        stats={
            "opportunity_analyzed": len(enriched),
            "opportunity_levels": levels,
            "opportunity_average_score": round(sum(scores) / len(scores), 1) if scores else 0.0,
            "opportunity_high_priority": levels.get("A", 0),
            "opportunity_market": market,
        },
    )


def analyze_opportunity_payload(
    payload: dict[str, Any],
    *,
    as_of: datetime | date | None = None,
) -> dict[str, object]:
    return _analyze(_normalized_payload(payload), as_of=as_of)


def _normalized_payload(payload: dict[str, Any]) -> dict[str, Any]:
    structured = _mapping(payload.get("structured_fields"))
    evidence = _mapping(payload.get("evidence"))
    fields = _mapping(payload.get("fields"))
    nested_structured = _mapping(fields.get("structured_fields"))
    nested_evidence = _mapping(fields.get("evidence"))
    structured = {**nested_structured, **structured}
    evidence = {**nested_evidence, **evidence}
    return {
        "title": _first(payload, "title", "标题"),
        "publish_time": _first(payload, "publish_time", "发布时间"),
        "region": _first(payload, "region", "地区"),
        "purchaser": _first(payload, "purchaser", "采购人"),
        "source_url": _first(payload, "source_url", "来源链接"),
        "source_site": _first(payload, "source_site", "来源"),
        "content_text": _first(payload, "content_text", "正文", "核心内容"),
        "core_content": _first(payload, "core_content", "核心内容"),
        "attachments": payload.get("attachments") or payload.get("附件链接") or [],
        "structured_fields": {
            **structured,
            "project_no": _first(structured, "project_no") or _first(payload, "项目编号"),
            "budget": _first(structured, "budget") or _first(payload, "预算", "预算金额"),
            "bid_deadline": _first(structured, "bid_deadline")
            or _first(payload, "投标截止", "截止时间"),
            "purchaser": _first(structured, "purchaser") or _first(payload, "采购人"),
        },
        "evidence": evidence,
        "duplicate_count": payload.get("duplicate_count")
        or fields.get("duplicate_count")
        or payload.get("关联来源数")
        or 1,
    }


def analyze_opportunity_with_market_context(
    settings: Settings,
    payload: dict[str, Any],
    *,
    as_of: datetime | date | None = None,
) -> dict[str, object]:
    intelligence = analyze_opportunity_payload(payload, as_of=as_of)
    notices = [notice for _notice_id, notice in _recent_notices(settings, limit=500)]
    market = build_market_context(notices, as_of=as_of)
    normalized = _normalized_payload(payload)
    intelligence["market_context"] = {
        "benchmark": _market_benchmark(normalized, market),
        "signals": list(market.get("signals") or [])[:3],
        "sample_scope": {
            "notice_count": market.get("notice_count", 0),
            "budget_sample_count": market.get("budget_sample_count", 0),
        },
    }
    return intelligence


def intelligence_for_notice(notice: Notice) -> dict[str, object]:
    # Freshness and deadline readiness must reflect the current day, not the ingest day.
    return _analyze(_notice_payload(notice), as_of=None)


def build_market_context(
    notices: list[Notice],
    *,
    as_of: datetime | date | None = None,
) -> dict[str, object]:
    entries = [_market_entry(_notice_payload(notice), as_of=as_of) for notice in notices]
    budgets = [float(item["budget_cny"]) for item in entries if item["budget_cny"]]
    categories: dict[str, list[float]] = {}
    for item in entries:
        category = str(item["category"] or "")
        budget = item["budget_cny"]
        if category and budget:
            categories.setdefault(category, []).append(float(budget))
    category_benchmarks = {
        category: _budget_stats(values) for category, values in categories.items()
    }
    purchasers = Counter(str(item["purchaser"]) for item in entries if item["purchaser"])
    regions = Counter(str(item["region"]) for item in entries if item["region"])
    stages = Counter(str(item["stage"]) for item in entries if item["stage"])
    high_credibility = sum(1 for item in entries if int(item["credibility"] or 0) >= 80)
    budget_coverage = round(len(budgets) / len(entries) * 100, 1) if entries else 0.0
    signals: list[str] = []
    if budgets:
        overall = _budget_stats(budgets)
        signals.append(
            f"价格样本：{len(budgets)} 条有效预算，中位数 {_format_cny(overall['median_cny'])}，"
            f"覆盖率 {budget_coverage}%"
        )
    else:
        overall = _budget_stats([])
        signals.append("价格样本不足：当前公告未形成可计算的预算基准")
    if purchasers:
        name, count = purchasers.most_common(1)[0]
        signals.append(f"客户集中度：{name} 出现 {count} 次，建议核查连续采购计划")
    if stages:
        stage, count = stages.most_common(1)[0]
        signals.append(f"采购阶段：{stage} 占 {count}/{len(entries)} 条")
    if entries and budget_coverage < 30:
        signals.append("数据提示：预算覆盖率低于 30%，价格判断仅作线索参考")
    return {
        "notice_count": len(entries),
        "budget_sample_count": len(budgets),
        "budget_coverage": budget_coverage,
        "budget": overall,
        "category_benchmarks": category_benchmarks,
        "top_purchasers": _counter_items(purchasers),
        "top_regions": _counter_items(regions),
        "stage_distribution": _counter_items(stages, limit=8),
        "high_credibility_count": high_credibility,
        "signals": signals[:4],
    }


def market_benchmark_for_notice(
    notice: Notice,
    market: dict[str, object],
) -> dict[str, object]:
    return _market_benchmark(_notice_payload(notice), market)


def list_opportunities(
    settings: Settings,
    *,
    limit: int = 50,
    level: str | None = None,
) -> dict[str, object]:
    limit = max(1, min(int(limit), 200))
    market_rows = _recent_notices(settings, limit=500)
    rows = market_rows[: min(limit * 4, 500)]
    market_notices = [notice for _notice_id, notice in market_rows]
    market = build_market_context(market_notices)
    items: list[dict[str, object]] = []
    for notice_id, notice in rows:
        intelligence = intelligence_for_notice(notice)
        if level and str(intelligence.get("level") or "").upper() != level.upper():
            continue
        intelligence["market_context"] = {
            "benchmark": _market_benchmark(_notice_payload(notice), market),
            "signals": list(market.get("signals") or [])[:3],
        }
        structured = _mapping(notice.fields.get("structured_fields"))
        items.append(
            {
                "notice_id": notice_id,
                "title": notice.title,
                "publish_time": notice.publish_time,
                "region": notice.region,
                "purchaser": notice.purchaser,
                "source_site": notice.source_site,
                "source_url": notice.source_url,
                "budget": str(structured.get("budget") or ""),
                "bid_deadline": str(structured.get("bid_deadline") or ""),
                "intelligence": intelligence,
            }
        )
        if len(items) >= limit:
            break
    level_counts = {name: 0 for _threshold, name, _label in LEVELS}
    for item in items:
        intelligence = _mapping(item.get("intelligence"))
        name = str(intelligence.get("level") or "D")
        level_counts[name] = level_counts.get(name, 0) + 1
    return {
        "items": items,
        "summary": {
            "total": len(items),
            "levels": level_counts,
            "average_score": round(
                sum(int(_mapping(item.get("intelligence")).get("score") or 0) for item in items)
                / len(items),
                1,
            )
            if items
            else 0.0,
            "market": market,
        },
    }


def get_opportunity(settings: Settings, notice_id: str) -> dict[str, object] | None:
    with connection(settings) as conn:
        row = conn.execute(
            """
            SELECT id, source_site, source_url, title, publish_time, region, purchaser,
                   content_text, core_content, attachments_json, fields_json, created_at
            FROM notices
            WHERE id = ?
            """,
            (notice_id,),
        ).fetchone()
    if row is None:
        return None
    notice = _notice_from_row(row)
    structured = _mapping(notice.fields.get("structured_fields"))
    intelligence = intelligence_for_notice(notice)
    market = build_market_context(
        [item for _notice_id, item in _recent_notices(settings, limit=500)]
    )
    intelligence["market_context"] = {
        "benchmark": _market_benchmark(_notice_payload(notice), market),
        "signals": list(market.get("signals") or [])[:3],
    }
    return {
        "notice_id": str(row["id"]),
        "title": notice.title,
        "publish_time": notice.publish_time,
        "region": notice.region,
        "purchaser": notice.purchaser,
        "source_site": notice.source_site,
        "source_url": notice.source_url,
        "budget": str(structured.get("budget") or ""),
        "bid_deadline": str(structured.get("bid_deadline") or ""),
        "intelligence": intelligence,
    }


def parse_budget_cny(value: object) -> float | None:
    text = _string_value(value).replace(",", "").replace("，", "")
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(亿元|万元|元|million)?", text, re.IGNORECASE)
    if not match:
        return None
    amount = float(match.group(1))
    unit = (match.group(2) or "元").lower()
    multiplier = 100_000_000 if unit == "亿元" else 10_000 if unit == "万元" else 1_000_000 if unit == "million" else 1
    return amount * multiplier if amount > 0 else None


def _recent_notices(settings: Settings, *, limit: int) -> list[tuple[str, Notice]]:
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT id, source_site, source_url, title, publish_time, region, purchaser,
                   content_text, core_content, attachments_json, fields_json, created_at
            FROM notices
            ORDER BY publish_time DESC, created_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 500)),),
        ).fetchall()
    return [(str(row["id"]), _notice_from_row(row)) for row in rows]


def _market_entry(payload: dict[str, Any], *, as_of: datetime | date | None) -> dict[str, object]:
    structured = _mapping(payload.get("structured_fields"))
    evidence = _mapping(payload.get("evidence"))
    credibility, _basis = _credibility_score(payload, evidence)
    return {
        "category": _primary_category(payload),
        "budget_cny": parse_budget_cny(structured.get("budget")),
        "purchaser": str(structured.get("purchaser") or payload.get("purchaser") or "").strip(),
        "region": str(payload.get("region") or "").strip(),
        "stage": _stage(structured, _as_date(as_of)),
        "credibility": credibility,
    }


def _primary_category(payload: dict[str, Any]) -> str:
    text = " ".join(
        str(payload.get(key) or "") for key in ("title", "core_content", "content_text")
    )
    topic = extract_topic(text)
    if topic.get("origin") != "category_dict":
        return ""
    core = topic.get("core")
    return str(core[0]) if isinstance(core, list) and core else ""


def _budget_stats(values: list[float]) -> dict[str, object]:
    if not values:
        return {
            "sample_count": 0,
            "median_cny": None,
            "min_cny": None,
            "max_cny": None,
        }
    return {
        "sample_count": len(values),
        "median_cny": round(float(median(values)), 2),
        "min_cny": round(min(values), 2),
        "max_cny": round(max(values), 2),
    }


def _market_benchmark(payload: dict[str, Any], market: dict[str, object]) -> dict[str, object]:
    category = _primary_category(payload)
    structured = _mapping(payload.get("structured_fields"))
    amount = parse_budget_cny(structured.get("budget"))
    category_map = _mapping(market.get("category_benchmarks"))
    stats = _mapping(category_map.get(category)) if category else {}
    sample_count = int(stats.get("sample_count") or 0)
    median_cny = stats.get("median_cny")
    if not category:
        return {
            "status": "insufficient",
            "category": "",
            "sample_count": 0,
            "message": "尚未识别可比采购品类，暂不生成价格判断",
        }
    if sample_count < 2 or not median_cny:
        return {
            "status": "insufficient",
            "category": category,
            "sample_count": sample_count,
            "amount_cny": amount,
            "message": f"{category} 有效预算样本少于 2 条，暂不生成价格位置判断",
        }
    median_value = float(median_cny)
    position = "unknown"
    position_label = "当前公告缺少可换算预算"
    if amount:
        ratio = amount / median_value
        if ratio < 0.8:
            position, position_label = "below", "低于同品类历史中位数"
        elif ratio > 1.2:
            position, position_label = "above", "高于同品类历史中位数"
        else:
            position, position_label = "near", "接近同品类历史中位数"
    return {
        "status": "ready",
        "category": category,
        "sample_count": sample_count,
        "amount_cny": amount,
        "median_cny": median_value,
        "min_cny": stats.get("min_cny"),
        "max_cny": stats.get("max_cny"),
        "position": position,
        "message": (
            f"{category} 可比样本 {sample_count} 条，中位数 {_format_cny(median_value)}；"
            f"{position_label}"
        ),
    }


def _counter_items(counter: Counter[str], *, limit: int = 5) -> list[dict[str, object]]:
    return [{"name": name, "count": count} for name, count in counter.most_common(limit)]


def _format_cny(value: object) -> str:
    try:
        amount = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "待确认"
    if amount >= 100_000_000:
        return f"{amount / 100_000_000:.2f}".rstrip("0").rstrip(".") + " 亿元"
    if amount >= 10_000:
        return f"{amount / 10_000:.1f}".rstrip("0").rstrip(".") + " 万元"
    return f"{amount:.0f} 元"


def _with_intelligence(notice: Notice, *, as_of: datetime | date | None) -> Notice:
    intelligence = _analyze(_notice_payload(notice), as_of=as_of)
    return Notice(
        id=notice.id,
        source_site=notice.source_site,
        title=notice.title,
        publish_time=notice.publish_time,
        region=notice.region,
        purchaser=notice.purchaser,
        source_url=notice.source_url,
        content_text=notice.content_text,
        core_content=notice.core_content,
        attachments=notice.attachments,
        fields={**notice.fields, "opportunity_intelligence": intelligence},
    )


def _notice_payload(notice: Notice) -> dict[str, Any]:
    fields = notice.fields
    return {
        "title": notice.title,
        "publish_time": notice.publish_time,
        "region": notice.region,
        "purchaser": notice.purchaser,
        "source_url": notice.source_url,
        "source_site": notice.source_site,
        "content_text": notice.content_text,
        "core_content": notice.core_content,
        "attachments": [item.url for item in notice.attachments],
        "structured_fields": _mapping(fields.get("structured_fields")),
        "evidence": _mapping(fields.get("evidence")),
        "duplicate_count": fields.get("duplicate_count") or 1,
    }


def _notice_from_row(row: Any) -> Notice:
    attachments_raw = _json_value(row["attachments_json"], [])
    fields = _json_value(row["fields_json"], {})
    attachments = [
        Attachment(name=str(item.get("name") or ""), url=str(item.get("url") or ""))
        for item in attachments_raw
        if isinstance(item, dict)
    ]
    return Notice(
        id=str(row["id"]),
        source_site=str(row["source_site"] or ""),
        title=str(row["title"] or ""),
        publish_time=str(row["publish_time"] or ""),
        region=str(row["region"] or ""),
        purchaser=str(row["purchaser"] or ""),
        source_url=str(row["source_url"] or ""),
        content_text=str(row["content_text"] or ""),
        core_content=str(row["core_content"] or ""),
        attachments=attachments,
        fields=fields if isinstance(fields, dict) else {},
    )


def _analyze(payload: dict[str, Any], *, as_of: datetime | date | None) -> dict[str, object]:
    structured = _mapping(payload.get("structured_fields"))
    evidence = _mapping(payload.get("evidence"))
    reference_date = _as_date(as_of)
    publish_date = parse_date(str(payload.get("publish_time") or ""))
    freshness, age_days = _freshness_score(publish_date, reference_date)
    completeness, missing_fields = _completeness_score(payload, structured, evidence)
    credibility, credibility_basis = _credibility_score(payload, evidence)
    readiness, readiness_basis = _readiness_score(structured, reference_date)
    score = round(
        freshness * 0.20 + completeness * 0.25 + credibility * 0.30 + readiness * 0.25
    )
    level, level_label = _level(score)
    risks = _risk_signals(
        payload,
        structured,
        evidence,
        age_days=age_days,
        missing_fields=missing_fields,
    )
    actions = _actions(level, structured, missing_fields, risks)
    target = _target(level, structured, payload)
    return {
        "score": score,
        "level": level,
        "level_label": level_label,
        "stage": _stage(structured, reference_date),
        "scores": {
            "freshness": freshness,
            "completeness": completeness,
            "credibility": credibility,
            "readiness": readiness,
        },
        "age_days": age_days,
        "missing_fields": missing_fields,
        "risks": risks,
        "recommended_actions": actions,
        "project_target": target,
        "strategy": _strategy(level, payload, structured, credibility_basis),
        "market_signals": _market_signals(payload, structured),
        "basis": {
            "credibility": credibility_basis,
            "readiness": readiness_basis,
            "evidence_hash": str(evidence.get("snapshot_sha256") or ""),
            "source_url": str(payload.get("source_url") or ""),
        },
        "evaluated_at": reference_date.isoformat(),
        "engine": "tendertrace_opportunity_rules_v2",
    }


def _freshness_score(published: date | None, reference: date) -> tuple[int, int | None]:
    if published is None:
        return 20, None
    age = (reference - published).days
    if age < 0:
        return 55, age
    for maximum, score in ((3, 100), (7, 90), (14, 78), (30, 62), (90, 38)):
        if age <= maximum:
            return score, age
    return 15, age


def _completeness_score(
    payload: dict[str, Any],
    structured: dict[str, Any],
    evidence: dict[str, Any],
) -> tuple[int, list[str]]:
    checks = (
        ("标题", payload.get("title"), 10),
        ("发布时间", payload.get("publish_time"), 10),
        ("地区", payload.get("region"), 8),
        ("采购人", payload.get("purchaser"), 8),
        ("来源链接", payload.get("source_url"), 8),
        ("正文", payload.get("content_text") or payload.get("core_content"), 12),
        ("项目编号", structured.get("project_no"), 10),
        ("预算", structured.get("budget"), 10),
        ("投标截止", structured.get("bid_deadline"), 10),
        ("附件", payload.get("attachments"), 6),
        ("证据摘录", evidence.get("excerpt"), 8),
    )
    score = sum(weight for _label, value, weight in checks if _present(value))
    missing = [label for label, value, _weight in checks if not _present(value)]
    return score, missing


def _credibility_score(
    payload: dict[str, Any], evidence: dict[str, Any]
) -> tuple[int, list[str]]:
    raw_quality = evidence.get("quality_score")
    try:
        quality = max(0.0, min(float(raw_quality), 1.0))
    except (TypeError, ValueError):
        quality = 0.35 if evidence else 0.15
    url = str(payload.get("source_url") or "")
    source_score = 20 if url.startswith("https://") else 12 if url.startswith("http://") else 0
    duplicate_count = _as_int(payload.get("duplicate_count"), default=1)
    corroboration = 15 if duplicate_count >= 3 else 10 if duplicate_count == 2 else 4
    score = round(quality * 65 + source_score + corroboration)
    basis = [f"证据质量 {quality:.0%}", f"来源协议 {source_score}/20", f"交叉来源 {duplicate_count} 个"]
    return min(score, 100), basis


def _readiness_score(structured: dict[str, Any], reference: date) -> tuple[int, list[str]]:
    score = 20
    basis = ["已识别为公开采购线索"]
    for label, key, weight in (
        ("项目编号", "project_no", 18),
        ("预算", "budget", 22),
        ("采购人", "purchaser", 15),
        ("投标截止", "bid_deadline", 25),
    ):
        if _present(structured.get(key)):
            score += weight
            basis.append(f"已识别{label}")
    deadline = parse_date(str(structured.get("bid_deadline") or ""))
    if deadline and deadline < reference:
        score = min(score, 35)
        basis.append("投标截止日期可能已过")
    return min(score, 100), basis


def _risk_signals(
    payload: dict[str, Any],
    structured: dict[str, Any],
    evidence: dict[str, Any],
    *,
    age_days: int | None,
    missing_fields: list[str],
) -> list[str]:
    risks: list[str] = []
    if str(evidence.get("status") or "") not in {"passed", "通过"}:
        risks.append("原文证据尚未全部通过事实校验")
    if missing_fields:
        risks.append(f"关键信息待补全：{'、'.join(missing_fields[:4])}")
    if age_days is None:
        risks.append("发布时间无法解析，需人工确认时效")
    elif age_days > 30:
        risks.append(f"公告距今 {age_days} 天，机会时效偏低")
    if _as_int(payload.get("duplicate_count"), default=1) == 1:
        risks.append("暂未发现跨来源佐证")
    if not _present(structured.get("bid_deadline")):
        risks.append("投标截止时间缺失，无法判断剩余响应窗口")
    return risks[:4]


def _actions(
    level: str,
    structured: dict[str, Any],
    missing_fields: list[str],
    risks: list[str],
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    if level in {"A", "B"}:
        actions.append(
            {
                "role": "机会点负责人",
                "action": "确认客户关系、预算口径和投标窗口，建立下一步动作与责任人。",
            }
        )
        actions.append(
            {
                "role": "机会点团队",
                "action": "评估技术匹配度、交付边界、竞争态势和报价策略。",
            }
        )
    if missing_fields:
        actions.append(
            {
                "role": "情报支持",
                "action": f"回看原文及附件，优先补齐{'、'.join(missing_fields[:3])}。",
            }
        )
    if risks:
        actions.append(
            {
                "role": "机会点负责人",
                "action": "在定级前逐项关闭风险提示，并保留来源链接和证据摘录。",
            }
        )
    actions.append(
        {
            "role": "合作伙伴",
            "action": "根据资质、区域覆盖和交付能力确认参与方式及联合方案。",
        }
    )
    return actions[:4]


def _target(level: str, structured: dict[str, Any], payload: dict[str, Any]) -> str:
    purchaser = str(structured.get("purchaser") or payload.get("purchaser") or "目标客户")
    budget = str(structured.get("budget") or "预算待确认")
    if level == "A":
        return f"在投标窗口内完成 {purchaser} 的需求确认与项目立项，预算参考：{budget}。"
    if level == "B":
        return f"补齐关键事实后决定是否进入正式机会池，客户：{purchaser}。"
    return "先完成信息核验与适配性判断，再决定是否投入销售资源。"


def _strategy(
    level: str,
    payload: dict[str, Any],
    structured: dict[str, Any],
    credibility_basis: list[str],
) -> str:
    source = str(payload.get("source_site") or "公开来源")
    budget = str(structured.get("budget") or "预算待补充")
    if level == "A":
        return f"以客户需求和投标时限为主线，结合 {source} 原文及附件形成技术、商务双线策略；{budget}。"
    if level == "B":
        return f"先核实预算、采购人和截止时间，再依据{'；'.join(credibility_basis[:2])}完成项目定级。"
    return "控制前期投入，优先补齐证据与关键字段；满足进入标准后再升级跟进。"


def _market_signals(payload: dict[str, Any], structured: dict[str, Any]) -> list[str]:
    signals: list[str] = []
    budget = str(structured.get("budget") or "").strip()
    if budget:
        signals.append(f"价格基准：公告预算/限价为 {budget}")
    duplicate_count = _as_int(payload.get("duplicate_count"), default=1)
    if duplicate_count > 1:
        signals.append(f"传播热度：发现 {duplicate_count} 个关联来源，可用于交叉核验")
    text = " ".join(
        str(payload.get(key) or "") for key in ("title", "content_text", "core_content")
    )
    if re.search(r"中标|成交|结果公告", text):
        signals.append("竞争动态：已进入结果/成交阶段，可用于供应商与价格复盘")
    else:
        signals.append("采购阶段：处于公告或需求释放阶段，适合开展前置研判")
    return signals[:3]


def _stage(structured: dict[str, Any], reference: date) -> str:
    deadline = parse_date(str(structured.get("bid_deadline") or ""))
    if deadline is None:
        return "线索识别"
    if deadline < reference:
        return "结果跟踪"
    if (deadline - reference).days <= 7:
        return "投标冲刺"
    return "机会确认"


def _level(score: int) -> tuple[str, str]:
    for threshold, level, label in LEVELS:
        if score >= threshold:
            return level, label
    return "D", "低优先级"


def _as_date(value: datetime | date | None) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.today()


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first(mapping: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = mapping.get(key)
        if _present(value):
            return _string_value(value)
    return ""


def _string_value(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return " ".join(_string_value(item) for item in value).strip()
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or value.get("link") or "").strip()
    return str(value or "").strip()


def _present(value: object) -> bool:
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return bool(str(value or "").strip())


def _as_int(value: object, *, default: int) -> int:
    try:
        return max(int(value), 0)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _json_value(value: object, fallback: Any) -> Any:
    try:
        return json.loads(str(value or ""))
    except json.JSONDecodeError:
        return fallback
