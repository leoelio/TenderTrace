from __future__ import annotations

from datetime import datetime
import json
import re
from time import perf_counter
from typing import Any
from uuid import uuid4

from tendertrace.adapters.ccgp import Notice
from tendertrace.adapters.multi import MultiSourceAdapter
from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps
from tendertrace.intent.compiler import compile_intent
from tendertrace.pipeline.dedup import clean_and_cluster_notices
from tendertrace.retrieval import search_notices
from tendertrace.runner import persist_notices_and_clusters


TIME_WINDOWS = {
    "7d": "最近7天",
    "30d": "最近30天",
    "90d": "最近3个月",
    "365d": "最近12个月",
}

TERMINAL_STATUSES = {
    "completed",
    "completed_with_errors",
    "cancelled",
    "failed",
}

_UNSAFE_PATTERNS = (
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior)\s+(?:instructions?|prompts?)", re.I),
    re.compile(r"忽略.{0,12}(?:指令|规则|提示词|要求)"),
    re.compile(r"(?:system\s*prompt|developer\s*message|jailbreak|系统提示词|开发者消息)", re.I),
    re.compile(r"(?:https?|file|ftp)://", re.I),
    re.compile(r"(?:\.\.[/\\]|api[_\s-]?key|cookie|token|密码|口令)", re.I),
    re.compile(r"\b(?:select|insert|update|delete|drop|pragma)\b", re.I),
)


def create_live_challenge(
    settings: Settings,
    *,
    category: object,
    region: object,
    time_window: object = "90d",
    keyword: object = "",
    actor: object = "judge",
    max_results: int = 12,
    now: datetime | None = None,
) -> dict[str, object]:
    init_db(settings)
    category_text = _controlled_text(category, "category", required=True, max_length=30)
    region_text = _controlled_text(region, "region", required=True, max_length=30)
    keyword_text = _controlled_text(keyword, "keyword", required=False, max_length=40)
    actor_text = _controlled_text(actor, "actor", required=True, max_length=40, check_unsafe=False)
    window_key = str(time_window or "90d").strip().lower()
    if window_key not in TIME_WINDOWS:
        raise ValueError(f"time_window must be one of: {', '.join(TIME_WINDOWS)}")
    result_limit = max(1, min(int(max_results), 20))
    query = _query_text(category_text, region_text, window_key, keyword_text)
    intent = _controlled_intent(
        query,
        category=category_text,
        region=region_text,
        keyword=keyword_text,
        now=now or datetime.now().astimezone(),
    )

    started = perf_counter()
    local = search_notices(settings, intent, max_results=result_limit)
    duration_ms = max(0, round((perf_counter() - started) * 1000))
    session_id = str(uuid4())
    notices = list(local.notices)
    metadata = _notice_metadata(settings, notices)
    source_summary = [
        {
            "source": "local_index",
            "label": "本地已验证索引",
            "status": "available",
            "count": len(notices),
            "detail": f"{local.stats.get('engine') or 'local'} · {duration_ms} ms",
        }
    ]
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO live_challenge_sessions(
                id, category, region, time_window, keyword, normalized_query,
                intent_json, status, local_duration_ms, local_result_count,
                source_summary_json, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                category_text,
                region_text,
                window_key,
                keyword_text,
                query,
                json_dumps(intent),
                "local_ready" if notices else "local_empty",
                duration_ms,
                len(notices),
                json_dumps(source_summary),
                actor_text,
            ),
        )
        _store_results(
            conn,
            session_id=session_id,
            notices=notices,
            origin="local",
            verification_status="local_verified",
            metadata=metadata,
            start_position=1,
        )
    return get_live_challenge(settings, session_id)


