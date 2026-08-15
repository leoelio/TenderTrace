from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
import json
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5
from zoneinfo import ZoneInfo

from tendertrace.config import Settings
from tendertrace.db import connection, json_dumps
from tendertrace.intent import compile_intent


DEFAULT_USER_ID = "admin"
MAX_REPORT_DAYS = 31
ADVICE_FEEDBACK_STATUSES = {"accepted", "completed", "dismissed"}


def record_activity(
    settings: Settings,
    *,
    event_type: str,
    target: str | None = None,
    label: str | None = None,
    metadata: dict[str, Any] | None = None,
    user_id: str = DEFAULT_USER_ID,
    created_at: datetime | str | None = None,
) -> dict[str, object]:
    event_type = event_type.strip()
    if not event_type:
        raise ValueError("event_type is required")
    user_id = (user_id or DEFAULT_USER_ID).strip() or DEFAULT_USER_ID
    timestamp = _coerce_datetime(settings, created_at)
    event = {
        "id": str(uuid4()),
        "user_id": user_id,
        "event_type": event_type,
        "target": (target or "").strip(),
        "label": (label or "").strip(),
        "metadata": _metadata_dict(metadata),
        "created_at": timestamp.isoformat(timespec="seconds"),
        "created_date": timestamp.date().isoformat(),
    }
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO user_activity_events(
                id, user_id, event_type, target, label, metadata_json, created_at, created_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["id"],
                event["user_id"],
                event["event_type"],
                event["target"],
                event["label"],
                json_dumps(event["metadata"]),
                event["created_at"],
                event["created_date"],
            ),
        )
    return event


def build_weekly_report(
    settings: Settings,
    *,
    user_id: str = DEFAULT_USER_ID,
    days: int = 7,
    now: datetime | str | None = None,
) -> dict[str, object]:
    user_id = (user_id or DEFAULT_USER_ID).strip() or DEFAULT_USER_ID
    days = max(1, min(int(days), MAX_REPORT_DAYS))
    end_at = _coerce_datetime(settings, now)
    start_date = end_at.date() - timedelta(days=days - 1)
    end_date = end_at.date()
    events = _load_events(settings, user_id, start_date, end_date)
    runs = _load_runs(settings, start_date, end_date)
    subscriptions = _load_subscription_count(settings, start_date, end_date)
    opportunity_summary = _load_opportunity_summary(settings, start_date, end_date)

    event_counts = Counter(event["event_type"] for event in events)
    daily = _daily_rows(start_date, end_date, events, runs)
    top_queries = _top_queries(events, runs)
    downloads = [event for event in events if event["event_type"] == "download"]
    failed_runs = [run for run in runs if run.get("status") == "failed"]
    finished_runs = [run for run in runs if run.get("status") == "finished"]

    summary = {
        "total_events": len(events),
        "active_days": sum(1 for row in daily if row["events"] or row["runs"]),
        "clicks": event_counts["click"],
        "downloads": len(downloads),
        "runs_started": event_counts["run_start"] or len(runs),
        "runs_finished": len(finished_runs),
        "failed_runs": len(failed_runs),
        "subscriptions_created": event_counts["subscription_create"] or subscriptions,
        "weekly_reports_viewed": event_counts["weekly_report_view"],
    }
    knowledge_profile = _knowledge_profile(events, runs, top_queries, summary)
    risk_signals = _risk_signals(summary, knowledge_profile, failed_runs)
    recommendation_plan = _recommendation_plan(
        summary,
        top_queries,
        failed_runs,
        knowledge_profile,
        risk_signals,
        opportunity_summary,
    )
    recommendation_plan = _attach_advice_feedback(settings, user_id, recommendation_plan)
    active_recommendations = [
        item
        for item in recommendation_plan
        if item.get("feedback_status") not in {"completed", "dismissed"}
    ]
    return {
        "user_id": user_id,
        "period": {
            "from": start_date.isoformat(),
            "to": end_date.isoformat(),
            "days": days,
            "generated_at": end_at.isoformat(timespec="seconds"),
        },
        "summary": summary,
        "event_counts": dict(event_counts),
        "daily": daily,
        "top_queries": top_queries,
        "downloads": _compact_events(downloads, limit=10),
        "recent_events": _compact_events(list(reversed(events)), limit=12),
        "knowledge_profile": knowledge_profile,
        "opportunity_summary": opportunity_summary,
        "risk_signals": risk_signals,
        "recommendation_plan": recommendation_plan,
        "recommendation_feedback": _feedback_summary(recommendation_plan),
        "generated_advice": _generated_advice(
            summary,
            knowledge_profile,
            active_recommendations,
            opportunity_summary,
        ),
        "analysis": _analysis(
            summary,
            top_queries,
            knowledge_profile,
            risk_signals,
            opportunity_summary,
        ),
        "suggestions": _suggestions(active_recommendations),
    }


