from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from typing import Any
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps
from tendertrace.intent import compile_intent
from tendertrace.runner import NoticeAdapter, RunOnceResult, run_once


@dataclass(frozen=True)
class Subscription:
    id: str
    original_query: str
    bidql: dict[str, Any]
    schedule_kind: str
    cron: str | None
    timezone: str
    status: str
    created_at: str | None = None
    updated_at: str | None = None
    last_run_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def create_subscription(
    settings: Settings,
    *,
    query: str,
    now: datetime | None = None,
    max_pages: int = 1,
    max_results: int = 10,
    schedule_override: dict[str, Any] | None = None,
    model_strategy: str | None = None,
) -> Subscription:
    init_db(settings)
    bidql = compile_intent(query, now=now)
    if schedule_override:
        bidql["schedule"] = _schedule_from_override(schedule_override, settings.timezone)
    schedule = bidql.get("schedule", {})
    schedule_kind = str(schedule.get("kind") or "immediate")
    if schedule_kind == "immediate":
        raise ValueError("subscription query must include a sending time or frequency")
    runtime: dict[str, Any] = {"max_pages": max_pages, "max_results": max_results}
    if model_strategy:
        runtime["model_strategy"] = model_strategy
    bidql["_runtime"] = runtime
    subscription_id = str(uuid4())
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO subscriptions(
                id, original_query, bidql_json, schedule_kind, cron, timezone
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                subscription_id,
                query,
                json_dumps(bidql),
                schedule_kind,
                schedule.get("cron"),
                str(schedule.get("tz") or settings.timezone),
            ),
        )
    subscription = get_subscription(settings, subscription_id)
    if subscription is None:
        raise RuntimeError("subscription was not persisted")
    return subscription


def get_subscription(settings: Settings, subscription_id: str) -> Subscription | None:
    with connection(settings) as conn:
        row = conn.execute(
            """
            SELECT id, original_query, bidql_json, schedule_kind, cron, timezone,
                   status, created_at, updated_at, last_run_at
            FROM subscriptions
            WHERE id = ?
            """,
            (subscription_id,),
        ).fetchone()
    return _subscription_from_row(row) if row else None


def list_subscriptions(settings: Settings, *, include_inactive: bool = False) -> list[Subscription]:
    where = "" if include_inactive else "WHERE status = 'active'"
    with connection(settings) as conn:
        rows = conn.execute(
            f"""
            SELECT id, original_query, bidql_json, schedule_kind, cron, timezone,
                   status, created_at, updated_at, last_run_at
            FROM subscriptions
            {where}
            ORDER BY created_at DESC
            """
        ).fetchall()
    return [_subscription_from_row(row) for row in rows]


def run_subscription(
    settings: Settings,
    *,
    subscription_id: str,
    now: datetime | None = None,
    adapter: NoticeAdapter | None = None,
) -> RunOnceResult:
    subscription = get_subscription(settings, subscription_id)
    if subscription is None:
        raise ValueError("subscription not found")
    if subscription.status != "active":
        raise ValueError("subscription is not active")
    runtime = subscription.bidql.get("_runtime", {})
    max_pages = int(runtime.get("max_pages") or 1)
    max_results = int(runtime.get("max_results") or 10)
    model_strategy = str(runtime.get("model_strategy") or "config")
    result = run_once(
        settings=settings,
        query=subscription.original_query,
        now=now,
        max_pages=max_pages,
        max_results=max_results,
        adapter=adapter,
        subscription_id=subscription.id,
        incremental=True,
        model_strategy=model_strategy,
    )
    with connection(settings) as conn:
        conn.execute(
            """
            UPDATE subscriptions
            SET last_run_at = datetime('now'), updated_at = datetime('now')
            WHERE id = ?
            """,
            (subscription.id,),
        )
    return result


def _subscription_from_row(row) -> Subscription:
    return Subscription(
        id=row["id"],
        original_query=row["original_query"],
        bidql=json.loads(row["bidql_json"]),
        schedule_kind=row["schedule_kind"],
        cron=row["cron"],
        timezone=row["timezone"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_run_at=row["last_run_at"],
    )


def _schedule_from_override(value: dict[str, Any], timezone: str) -> dict[str, Any]:
    kind = str(value.get("kind") or "recurring")
    time_value = _normalize_time(str(value.get("time") or "09:00"))
    hour, minute = [int(part) for part in time_value.split(":", 1)]
    if kind == "once_at":
        return {
            "kind": "once_at",
            "time": time_value,
            "tz": timezone,
            "origin": "ui_override",
        }
    if kind != "recurring":
        raise ValueError("schedule.kind must be recurring or once_at")
    frequency = str(value.get("frequency") or "daily")
    if frequency == "daily":
        cron = f"{minute} {hour} * * *"
    elif frequency == "weekly":
        weekday = int(value.get("weekday") or 1)
        if weekday < 0 or weekday > 6:
            raise ValueError("schedule.weekday must be between 0 and 6")
        cron = f"{minute} {hour} * * {weekday}"
    elif frequency == "monthly":
        day = int(value.get("day") or 1)
        if day < 1 or day > 31:
            raise ValueError("schedule.day must be between 1 and 31")
        cron = f"{minute} {hour} {day} * *"
    else:
        raise ValueError("schedule.frequency must be daily, weekly or monthly")
    return {
        "kind": "recurring",
        "frequency": frequency,
        "cron": cron,
        "time": time_value,
        "tz": timezone,
        "origin": "ui_override",
    }


def _normalize_time(value: str) -> str:
    parts = value.strip().split(":", 1)
    if len(parts) != 2:
        raise ValueError("schedule.time must use HH:MM")
    hour = int(parts[0])
    minute = int(parts[1])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("schedule.time must be a valid HH:MM value")
    return f"{hour:02d}:{minute:02d}"
