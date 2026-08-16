from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

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
    delivery_channels: list[str] | tuple[str, ...] | None = None,
    feishu_receive_id: str | None = None,
    feishu_receive_id_type: str | None = None,
) -> Subscription:
    init_db(settings)
    bidql, schedule_kind, schedule = _prepare_subscription(
        settings,
        query=query,
        now=now,
        max_pages=max_pages,
        max_results=max_results,
        schedule_override=schedule_override,
        model_strategy=model_strategy,
        delivery_channels=delivery_channels,
        feishu_receive_id=feishu_receive_id,
        feishu_receive_id_type=feishu_receive_id_type,
    )
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


def ensure_subscription(
    settings: Settings,
    *,
    query: str,
    now: datetime | None = None,
    max_pages: int = 1,
    max_results: int = 10,
    schedule_override: dict[str, Any] | None = None,
    model_strategy: str | None = None,
    delivery_channels: list[str] | tuple[str, ...] | None = None,
    feishu_receive_id: str | None = None,
    feishu_receive_id_type: str | None = None,
) -> tuple[Subscription, bool]:
    init_db(settings)
    bidql, schedule_kind, schedule = _prepare_subscription(
        settings,
        query=query,
        now=now,
        max_pages=max_pages,
        max_results=max_results,
        schedule_override=schedule_override,
        model_strategy=model_strategy,
        delivery_channels=delivery_channels,
        feishu_receive_id=feishu_receive_id,
        feishu_receive_id_type=feishu_receive_id_type,
    )
    identity = _subscription_identity(
        query=query,
        schedule_kind=schedule_kind,
        cron=schedule.get("cron"),
        timezone=str(schedule.get("tz") or settings.timezone),
        bidql=bidql,
    )
    for existing in list_subscriptions(settings, include_inactive=True):
        if _subscription_identity(
            query=existing.original_query,
            schedule_kind=existing.schedule_kind,
            cron=existing.cron,
            timezone=existing.timezone,
            bidql=existing.bidql,
        ) != identity:
            continue
        with connection(settings) as conn:
            conn.execute(
                """
                UPDATE subscriptions
                SET bidql_json = ?, status = 'active', updated_at = datetime('now')
                WHERE id = ?
                """,
                (json_dumps(bidql), existing.id),
            )
        reused = get_subscription(settings, existing.id)
        if reused is None:
            raise RuntimeError("subscription was not persisted")
        return reused, False

    subscription_id = str(uuid5(NAMESPACE_URL, f"tendertrace:subscription:{identity}"))
    with connection(settings) as conn:
        existed = conn.execute(
            "SELECT 1 FROM subscriptions WHERE id = ?",
            (subscription_id,),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO subscriptions(
                id, original_query, bidql_json, schedule_kind, cron, timezone, status
            ) VALUES (?, ?, ?, ?, ?, ?, 'active')
            ON CONFLICT(id) DO UPDATE SET
                original_query = excluded.original_query,
                bidql_json = excluded.bidql_json,
                schedule_kind = excluded.schedule_kind,
                cron = excluded.cron,
                timezone = excluded.timezone,
                status = 'active',
                updated_at = datetime('now')
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
    return subscription, existed is None


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
    delivery_channels = _normalize_delivery_channels(runtime.get("delivery_channels"))
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
        delivery_channels=delivery_channels,
        feishu_receive_id=str(runtime.get("feishu_receive_id") or "") or None,
        feishu_receive_id_type=str(runtime.get("feishu_receive_id_type") or "") or None,
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


def _normalize_delivery_channels(value: object) -> list[str]:
    selected = {"web", "outbox"}
    if isinstance(value, (list, tuple)):
        selected.update(
            str(channel).strip().lower()
            for channel in value
            if str(channel).strip().lower() in {"web", "outbox", "feishu", "feishu_message"}
        )
    if "feishu_message" in selected:
        selected.remove("feishu_message")
        selected.add("feishu")
    return [channel for channel in ("web", "outbox", "feishu") if channel in selected]


def _prepare_subscription(
    settings: Settings,
    *,
    query: str,
    now: datetime | None,
    max_pages: int,
    max_results: int,
    schedule_override: dict[str, Any] | None,
    model_strategy: str | None,
    delivery_channels: list[str] | tuple[str, ...] | None,
    feishu_receive_id: str | None,
    feishu_receive_id_type: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
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
    if delivery_channels is not None:
        runtime["delivery_channels"] = _normalize_delivery_channels(delivery_channels)
    if feishu_receive_id:
        runtime["feishu_receive_id"] = feishu_receive_id
        runtime["feishu_receive_id_type"] = feishu_receive_id_type or "chat_id"
    bidql["_runtime"] = runtime
    return bidql, schedule_kind, schedule


def _subscription_identity(
    *,
    query: str,
    schedule_kind: str,
    cron: object,
    timezone: str,
    bidql: dict[str, Any],
) -> str:
    runtime = bidql.get("_runtime") if isinstance(bidql.get("_runtime"), dict) else {}
    payload = {
        "query": " ".join(query.split()).casefold(),
        "schedule_kind": schedule_kind,
        "cron": str(cron or ""),
        "timezone": timezone,
        "max_pages": int(runtime.get("max_pages") or 1),
        "max_results": int(runtime.get("max_results") or 10),
        "model_strategy": str(runtime.get("model_strategy") or "config"),
        "delivery_channels": _normalize_delivery_channels(runtime.get("delivery_channels")),
        "feishu_receive_id": str(runtime.get("feishu_receive_id") or ""),
        "feishu_receive_id_type": str(runtime.get("feishu_receive_id_type") or "chat_id"),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


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
