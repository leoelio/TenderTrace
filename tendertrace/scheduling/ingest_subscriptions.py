from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps
from tendertrace.ingest import IngestCycleResult, run_ingest_cycle
from tendertrace.runner import NoticeAdapter


@dataclass(frozen=True)
class IngestSubscription:
    id: str
    name: str
    topics: list[str]
    regions: list[str]
    cron: str
    timezone: str
    window_days: int
    max_pages: int
    max_results: int
    status: str
    created_at: str | None = None
    updated_at: str | None = None
    last_run_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def create_ingest_subscription(
    settings: Settings,
    *,
    name: str,
    topics: list[str],
    regions: list[str],
    cron: str | None = None,
    timezone: str | None = None,
    window_days: int = 30,
    max_pages: int = 1,
    max_results: int = 20,
) -> IngestSubscription:
    init_db(settings)
    _validate_pool(topics, "topics")
    _validate_pool(regions, "regions")
    _validate_positive(window_days, "window_days")
    _validate_positive(max_pages, "max_pages")
    _validate_positive(max_results, "max_results")
    subscription_id = str(uuid4())
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO ingest_subscriptions(
                id, name, topics_json, regions_json, cron, timezone,
                window_days, max_pages, max_results
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                subscription_id,
                name.strip() or "ingest",
                json_dumps(topics),
                json_dumps(regions),
                cron or settings.ingest_cron,
                timezone or settings.timezone,
                window_days,
                max_pages,
                max_results,
            ),
        )
    subscription = get_ingest_subscription(settings, subscription_id)
    if subscription is None:
        raise RuntimeError("ingest subscription was not persisted")
    return subscription


def ensure_ingest_subscription(
    settings: Settings,
    *,
    name: str,
    topics: list[str],
    regions: list[str],
    cron: str | None = None,
    timezone: str | None = None,
    window_days: int = 30,
    max_pages: int = 1,
    max_results: int = 20,
) -> tuple[IngestSubscription, bool]:
    init_db(settings)
    normalized_topics = _normalize_pool(topics)
    normalized_regions = _normalize_pool(regions)
    _validate_pool(normalized_topics, "topics")
    _validate_pool(normalized_regions, "regions")
    _validate_positive(window_days, "window_days")
    _validate_positive(max_pages, "max_pages")
    _validate_positive(max_results, "max_results")
    for subscription in list_ingest_subscriptions(settings):
        if _same_pool(subscription.topics, normalized_topics) and _same_pool(
            subscription.regions, normalized_regions
        ):
            return subscription, False

    identity = json.dumps(
        {
            "regions": sorted(value.casefold() for value in normalized_regions),
            "topics": sorted(value.casefold() for value in normalized_topics),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    subscription_id = str(uuid5(NAMESPACE_URL, f"tendertrace:adaptive-ingest:{identity}"))
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO ingest_subscriptions(
                id, name, topics_json, regions_json, cron, timezone,
                window_days, max_pages, max_results, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                topics_json = excluded.topics_json,
                regions_json = excluded.regions_json,
                cron = excluded.cron,
                timezone = excluded.timezone,
                window_days = excluded.window_days,
                max_pages = excluded.max_pages,
                max_results = excluded.max_results,
                status = 'active',
                updated_at = datetime('now')
            """,
            (
                subscription_id,
                name.strip() or "adaptive-ingest",
                json_dumps(normalized_topics),
                json_dumps(normalized_regions),
                cron or settings.ingest_cron,
                timezone or settings.timezone,
                window_days,
                max_pages,
                max_results,
            ),
        )
    subscription = get_ingest_subscription(settings, subscription_id)
    if subscription is None:
        raise RuntimeError("adaptive ingest subscription was not persisted")
    return subscription, True


def get_ingest_subscription(
    settings: Settings,
    subscription_id: str,
) -> IngestSubscription | None:
    with connection(settings) as conn:
        row = conn.execute(
            """
            SELECT id, name, topics_json, regions_json, cron, timezone,
                   window_days, max_pages, max_results, status,
                   created_at, updated_at, last_run_at
            FROM ingest_subscriptions
            WHERE id = ?
            """,
            (subscription_id,),
        ).fetchone()
    return _subscription_from_row(row) if row else None


def list_ingest_subscriptions(
    settings: Settings,
    *,
    include_inactive: bool = False,
) -> list[IngestSubscription]:
    where = "" if include_inactive else "WHERE status = 'active'"
    with connection(settings) as conn:
        rows = conn.execute(
            f"""
            SELECT id, name, topics_json, regions_json, cron, timezone,
                   window_days, max_pages, max_results, status,
                   created_at, updated_at, last_run_at
            FROM ingest_subscriptions
            {where}
            ORDER BY created_at DESC
            """
        ).fetchall()
    return [_subscription_from_row(row) for row in rows]


def run_ingest_subscription(
    settings: Settings,
    *,
    subscription_id: str,
    adapter: NoticeAdapter | None = None,
) -> IngestCycleResult:
    subscription = get_ingest_subscription(settings, subscription_id)
    if subscription is None:
        raise ValueError("ingest subscription not found")
    if subscription.status != "active":
        raise ValueError("ingest subscription is not active")
    result = run_ingest_cycle(
        settings,
        topics=subscription.topics,
        regions=subscription.regions,
        window_days=subscription.window_days,
        max_pages=subscription.max_pages,
        max_results=subscription.max_results,
        adapter=adapter,
    )
    with connection(settings) as conn:
        conn.execute(
            """
            UPDATE ingest_subscriptions
            SET last_run_at = datetime('now'), updated_at = datetime('now')
            WHERE id = ?
            """,
            (subscription.id,),
        )
    return result


def delete_ingest_subscription(settings: Settings, subscription_id: str) -> bool:
    with connection(settings) as conn:
        row = conn.execute(
            "SELECT id FROM ingest_subscriptions WHERE id = ?",
            (subscription_id,),
        ).fetchone()
        if row is None:
            return False
        conn.execute(
            """
            UPDATE ingest_subscriptions
            SET status = 'deleted', updated_at = datetime('now')
            WHERE id = ?
            """,
            (subscription_id,),
        )
    return True


def _subscription_from_row(row) -> IngestSubscription:
    return IngestSubscription(
        id=row["id"],
        name=row["name"],
        topics=_loads_list(row["topics_json"]),
        regions=_loads_list(row["regions_json"]),
        cron=row["cron"],
        timezone=row["timezone"],
        window_days=int(row["window_days"]),
        max_pages=int(row["max_pages"]),
        max_results=int(row["max_results"]),
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_run_at=row["last_run_at"],
    )


def _loads_list(value: str) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _validate_pool(values: list[str], name: str) -> None:
    if not values or not all(str(item).strip() for item in values):
        raise ValueError(f"{name} must contain at least one non-empty value")


def _normalize_pool(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value).strip()
        key = item.casefold()
        if not item or key in seen:
            continue
        seen.add(key)
        normalized.append(item)
    return normalized


def _same_pool(left: list[str], right: list[str]) -> bool:
    return {value.strip().casefold() for value in left} == {
        value.strip().casefold() for value in right
    }


def _validate_positive(value: int, name: str) -> None:
    if value < 1:
        raise ValueError(f"{name} must be positive")
