from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

from tendertrace.adapters.ccgp import CCGP_LIST_URLS
from tendertrace.adapters.ggzy import GGZY_DEAL_LIST_URL, GGZY_LIST_API
from tendertrace.adapters.idb import IDB_DATASTORE_API
from tendertrace.adapters.ted import TED_SEARCH_API
from tendertrace.adapters.uk_ocds import (
    CONTRACTS_FINDER_API,
    CONTRACTS_FINDER_SEARCH,
    FIND_TENDER_API,
    FIND_TENDER_SEARCH,
)
from tendertrace.adapters.ungm import UNGM_SEARCH_URL
from tendertrace.adapters.worldbank import WORLD_BANK_API
from tendertrace.config import Settings
from tendertrace.db import connection
from tendertrace.vault.qianlima import QIANLIMA_MEMBER_SEARCH_URL, QianlimaSessionVault


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
    qianlima_health = health.get("qianlima", {})
    qianlima_expired = _qianlima_login_expired(qianlima_health)
    qianlima_ready = qianlima_status.ready and not qianlima_expired
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
            site="ted",
            engine="official-json-api",
            status="configured",
            requires_login=False,
            routes=[
                SourceMapRoute(name="ted-search-api", url=TED_SEARCH_API, kind="api", method="POST")
            ],
            health=health.get("ted", {}),
            discovery_rules={
                "scope": ["global", "eu"],
                "authority": "Publications Office of the European Union",
                "same_domain": True,
            },
        ),
        SourceMapItem(
            site="ungm",
            engine="official-public-search",
            status="configured",
            requires_login=False,
            routes=[
                SourceMapRoute(
                    name="ungm-procurement-search",
                    url=UNGM_SEARCH_URL,
                    kind="api",
                    method="POST",
                )
            ],
            health=health.get("ungm", {}),
            discovery_rules={
                "scope": ["global"],
                "authority": "United Nations Global Marketplace",
                "coverage": "32 UN organizations",
                "same_domain": True,
            },
        ),
        SourceMapItem(
            site="worldbank",
            engine="official-json-api",
            status="configured",
            requires_login=False,
            routes=[
                SourceMapRoute(name="worldbank-procurement-api", url=WORLD_BANK_API, kind="api")
            ],
            health=health.get("worldbank", {}),
            discovery_rules={
                "scope": ["global", "worldbank"],
                "authority": "World Bank Group",
                "same_domain": False,
            },
        ),
        SourceMapItem(
            site="idb",
            engine="official-ckan-api",
            status="configured",
            requires_login=False,
            routes=[
                SourceMapRoute(name="idb-procurement-datastore", url=IDB_DATASTORE_API, kind="api")
            ],
            health=health.get("idb", {}),
            discovery_rules={
                "scope": ["global", "idb"],
                "authority": "Inter-American Development Bank",
                "license": "CC BY 4.0",
                "same_domain": True,
            },
        ),
        SourceMapItem(
            site="contracts_finder",
            engine="official-search+ocds",
            status="configured",
            requires_login=False,
            routes=[
                SourceMapRoute(
                    name="uk-contracts-finder-ocds", url=CONTRACTS_FINDER_API, kind="api"
                ),
                SourceMapRoute(
                    name="uk-contracts-finder-search",
                    url=CONTRACTS_FINDER_SEARCH,
                    kind="search",
                    method="POST",
                ),
            ],
            health=health.get("contracts_finder", {}),
            discovery_rules={
                "scope": ["global", "uk"],
                "authority": "UK Cabinet Office",
                "standard": "OCDS 1.1",
                "same_domain": True,
            },
        ),
        SourceMapItem(
            site="find_tender",
            engine="official-search+ocds",
            status="configured",
            requires_login=False,
            routes=[
                SourceMapRoute(name="uk-find-tender-ocds", url=FIND_TENDER_API, kind="api"),
                SourceMapRoute(
                    name="uk-find-tender-search",
                    url=FIND_TENDER_SEARCH,
                    kind="search",
                    method="POST",
                ),
            ],
            health=health.get("find_tender", {}),
            discovery_rules={
                "scope": ["global", "uk"],
                "authority": "UK Cabinet Office",
                "standard": "OCDS 1.1",
                "same_domain": True,
            },
        ),
        SourceMapItem(
            site="qianlima",
            engine="playwright+storage-state",
            status=(
                "configured"
                if qianlima_ready
                else "login_expired"
                if qianlima_expired
                else "login_required"
            ),
            requires_login=True,
            routes=[
                SourceMapRoute(
                    name="qianlima-member-search",
                    url=QIANLIMA_MEMBER_SEARCH_URL,
                    kind="search",
                )
            ],
            health=qianlima_health,
            discovery_rules={
                "allow": [r"/bid-\d+\.html$", r"/notice/", r"\.(pdf|docx?|xlsx?|zip|rar)$"],
                "deny": [r"/login", r"/register"],
                "same_domain": False,
            },
        ),
    ]
    qianlima_payload = qianlima_status.to_dict()
    qianlima_payload["storage_state_ready"] = qianlima_status.ready
    if qianlima_expired:
        qianlima_payload.update(
            {
                "ready": False,
                "validation": "expired",
                "detail": "登录态已过期，请运行 python -m tendertrace login-qianlima 重新保存",
            }
        )
    return {
        "items": [item.to_dict() for item in items],
        "source_count": len(items),
        "login_source_ready": qianlima_ready,
        "qianlima": qianlima_payload,
    }


