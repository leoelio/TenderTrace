from __future__ import annotations

from datetime import datetime
import json
from statistics import mean
from typing import Any
from zoneinfo import ZoneInfo

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.gold import evaluate_gold_recall
from tendertrace.intent import compile_intent
from tendertrace.vector import vector_coverage


def build_agent_evaluation_report(settings: Settings) -> dict[str, object]:
    init_db(settings)
    stats = _runtime_stats(settings)
    harness = _intent_harness()
    rag = _rag_metrics(stats)
    agent = _agent_metrics(stats)
    gold = evaluate_gold_recall(settings)
    vector = vector_coverage(settings)
    recall = _recall_metrics(stats, gold.to_dict(), vector)
    recall_score = (
        recall["strict_recall_at_10"]
        if recall["strict_recall_available"]
        else recall["recall_proxy"]
    )
    overall_score = round(
        0.25 * harness["field_accuracy"]
        + 0.25 * rag["grounding_pass_rate"]
        + 0.25 * agent["checkpoint_completion_rate"]
        + 0.25 * float(recall_score),
        3,
    )
    return {
        "status": "pass" if overall_score >= 0.75 else "warn",
        "overall_score": overall_score,
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).replace(microsecond=0).isoformat(),
        "summary": {
            "runs": stats["run_count"],
            "finished_runs": stats["finished_runs"],
            "failed_runs": stats["failed_runs"],
            "model_audits": stats["model_audits"],
            "evaluated_cases": harness["case_count"],
            "gold_cases": gold.case_count,
            "annotated_gold_cases": gold.annotated_case_count,
        },
        "rag": rag,
        "agent": agent,
        "harness": harness,
        "recall": recall,
        "gold": gold.to_dict(),
        "notes": [
            "有人工标注金标集时，严格召回率使用 Recall@K；金标为空时仅展示 recall_proxy。",
            "harness 字段准确率来自固定自然语言样例的 BidQL 编译检查。",
            "RAG 指标来自 evidence_validate、附件抽取和报告必要字段检查。",
        ],
    }


def _runtime_stats(settings: Settings) -> dict[str, Any]:
    with connection(settings) as conn:
        run_rows = conn.execute(
            """
            SELECT id, status, stats_json
            FROM runs
            WHERE status != 'deleted'
            ORDER BY started_at DESC
            LIMIT 200
            """
        ).fetchall()
        checkpoint_rows = conn.execute(
            """
            SELECT run_id, COUNT(DISTINCT node) AS node_count
            FROM run_checkpoints
            GROUP BY run_id
            """
        ).fetchall()
        audit_count = conn.execute("SELECT COUNT(*) AS count FROM model_audits").fetchone()["count"]
        notice_count = conn.execute("SELECT COUNT(*) AS count FROM notices").fetchone()["count"]
        try:
            fts_count = conn.execute("SELECT COUNT(*) AS count FROM notices_fts").fetchone()["count"]
        except Exception:
            fts_count = 0
    checkpoint_counts = {row["run_id"]: int(row["node_count"] or 0) for row in checkpoint_rows}
    runs: list[dict[str, Any]] = []
    for row in run_rows:
        try:
            run_stats = json.loads(row["stats_json"] or "{}")
        except json.JSONDecodeError:
            run_stats = {}
        runs.append(
            {
                "id": row["id"],
                "status": row["status"],
                "stats": run_stats,
                "checkpoint_nodes": checkpoint_counts.get(row["id"], 0),
            }
        )
    return {
        "runs": runs,
        "run_count": len(runs),
        "finished_runs": sum(1 for run in runs if run["status"] == "finished"),
        "failed_runs": sum(1 for run in runs if run["status"] == "failed"),
        "model_audits": int(audit_count or 0),
        "notice_count": int(notice_count or 0),
        "fts_count": int(fts_count or 0),
    }


def _rag_metrics(stats: dict[str, Any]) -> dict[str, object]:
    runs = stats["runs"]
    evidence_checked = sum(_int(run["stats"].get("evidence_checked")) for run in runs)
    evidence_passed = sum(_int(run["stats"].get("evidence_passed")) for run in runs)
    attachments_seen = sum(_int(run["stats"].get("attachments_seen")) for run in runs)
    attachments_extracted = sum(_int(run["stats"].get("attachments_extracted")) for run in runs)
    report_ready = sum(1 for run in runs if _int(run["stats"].get("notice_count")) > 0)
    finished = max(1, stats["finished_runs"])
    return {
        "grounding_pass_rate": _ratio(evidence_passed, evidence_checked),
        "evidence_checked": evidence_checked,
        "evidence_passed": evidence_passed,
        "attachment_extract_rate": _ratio(attachments_extracted, attachments_seen),
        "attachments_seen": attachments_seen,
        "attachments_extracted": attachments_extracted,
        "report_yield_rate": _ratio(report_ready, finished),
    }


def _agent_metrics(stats: dict[str, Any]) -> dict[str, object]:
    runs = stats["runs"]
    finished = [run for run in runs if run["status"] == "finished"]
    failed = stats["failed_runs"]
    trace_events = [_int(run["stats"].get("trace_events")) for run in runs if run["stats"]]
    complete_checkpoints = sum(1 for run in finished if run["checkpoint_nodes"] >= 4)
    return {
        "checkpoint_completion_rate": _ratio(complete_checkpoints, len(finished)),
        "complete_checkpoint_runs": complete_checkpoints,
        "avg_trace_events": round(mean(trace_events), 2) if trace_events else 0,
        "failure_rate": _ratio(failed, max(1, stats["run_count"])),
        "model_audit_count": stats["model_audits"],
    }


