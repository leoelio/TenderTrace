from __future__ import annotations

from datetime import datetime
import hashlib
from typing import Any
from zoneinfo import ZoneInfo

from tendertrace.company_due_diligence import record_company_task_feishu_receipt
from tendertrace.config import Settings
from tendertrace.db import connection
from tendertrace.integrations.feishu import FeishuClient, FeishuError


def sync_company_due_diligence_task(
    settings: Settings,
    task_id: str,
    *,
    client: FeishuClient | None = None,
) -> dict[str, object]:
    with connection(settings) as conn:
        row = conn.execute(
            """
            SELECT task.*, entity.legal_name
            FROM company_due_diligence_tasks task
            JOIN company_entities entity ON entity.id = task.entity_id
            WHERE task.id = ?
            """,
            (task_id,),
        ).fetchone()
    if row is None:
        raise LookupError("company due diligence task not found")
    if str(row["feishu_task_guid"] or ""):
        return {
            "status": "reused",
            "task_id": task_id,
            "task_guid": str(row["feishu_task_guid"]),
            "receipt": _json_object(row["feishu_receipt_json"]),
        }
    feishu = client or FeishuClient(settings)
    try:
        response = feishu.create_task(
            summary=f"合作方尽调：{row['title']}"[:3000],
            description="\n".join(
                (
                    f"合作方：{row['legal_name']}",
                    f"责任域：{row['task_type']}",
                    f"核验问题：{row['question']}",
                    f"TenderTrace任务ID：{task_id}",
                )
            ),
            client_token=hashlib.sha256(
                f"tendertrace:company-due-diligence:{task_id}".encode()
            ).hexdigest(),
            due_timestamp_ms=str(int(_parse_due(str(row["due_at"]), settings.timezone).timestamp() * 1000)),
            assignee_open_id=str(row["assignee_open_id"] or ""),
        )
        task_guid = _nested_string(response, "data", "task", "guid")
        if not task_guid:
            raise ValueError("Feishu due diligence task guid is missing")
    except (FeishuError, ValueError, TypeError) as exc:
        record_company_task_feishu_receipt(
            settings,
            task_id,
            status="failed",
            receipt={},
            error=f"{type(exc).__name__}: {exc}",
        )
        raise
    updated = record_company_task_feishu_receipt(
        settings,
        task_id,
        task_guid=task_guid,
        status="open",
        receipt=response,
        error="",
    )
    return {
        "status": "created",
        "task_id": task_id,
        "task_guid": task_guid,
        "receipt": updated["feishu_receipt"],
    }


def _parse_due(value: str, timezone_name: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
    return parsed


def _nested_string(payload: dict[str, Any], *path: str) -> str:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return ""
        value = value.get(key)
    return str(value or "")


def _json_object(value: object) -> dict[str, object]:
    import json

    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
