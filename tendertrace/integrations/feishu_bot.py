from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
import importlib.util
import json
from typing import Any, Callable
from urllib.parse import quote

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.integrations.feishu import FeishuClient, FeishuError, feishu_status
from tendertrace.integrations.feishu_card_actions import (
    callback_response_payload,
    process_feishu_card_action,
)
from tendertrace.integrations.feishu_briefing import send_opportunity_briefing
from tendertrace.integrations.feishu_opportunity import start_opportunity_collaboration
from tendertrace.intent import compile_intent
from tendertrace.organization_memory import (
    ensure_chat_workspace,
    record_memory,
    search_memories,
)
from tendertrace.opportunity import get_opportunity
from tendertrace.opportunity_collaboration import record_collaboration_note
from tendertrace.runner import RunOnceResult, run_once
from tendertrace.scheduling.scheduler import (
    schedule_ingest_subscription,
    schedule_subscription,
    start_subscription_scheduler,
)
from tendertrace.scheduling.subscriptions import Subscription, create_subscription


@dataclass(frozen=True)
class FeishuMessageEvent:
    event_id: str
    message_id: str
    chat_id: str
    chat_type: str
    sender_open_id: str
    query: str
    command_kind: str
    status: str
    run_id: str = ""
    subscription_id: str = ""
    error: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def accept_feishu_message_event(
    settings: Settings,
    payload: dict[str, Any],
) -> FeishuMessageEvent:
    init_db(settings)
    parsed = _parse_message_event(payload)
    with connection(settings) as conn:
        inserted = conn.execute(
            """
            INSERT OR IGNORE INTO feishu_message_events(
                event_id, message_id, chat_id, chat_type, sender_open_id,
                query, command_kind, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                parsed.event_id,
                parsed.message_id,
                parsed.chat_id,
                parsed.chat_type,
                parsed.sender_open_id,
                parsed.query,
                parsed.command_kind,
                parsed.status,
            ),
        ).rowcount
        row = conn.execute(
            """
            SELECT * FROM feishu_message_events
            WHERE event_id = ? OR message_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (parsed.event_id, parsed.message_id),
        ).fetchone()
    if row is None:
        raise RuntimeError("Feishu message event was not persisted")
    event = _from_row(row)
    if not inserted and event.status not in {"completed", "failed", "ignored"}:
        return FeishuMessageEvent(**{**event.to_dict(), "status": "duplicate"})
    return event


