from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from tendertrace.config import Settings
from tendertrace.ingest import run_ingest_cycle
from tendertrace.integrations.feishu_briefing import send_opportunity_briefing
from tendertrace.integrations.feishu_escalation import send_opportunity_escalation_summary
from tendertrace.integrations.feishu_source_alerts import send_source_health_alert
from tendertrace.integrations.feishu_source_incidents import sync_source_incidents
from tendertrace.integrations.feishu_leads import import_partner_leads
from tendertrace.integrations.feishu_tasks import sync_feishu_tasks
from tendertrace.scheduling.ingest_subscriptions import (
    IngestSubscription,
    list_ingest_subscriptions,
    run_ingest_subscription,
)
from tendertrace.scheduling.subscriptions import (
    Subscription,
    list_subscriptions,
    run_subscription,
)


def start_subscription_scheduler(settings: Settings):
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError as exc:
        raise RuntimeError("APScheduler is not installed. Run: python -m pip install -e .[dev]") from exc

    scheduler = BackgroundScheduler(timezone=settings.timezone)
    for subscription in list_subscriptions(settings):
        schedule_subscription(scheduler, settings, subscription)
    for subscription in list_ingest_subscriptions(settings):
        schedule_ingest_subscription(scheduler, settings, subscription)
    if settings.ingest_enabled:
        schedule_ingest_pool(scheduler, settings)
    if settings.feishu_lead_import_enabled:
        schedule_feishu_lead_import(scheduler, settings)
    if settings.opportunity_escalation_enabled:
        schedule_opportunity_escalation(scheduler, settings)
    if settings.opportunity_briefing_enabled:
        schedule_opportunity_briefing(scheduler, settings)
    if settings.feishu_task_sync_enabled:
        schedule_feishu_task_sync(scheduler, settings)
        schedule_source_incident_sync(scheduler, settings)
    if settings.source_alert_enabled:
        schedule_source_health_alert(scheduler, settings)
    scheduler.start()
    return scheduler


def schedule_subscription(scheduler, settings: Settings, subscription: Subscription) -> None:
    trigger = _trigger_for(subscription, settings)
    if trigger is None:
        return
    scheduler.add_job(
        run_subscription,
        trigger=trigger,
        id=f"subscription:{subscription.id}",
        kwargs={"settings": settings, "subscription_id": subscription.id},
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )


def schedule_ingest_pool(scheduler, settings: Settings) -> None:
    try:
        from apscheduler.triggers.cron import CronTrigger
    except ImportError as exc:
        raise RuntimeError("APScheduler is not installed. Run: python -m pip install -e .[dev]") from exc
    scheduler.add_job(
        run_ingest_cycle,
        trigger=CronTrigger.from_crontab(settings.ingest_cron, timezone=settings.timezone),
        id="ingest:pool",
        kwargs={"settings": settings},
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )


def schedule_ingest_subscription(
    scheduler,
    settings: Settings,
    subscription: IngestSubscription,
) -> None:
    try:
        from apscheduler.triggers.cron import CronTrigger
    except ImportError as exc:
        raise RuntimeError("APScheduler is not installed. Run: python -m pip install -e .[dev]") from exc
    scheduler.add_job(
        run_ingest_subscription,
        trigger=CronTrigger.from_crontab(subscription.cron, timezone=subscription.timezone),
        id=f"ingest_subscription:{subscription.id}",
        kwargs={"settings": settings, "subscription_id": subscription.id},
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )


def schedule_feishu_lead_import(scheduler, settings: Settings) -> None:
    try:
        from apscheduler.triggers.cron import CronTrigger
    except ImportError as exc:
        raise RuntimeError("APScheduler is not installed. Run: python -m pip install -e .[dev]") from exc
    scheduler.add_job(
        import_partner_leads,
        trigger=CronTrigger.from_crontab(
            settings.feishu_lead_import_cron,
            timezone=settings.timezone,
        ),
        id="feishu:partner-leads",
        kwargs={"settings": settings},
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )


def schedule_opportunity_escalation(scheduler, settings: Settings) -> None:
    try:
        from apscheduler.triggers.cron import CronTrigger
    except ImportError as exc:
        raise RuntimeError("APScheduler is not installed. Run: python -m pip install -e .[dev]") from exc
    scheduler.add_job(
        send_opportunity_escalation_summary,
        trigger=CronTrigger.from_crontab(
            settings.opportunity_escalation_cron,
            timezone=settings.timezone,
        ),
        id="feishu:opportunity-escalation",
        kwargs={"settings": settings},
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )


def schedule_opportunity_briefing(scheduler, settings: Settings) -> None:
    try:
        from apscheduler.triggers.cron import CronTrigger
    except ImportError as exc:
        raise RuntimeError("APScheduler is not installed. Run: python -m pip install -e .[dev]") from exc
    scheduler.add_job(
        send_opportunity_briefing,
        trigger=CronTrigger.from_crontab(
            settings.opportunity_briefing_cron,
            timezone=settings.timezone,
        ),
        id="feishu:opportunity-briefing",
        kwargs={"settings": settings},
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )


def schedule_feishu_task_sync(scheduler, settings: Settings) -> None:
    try:
        from apscheduler.triggers.cron import CronTrigger
    except ImportError as exc:
        raise RuntimeError("APScheduler is not installed. Run: python -m pip install -e .[dev]") from exc
    scheduler.add_job(
        sync_feishu_tasks,
        trigger=CronTrigger.from_crontab(
            settings.feishu_task_sync_cron,
            timezone=settings.timezone,
        ),
        id="feishu:task-sync",
        kwargs={"settings": settings},
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )


def schedule_source_health_alert(scheduler, settings: Settings) -> None:
    try:
        from apscheduler.triggers.cron import CronTrigger
    except ImportError as exc:
        raise RuntimeError("APScheduler is not installed. Run: python -m pip install -e .[dev]") from exc
    scheduler.add_job(
        send_source_health_alert,
        trigger=CronTrigger.from_crontab(
            settings.source_alert_cron,
            timezone=settings.timezone,
        ),
        id="feishu:source-health-alert",
        kwargs={"settings": settings},
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )


def schedule_source_incident_sync(scheduler, settings: Settings) -> None:
    try:
        from apscheduler.triggers.cron import CronTrigger
    except ImportError as exc:
        raise RuntimeError("APScheduler is not installed. Run: python -m pip install -e .[dev]") from exc
    scheduler.add_job(
        sync_source_incidents,
        trigger=CronTrigger.from_crontab(
            settings.feishu_task_sync_cron,
            timezone=settings.timezone,
        ),
        id="feishu:source-incident-sync",
        kwargs={"settings": settings},
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )


def _trigger_for(subscription: Subscription, settings: Settings):
    try:
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.date import DateTrigger
    except ImportError as exc:
        raise RuntimeError("APScheduler is not installed. Run: python -m pip install -e .[dev]") from exc

    if subscription.schedule_kind == "recurring" and subscription.cron:
        minute, hour, day, month, day_of_week = subscription.cron.split()
        return CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            timezone=subscription.timezone,
        )
    if subscription.schedule_kind == "once_at":
        schedule = subscription.bidql.get("schedule", {})
        time_text = str(schedule.get("time") or "09:00")
        hour, minute = [int(part) for part in time_text.split(":", 1)]
        tz = ZoneInfo(subscription.timezone or settings.timezone)
        now = datetime.now(tz)
        run_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if run_at < now:
            run_at = now
        return DateTrigger(run_date=run_at, timezone=tz)
    return None
