from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Callable
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.delivery.feishu_bitable import update_opportunity_workflow_in_bitable
from tendertrace.delivery.ledger import record_delivery_attempt
from tendertrace.delivery.preferences import resolve_feishu_receiver
from tendertrace.integrations.feishu import FeishuClient, FeishuError
from tendertrace.integrations.feishu_opportunity import build_opportunity_card
from tendertrace.opportunity import get_opportunity
from tendertrace.workflow import OpportunityWorkflow, get_workflow, update_workflow


@dataclass(frozen=True)
class TaskSyncResult:
    status: str
    scanned_count: int
    updated_count: int
    completed_count: int
    overdue_count: int
    bitable_updated_count: int
    bitable_failed_count: int
    completion_notifications_sent: int
    completion_notifications_skipped: int
    failed_count: int
    failures: tuple[dict[str, str], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def sync_feishu_tasks(
    settings: Settings,
    *,
    limit: int = 200,
    client: FeishuClient | None = None,
    bitable_updater: Callable[..., object] = update_opportunity_workflow_in_bitable,
    now: datetime | None = None,
) -> TaskSyncResult:
    init_db(settings)
    reference_time = now or datetime.now(timezone.utc)
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT notice_id
            FROM opportunity_workflows
            WHERE COALESCE(feishu_task_guid, '') <> ''
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 500)),),
        ).fetchall()
    if not rows:
        return TaskSyncResult(
            status="skipped",
            scanned_count=0,
            updated_count=0,
            completed_count=0,
            overdue_count=0,
            bitable_updated_count=0,
            bitable_failed_count=0,
            completion_notifications_sent=0,
            completion_notifications_skipped=0,
            failed_count=0,
        )

    feishu = client or FeishuClient(settings)
    updated_count = 0
    completed_count = 0
    overdue_count = 0
    bitable_updated_count = 0
    bitable_failed_count = 0
    completion_notifications_sent = 0
    completion_notifications_skipped = 0
    failures: list[dict[str, str]] = []
    for row in rows:
        notice_id = str(row["notice_id"])
        current = get_workflow(settings, notice_id)
        try:
            payload = feishu.get_task(current.feishu_task_guid)
            task = _task(payload)
            status, completed_at = _task_status(task, reference_time)
            updated = update_workflow(
                settings,
                notice_id,
                feishu_task_status=status,
                feishu_task_completed_at=completed_at,
                feishu_task_synced_at=reference_time.isoformat(timespec="seconds"),
                updated_by="feishu_task_sync",
            )
            if current.feishu_task_status != status:
                _record_status_change(settings, current, updated)
                updated_count += 1
            completed_count += int(status == "completed")
            overdue_count += int(status == "overdue")
        except (FeishuError, ValueError, TypeError) as exc:
            failures.append(
                {
                    "notice_id": notice_id,
                    "stage": "task_read",
                    "error": f"{type(exc).__name__}: {exc}"[:500],
                }
            )
            continue
        try:
            bitable_result = bitable_updater(
                settings,
                notice_id=notice_id,
                workflow=updated.to_dict(),
            )
            if getattr(bitable_result, "status", "") == "sent":
                bitable_updated_count += 1
            elif getattr(bitable_result, "status", "") == "failed":
                bitable_failed_count += 1
                failures.append(
                    {
                        "notice_id": notice_id,
                        "stage": "bitable_write",
                        "error": str(getattr(bitable_result, "message", "write failed"))[:500],
                    }
                )
        except Exception as exc:
            bitable_failed_count += 1
            failures.append(
                {
                    "notice_id": notice_id,
                    "stage": "bitable_write",
                    "error": f"{type(exc).__name__}: {exc}"[:500],
                }
            )
        if status == "completed":
            try:
                notification_status = _send_completion_follow_up(
                    settings,
                    updated,
                    client=feishu,
                )
                completion_notifications_sent += int(notification_status == "sent")
                completion_notifications_skipped += int(notification_status == "skipped")
            except (FeishuError, ValueError, TypeError) as exc:
                failures.append(
                    {
                        "notice_id": notice_id,
                        "stage": "completion_notify",
                        "error": f"{type(exc).__name__}: {exc}"[:500],
                    }
                )
    return TaskSyncResult(
        status="partial" if failures else "finished",
        scanned_count=len(rows),
        updated_count=updated_count,
        completed_count=completed_count,
        overdue_count=overdue_count,
        bitable_updated_count=bitable_updated_count,
        bitable_failed_count=bitable_failed_count,
        completion_notifications_sent=completion_notifications_sent,
        completion_notifications_skipped=completion_notifications_skipped,
        failed_count=len(failures),
        failures=tuple(failures),
    )