def process_feishu_message_event(
    settings: Settings,
    event_id: str,
    *,
    scheduler=None,
    client: FeishuClient | None = None,
    run_func: Callable[..., RunOnceResult] = run_once,
    subscription_creator: Callable[..., Subscription] = create_subscription,
) -> FeishuMessageEvent:
    event = get_feishu_message_event(settings, event_id)
    if event is None:
        raise ValueError("Feishu message event not found")
    if not _claim_event(settings, event_id):
        return event
    feishu = client or FeishuClient(settings)
    try:
        organization_command, organization_value = _organization_command(event.query)
        if organization_command:
            if event.chat_type != "group":
                raise ValueError("组织记忆指令仅支持飞书群聊")
            workspace = ensure_chat_workspace(
                settings,
                chat_id=event.chat_id,
                sender_open_id=event.sender_open_id,
            )
            workspace_url = (
                f"{settings.public_base_url}/?view=organizationView&workspace={workspace.id}"
            )
            if organization_command == "organization_record":
                memory = record_memory(
                    settings,
                    workspace_id=workspace.id,
                    content=organization_value,
                    source_type="feishu_message",
                    source_message_id=event.message_id,
                    sender_open_id=event.sender_open_id,
                    actor=event.sender_open_id or "feishu",
                )
                reply = f"已沉淀为组织记忆：{memory.title}\n回到 TenderTrace：{workspace_url}"
            else:
                memories = search_memories(
                    settings,
                    workspace_id=workspace.id,
                    query=organization_value,
                    limit=5,
                )
                if memories:
                    lines = [f"{index}. {item.title}：{item.content[:120]}" for index, item in enumerate(memories, 1)]
                    reply = "组织记忆检索结果：\n" + "\n".join(lines)
                else:
                    reply = "当前群的组织记忆中没有匹配内容。"
                reply += f"\n回到 TenderTrace：{workspace_url}"
            _update_event(
                settings,
                event_id,
                status="completed",
                command_kind=organization_command,
            )
            feishu.reply_text(event.message_id, reply)
            updated = get_feishu_message_event(settings, event_id)
            if updated is None:
                raise RuntimeError("Feishu message event disappeared after processing")
            return updated
        collaboration_note = _opportunity_note_command(event.query)
        if collaboration_note:
            if event.chat_type != "group":
                raise ValueError("项目意见仅支持飞书群聊")
            notice_id, content = collaboration_note
            if get_opportunity(settings, notice_id) is None:
                raise ValueError("未找到对应机会，请从机会详情复制机会编号")
            note = record_collaboration_note(
                settings,
                notice_id=notice_id,
                content=content,
                actor=event.sender_open_id or "飞书成员",
                channel="feishu_group",
                source_message_id=event.message_id,
            )
            _update_event(
                settings,
                event_id,
                status="completed",
                command_kind="opportunity_note",
            )
            feishu.reply_text(
                event.message_id,
                (
                    f"已记录项目协作意见：{note.content[:100]}\n"
                    "回到 TenderTrace："
                    f"{settings.public_base_url}/?view=opportunityView&opportunity={quote(notice_id, safe='')}"
                ),
            )
            updated = get_feishu_message_event(settings, event_id)
            if updated is None:
                raise RuntimeError("Feishu message event disappeared after processing")
            return updated
        bidql = compile_intent(event.query)
        schedule = bidql.get("schedule") if isinstance(bidql.get("schedule"), dict) else {}
        if str(schedule.get("kind") or "immediate") == "immediate":
            result = run_func(
                settings=settings,
                query=event.query,
                max_pages=1,
                max_results=10,
                delivery_channels=("web", "outbox", "feishu"),
                feishu_receive_id=event.chat_id,
                feishu_receive_id_type="chat_id",
            )
            _update_event(
                settings,
                event_id,
                status="completed",
                command_kind="run",
                run_id=result.run_id,
            )
            feishu.reply_text(
                event.message_id,
                f"检索完成：共 {result.notice_count} 条，Word 报告已发送到当前会话。",
            )
        else:
            subscription = subscription_creator(
                settings,
                query=event.query,
                max_pages=1,
                max_results=10,
                delivery_channels=("web", "outbox", "feishu"),
                feishu_receive_id=event.chat_id,
                feishu_receive_id_type="chat_id",
            )
            if scheduler is not None:
                schedule_subscription(scheduler, settings, subscription)
            _update_event(
                settings,
                event_id,
                status="completed",
                command_kind="subscription",
                subscription_id=subscription.id,
            )
            feishu.reply_text(
                event.message_id,
                (
                    f"订阅已创建：{subscription.schedule_kind}，后续增量报告将发送到当前会话。"
                    if scheduler is not None
                    else "订阅已保存；调度器当前未运行，启用后将按计划发送到当前会话。"
                ),
            )
    except Exception as exc:
        _update_event(
            settings,
            event_id,
            status="failed",
            error=f"{type(exc).__name__}: {exc}"[:1000],
        )
        try:
            feishu.reply_text(
                event.message_id,
                f"处理失败，请在 TenderTrace 事件审计中查看事件 {event_id}。",
            )
        except Exception:
            pass
    updated = get_feishu_message_event(settings, event_id)
    if updated is None:
        raise RuntimeError("Feishu message event disappeared after processing")
    return updated


def get_feishu_message_event(
    settings: Settings,
    event_id: str,
) -> FeishuMessageEvent | None:
    with connection(settings) as conn:
        row = conn.execute(
            "SELECT * FROM feishu_message_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
    return _from_row(row) if row else None


def list_feishu_message_events(
    settings: Settings,
    *,
    limit: int = 20,
) -> list[FeishuMessageEvent]:
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT * FROM feishu_message_events
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 100)),),
        ).fetchall()
    return [_from_row(row) for row in rows]