def source_health(settings: Settings, *, limit: int = 50) -> dict[str, dict[str, object]]:
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT started_at, stats_json
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
            status = str(item.get("status") or "")
            if status == "skipped":
                bucket["skipped_runs"] = int(bucket["skipped_runs"]) + 1
                continue
            bucket["runs"] = int(bucket["runs"]) + 1
            if not bucket["last_run_at"]:
                bucket["last_run_at"] = str(row["started_at"] or "")
            if status == "failed":
                bucket["failed_runs"] = int(bucket["failed_runs"]) + 1
            else:
                bucket["finished_runs"] = int(bucket["finished_runs"]) + 1
                if not bucket["last_success_at"]:
                    bucket["last_success_at"] = str(row["started_at"] or "")
            if int(item.get("count") or 0) > 0:
                bucket["hit_runs"] = int(bucket["hit_runs"]) + 1
            bucket["notices"] = int(bucket["notices"]) + int(item.get("count") or 0)
            fetch_stats = item.get("fetch_stats")
            if isinstance(fetch_stats, dict):
                _merge_fetch_stats(bucket, fetch_stats)
            if item.get("error") and not bucket["last_error"]:
                bucket["last_error"] = str(item["error"])
    for site, count in artifact_counts.items():
        bucket = health.setdefault(site, _empty_health())
        bucket["page_artifacts"] = count
    for bucket in health.values():
        requests = int(bucket["requests"])
        bucket["success_rate"] = (
            round(float(bucket["succeeded"]) / requests, 3) if requests else None
        )
        bucket["hit_rate"] = (
            round(float(bucket["hit_runs"]) / int(bucket["runs"]), 3)
            if int(bucket["runs"])
            else None
        )
        bucket["reliability_score"] = _reliability_score(bucket)
        bucket["health_status"] = _health_status(bucket)
    return health


def _empty_health() -> dict[str, object]:
    return {
        "runs": 0,
        "finished_runs": 0,
        "failed_runs": 0,
        "skipped_runs": 0,
        "hit_runs": 0,
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
        "hit_rate": None,
        "reliability_score": 0.0,
        "health_status": "unknown",
        "last_run_at": "",
        "last_success_at": "",
    }


def _reliability_score(bucket: dict[str, object]) -> float:
    runs = int(bucket["runs"])
    if not runs:
        return 0.0
    requests = int(bucket["requests"])
    request_success = bucket["success_rate"]
    run_success = float(bucket["finished_runs"]) / runs
    success = (
        0.6 * float(request_success) + 0.4 * run_success
        if request_success is not None
        else run_success
    )
    hit_rate = float(bucket["hit_rate"] or 0.0)
    blocked_ratio = float(bucket["blocked"]) / requests if requests else 0.0
    latency_ms = int(bucket["avg_elapsed_ms"])
    latency_score = 1.0 if latency_ms <= 1500 else 0.7 if latency_ms <= 4000 else 0.35
    return round(
        max(
            0.0,
            0.55 * success
            + 0.20 * hit_rate
            + 0.15 * (1 - blocked_ratio)
            + 0.10 * latency_score,
        ),
        3,
    )


def _health_status(bucket: dict[str, object]) -> str:
    if not int(bucket["runs"]):
        return "unknown"
    score = float(bucket["reliability_score"])
    if score >= 0.85:
        return "healthy"
    if score >= 0.6:
        return "degraded"
    return "unhealthy"


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
    if fetch_stats.get("last_error") and not bucket["last_error"]:
        bucket["last_error"] = str(fetch_stats["last_error"])


def _qianlima_login_expired(health: dict[str, object]) -> bool:
    error = str(health.get("last_error") or "").casefold()
    return "qianlima login session expired" in error


def _loads(value: str) -> dict[str, Any]:
    try:
        payload = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