def _send_completion_follow_up(
    settings: Settings,
    workflow: OpportunityWorkflow,
    *,
    client: FeishuClient,
) -> str:
    if workflow.stage in {"won", "lost", "archived"}:
        return "skipped"
    if workflow.owner_open_id:
        receive_id, receive_id_type = workflow.owner_open_id, "open_id"
    else:
        receive_id, receive_id_type = resolve_feishu_receiver(settings)
    if not receive_id:
        return "skipped"
    artifact_key = _completion_artifact_key(
        workflow,
        receive_id=receive_id,
        receive_id_type=receive_id_type or "open_id",
    )
    if _completion_already_sent(settings, artifact_key):
        return "skipped"
    opportunity = get_opportunity(settings, workflow.notice_id)
    if opportunity is None:
        raise ValueError("opportunity not found for completed Feishu task")
    card = build_opportunity_card(
        opportunity,
        workflow,
        next_action=_completion_next_action(workflow),
    )
    card["header"]["template"] = "green"
    card["elements"].insert(
        0,
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    "**跟进任务已完成，机会尚未结束。**\n"
                    "请结合当前证据与资格门禁，确认下一阶段动作。"
                ),
            },
        },
    )
    try:
        response = client.send_card(
            card,
            receive_id=receive_id,
            receive_id_type=receive_id_type,
        )
        message_id = _nested_string(response, "data", "message_id")
        record_delivery_attempt(
            settings,
            channel="feishu",
            artifact_type="opportunity_task_completion",
            artifact_key=artifact_key,
            status="sent",
            external_id=message_id or None,
        )
    except (FeishuError, ValueError) as exc:
        record_delivery_attempt(
            settings,
            channel="feishu",
            artifact_type="opportunity_task_completion",
            artifact_key=artifact_key,
            status="failed",
            error=str(exc),
        )
        raise
    return "sent"


def _completion_next_action(workflow: OpportunityWorkflow) -> str:
    return {
        "identified": "认领机会并核对项目范围、预算与关键时间节点",
        "qualifying": "确认机会是否进入策略制定",
        "pursuing": "完成 Go、Hold 或 No-Go 决策",
        "bidding": "跟踪投标交付与中标结果",
    }.get(workflow.stage, "复核当前机会状态")


def _completion_artifact_key(
    workflow: OpportunityWorkflow,
    *,
    receive_id: str,
    receive_id_type: str,
) -> str:
    raw = "|".join(
        (
            workflow.notice_id,
            workflow.feishu_task_guid,
            workflow.feishu_task_completed_at,
            receive_id_type,
            receive_id,
        )
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"opportunity_task_completion:{digest}"


def _completion_already_sent(settings: Settings, artifact_key: str) -> bool:
    with connection(settings) as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM delivery_attempts
            WHERE channel = 'feishu'
              AND artifact_type = 'opportunity_task_completion'
              AND artifact_key = ?
              AND status = 'sent'
            LIMIT 1
            """,
            (artifact_key,),
        ).fetchone()
    return row is not None


def _nested_string(payload: dict[str, Any], *keys: str) -> str:
    value: object = payload
    for key in keys:
        if not isinstance(value, dict):
            return ""
        value = value.get(key)
    return str(value or "")


def _task(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    task = data.get("task") if isinstance(data, dict) else None
    if not isinstance(task, dict):
        raise ValueError("Feishu task is missing in response")
    return task


def _task_status(task: dict[str, Any], now: datetime) -> tuple[str, str]:
    completed_timestamp = _timestamp_ms(task.get("completed_at"))
    if completed_timestamp is not None:
        return "completed", completed_timestamp.isoformat(timespec="seconds")
    due = task.get("due")
    due_timestamp = _timestamp_ms(due.get("timestamp")) if isinstance(due, dict) else None
    if due_timestamp is not None and due_timestamp < now.astimezone(timezone.utc):
        return "overdue", ""
    return "open", ""


def _timestamp_ms(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text or text == "0":
        return None
    try:
        return datetime.fromtimestamp(int(text) / 1000, tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def _record_status_change(
    settings: Settings,
    before: OpportunityWorkflow,
    after: OpportunityWorkflow,
) -> None:
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO opportunity_events(
                id, notice_id, action, from_stage, to_stage, actor_open_id, payload_json
            ) VALUES (?, ?, 'feishu_task_sync', ?, ?, 'feishu', ?)
            """,
            (
                str(uuid4()),
                before.notice_id,
                before.stage,
                after.stage,
                json.dumps(
                    {
                        "from_status": before.feishu_task_status,
                        "to_status": after.feishu_task_status,
                        "completed_at": after.feishu_task_completed_at,
                    },
                    ensure_ascii=False,
                ),
            ),
        )
