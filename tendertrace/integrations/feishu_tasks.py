from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from typing import Any, Callable
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.delivery.feishu_bitable import update_opportunity_workflow_in_bitable
from tendertrace.integrations.feishu import FeishuClient, FeishuError
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
        return TaskSyncResult("skipped", 0, 0, 0, 0, 0, 0, 0)

    feishu = client or FeishuClient(settings)
    updated_count = 0
    completed_count = 0
    overdue_count = 0
    bitable_updated_count = 0
    bitable_failed_count = 0
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
    return TaskSyncResult(
        status="partial" if failures else "finished",
        scanned_count=len(rows),
        updated_count=updated_count,
        completed_count=completed_count,
        overdue_count=overdue_count,
        bitable_updated_count=bitable_updated_count,
        bitable_failed_count=bitable_failed_count,
        failed_count=len(failures),
        failures=tuple(failures),
    )


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
