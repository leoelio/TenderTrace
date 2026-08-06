from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from tendertrace.config import Settings
from tendertrace.runlog import get_run
from tendertrace.runner import NoticeAdapter
from tendertrace.scheduling.subscriptions import create_subscription, run_subscription


def run_incremental_demo(
    settings: Settings,
    *,
    query: str,
    now: datetime | None = None,
    max_pages: int = 1,
    max_results: int = 10,
    model_strategy: str | None = None,
    adapter: NoticeAdapter | None = None,
) -> dict[str, Any]:
    first_now = now
    second_now = now + timedelta(minutes=1) if now else None
    subscription = create_subscription(
        settings,
        query=query,
        now=now,
        max_pages=max_pages,
        max_results=max_results,
        model_strategy=model_strategy,
    )
    first = run_subscription(
        settings,
        subscription_id=subscription.id,
        now=first_now,
        adapter=adapter,
    )
    second = run_subscription(
        settings,
        subscription_id=subscription.id,
        now=second_now,
        adapter=adapter,
    )
    first_run = get_run(settings, first.run_id) or {}
    second_run = get_run(settings, second.run_id) or {}
    return {
        "subscription": subscription.to_dict(),
        "first_run": first.to_dict(),
        "second_run": second.to_dict(),
        "incremental": {
            "first_notice_count": first.notice_count,
            "second_notice_count": second.notice_count,
            "first_new": _stat(first_run, "new"),
            "second_new": _stat(second_run, "new"),
            "second_skipped_sent": _stat(second_run, "skipped_sent"),
            "only_new_content_on_second_run": second.notice_count == _stat(second_run, "new")
            and _stat(second_run, "skipped_sent") > 0,
        },
    }


def _stat(run: dict[str, Any], key: str) -> int:
    stats = run.get("stats")
    if not isinstance(stats, dict):
        return 0
    try:
        return int(stats.get(key) or 0)
    except (TypeError, ValueError):
        return 0