def pending_feishu_message_event_ids(
    settings: Settings,
    *,
    limit: int = 50,
) -> list[str]:
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT event_id
            FROM feishu_message_events
            WHERE status = 'accepted'
               OR (status = 'processing' AND updated_at <= datetime('now', '-15 minutes'))
            ORDER BY created_at
            LIMIT ?
            """,
            (max(1, min(int(limit), 200)),),
        ).fetchall()
    return [str(row["event_id"]) for row in rows]


def feishu_long_connection_available() -> bool:
    return importlib.util.find_spec("lark_oapi") is not None


def start_feishu_bot_listener(settings: Settings) -> None:
    if not feishu_status(settings).configured:
        raise FeishuError("Feishu bot listener requires enabled message-app credentials")
    try:
        import lark_oapi as lark
    except ImportError as exc:
        raise RuntimeError(
            "Feishu long connection requires: python -m pip install -e .[feishu]"
        ) from exc

    init_db(settings)
    owned_scheduler = start_subscription_scheduler(settings) if settings.scheduler_enabled else None

    def schedule_ingest_callback(subscription) -> None:
        if owned_scheduler is not None:
            schedule_ingest_subscription(owned_scheduler, settings, subscription)

    def schedule_user_callback(subscription) -> None:
        if owned_scheduler is not None:
            schedule_subscription(owned_scheduler, settings, subscription)

    def send_briefing_callback(receive_id: str | None, receive_id_type: str | None):
        return send_opportunity_briefing(
            settings,
            receive_id=receive_id,
            receive_id_type=receive_id_type,
        )

    def start_collaboration_callback(
        opportunity: dict[str, object],
        owner_open_id: str,
        owner_name: str,
    ):
        return start_opportunity_collaboration(
            settings,
            opportunity,
            owner_open_id=owner_open_id,
            owner_name=owner_name,
            create_task=True,
            create_calendar_event=True,
        )
    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="feishu-bot")
    for event_id in pending_feishu_message_event_ids(settings):
        executor.submit(
            process_feishu_message_event,
            settings,
            event_id,
            scheduler=owned_scheduler,
        )

    def on_message(data) -> None:
        payload = json.loads(lark.JSON.marshal(data) or "{}")
        event = accept_feishu_message_event(settings, payload)
        if event.status == "accepted":
            executor.submit(
                process_feishu_message_event,
                settings,
                event.event_id,
                scheduler=owned_scheduler,
            )

    def on_card_action(data):
        from lark_oapi.event.callback.model.p2_card_action_trigger import (
            P2CardActionTriggerResponse,
        )

        payload = json.loads(lark.JSON.marshal(data) or "{}")
        try:
            result = process_feishu_card_action(
                settings,
                payload,
                schedule_ingest=(schedule_ingest_callback if owned_scheduler is not None else None),
                schedule_subscription=(schedule_user_callback if owned_scheduler is not None else None),
                send_opportunity_briefing=send_briefing_callback,
                start_collaboration=start_collaboration_callback,
            )
            response = callback_response_payload(result)
        except (FeishuError, ValueError) as exc:
            response = {
                "toast": {
                    "type": "error",
                    "content": f"机会更新失败：{exc}",
                }
            }
        return P2CardActionTriggerResponse(response)

    handler = (
        lark.EventDispatcherHandler.builder(
            "",
            settings.feishu_callback_verification_token(),
        )
        .register_p2_im_message_receive_v1(on_message)
        .register_p2_card_action_trigger(on_card_action)
        .build()
    )
    client = lark.ws.Client(
        settings.feishu_message_app_id(),
        settings.feishu_message_app_secret(),
        event_handler=handler,
        domain=settings.feishu_base_url,
        log_level=lark.LogLevel.INFO,
    )
    try:
        client.start()
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
        if owned_scheduler is not None:
            owned_scheduler.shutdown(wait=False)


def _parse_message_event(payload: dict[str, Any]) -> FeishuMessageEvent:
    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    event_type = str(header.get("event_type") or "")
    if event_type not in {"im.message.receive_v1", "p2.im.message.receive_v1"}:
        raise ValueError(f"unsupported Feishu event type: {event_type}")
    body = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    message = body.get("message") if isinstance(body.get("message"), dict) else {}
    sender = body.get("sender") if isinstance(body.get("sender"), dict) else {}
    sender_id = sender.get("sender_id") if isinstance(sender.get("sender_id"), dict) else {}
    message_id = str(message.get("message_id") or "").strip()
    event_id = str(header.get("event_id") or message_id).strip()
    chat_id = str(message.get("chat_id") or "").strip()
    if not event_id or not message_id or not chat_id:
        raise ValueError("Feishu message event requires event_id, message_id and chat_id")
    message_type = str(message.get("message_type") or "")
    sender_type = str(sender.get("sender_type") or "")
    query = _message_text(message)
    status = "accepted"
    if message_type != "text" or sender_type != "user" or not query:
        status = "ignored"
    return FeishuMessageEvent(
        event_id=event_id,
        message_id=message_id,
        chat_id=chat_id,
        chat_type=str(message.get("chat_type") or ""),
        sender_open_id=str(sender_id.get("open_id") or ""),
        query=query,
        command_kind="pending",
        status=status,
    )


def _message_text(message: dict[str, Any]) -> str:
    try:
        content = json.loads(str(message.get("content") or "{}"))
    except json.JSONDecodeError:
        return ""
    text = str(content.get("text") or "").strip() if isinstance(content, dict) else ""
    mentions = message.get("mentions") if isinstance(message.get("mentions"), list) else []
    for mention in mentions:
        if isinstance(mention, dict):
            key = str(mention.get("key") or "")
            if key:
                text = text.replace(key, " ")
    return " ".join(text.split())[:2000]


def _organization_command(query: str) -> tuple[str, str]:
    normalized = query.strip()
    commands = (
        ("organization_record", ("记录组织记忆", "组织记录", "记录")),
        ("organization_search", ("查询组织记忆", "组织记忆查询", "查记忆")),
    )
    for command, prefixes in commands:
        for prefix in prefixes:
            if normalized == prefix:
                raise ValueError(f"{prefix} 后需要填写内容")
            for separator in ("：", ":", " "):
                marker = f"{prefix}{separator}"
                if normalized.startswith(marker):
                    value = normalized[len(marker) :].strip()
                    if not value:
                        raise ValueError(f"{prefix} 后需要填写内容")
                    return command, value
    return "", ""


def _opportunity_note_command(query: str) -> tuple[str, str] | None:
    """Parse `项目意见 <机会编号>：<意见>` without colliding with tender queries."""
    normalized = query.strip()
    for prefix in ("项目意见", "机会意见"):
        if not normalized.startswith(prefix):
            continue
        remainder = normalized[len(prefix) :].strip()
        if not remainder:
            raise ValueError(f"{prefix} 后需要填写机会编号和意见")
        for separator in ("：", ":"):
            if separator not in remainder:
                continue
            notice_id, content = (part.strip() for part in remainder.split(separator, 1))
            if not notice_id or not content:
                raise ValueError(f"请使用：{prefix} <机会编号>：<意见>")
            return notice_id[:200], content[:2000]
        raise ValueError(f"请使用：{prefix} <机会编号>：<意见>")
    return None


def _update_event(settings: Settings, event_id: str, **values: str) -> None:
    allowed = {"status", "command_kind", "run_id", "subscription_id", "error"}
    changes = {key: value for key, value in values.items() if key in allowed}
    if not changes:
        return
    assignments = ", ".join(f"{key} = ?" for key in changes)
    with connection(settings) as conn:
        conn.execute(
            f"""
            UPDATE feishu_message_events
            SET {assignments}, updated_at = datetime('now')
            WHERE event_id = ?
            """,
            (*changes.values(), event_id),
        )


def _claim_event(settings: Settings, event_id: str) -> bool:
    with connection(settings) as conn:
        changed = conn.execute(
            """
            UPDATE feishu_message_events
            SET status = 'processing', error = '', updated_at = datetime('now')
            WHERE event_id = ?
              AND (
                    status = 'accepted'
                    OR (
                        status = 'processing'
                        AND updated_at <= datetime('now', '-15 minutes')
                    )
              )
            """,
            (event_id,),
        ).rowcount
    return bool(changed)


def _from_row(row) -> FeishuMessageEvent:
    return FeishuMessageEvent(
        event_id=str(row["event_id"]),
        message_id=str(row["message_id"]),
        chat_id=str(row["chat_id"]),
        chat_type=str(row["chat_type"] or ""),
        sender_open_id=str(row["sender_open_id"] or ""),
        query=str(row["query"] or ""),
        command_kind=str(row["command_kind"] or ""),
        status=str(row["status"]),
        run_id=str(row["run_id"] or ""),
        subscription_id=str(row["subscription_id"] or ""),
        error=str(row["error"] or ""),
        created_at=str(row["created_at"] or ""),
        updated_at=str(row["updated_at"] or ""),
    )