def _recall_metrics(
    stats: dict[str, Any],
    gold: dict[str, Any],
    vector: dict[str, Any],
) -> dict[str, object]:
    runs = [run for run in stats["runs"] if run["stats"]]
    collected = sum(_int(run["stats"].get("collected")) for run in runs)
    deduped = sum(_int(run["stats"].get("deduped")) for run in runs)
    local_retrieved = sum(_int(run["stats"].get("local_retrieved")) for run in runs)
    source_collected = sum(_int(run["stats"].get("source_collected")) for run in runs)
    source_stats = [
        item
        for run in runs
        for item in run["stats"].get("source_stats", [])
        if isinstance(item, dict)
    ]
    active_source_hits = sum(1 for item in source_stats if _int(item.get("count")) > 0)
    source_attempts = len(source_stats)
    multi_source_runs = sum(
        1
        for run in runs
        if isinstance(run["stats"].get("source_sites"), list)
        and len(set(run["stats"]["source_sites"])) >= 2
    )
    dedup_retention = _ratio(deduped, collected)
    source_coverage = _ratio(active_source_hits, source_attempts)
    multi_source_rate = _ratio(multi_source_runs, len(runs))
    fts_coverage = _ratio(stats["fts_count"], stats["notice_count"])
    local_reuse_rate = _ratio(local_retrieved, collected)
    vector_coverage_rate = _ratio(
        _int(vector.get("embedded_notices")),
        _int(vector.get("indexed_notices")),
    )
    recall_proxy = round(
        0.30 * source_coverage
        + 0.25 * dedup_retention
        + 0.15 * multi_source_rate
        + 0.20 * fts_coverage
        + 0.10 * local_reuse_rate,
        3,
    )
    recall_at = gold.get("recall_at") if isinstance(gold.get("recall_at"), dict) else {}
    precision_at = gold.get("precision_at") if isinstance(gold.get("precision_at"), dict) else {}
    return {
        "recall_proxy": recall_proxy,
        "source_coverage_rate": source_coverage,
        "dedup_retention_rate": dedup_retention,
        "multi_source_rate": multi_source_rate,
        "fts_coverage_rate": fts_coverage,
        "local_reuse_rate": local_reuse_rate,
        "vector_coverage_rate": vector_coverage_rate,
        "vector_enabled": bool(vector.get("enabled")),
        "vector_embedded_notices": _int(vector.get("embedded_notices")),
        "vector_model": str(vector.get("model") or ""),
        "collected": collected,
        "deduped": deduped,
        "local_retrieved": local_retrieved,
        "source_collected": source_collected,
        "indexed_notices": stats["notice_count"],
        "fts_indexed_notices": stats["fts_count"],
        "source_attempts": source_attempts,
        "source_hits": active_source_hits,
        "strict_recall_available": bool(gold.get("available")),
        "strict_recall_at_5": float(recall_at.get("5") or 0),
        "strict_recall_at_10": float(recall_at.get("10") or 0),
        "strict_precision_at_10": float(precision_at.get("10") or 0),
        "gold_case_count": _int(gold.get("case_count")),
        "annotated_gold_case_count": _int(gold.get("annotated_case_count")),
        "gold_expected_total": _int(gold.get("expected_total")),
    }


def _intent_harness() -> dict[str, Any]:
    now = datetime(2026, 7, 6, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    cases = [
        {
            "name": "relative_province_topic",
            "query": "最近1个月的安徽省区域内的服务器招标信息都有哪些",
            "expect": {"province": "安徽", "topic": "服务器", "schedule": "immediate"},
        },
        {
            "name": "city_multi_topic",
            "query": "最近36个月杭州市的空调或者服务器投标信息都有哪些",
            "expect": {"province": "浙江", "city": "杭州", "topics": ["空调", "服务器"]},
        },
        {
            "name": "daily_subscription",
            "query": "最近3个月的上海区域内的充电桩招标信息都有哪些，请汇总后每天9:00发送给我",
            "expect": {"province": "上海", "topic": "充电桩", "schedule": "recurring"},
        },
        {
            "name": "absolute_month",
            "query": "2026年4月份北京充电桩相关的招标信息都有哪些",
            "expect": {"province": "北京", "topic": "充电桩", "time_kind": "absolute_month"},
        },
    ]
    results = [_score_intent_case(case, now) for case in cases]
    passed = sum(1 for item in results if item["passed"])
    field_total = sum(item["field_total"] for item in results)
    field_passed = sum(item["field_passed"] for item in results)
    return {
        "case_count": len(results),
        "passed_cases": passed,
        "case_pass_rate": _ratio(passed, len(results)),
        "field_accuracy": _ratio(field_passed, field_total),
        "cases": results,
    }


def _score_intent_case(case: dict[str, Any], now: datetime) -> dict[str, Any]:
    bidql = compile_intent(case["query"], now=now)
    expect = case["expect"]
    checks: list[bool] = []
    if "province" in expect:
        checks.append(bidql.get("region", {}).get("province") == expect["province"])
    if "city" in expect:
        checks.append(bidql.get("region", {}).get("city") == expect["city"])
    if "topic" in expect:
        checks.append(expect["topic"] in bidql.get("topic", {}).get("core", []))
    if "topics" in expect:
        core = set(bidql.get("topic", {}).get("core", []))
        checks.append(set(expect["topics"]).issubset(core))
    if "schedule" in expect:
        checks.append(bidql.get("schedule", {}).get("kind") == expect["schedule"])
    if "time_kind" in expect:
        checks.append(bidql.get("time", {}).get("kind") == expect["time_kind"])
    field_passed = sum(1 for item in checks if item)
    return {
        "name": case["name"],
        "query": case["query"],
        "passed": bool(checks and field_passed == len(checks)),
        "field_passed": field_passed,
        "field_total": len(checks),
    }


def _ratio(numerator: int | float, denominator: int | float) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 3)


def _int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