def list_live_challenges(settings: Settings, *, limit: int = 20) -> dict[str, object]:
    init_db(settings)
    bounded = max(1, min(int(limit), 100))
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT * FROM live_challenge_sessions
            ORDER BY created_at DESC, rowid DESC LIMIT ?
            """,
            (bounded,),
        ).fetchall()
    items = [_session_summary(row) for row in rows]
    return {"items": items, "returned": len(items)}


def get_live_challenge(settings: Settings, session_id: str) -> dict[str, object]:
    init_db(settings)
    with connection(settings) as conn:
        row = conn.execute(
            "SELECT * FROM live_challenge_sessions WHERE id = ?",
            (str(session_id),),
        ).fetchone()
        if row is None:
            raise ValueError("live challenge session not found")
        result_rows = conn.execute(
            """
            SELECT * FROM live_challenge_results
            WHERE session_id = ? ORDER BY position, created_at, id
            """,
            (str(session_id),),
        ).fetchall()
    payload = _session_summary(row)
    payload["results"] = [_result_payload(item) for item in result_rows]
    payload["result_count"] = len(result_rows)
    payload["generalization_allowed"] = False
    payload["protocol"] = {
        "local_first": True,
        "network_optional": True,
        "results_are_live_data": True,
        "replay_mode": False,
        "input_fields": ["category", "region", "time_window", "keyword"],
    }
    return payload


def begin_live_challenge_supplement(settings: Settings, session_id: str) -> dict[str, object]:
    init_db(settings)
    with connection(settings) as conn:
        row = conn.execute(
            "SELECT status FROM live_challenge_sessions WHERE id = ?",
            (str(session_id),),
        ).fetchone()
        if row is None:
            raise ValueError("live challenge session not found")
        if str(row["status"]) == "supplementing":
            raise ValueError("live challenge is already supplementing")
        conn.execute(
            """
            UPDATE live_challenge_sessions
            SET status = 'supplementing', cancel_requested = 0,
                error_text = '', completed_at = NULL
            WHERE id = ?
            """,
            (str(session_id),),
        )
    return get_live_challenge(settings, session_id)


def run_live_challenge_supplement(
    settings: Settings,
    session_id: str,
    *,
    adapter: MultiSourceAdapter | None = None,
    max_results: int = 12,
) -> dict[str, object]:
    session = get_live_challenge(settings, session_id)
    if session["status"] != "supplementing":
        raise ValueError("live challenge must be marked supplementing before it runs")
    if _cancel_requested(settings, session_id):
        return get_live_challenge(settings, session_id)
    intent = _json_object(session.get("intent"))
    source_adapter = adapter or MultiSourceAdapter.default(settings)
    started = perf_counter()
    try:
        collected = source_adapter.collect(
            intent,
            max_pages=1,
            max_results=max(1, min(int(max_results), 20)),
        )
        duration_ms = max(0, round((perf_counter() - started) * 1000))
        if _cancel_requested(settings, session_id):
            return get_live_challenge(settings, session_id)
        deduped = clean_and_cluster_notices(list(collected)).notices
        if deduped:
            persist_notices_and_clusters(settings, deduped)
        stats = [
            item.to_dict() if hasattr(item, "to_dict") else dict(item)
            for item in getattr(source_adapter, "last_source_stats", [])
        ]
        source_summary = _source_summary(stats)
        failed = [item for item in stats if str(item.get("status")) == "failed"]
        with connection(settings) as conn:
            local_count = conn.execute(
                "SELECT COUNT(*) FROM live_challenge_results WHERE session_id = ? AND origin = 'local'",
                (str(session_id),),
            ).fetchone()[0]
            metadata = _notice_metadata(settings, deduped)
            _store_results(
                conn,
                session_id=session_id,
                notices=deduped,
                origin="online",
                verification_status="network_result",
                metadata=metadata,
                start_position=int(local_count) + 1,
            )
            online_count = conn.execute(
                "SELECT COUNT(*) FROM live_challenge_results WHERE session_id = ? AND origin = 'online'",
                (str(session_id),),
            ).fetchone()[0]
            existing_summary = _json_list(
                conn.execute(
                    "SELECT source_summary_json FROM live_challenge_sessions WHERE id = ?",
                    (str(session_id),),
                ).fetchone()[0]
            )
            conn.execute(
                """
                UPDATE live_challenge_sessions
                SET status = ?, online_duration_ms = ?, online_result_count = ?,
                    source_summary_json = ?, error_text = ?, completed_at = datetime('now')
                WHERE id = ?
                """,
                (
                    "completed_with_errors" if failed else "completed",
                    duration_ms,
                    int(online_count),
                    json_dumps([*existing_summary[:1], *source_summary]),
                    f"{len(failed)} 个来源暂不可访问" if failed else "",
                    str(session_id),
                ),
            )
    except Exception as exc:
        with connection(settings) as conn:
            if not _cancel_requested_in_connection(conn, session_id):
                conn.execute(
                    """
                    UPDATE live_challenge_sessions
                    SET status = 'failed', error_text = ?, completed_at = datetime('now')
                    WHERE id = ?
                    """,
                    (f"{type(exc).__name__}: {exc}", str(session_id)),
                )
    return get_live_challenge(settings, session_id)


def cancel_live_challenge_supplement(settings: Settings, session_id: str) -> dict[str, object]:
    init_db(settings)
    with connection(settings) as conn:
        row = conn.execute(
            "SELECT status FROM live_challenge_sessions WHERE id = ?",
            (str(session_id),),
        ).fetchone()
        if row is None:
            raise ValueError("live challenge session not found")
        if str(row["status"]) == "supplementing":
            conn.execute(
                """
                UPDATE live_challenge_sessions
                SET status = 'cancelled', cancel_requested = 1,
                    error_text = '联网补充已由现场人员停止', completed_at = datetime('now')
                WHERE id = ?
                """,
                (str(session_id),),
            )
    return get_live_challenge(settings, session_id)


def _controlled_text(
    value: object,
    field: str,
    *,
    required: bool,
    max_length: int,
    check_unsafe: bool = True,
) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if required and not text:
        raise ValueError(f"{field} is required")
    if len(text) > max_length:
        raise ValueError(f"{field} is too long")
    if any(ord(char) < 32 for char in text):
        raise ValueError(f"{field} contains control characters")
    if check_unsafe and any(pattern.search(text) for pattern in _UNSAFE_PATTERNS):
        raise ValueError(f"{field} contains unsupported instructions or unsafe content")
    return text


def _query_text(category: str, region: str, time_window: str, keyword: str) -> str:
    extra = f"，关键词 {keyword}" if keyword else ""
    return f"{TIME_WINDOWS[time_window]} {region} {category} 招标采购信息{extra}"


def _controlled_intent(
    query: str,
    *,
    category: str,
    region: str,
    keyword: str,
    now: datetime,
) -> dict[str, Any]:
    intent = compile_intent(query, now=now)
    topic = intent.get("topic")
    if not isinstance(topic, dict):
        topic = {}
        intent["topic"] = topic
    topic["core"] = _dedupe_text([category, keyword])
    source_terms = [
        str(item)
        for item in topic.get("source_terms", [])
        if item and str(item).casefold() != region.casefold()
    ]
    topic["source_terms"] = _dedupe_text([category, keyword, *source_terms])
    topic["origin"] = "controlled_fields"

    region_intent = intent.get("region")
    if not isinstance(region_intent, dict):
        region_intent = {}
        intent["region"] = region_intent
    if str(region_intent.get("origin") or "") == "missing":
        international = bool(re.search(r"[A-Za-z]", region))
        region_intent.update(
            {
                "scope": "global" if international else "domestic",
                "aliases": [region],
                "location_aliases": [region],
                "origin": "controlled_field",
            }
        )
    return intent


def _dedupe_text(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def _notice_metadata(settings: Settings, notices: list[Notice]) -> dict[str, dict[str, str]]:
    notice_ids = [f"{notice.source_site}:{notice.id}" for notice in notices]
    if not notice_ids:
        return {}
    placeholders = ",".join("?" for _ in notice_ids)
    with connection(settings) as conn:
        rows = conn.execute(
            f"""
            SELECT id, updated_at, last_seen_at, created_at
            FROM notices WHERE id IN ({placeholders})
            """,
            notice_ids,
        ).fetchall()
    return {
        str(row["id"]): {
            "indexed_at": str(row["last_seen_at"] or row["updated_at"] or row["created_at"] or "")
        }
        for row in rows
    }


def _store_results(
    conn: Any,
    *,
    session_id: str,
    notices: list[Notice],
    origin: str,
    verification_status: str,
    metadata: dict[str, dict[str, str]],
    start_position: int,
) -> None:
    for offset, notice in enumerate(notices):
        notice_id = f"{notice.source_site}:{notice.id}"
        result_id = f"{session_id}:{notice_id}"
        indexed_at = metadata.get(notice_id, {}).get("indexed_at", "")
        conn.execute(
            """
            INSERT INTO live_challenge_results(
                id, session_id, notice_id, origin, verification_status,
                source_site, title, publish_time, region, purchaser,
                source_url, indexed_at, position, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (
                result_id,
                session_id,
                notice_id,
                origin,
                verification_status,
                notice.source_site,
                notice.title,
                notice.publish_time,
                notice.region,
                notice.purchaser,
                notice.source_url,
                indexed_at,
                start_position + offset,
                json_dumps(notice.to_dict()),
            ),
        )


