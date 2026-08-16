from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from tendertrace.config import Settings
from tendertrace.memory import build_weekly_report, record_advice_feedback
from tendertrace.scheduling.ingest_subscriptions import (
    IngestSubscription,
    ensure_ingest_subscription,
)


IngestScheduler = Callable[[IngestSubscription], None]


@dataclass(frozen=True)
class MemoryAdviceActionResult:
    feedback: dict[str, object]
    automation: dict[str, object]
    report: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def apply_memory_advice_feedback(
    settings: Settings,
    *,
    advice_id: str,
    status: str,
    user_id: str = "admin",
    source: str = "web",
    actor: str = "",
    note: str = "",
    context: dict[str, Any] | None = None,
    days: int = 7,
    now: datetime | str | None = None,
    schedule_ingest: IngestScheduler | None = None,
) -> MemoryAdviceActionResult:
    report = build_weekly_report(settings, user_id=user_id, days=days, now=now)
    advice = _find_advice(report, advice_id)
    automation = _execute_advice(
        settings,
        advice,
        status=status,
        schedule_ingest=schedule_ingest,
    )
    feedback_context = dict(context or {})
    if advice:
        feedback_context["advice_kind"] = str(advice.get("kind") or "")
    if automation.get("status") != "not_applicable":
        feedback_context["automation"] = automation
    feedback = record_advice_feedback(
        settings,
        advice_id=advice_id,
        status=status,
        user_id=user_id,
        source=source,
        actor=actor,
        note=note,
        context=feedback_context,
    )
    refreshed = build_weekly_report(settings, user_id=user_id, days=days, now=now)
    return MemoryAdviceActionResult(
        feedback=feedback,
        automation=automation,
        report=refreshed,
    )


def _find_advice(report: dict[str, object], advice_id: str) -> dict[str, object]:
    for item in report.get("recommendation_plan") or []:
        if isinstance(item, dict) and str(item.get("id") or "") == advice_id:
            return item
    return {}


def _execute_advice(
    settings: Settings,
    advice: dict[str, object],
    *,
    status: str,
    schedule_ingest: IngestScheduler | None,
) -> dict[str, object]:
    kind = str(advice.get("kind") or "")
    if status.strip().lower() != "accepted" or kind != "knowledge_base":
        return {"status": "not_applicable", "kind": kind}
    evidence = advice.get("evidence") if isinstance(advice.get("evidence"), dict) else {}
    topic = str(evidence.get("topic") or "").strip()
    region = str(evidence.get("region") or "").strip()
    if not topic or not region:
        raise ValueError("knowledge_base advice is missing topic or region evidence")
    subscription, created = ensure_ingest_subscription(
        settings,
        name=f"{region} {topic} 智能采集",
        topics=[topic],
        regions=[region],
    )
    if schedule_ingest is not None:
        schedule_ingest(subscription)
    status_text = "created" if created else "reused"
    action_text = (
        f"已创建 {region} / {topic} 后台采集"
        if created
        else f"已复用 {region} / {topic} 后台采集"
    )
    if schedule_ingest is None:
        action_text = f"{action_text}；调度器未启用，启用后生效"
    return {
        "status": status_text,
        "kind": "ingest_subscription",
        "message": action_text,
        "scheduled": schedule_ingest is not None,
        "subscription": subscription.to_dict(),
    }