def persist_weekly_report(settings: Settings, report: dict[str, object]) -> dict[str, object]:
    period = report.get("period")
    if not isinstance(period, dict):
        raise ValueError("report.period is required")
    user_id = str(report.get("user_id") or DEFAULT_USER_ID)
    week_start = str(period.get("from") or "")
    week_end = str(period.get("to") or "")
    if not week_start or not week_end:
        raise ValueError("report period is incomplete")
    report_id = str(uuid5(NAMESPACE_URL, f"tendertrace:weekly:{user_id}:{week_start}:{week_end}"))
    profile_snapshot = _profile_snapshot(report)
    profile_id = str(uuid5(NAMESPACE_URL, f"tendertrace:memory-profile:{user_id}"))
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO weekly_reports(id, user_id, week_start, week_end, report_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, week_start, week_end) DO UPDATE SET
                report_json = excluded.report_json,
                created_at = datetime('now')
            """,
            (report_id, user_id, week_start, week_end, json_dumps(report)),
        )
        conn.execute(
            """
            INSERT INTO user_memory_profiles(id, user_id, profile_json)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                profile_json = excluded.profile_json,
                updated_at = datetime('now')
            """,
            (profile_id, user_id, json_dumps(profile_snapshot)),
        )
    return {**report, "saved_report_id": report_id}


def load_memory_profile(settings: Settings, *, user_id: str = DEFAULT_USER_ID) -> dict[str, object] | None:
    user_id = (user_id or DEFAULT_USER_ID).strip() or DEFAULT_USER_ID
    with connection(settings) as conn:
        row = conn.execute(
            """
            SELECT profile_json, updated_at
            FROM user_memory_profiles
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    payload = _loads_json(row["profile_json"], {})
    if isinstance(payload, dict):
        return {**payload, "updated_at": row["updated_at"]}
    return {"user_id": user_id, "updated_at": row["updated_at"]}