def _session_summary(row: Any) -> dict[str, object]:
    local_count = int(row["local_result_count"] or 0)
    online_count = int(row["online_result_count"] or 0)
    return {
        "id": str(row["id"]),
        "category": str(row["category"]),
        "region": str(row["region"]),
        "time_window": str(row["time_window"]),
        "time_window_label": TIME_WINDOWS.get(str(row["time_window"]), str(row["time_window"])),
        "keyword": str(row["keyword"] or ""),
        "normalized_query": str(row["normalized_query"]),
        "intent": _json_object(row["intent_json"]),
        "status": str(row["status"]),
        "local_duration_ms": int(row["local_duration_ms"] or 0),
        "online_duration_ms": int(row["online_duration_ms"] or 0),
        "local_result_count": local_count,
        "online_result_count": online_count,
        "result_count": local_count + online_count,
        "source_summary": _json_list(row["source_summary_json"]),
        "cancel_requested": bool(row["cancel_requested"]),
        "error_text": str(row["error_text"] or ""),
        "created_by": str(row["created_by"]),
        "created_at": str(row["created_at"]),
        "completed_at": str(row["completed_at"] or ""),
    }


def _result_payload(row: Any) -> dict[str, object]:
    return {
        "id": str(row["id"]),
        "notice_id": str(row["notice_id"]),
        "origin": str(row["origin"]),
        "verification_status": str(row["verification_status"]),
        "source_site": str(row["source_site"]),
        "title": str(row["title"]),
        "publish_time": str(row["publish_time"] or ""),
        "region": str(row["region"] or ""),
        "purchaser": str(row["purchaser"] or ""),
        "source_url": str(row["source_url"] or ""),
        "indexed_at": str(row["indexed_at"] or ""),
        "position": int(row["position"] or 0),
        "recorded_at": str(row["created_at"] or ""),
    }


def _source_summary(stats: list[dict[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for item in stats:
        raw_status = str(item.get("status") or "unknown")
        status = "available" if raw_status == "finished" else "not_applicable" if raw_status == "skipped" else "restricted"
        error = str(item.get("error") or "")
        result.append(
            {
                "source": str(item.get("source") or "unknown"),
                "label": str(item.get("source") or "unknown"),
                "status": status,
                "count": int(item.get("count") or 0),
                "detail": error[:180] if error else ("本次查询不适用" if status == "not_applicable" else "已完成联网补充"),
            }
        )
    return result


def _cancel_requested(settings: Settings, session_id: str) -> bool:
    with connection(settings) as conn:
        return _cancel_requested_in_connection(conn, session_id)


def _cancel_requested_in_connection(conn: Any, session_id: str) -> bool:
    row = conn.execute(
        "SELECT cancel_requested FROM live_challenge_sessions WHERE id = ?",
        (str(session_id),),
    ).fetchone()
    return bool(row and row["cancel_requested"])


def _json_object(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: object) -> list[dict[str, object]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []
