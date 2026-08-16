from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import re
import sqlite3
from typing import Any

import jieba

from tendertrace.adapters.ccgp import Attachment, Notice
from tendertrace.config import Settings
from tendertrace.db import FTS_DDL, connection
from tendertrace.vector import VectorUnavailable, cosine_similarity, embed_query


_INTERNATIONAL_SOURCE_SCOPES = {
    "ted": {"global", "eu"},
    "ungm": {"global"},
    "worldbank": {"global", "worldbank"},
    "idb": {"global", "idb"},
    "adb": {"global", "adb"},
    "afdb": {"global", "afdb"},
    "contracts_finder": {"global", "uk"},
    "find_tender": {"global", "uk"},
}


@dataclass(frozen=True)
class LocalSearchResult:
    notices: list[Notice]
    stats: dict[str, object]


def upsert_notice_fts(
    conn: sqlite3.Connection,
    *,
    notice_id: str,
    title: str,
    content_text: str,
    core_content: str = "",
) -> None:
    if not ensure_notice_fts(conn):
        return
    conn.execute("DELETE FROM notices_fts WHERE notice_id = ?", (notice_id,))
    conn.execute(
        "INSERT INTO notices_fts(notice_id, title, content_text) VALUES (?, ?, ?)",
        (
            notice_id,
            segment_for_fts(title),
            segment_for_fts(f"{content_text} {core_content}"),
        ),
    )


def search_notices(
    settings: Settings,
    bidql: dict[str, Any],
    *,
    max_results: int = 10,
) -> LocalSearchResult:
    with connection(settings) as conn:
        engine = "fts5" if ensure_notice_fts(conn) else "like"
        if engine == "fts5":
            rebuild_notice_fts_if_needed(conn)
        exact, vector_stats = _search_with_optional_vector(
            conn,
            settings,
            bidql,
            max_results=max_results,
            engine=engine,
            relax_city=False,
        )
        if exact or not _has_city_scope(bidql):
            return LocalSearchResult(
                notices=exact,
                stats={
                    "source": f"local_{engine}",
                    "status": "finished",
                    "count": len(exact),
                    "relaxed_city": False,
                    "engine": engine,
                    **vector_stats,
                },
            )
        relaxed, relaxed_vector_stats = _search_with_optional_vector(
            conn,
            settings,
            bidql,
            max_results=max_results,
            engine=engine,
            relax_city=True,
        )
        return LocalSearchResult(
            notices=relaxed,
            stats={
                "source": f"local_{engine}",
                "status": "finished",
                "count": len(relaxed),
                "relaxed_city": bool(relaxed),
                "engine": engine,
                **relaxed_vector_stats,
            },
        )