def record_advice_feedback(
    settings: Settings,
    *,
    advice_id: str,
    status: str,
    user_id: str = DEFAULT_USER_ID,
    source: str = "web",
    actor: str = "",
    note: str = "",
    context: dict[str, Any] | None = None,
) -> dict[str, object]:
    advice_id = advice_id.strip()
    status = status.strip().lower()
    user_id = (user_id or DEFAULT_USER_ID).strip() or DEFAULT_USER_ID
    if not advice_id:
        raise ValueError("advice_id is required")
    try:
        UUID(advice_id)
    except ValueError as exc:
        raise ValueError("advice_id must be a UUID") from exc
    if status not in ADVICE_FEEDBACK_STATUSES:
        allowed = ", ".join(sorted(ADVICE_FEEDBACK_STATUSES))
        raise ValueError(f"status must be one of: {allowed}")
    feedback_id = str(uuid5(NAMESPACE_URL, f"tendertrace:advice-feedback:{user_id}:{advice_id}"))
    payload = _metadata_dict(context)
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO memory_advice_feedback(
                id, user_id, advice_id, status, source, actor, note, context_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, advice_id) DO UPDATE SET
                status = excluded.status,
                source = excluded.source,
                actor = excluded.actor,
                note = excluded.note,
                context_json = excluded.context_json,
                updated_at = datetime('now')
            """,
            (
                feedback_id,
                user_id,
                advice_id,
                status,
                source.strip() or "web",
                actor.strip(),
                note.strip(),
                json_dumps(payload),
            ),
        )
        row = conn.execute(
            """
            SELECT id, user_id, advice_id, status, source, actor, note, context_json,
                   created_at, updated_at
            FROM memory_advice_feedback
            WHERE user_id = ? AND advice_id = ?
            """,
            (user_id, advice_id),
        ).fetchone()
    return _feedback_row(row)


def _load_events(
    settings: Settings,
    user_id: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT event_type, target, label, metadata_json, created_at, created_date
            FROM user_activity_events
            WHERE user_id = ?
              AND created_date >= ?
              AND created_date <= ?
            ORDER BY created_at ASC
            """,
            (user_id, start_date.isoformat(), end_date.isoformat()),
        ).fetchall()
    events: list[dict[str, Any]] = []
    for row in rows:
        events.append(
            {
                "event_type": row["event_type"],
                "target": row["target"] or "",
                "label": row["label"] or "",
                "metadata": _loads_json(row["metadata_json"], {}),
                "created_at": row["created_at"],
                "created_date": row["created_date"],
            }
        )
    return events


def _load_runs(settings: Settings, start_date: date, end_date: date) -> list[dict[str, Any]]:
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT id, original_query, status, started_at, finished_at, stats_json
            FROM runs
            WHERE status != 'deleted'
              AND date(started_at) >= ?
              AND date(started_at) <= ?
            ORDER BY started_at ASC
            """,
            (start_date.isoformat(), end_date.isoformat()),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "original_query": row["original_query"],
            "status": row["status"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "stats": _loads_json(row["stats_json"], {}),
        }
        for row in rows
    ]


def _load_subscription_count(settings: Settings, start_date: date, end_date: date) -> int:
    with connection(settings) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM subscriptions
            WHERE date(created_at) >= ?
              AND date(created_at) <= ?
            """,
            (start_date.isoformat(), end_date.isoformat()),
        ).fetchone()
    return int(row["count"] if row else 0)


