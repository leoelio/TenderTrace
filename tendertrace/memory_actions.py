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
from tendertrace.scheduling.subscriptions import Subscription, ensure_subscription


IngestScheduler = Callable[[IngestSubscription], None]
SubscriptionScheduler = Callable[[Subscription], None]


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
    schedule_subscription: SubscriptionScheduler | None = None,
) -> MemoryAdviceActionResult:
    report = build_weekly_report(settings, user_id=user_id, days=days, now=now)
    advice = _find_advice(report, advice_id)
    automation = _execute_advice(
        settings,
        advice,
        status=status,
        source=source,
        context=context,
        schedule_ingest=schedule_ingest,
        schedule_subscription=schedule_subscription,
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
    source: str,
    context: dict[str, Any] | None,
    schedule_ingest: IngestScheduler | None,
    schedule_subscription: SubscriptionScheduler | None,
) -> dict[str, object]:
    kind = str(advice.get("kind") or "")
    if status.strip().lower() != "accepted":
        return {"status": "not_applicable", "kind": kind}
    if kind == "subscription":
        return _execute_subscription_advice(
            settings,
            advice,
            source=source,
            context=context,
            schedule_subscription=schedule_subscription,
        )
    if kind != "knowledge_base":
        return {"status": "not_applicable", "kind": kind}
    return _execute_knowledge_advice(
        settings,
        advice,
        schedule_ingest=schedule_ingest,
    )


def _execute_knowledge_advice(
    settings: Settings,
    advice: dict[str, object],
    *,
    schedule_ingest: IngestScheduler | None,
) -> dict[str, object]:
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


def _execute_subscription_advice(
    settings: Settings,
    advice: dict[str, object],
    *,
    source: str,
    context: dict[str, Any] | None,
    schedule_subscription: SubscriptionScheduler | None,
) -> dict[str, object]:
    evidence = advice.get("evidence") if isinstance(advice.get("evidence"), dict) else {}
    query = str(evidence.get("query") or "").strip()
    if not query:
        raise ValueError("subscription advice is missing query evidence")
    action_context = context or {}
    receive_id = ""
    receive_id_type = "chat_id"
    delivery_channels = ["web", "outbox"]
    if source.strip().lower() == "feishu":
        receive_id = str(action_context.get("feishu_receive_id") or "").strip()
        receive_id_type = str(
            action_context.get("feishu_receive_id_type") or "chat_id"
        ).strip()
        if receive_id:
            delivery_channels.append("feishu")
    subscription, created = ensure_subscription(
        settings,
        query=query,
        schedule_override={
            "kind": "recurring",
            "frequency": "daily",
            "time": "09:00",
        },
        delivery_channels=delivery_channels,
        feishu_receive_id=receive_id or None,
        feishu_receive_id_type=receive_id_type,
    )
    if schedule_subscription is not None:
        schedule_subscription(subscription)
    action_text = "已创建每日 09:00 增量订阅" if created else "已复用每日 09:00 增量订阅"
    if receive_id:
        action_text = f"{action_text}，后续 Word 将推送到当前飞书会话"
    elif source.strip().lower() == "feishu":
        action_text = f"{action_text}；未识别当前飞书会话，仅写入 Web outbox"
    if schedule_subscription is None:
        action_text = f"{action_text}；调度器未启用，启用后生效"
    return {
        "status": "created" if created else "reused",
        "kind": "user_subscription",
        "message": action_text,
        "scheduled": schedule_subscription is not None,
        "delivery_channels": delivery_channels,
        "subscription": subscription.to_dict(),
    }