def ensure_notice_fts(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute(FTS_DDL)
        return True
    except sqlite3.OperationalError:
        return False


def rebuild_notice_fts_if_needed(conn: sqlite3.Connection) -> None:
    notice_count = conn.execute("SELECT COUNT(*) FROM notices").fetchone()[0]
    fts_count = conn.execute("SELECT COUNT(*) FROM notices_fts").fetchone()[0]
    if fts_count >= notice_count:
        return
    conn.execute("DELETE FROM notices_fts")
    rows = conn.execute(
        "SELECT id, title, content_text, core_content FROM notices ORDER BY created_at"
    ).fetchall()
    for row in rows:
        upsert_notice_fts(
            conn,
            notice_id=row["id"],
            title=row["title"] or "",
            content_text=row["content_text"] or "",
            core_content=row["core_content"] or "",
        )


def segment_for_fts(text: str) -> str:
    tokens = []
    for token in jieba.lcut_for_search(text or ""):
        token = token.strip()
        if _valid_token(token):
            tokens.append(token)
    return " ".join(_dedupe(tokens))


def _search_once(
    conn: sqlite3.Connection,
    bidql: dict[str, Any],
    *,
    max_results: int,
    engine: str,
    relax_city: bool,
) -> list[Notice]:
    where, params = _filters(bidql, relax_city=relax_city)
    topic_terms = _topic_terms(bidql)
    if engine == "fts5" and topic_terms:
        query = _fts_query(topic_terms)
        if not query:
            return []
        rows = conn.execute(
            f"""
            SELECT n.*, bm25(notices_fts, 8.0, 1.0) AS rank
            FROM notices_fts
            JOIN notices n ON n.id = notices_fts.notice_id
            WHERE notices_fts MATCH ?
              {where}
            ORDER BY rank ASC, n.publish_time DESC, n.created_at DESC
            LIMIT ?
            """,
            (query, *params, max_results),
        ).fetchall()
        return [_notice_from_row(row) for row in rows]
    where_like, like_params = _topic_like_filter(topic_terms)
    rows = conn.execute(
        f"""
        SELECT n.*, 0.0 AS rank
        FROM notices n
        WHERE 1 = 1
          {where}
          {where_like}
        ORDER BY n.publish_time DESC, n.created_at DESC
        LIMIT ?
        """,
        (*params, *like_params, max_results),
    ).fetchall()
    return [_notice_from_row(row) for row in rows]


def _search_with_optional_vector(
    conn: sqlite3.Connection,
    settings: Settings,
    bidql: dict[str, Any],
    *,
    max_results: int,
    engine: str,
    relax_city: bool,
) -> tuple[list[Notice], dict[str, object]]:
    lexical = _search_once(conn, bidql, max_results=max_results, engine=engine, relax_city=relax_city)
    if not settings.vector_enabled:
        return lexical, {"vector_status": "disabled", "vector_retrieved": 0}
    vector, status = _vector_search_once(
        conn,
        settings,
        bidql,
        max_results=max_results,
        relax_city=relax_city,
    )
    if not vector:
        return lexical, {"vector_status": status, "vector_retrieved": 0}
    return _rrf_merge(lexical, vector, max_results=max_results), {
        "vector_status": status,
        "vector_retrieved": len(vector),
        "engine": f"{engine}+vector",
    }


def _vector_search_once(
    conn: sqlite3.Connection,
    settings: Settings,
    bidql: dict[str, Any],
    *,
    max_results: int,
    relax_city: bool,
) -> tuple[list[Notice], str]:
    query_text = _vector_query_text(bidql)
    if not query_text:
        return [], "empty_query"
    try:
        query_vector = embed_query(settings, query_text)
    except VectorUnavailable:
        return [], "unavailable"
    where, params = _filters(bidql, relax_city=relax_city)
    rows = conn.execute(
        f"""
        SELECT n.*, e.vector_json
        FROM notice_embeddings e
        JOIN notices n ON n.id = e.notice_id
        WHERE e.model = ?
          {where}
        ORDER BY n.publish_time DESC, n.created_at DESC
        LIMIT ?
        """,
        (settings.vector_model, *params, max(settings.vector_top_k * 10, max_results)),
    ).fetchall()
    scored: list[tuple[float, Notice]] = []
    for row in rows:
        try:
            vector = [float(value) for value in json.loads(row["vector_json"])]
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        score = cosine_similarity(query_vector, vector)
        if score > 0:
            scored.append((score, _notice_from_row(row)))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [notice for _score, notice in scored[:max_results]], "finished"


def _rrf_merge(
    lexical: list[Notice],
    vector: list[Notice],
    *,
    max_results: int,
) -> list[Notice]:
    notices: dict[str, Notice] = {}
    scores: dict[str, float] = {}
    for source in (lexical, vector):
        for rank, notice in enumerate(source, start=1):
            key = _notice_key(notice)
            notices.setdefault(key, notice)
            scores[key] = scores.get(key, 0.0) + 1.0 / (60 + rank)
    ordered = sorted(scores, key=lambda key: scores[key], reverse=True)
    return [notices[key] for key in ordered[:max_results]]


def _vector_query_text(bidql: dict[str, Any]) -> str:
    parts: list[str] = []
    region = bidql.get("region")
    if isinstance(region, dict):
        parts.extend(str(region.get(key) or "") for key in ("province", "city", "district"))
    parts.extend(_topic_terms(bidql))
    return " ".join(part for part in _dedupe([part.strip() for part in parts]) if part)


def _notice_key(notice: Notice) -> str:
    if notice.source_site and notice.id:
        return f"{notice.source_site}:{notice.id}"
    return notice.source_url or notice.title


def _filters(bidql: dict[str, Any], *, relax_city: bool) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    window = bidql.get("time", {}).get("resolved_window")
    if isinstance(window, dict) and window.get("from") and window.get("to"):
        clauses.append(
            "AND n.publish_time IS NOT NULL "
            "AND date(substr(n.publish_time, 1, 10)) BETWEEN date(?) AND date(?)"
        )
        params.extend([window["from"], window["to"]])

    region = bidql.get("region")
    if isinstance(region, dict):
        scope = str(region.get("scope") or "domestic")
        source_clause, source_params = _source_scope_filter(scope)
        clauses.append(source_clause)
        params.extend(source_params)
        if scope == "domestic":
            if not relax_city and region.get("district_aliases"):
                clause, values = _alias_filter(
                    [str(item) for item in region["district_aliases"]]
                )
                clauses.append(f"AND ({clause})")
                params.extend(values)
            elif not relax_city and region.get("city_aliases"):
                clause, values = _alias_filter([str(item) for item in region["city_aliases"]])
                clauses.append(f"AND ({clause})")
                params.extend(values)
            elif region.get("aliases"):
                aliases = [
                    str(item)
                    for item in region["aliases"]
                    if item and item not in set(region.get("city_aliases") or [])
                ]
                clause, values = _alias_filter(aliases)
                clauses.append(f"AND ({clause})")
                params.extend(values)

    negatives = bidql.get("topic", {}).get("negative", [])
    for term in negatives if isinstance(negatives, list) else []:
        clauses.append("AND n.title NOT LIKE ? AND COALESCE(n.content_text, '') NOT LIKE ?")
        params.extend([f"%{term}%", f"%{term}%"])
    return "\n          ".join(clauses), params


def _source_scope_filter(scope: str) -> tuple[str, list[object]]:
    international = list(_INTERNATIONAL_SOURCE_SCOPES)
    if scope == "domestic":
        placeholders = ", ".join("?" for _ in international)
        return f"AND n.source_site NOT IN ({placeholders})", international
    allowed = [
        source_site
        for source_site, scopes in _INTERNATIONAL_SOURCE_SCOPES.items()
        if scope in scopes
    ]
    if not allowed:
        return "AND 1 = 0", []
    placeholders = ", ".join("?" for _ in allowed)
    return f"AND n.source_site IN ({placeholders})", allowed


def _alias_filter(aliases: list[str]) -> tuple[str, list[object]]:
    values = [item for item in _dedupe(aliases) if item]
    if not values:
        return "1 = 1", []
    fields = (
        "COALESCE(n.region, '')",
        "COALESCE(n.title, '')",
        "COALESCE(n.content_text, '')",
        "COALESCE(n.purchaser, '')",
    )
    clauses: list[str] = []
    params: list[object] = []
    for alias in values:
        clauses.append("(" + " OR ".join(f"{field} LIKE ?" for field in fields) + ")")
        params.extend([f"%{alias}%"] * len(fields))
    return " OR ".join(clauses), params


def _topic_like_filter(terms: list[str]) -> tuple[str, list[object]]:
    if not terms:
        return "", []
    fields = ("COALESCE(n.title, '')", "COALESCE(n.content_text, '')")
    clauses: list[str] = []
    params: list[object] = []
    for term in terms:
        clauses.append("(" + " OR ".join(f"{field} LIKE ?" for field in fields) + ")")
        params.extend([f"%{term}%"] * len(fields))
    return "AND (" + " OR ".join(clauses) + ")", params


def _topic_terms(bidql: dict[str, Any]) -> list[str]:
    topic = bidql.get("topic")
    if not isinstance(topic, dict):
        return []
    terms = [str(item) for item in topic.get("core", []) if item]
    terms.extend(str(item) for item in topic.get("source_terms", []) if item)
    for item in topic.get("expanded", []):
        if isinstance(item, dict) and item.get("term"):
            terms.append(str(item["term"]))
        elif item:
            terms.append(str(item))
    return _dedupe(terms)


def _fts_query(terms: list[str]) -> str:
    groups: list[str] = []
    for term in terms:
        tokens = _dedupe(segment_for_fts(term).split())
        quoted = [f'"{token.replace(chr(34), chr(34) + chr(34))}"' for token in tokens]
        if quoted:
            groups.append(f"({' AND '.join(quoted)})" if len(quoted) > 1 else quoted[0])
    return " OR ".join(_dedupe(groups))


def _notice_from_row(row: sqlite3.Row) -> Notice:
    fields = _loads(row["fields_json"], {})
    attachments = [
        Attachment(name=str(item.get("name") or ""), url=str(item.get("url") or ""))
        for item in _loads(row["attachments_json"], [])
        if isinstance(item, dict)
    ]
    return Notice(
        id=str(row["id"]).split(":", 1)[-1],
        source_site=str(row["source_site"] or ""),
        title=str(row["title"] or ""),
        publish_time=str(row["publish_time"] or ""),
        region=str(row["region"] or ""),
        purchaser=str(row["purchaser"] or ""),
        source_url=str(row["source_url"] or ""),
        content_text=str(row["content_text"] or ""),
        core_content=str(row["core_content"] or ""),
        attachments=attachments,
        fields=fields,
    )


def _loads(value: object, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return fallback


def _has_city_scope(bidql: dict[str, Any]) -> bool:
    region = bidql.get("region")
    return isinstance(region, dict) and bool(region.get("city"))


def _valid_token(token: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9\u4e00-\u9fff]{1,40}", token))


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def parse_date(value: str) -> date | None:
    match = re.search(
        r"(?<!\d)(20\d{2})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})\s*日?",
        value or "",
    )
    if match:
        try:
            return date(*(int(part) for part in match.groups()))
        except ValueError:
            return None
    return None