def _load_opportunity_summary(
    settings: Settings,
    start_date: date,
    end_date: date,
) -> dict[str, object]:
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT fields_json
            FROM notices
            WHERE date(created_at) >= ? AND date(created_at) <= ?
            """,
            (start_date.isoformat(), end_date.isoformat()),
        ).fetchall()
    levels: Counter[str] = Counter()
    missing_fields: Counter[str] = Counter()
    scores: list[int] = []
    credibility_scores: list[int] = []
    risk_count = 0
    for row in rows:
        fields = _loads_json(row["fields_json"], {})
        if not isinstance(fields, dict):
            continue
        intelligence = fields.get("opportunity_intelligence")
        if not isinstance(intelligence, dict):
            continue
        levels[str(intelligence.get("level") or "D")] += 1
        scores.append(_coerce_int(intelligence.get("score")))
        score_parts = intelligence.get("scores")
        if isinstance(score_parts, dict):
            credibility_scores.append(_coerce_int(score_parts.get("credibility")))
        for field in intelligence.get("missing_fields") or []:
            if str(field).strip():
                missing_fields[str(field).strip()] += 1
        risks = intelligence.get("risks")
        if isinstance(risks, list):
            risk_count += len(risks)
    total = sum(levels.values())
    return {
        "total": total,
        "levels": {level: levels.get(level, 0) for level in ("A", "B", "C", "D")},
        "average_score": round(sum(scores) / len(scores), 1) if scores else 0.0,
        "average_credibility": (
            round(sum(credibility_scores) / len(credibility_scores), 1)
            if credibility_scores
            else 0.0
        ),
        "risk_count": risk_count,
        "missing_fields": _counter_rows(missing_fields, limit=5),
    }


def _daily_rows(
    start_date: date,
    end_date: date,
    events: list[dict[str, Any]],
    runs: list[dict[str, Any]],
) -> list[dict[str, object]]:
    event_counter: dict[str, Counter[str]] = defaultdict(Counter)
    for event in events:
        event_counter[event["created_date"]][event["event_type"]] += 1
    run_counter: Counter[str] = Counter()
    for run in runs:
        started_at = str(run.get("started_at") or "")
        if started_at:
            run_counter[started_at[:10]] += 1
    rows = []
    cursor = start_date
    while cursor <= end_date:
        key = cursor.isoformat()
        counts = event_counter[key]
        rows.append(
            {
                "date": key,
                "events": sum(counts.values()),
                "clicks": counts["click"],
                "downloads": counts["download"],
                "runs": run_counter[key],
                "event_types": dict(counts),
            }
        )
        cursor += timedelta(days=1)
    return rows


def _top_queries(events: list[dict[str, Any]], runs: list[dict[str, Any]]) -> list[dict[str, object]]:
    counter: Counter[str] = Counter()
    for event in events:
        metadata = event.get("metadata") or {}
        if isinstance(metadata, dict):
            query = str(metadata.get("query") or "").strip()
            if query:
                counter[query] += 1
    for run in runs:
        query = str(run.get("original_query") or "").strip()
        if query:
            counter[query] += 1
    return [{"query": query, "count": count} for query, count in counter.most_common(8)]


def _compact_events(events: list[dict[str, Any]], *, limit: int) -> list[dict[str, object]]:
    return [
        {
            "event_type": event["event_type"],
            "target": event["target"],
            "label": event["label"],
            "created_at": event["created_at"],
            "metadata": event["metadata"],
        }
        for event in events[:limit]
    ]


def _knowledge_profile(
    events: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    top_queries: list[dict[str, object]],
    summary: dict[str, int],
) -> dict[str, object]:
    topic_counter: Counter[str] = Counter()
    region_counter: Counter[str] = Counter()
    schedule_counter: Counter[str] = Counter()
    source_counter: Counter[str] = Counter()
    source_failures: Counter[str] = Counter()
    clarify_risk_count = 0

    for item in top_queries:
        query = str(item.get("query") or "").strip()
        weight = _coerce_int(item.get("count"), default=1)
        if not query:
            continue
        try:
            bidql = compile_intent(query)
        except Exception:
            continue
        topic = bidql.get("topic") if isinstance(bidql.get("topic"), dict) else {}
        for value in topic.get("core") or []:
            if str(value).strip():
                topic_counter[str(value).strip()] += weight
        region_label = _region_label(bidql.get("region"))
        if region_label:
            region_counter[region_label] += weight
        schedule_label = _schedule_label(bidql.get("schedule"))
        if schedule_label:
            schedule_counter[schedule_label] += weight
        meta = bidql.get("meta") if isinstance(bidql.get("meta"), dict) else {}
        clarify_needed = meta.get("clarify_needed") if isinstance(meta, dict) else []
        if isinstance(clarify_needed, list) and clarify_needed:
            clarify_risk_count += weight

    for run in runs:
        stats = run.get("stats") if isinstance(run.get("stats"), dict) else {}
        for item in stats.get("source_stats") or []:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source") or item.get("site") or "").strip()
            if not source:
                continue
            count = _coerce_int(item.get("count"), default=0)
            if count > 0:
                source_counter[source] += count
            if item.get("status") == "failed":
                source_failures[source] += 1

    return {
        "topics": _counter_rows(topic_counter),
        "regions": _counter_rows(region_counter),
        "schedules": _counter_rows(schedule_counter),
        "sources": _counter_rows(source_counter),
        "source_failures": _counter_rows(source_failures),
        "query_patterns": {
            "repeat_queries": [
                {"query": item["query"], "count": item["count"]}
                for item in top_queries
                if _coerce_int(item.get("count")) >= 2
            ],
            "clarify_risk_count": clarify_risk_count,
            "scheduled_intent_count": sum(schedule_counter.values()),
        },
        "behavior": {
            "download_rate": round(_safe_div(summary["downloads"], summary["runs_finished"]), 3),
            "completion_rate": round(_safe_div(summary["runs_finished"], summary["runs_started"]), 3),
            "failure_rate": round(_safe_div(summary["failed_runs"], summary["runs_started"]), 3),
            "subscription_rate": round(
                _safe_div(summary["subscriptions_created"], summary["runs_started"]),
                3,
            ),
        },
    }


def _risk_signals(
    summary: dict[str, int],
    profile: dict[str, object],
    failed_runs: list[dict[str, Any]],
) -> list[dict[str, object]]:
    behavior = profile.get("behavior") if isinstance(profile.get("behavior"), dict) else {}
    query_patterns = profile.get("query_patterns")
    query_patterns = query_patterns if isinstance(query_patterns, dict) else {}
    risks: list[dict[str, object]] = []

    if failed_runs:
        risks.append(
            {
                "severity": "high",
                "title": "存在失败运行",
                "detail": f"{len(failed_runs)} 次运行失败，建议优先查看事件流和数据源状态。",
                "evidence": {"run_ids": [str(run.get("id") or "") for run in failed_runs[:5]]},
            }
        )
    if summary["runs_finished"] and float(behavior.get("download_rate") or 0) < 0.6:
        risks.append(
            {
                "severity": "medium",
                "title": "报告下载转化偏低",
                "detail": "已有 Word 生成但下载偏少，可能存在报告入口不明显或结果未及时复核。",
                "evidence": {
                    "runs_finished": summary["runs_finished"],
                    "downloads": summary["downloads"],
                },
            }
        )
    if _coerce_int(query_patterns.get("clarify_risk_count")):
        risks.append(
            {
                "severity": "medium",
                "title": "部分查询意图不够稳定",
                "detail": "历史查询中存在主题或区域置信度较低的表达，建议补充品类词典或主动反问。",
                "evidence": {"count": query_patterns["clarify_risk_count"]},
            }
        )
    if query_patterns.get("repeat_queries") and not summary["subscriptions_created"]:
        risks.append(
            {
                "severity": "low",
                "title": "高频查询尚未订阅化",
                "detail": "重复查询仍由人工触发，适合转成订阅并复用 sent_history 增量去重。",
                "evidence": {"repeat_queries": query_patterns["repeat_queries"][:3]},
            }
        )
    return risks[:5]


def _recommendation_plan(
    summary: dict[str, int],
    top_queries: list[dict[str, object]],
    failed_runs: list[dict[str, Any]],
    profile: dict[str, object],
    risk_signals: list[dict[str, object]],
    opportunity_summary: dict[str, object],
) -> list[dict[str, object]]:
    behavior = profile.get("behavior") if isinstance(profile.get("behavior"), dict) else {}
    topics = profile.get("topics") if isinstance(profile.get("topics"), list) else []
    regions = profile.get("regions") if isinstance(profile.get("regions"), list) else []
    repeat_query = top_queries[0] if top_queries and _coerce_int(top_queries[0].get("count")) >= 2 else None
    top_topic = str(topics[0]["name"]) if topics else ""
    top_region = str(regions[0]["name"]) if regions else ""
    plan: list[dict[str, object]] = []
    opportunity_levels = (
        opportunity_summary.get("levels")
        if isinstance(opportunity_summary.get("levels"), dict)
        else {}
    )
    priority_count = _coerce_int(opportunity_levels.get("A"))
    watch_count = _coerce_int(opportunity_levels.get("B"))

    if priority_count:
        plan.append(
            _recommendation(
                "high",
                "opportunity_followup",
                f"分派并复核 {priority_count} 个 A 级机会",
                "这些线索在时效、完整度、可信度和可行动性上达到优先跟进阈值。",
                "在机会情报页确认负责人和下一步动作，并将摘要发送到飞书协同群。",
                level="A",
                count=priority_count,
            )
        )
    elif watch_count:
        plan.append(
            _recommendation(
                "high",
                "opportunity_qualification",
                f"推动 {watch_count} 个 B 级线索完成机会确认",
                "当前线索具备业务相关性，但仍有关键事实或跨来源佐证待补齐。",
                "优先补充预算、采购人和投标截止时间，满足条件后升级为 A 级。",
                level="B",
                count=watch_count,
            )
        )

    if summary["downloads"] == 0 and summary["runs_finished"] == 0:
        plan.append(
            _recommendation(
                "high",
                "onboarding",
                "先完成一次真实查询并下载 Word",
                "当前记忆库还缺少结果转化样本，无法判断哪些主题真正有价值。",
                "运行一个明确区域和主题的查询，下载生成的 Word 后再查看周报。",
            )
        )
    if repeat_query:
        plan.append(
            _recommendation(
                "high",
                "subscription",
                "将高频查询升级为订阅",
                f"“{repeat_query['query']}” 已出现 {repeat_query['count']} 次，适合交给定时任务增量推送。",
                "在工作台切换到创建订阅，保持每天 09:00 推送并依赖 sent_history 去重。",
                query=str(repeat_query["query"]),
            )
        )
    if failed_runs:
        plan.append(
            _recommendation(
                "high",
                "reliability",
                "先处理失败运行对应的数据源",
                f"本周期有 {len(failed_runs)} 次失败运行，会持续拉低召回与周报可信度。",
                "打开历史运行的追踪视图，优先检查失败节点、源站状态和模型配置。",
                run_ids=[str(run.get("id") or "") for run in failed_runs[:5]],
            )
        )
    if summary["runs_finished"] and float(behavior.get("download_rate") or 0) < 0.6:
        plan.append(
            _recommendation(
                "medium",
                "workflow",
                "复核未下载的 Word 报告",
                "系统已经生成报告，但下载记录不足，说明结果可能没有进入业务归档。",
                "进入报告输出区下载最新 Word，并删除明显无价值或重复的旧报告。",
            )
        )
    if top_topic and top_region:
        plan.append(
            _recommendation(
                "medium",
                "knowledge_base",
                "围绕核心偏好扩展后台采集",
                f"当前偏好集中在“{top_region} / {top_topic}”，适合提前积累本地 notices 库。",
                f"创建采集订阅：区域={top_region}，主题={top_topic}，让后续查询优先走本地库。",
                topic=top_topic,
                region=top_region,
            )
        )
    if not plan and not risk_signals:
        plan.append(
            _recommendation(
                "low",
                "evaluation",
                "保持当前使用节奏并补充金标集",
                "当前运行、下载和订阅指标没有明显异常。",
                "继续扩充评测金标集，用真实 Recall@K 衡量后续优化收益。",
            )
        )
    return plan[:6]


def _generated_advice(
    summary: dict[str, int],
    profile: dict[str, object],
    plan: list[dict[str, object]],
    opportunity_summary: dict[str, object],
) -> dict[str, object]:
    topics = profile.get("topics") if isinstance(profile.get("topics"), list) else []
    regions = profile.get("regions") if isinstance(profile.get("regions"), list) else []
    top_topic = str(topics[0]["name"]) if topics else "暂无稳定主题"
    top_region = str(regions[0]["name"]) if regions else "暂无稳定区域"
    opportunity_levels = (
        opportunity_summary.get("levels")
        if isinstance(opportunity_summary.get("levels"), dict)
        else {}
    )
    priority_count = _coerce_int(opportunity_levels.get("A"))
    watch_count = _coerce_int(opportunity_levels.get("B"))
    if priority_count:
        headline = f"本周有 {priority_count} 个 A 级机会需要优先分派"
        summary_text = (
            f"机会库共沉淀 {opportunity_summary.get('total', 0)} 条线索，"
            f"平均可信度 {opportunity_summary.get('average_credibility', 0)} 分；"
            "建议先关闭 A 级机会的风险项，再进入项目定级与策略制定。"
        )
    elif watch_count:
        headline = f"本周重点是推动 {watch_count} 个 B 级线索完成确认"
        summary_text = "先补齐预算、采购人、投标截止与跨来源证据，再决定销售资源投入。"
    elif summary["total_events"] == 0 and summary["runs_finished"] == 0:
        headline = "记忆库正在等待第一批有效样本"
        summary_text = "完成真实查询、下载 Word、创建订阅后，系统会自动沉淀主题和区域偏好。"
    else:
        headline = f"当前重点是 {top_region} 的 {top_topic}"
        summary_text = (
            f"本周期完成 {summary['runs_finished']} 次运行、下载 {summary['downloads']} 份报告，"
            f"系统已据此生成 {len(plan)} 条可执行建议。"
        )
    return {
        "headline": headline,
        "summary": summary_text,
        "next_actions": [str(item.get("action") or "") for item in plan[:3]],
        "basis": {
            "top_topic": top_topic,
            "top_region": top_region,
            "runs_finished": summary["runs_finished"],
            "downloads": summary["downloads"],
            "opportunities": opportunity_summary.get("total", 0),
            "priority_opportunities": priority_count,
            "average_credibility": opportunity_summary.get("average_credibility", 0),
        },
        "engine": "local_profile_generator",
    }


def _analysis(
    summary: dict[str, int],
    top_queries: list[dict[str, object]],
    profile: dict[str, object],
    risk_signals: list[dict[str, object]],
    opportunity_summary: dict[str, object],
) -> list[str]:
    if summary["total_events"] == 0 and summary["runs_finished"] == 0:
        return ["本周期内还没有可分析的使用记录。"]
    topics = profile.get("topics") if isinstance(profile.get("topics"), list) else []
    regions = profile.get("regions") if isinstance(profile.get("regions"), list) else []
    behavior = profile.get("behavior") if isinstance(profile.get("behavior"), dict) else {}
    rows = [
        f"本周期记录 {summary['total_events']} 次交互，覆盖 {summary['active_days']} 个活跃日。",
        f"完成运行 {summary['runs_finished']} 次，下载报告 {summary['downloads']} 次。",
    ]
    if top_queries:
        rows.append(f"关注最高的查询是：{top_queries[0]['query']}。")
    if topics:
        rows.append(f"主题偏好集中在：{topics[0]['name']}。")
    if regions:
        rows.append(f"区域偏好集中在：{regions[0]['name']}。")
    if summary["runs_finished"]:
        rows.append(f"报告下载转化率为 {float(behavior.get('download_rate') or 0):.0%}。")
    if risk_signals:
        rows.append(f"检测到 {len(risk_signals)} 个需要关注的风险信号。")
    if _coerce_int(opportunity_summary.get("total")):
        levels = (
            opportunity_summary.get("levels")
            if isinstance(opportunity_summary.get("levels"), dict)
            else {}
        )
        rows.append(
            "机会库新增 "
            f"{opportunity_summary['total']} 条：A {levels.get('A', 0)} / "
            f"B {levels.get('B', 0)} / C {levels.get('C', 0)} / D {levels.get('D', 0)}，"
            f"平均可信度 {opportunity_summary.get('average_credibility', 0)} 分。"
        )
    return rows


def _suggestions(plan: list[dict[str, object]]) -> list[str]:
    if not plan:
        return ["当前使用节奏正常，可继续补充金标集来量化召回率变化。"]
    return [
        f"{item.get('title', '建议')}：{item.get('action', '')}".strip("：")
        for item in plan[:5]
    ]


def _recommendation(
    priority: str,
    kind: str,
    title: str,
    reason: str,
    action: str,
    **evidence: object,
) -> dict[str, object]:
    evidence = {key: value for key, value in evidence.items() if value not in (None, "", [])}
    identity = {
        key: value
        for key, value in evidence.items()
        if key not in {"count", "run_ids"}
    }
    identity_json = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "id": str(uuid5(NAMESPACE_URL, f"tendertrace:advice:{kind}:{identity_json}")),
        "priority": priority,
        "kind": kind,
        "title": title,
        "reason": reason,
        "action": action,
        "evidence": evidence,
        "feedback_status": "pending",
    }


def _attach_advice_feedback(
    settings: Settings,
    user_id: str,
    plan: list[dict[str, object]],
) -> list[dict[str, object]]:
    advice_ids = [str(item.get("id") or "") for item in plan if item.get("id")]
    if not advice_ids:
        return plan
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, advice_id, status, source, actor, note, context_json,
                   created_at, updated_at
            FROM memory_advice_feedback
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchall()
    wanted = set(advice_ids)
    feedback_by_advice = {
        str(row["advice_id"]): _feedback_row(row)
        for row in rows
        if str(row["advice_id"]) in wanted
    }
    return [
        {
            **item,
            "feedback_status": feedback_by_advice.get(str(item.get("id") or ""), {}).get(
                "status", "pending"
            ),
            "feedback": feedback_by_advice.get(str(item.get("id") or "")),
        }
        for item in plan
    ]


def _feedback_summary(plan: list[dict[str, object]]) -> dict[str, int]:
    counts = Counter(str(item.get("feedback_status") or "pending") for item in plan)
    return {
        "pending": counts["pending"],
        "accepted": counts["accepted"],
        "completed": counts["completed"],
        "dismissed": counts["dismissed"],
    }


def _feedback_row(row: Any) -> dict[str, object]:
    if row is None:
        return {}
    return {
        "id": str(row["id"]),
        "user_id": str(row["user_id"]),
        "advice_id": str(row["advice_id"]),
        "status": str(row["status"]),
        "source": str(row["source"] or ""),
        "actor": str(row["actor"] or ""),
        "note": str(row["note"] or ""),
        "context": _loads_json(row["context_json"], {}),
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }


def _profile_snapshot(report: dict[str, object]) -> dict[str, object]:
    return {
        "user_id": report.get("user_id") or DEFAULT_USER_ID,
        "period": report.get("period") or {},
        "knowledge_profile": report.get("knowledge_profile") or {},
        "opportunity_summary": report.get("opportunity_summary") or {},
        "risk_signals": report.get("risk_signals") or [],
        "recommendation_plan": report.get("recommendation_plan") or [],
        "recommendation_feedback": report.get("recommendation_feedback") or {},
        "generated_advice": report.get("generated_advice") or {},
    }


def _counter_rows(counter: Counter[str], *, limit: int = 6) -> list[dict[str, object]]:
    total = sum(counter.values())
    return [
        {"name": name, "count": count, "share": round(_safe_div(count, total), 3)}
        for name, count in counter.most_common(limit)
    ]


def _region_label(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    district = str(value.get("district") or "").strip()
    city = str(value.get("city") or "").strip()
    province = str(value.get("province") or "").strip()
    if district and city:
        return f"{province}/{city}/{district}" if province else f"{city}/{district}"
    if city and province:
        return f"{province}/{city}"
    return province or city or district


def _schedule_label(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    kind = str(value.get("kind") or "").strip()
    if kind == "recurring":
        cron = str(value.get("cron") or "").strip()
        return f"recurring:{cron}" if cron else "recurring"
    if kind == "once_at":
        return "once_at"
    return ""


def _coerce_int(value: object, *, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _safe_div(numerator: int, denominator: int) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def _metadata_dict(value: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        return {key: str(item) for key, item in value.items()}


def _loads_json(raw: str, fallback: Any) -> Any:
    try:
        return json.loads(raw or "")
    except json.JSONDecodeError:
        return fallback


def _coerce_datetime(settings: Settings, value: datetime | str | None) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value)
    try:
        tz = ZoneInfo(settings.timezone)
    except Exception:
        return datetime.now().astimezone().replace(microsecond=0)
    return datetime.now(tz).replace(microsecond=0)
