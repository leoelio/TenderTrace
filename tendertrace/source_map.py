from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

from tendertrace.adapters.ccgp import CCGP_LIST_URLS
from tendertrace.adapters.ggzy import GGZY_DEAL_LIST_URL, GGZY_LIST_API
from tendertrace.config import Settings
from tendertrace.db import connection
from tendertrace.vault.qianlima import QIANLIMA_SEARCH_URL, QianlimaSessionVault


@dataclass(frozen=True)
class SourceMapRoute:
    name: str
    url: str
    kind: str
    method: str = "GET"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class SourceMapItem:
    site: str
    engine: str
    status: str
    requires_login: bool
    routes: list[SourceMapRoute]
    health: dict[str, object]
    discovery_rules: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["routes"] = [route.to_dict() for route in self.routes]
        return value


def build_source_map(settings: Settings) -> dict[str, object]:
    health = source_health(settings)
    qianlima = QianlimaSessionVault(settings)
    qianlima_status = qianlima.status()
    items = [
        SourceMapItem(
            site="ccgp",
            engine="httpx+managed-fetcher",
            status="configured",
            requires_login=False,
            routes=[
                SourceMapRoute(name=f"ccgp-list-{index + 1}", url=url, kind="list")
                for index, url in enumerate(CCGP_LIST_URLS)
            ],
            health=health.get("ccgp", {}),
            discovery_rules={
                "allow": [r"/cggg/.+\.htm$", r"/cggg/.+\.(pdf|docx?|xlsx?|zip|rar)$"],
                "deny": [r"/zcfg/", r"/xwzx/"],
                "same_domain": True,
            },
        ),
        SourceMapItem(
            site="ggzy",
            engine="httpx+managed-fetcher",
            status="configured",
            requires_login=False,
            routes=[
                SourceMapRoute(name="ggzy-list-api", url=GGZY_LIST_API, kind="api", method="POST"),
                SourceMapRoute(name="ggzy-list-page", url=GGZY_DEAL_LIST_URL, kind="list"),
            ],
            health=health.get("ggzy", {}),
            discovery_rules={
                "allow": [r"/information/deal/html/.+\.html$", r"\.(pdf|docx?|xlsx?|zip|rar)$"],
                "deny": [],
                "same_domain": True,
            },
        ),
        SourceMapItem(
            site="qianlima",
            engine="playwright+storage-state",
            status="configured" if qianlima_status.ready else "login_required",
            requires_login=True,
            routes=[SourceMapRoute(name="qianlima-search", url=QIANLIMA_SEARCH_URL, kind="search")],
            health=health.get("qianlima", {}),
            discovery_rules={
                "allow": [r"/notice/", r"/spxm/", r"\.(pdf|docx?|xlsx?|zip|rar)$"],
                "deny": [r"/login", r"/register"],
                "same_domain": False,
            },
        ),
    ]
    return {
        "items": [item.to_dict() for item in items],
        "source_count": len(items),
        "login_source_ready": qianlima_status.ready,
        "qianlima": qianlima_status.to_dict(),
    }


def source_health(settings: Settings, *, limit: int = 50) -> dict[str, dict[str, object]]:
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT stats_json
            FROM runs
            WHERE status != 'deleted'
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        artifacts = conn.execute(
            """
            SELECT source_site, COUNT(*) AS count
            FROM page_artifacts
            GROUP BY source_site
            """
        ).fetchall()
    artifact_counts = {row["source_site"]: int(row["count"]) for row in artifacts}
    health: dict[str, dict[str, object]] = {}
    for row in rows:
        stats = _loads(row["stats_json"])
        source_stats = stats.get("source_stats")
        if not isinstance(source_stats, list):
            continue
        for item in source_stats:
            if not isinstance(item, dict):
                continue
            site = str(item.get("source") or "").strip()
            if not site:
                continue
            bucket = health.setdefault(site, _empty_health())
            bucket["runs"] = int(bucket["runs"]) + 1
            if item.get("status") == "failed":
                bucket["failed_runs"] = int(bucket["failed_runs"]) + 1
            else:
                bucket["finished_runs"] = int(bucket["finished_runs"]) + 1
            bucket["notices"] = int(bucket["notices"]) + int(item.get("count") or 0)
            fetch_stats = item.get("fetch_stats")
            if isinstance(fetch_stats, dict):
                _merge_fetch_stats(bucket, fetch_stats)
            if item.get("error"):
                bucket["last_error"] = str(item["error"])
    for site, count in artifact_counts.items():
        bucket = health.setdefault(site, _empty_health())
        bucket["page_artifacts"] = count
    for bucket in health.values():
        requests = int(bucket["requests"])
        bucket["success_rate"] = (
            round(float(bucket["succeeded"]) / requests, 3) if requests else None
        )
    return health


def _empty_health() -> dict[str, object]:
    return {
        "runs": 0,
        "finished_runs": 0,
        "failed_runs": 0,
        "notices": 0,
        "requests": 0,
        "succeeded": 0,
        "failed": 0,
        "blocked": 0,
        "retries": 0,
        "browser_fallbacks": 0,
        "page_artifacts": 0,
        "avg_elapsed_ms": 0,
        "last_error": "",
        "success_rate": None,
    }


def _merge_fetch_stats(bucket: dict[str, object], fetch_stats: dict[str, Any]) -> None:
    previous_requests = int(bucket["requests"])
    incoming_requests = int(fetch_stats.get("requests") or 0)
    bucket["requests"] = previous_requests + incoming_requests
    for key in ("succeeded", "failed", "blocked", "retries", "browser_fallbacks"):
        bucket[key] = int(bucket[key]) + int(fetch_stats.get(key) or 0)
    incoming_avg = int(fetch_stats.get("avg_elapsed_ms") or 0)
    total_requests = int(bucket["requests"])
    if total_requests:
        bucket["avg_elapsed_ms"] = int(
            (int(bucket["avg_elapsed_ms"]) * previous_requests + incoming_avg * incoming_requests)
            / total_requests
        )
    if fetch_stats.get("last_error"):
        bucket["last_error"] = str(fetch_stats["last_error"])


def _loads(value: str) -> dict[str, Any]:
    try:
        payload = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
