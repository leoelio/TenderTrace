from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from typing import Any, Iterable
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.delivery.feishu_bitable import update_requirements_in_bitable
from tendertrace.integrations.feishu import FeishuClient, FeishuError
from tendertrace.opportunity_requirements import list_requirements, requirement_summary


@dataclass(frozen=True)
class RequirementSyncResult:
    status: str
    scanned_count: int
    created_count: int
    skipped_count: int
    failed_count: int
    updated_count: int = 0
    conflict_count: int = 0
    failures: tuple[dict[str, str], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def sync_requirements_to_feishu(
    settings: Settings,
    notice_id: str,
    *,
    client: FeishuClient | None = None,
    limit: int = 100,
    requirement_ids: Iterable[str] | None = None,
) -> RequirementSyncResult:
    """Idempotently create one Feishu Task v2 per actionable requirement.

    A stable ``client_token`` derived from the requirement id makes task creation
    idempotent at the Feishu side, and the stored ``feishu_task_guid`` makes it
    idempotent locally. This layer only *creates* external tasks; it never rewrites
    a requirement's status, evidence or human conclusions.
    """
    init_db(settings)
    requirements = list_requirements(settings, notice_id)
    requested_ids = {str(value).strip() for value in requirement_ids or () if str(value).strip()}
    if requested_ids:
        requirements = [item for item in requirements if item.id in requested_ids]
    feishu = client or FeishuClient(settings)
    created_count = 0
    skipped_count = 0
    failures: list[dict[str, str]] = []
    for requirement in requirements[: max(1, min(int(limit), 500))]:
        if _task_guid(settings, requirement.id):
            skipped_count += 1
            continue
        if not _should_sync(requirement):
            skipped_count += 1
            continue
        try:
            response = feishu.create_task(
                summary=f"准备要求：{requirement.title}",
                description=_task_description(requirement),
                client_token=_idempotency_key(requirement.id),
                due_timestamp_ms=_due_timestamp_ms(requirement.due_at),
                assignee_open_id=requirement.assignee_member_id,
            )
            task_guid = _nested_string(response, "data", "task", "guid")
            if not task_guid:
                raise FeishuError("Feishu task guid is missing in response")
            _record_task(settings, requirement.id, task_guid)
            created_count += 1
        except (FeishuError, ValueError, TypeError) as exc:
            failures.append(
                {
                    "requirement_id": requirement.id,
                    "error": f"{type(exc).__name__}: {exc}"[:500],
                }
            )
    return RequirementSyncResult(
        status="partial" if failures else "finished",
        scanned_count=len(requirements),
        created_count=created_count,
        skipped_count=skipped_count,
        failed_count=len(failures),
        failures=tuple(failures),
    )


def sync_requirements_to_bitable(
    settings: Settings,
    notice_id: str,
    *,
    bitable_writer=update_requirements_in_bitable,
) -> dict[str, object]:
    """Write the requirement-ledger summary onto the opportunity's Bitable record.

    Returns a redacted result; the real Feishu App Token and table id are never
    surfaced to callers.
    """
    summary = requirement_summary(settings, notice_id)
    requirements = [item.to_dict() for item in list_requirements(settings, notice_id)]
    result = bitable_writer(
        settings,
        notice_id=notice_id,
        summary=summary,
        requirements=requirements,
    )
    return result.to_dict()


def sync_requirement_task_status(
    settings: Settings,
    notice_id: str,
    *,
    client: FeishuClient | None = None,
    limit: int = 100,
) -> RequirementSyncResult:
    """Read Feishu task status back into the requirement ledger.

    When Feishu reports a task as completed but the local requirement is not, a
    conflict event is recorded instead of auto-completing the requirement — a human
    must confirm the write-back.
    """
    init_db(settings)
    feishu = client or FeishuClient(settings)
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT id, feishu_task_guid, status
            FROM opportunity_requirements
            WHERE notice_id = ? AND COALESCE(feishu_task_guid, '') <> ''
            LIMIT ?
            """,
            (notice_id.strip(), max(1, min(int(limit), 500))),
        ).fetchall()

    updated_count = 0
    conflict_count = 0
    failures: list[dict[str, str]] = []
    for row in rows:
        requirement_id = str(row["id"])
        task_guid = str(row["feishu_task_guid"])
        try:
            payload = feishu.get_task(task_guid)
            task = _nested_dict(payload, "data", "task")
            completed = _task_completed(task)
        except (FeishuError, ValueError, TypeError, KeyError) as exc:
            failures.append(
                {"requirement_id": requirement_id, "error": f"{type(exc).__name__}: {exc}"[:500]}
            )
            continue
        status = "completed" if completed else "open"
        with connection(settings) as conn:
            conn.execute(
                "UPDATE opportunity_requirements SET feishu_task_status = ?, updated_at = datetime('now') WHERE id = ?",
                (status, requirement_id),
            )
        updated_count += 1
        if completed and str(row["status"]) != "completed":
            _record_task_conflict(settings, notice_id, requirement_id)
            conflict_count += 1

    return RequirementSyncResult(
        status="partial" if failures else "finished",
        scanned_count=len(rows),
        created_count=0,
        skipped_count=0,
        failed_count=len(failures),
        updated_count=updated_count,
        conflict_count=conflict_count,
        failures=tuple(failures),
    )


def sync_requirement_completion_to_feishu(
    settings: Settings,
    notice_id: str,
    *,
    client: FeishuClient | None = None,
    limit: int = 100,
) -> RequirementSyncResult:
    """Write local requirement completion back to Feishu Task v2.

    Only requirements that already have a Feishu task and were completed locally are
    pushed; the local ledger remains the source of truth.
    """
    init_db(settings)
    feishu = client or FeishuClient(settings)
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT id, feishu_task_guid
            FROM opportunity_requirements
            WHERE notice_id = ? AND COALESCE(feishu_task_guid, '') <> ''
              AND status = 'completed' AND COALESCE(feishu_task_status, '') <> 'completed'
            LIMIT ?
            """,
            (notice_id.strip(), max(1, min(int(limit), 500))),
        ).fetchall()

    updated_count = 0
    failures: list[dict[str, str]] = []
    for row in rows:
        requirement_id = str(row["id"])
        task_guid = str(row["feishu_task_guid"])
        try:
            feishu.complete_task(task_guid)
        except (FeishuError, ValueError, TypeError, KeyError) as exc:
            failures.append(
                {"requirement_id": requirement_id, "error": f"{type(exc).__name__}: {exc}"[:500]}
            )
            continue
        with connection(settings) as conn:
            conn.execute(
                "UPDATE opportunity_requirements SET feishu_task_status = 'completed', updated_at = datetime('now') WHERE id = ?",
                (requirement_id,),
            )
        updated_count += 1

    return RequirementSyncResult(
        status="partial" if failures else "finished",
        scanned_count=len(rows),
        created_count=0,
        skipped_count=0,
        failed_count=len(failures),
        updated_count=updated_count,
        failures=tuple(failures),
    )


def sync_bid_workplan_to_feishu(
    settings: Settings,
    notice_id: str,
    *,
    client: FeishuClient | None = None,
    limit: int = 200,
) -> dict[str, object]:
    """Create idempotent Feishu tasks and calendar milestones from a confirmed workplan."""
    init_db(settings)
    feishu = client or FeishuClient(settings)
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT task.*, member.member_open_id
            FROM bid_plan_tasks AS task
            LEFT JOIN opportunity_requirements AS requirement ON requirement.id = task.requirement_id
            LEFT JOIN opportunity_team_members AS member ON member.id = requirement.assignee_member_id
            WHERE task.notice_id = ? AND task.formal = 1
            ORDER BY task.due_at, task.task_key LIMIT ?
            """,
            (notice_id, max(1, min(int(limit), 500))),
        ).fetchall()
    created_count = 0
    skipped_count = 0
    calendar_created_count = 0
    failures: list[dict[str, str]] = []
    for row in rows:
        task_id = str(row["id"])
        due_at = str(row["due_at"] or "")
        try:
            if str(row["feishu_task_guid"] or ""):
                skipped_count += 1
            else:
                response = feishu.create_task(
                    summary=str(row["title"]),
                    description="\n".join(
                        (
                            f"作战图任务：{row['task_key']}",
                            f"里程碑类型：{row['milestone_type']}",
                            f"关联要求：{row['requirement_id'] or '项目级里程碑'}",
                            f"前置任务：{row['dependency_keys_json']}",
                        )
                    ),
                    client_token=hashlib.sha256(f"tendertrace:bid-plan:{task_id}".encode()).hexdigest(),
                    due_timestamp_ms=_due_timestamp_ms(due_at),
                    assignee_open_id=str(row["member_open_id"] or ""),
                )
                task_guid = _nested_string(response, "data", "task", "guid")
                if not task_guid:
                    raise FeishuError("Feishu task guid is missing in response")
                with connection(settings) as conn:
                    conn.execute(
                        "UPDATE bid_plan_tasks SET feishu_task_guid = ?, feishu_task_status = 'open', feishu_sync_error = '', updated_at = datetime('now') WHERE id = ?",
                        (task_guid, task_id),
                    )
                created_count += 1
            if (
                settings.feishu_calendar_id
                and due_at
                and str(row["milestone_type"]) in {"review", "seal", "package", "submission"}
            ):
                timestamp = _due_timestamp_seconds(due_at)
                if timestamp:
                    feishu.create_calendar_event(
                        calendar_id=settings.feishu_calendar_id,
                        summary=f"投标作战图 · {row['title']}",
                        description=f"任务 {row['task_key']}，关联 TenderTrace 机会 {notice_id}",
                        start_timestamp=timestamp,
                        end_timestamp=str(int(timestamp) + 3600),
                        idempotency_key=hashlib.sha256(f"tendertrace:bid-calendar:{task_id}".encode()).hexdigest(),
                    )
                    calendar_created_count += 1
        except (FeishuError, ValueError, TypeError, KeyError) as exc:
            with connection(settings) as conn:
                conn.execute(
                    "UPDATE bid_plan_tasks SET feishu_sync_error = ?, updated_at = datetime('now') WHERE id = ?",
                    (f"{type(exc).__name__}: {exc}"[:500], task_id),
                )
            failures.append({"task_id": task_id, "error": f"{type(exc).__name__}: {exc}"[:500]})
    return {
        "status": "partial" if failures else "finished",
        "scanned_count": len(rows),
        "created_count": created_count,
        "skipped_count": skipped_count,
        "calendar_created_count": calendar_created_count,
        "failed_count": len(failures),
        "failures": failures,
    }


def sync_bid_workplan_task_status(
    settings: Settings,
    notice_id: str,
    *,
    client: FeishuClient | None = None,
    limit: int = 200,
) -> dict[str, object]:
    """Read completed Feishu workplan tasks back into deliverables and requirements."""
    init_db(settings)
    feishu = client or FeishuClient(settings)
    with connection(settings) as conn:
        rows = conn.execute(
            "SELECT * FROM bid_plan_tasks WHERE notice_id = ? AND COALESCE(feishu_task_guid, '') <> '' LIMIT ?",
            (notice_id, max(1, min(int(limit), 500))),
        ).fetchall()
    completed_count = 0
    failures: list[dict[str, str]] = []
    for row in rows:
        try:
            payload = feishu.get_task(str(row["feishu_task_guid"]))
            completed = _task_completed(_nested_dict(payload, "data", "task"))
        except (FeishuError, ValueError, TypeError, KeyError) as exc:
            failures.append({"task_id": str(row["id"]), "error": f"{type(exc).__name__}: {exc}"[:500]})
            continue
        if not completed:
            continue
        with connection(settings) as conn:
            conn.execute(
                "UPDATE bid_plan_tasks SET status = 'completed', feishu_task_status = 'completed', completed_at = COALESCE(completed_at, datetime('now')), updated_at = datetime('now') WHERE id = ?",
                (row["id"],),
            )
            requirement_id = str(row["requirement_id"] or "")
            if requirement_id:
                conn.execute("UPDATE bid_deliverables SET status = 'completed', updated_at = datetime('now') WHERE requirement_id = ?", (requirement_id,))
                conn.execute("UPDATE opportunity_requirements SET status = 'completed', updated_at = datetime('now') WHERE id = ?", (requirement_id,))
            conn.execute(
                "INSERT INTO opportunity_events(id, notice_id, action, actor_open_id, payload_json) VALUES (?, ?, 'bid_plan_task_completed', 'feishu', ?)",
                (str(uuid4()), notice_id, json.dumps({"task_id": row["id"], "requirement_id": requirement_id}, ensure_ascii=False, sort_keys=True)),
            )
        completed_count += 1
    return {
        "status": "partial" if failures else "finished",
        "scanned_count": len(rows),
        "completed_count": completed_count,
        "failed_count": len(failures),
        "failures": failures,
    }


def _record_task_conflict(settings: Settings, notice_id: str, requirement_id: str) -> None:
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO opportunity_events(id, notice_id, action, actor_open_id, payload_json)
            VALUES (?, ?, 'requirement_task_conflict', 'feishu', ?)
            """,
            (
                str(uuid4()),
                notice_id,
                json.dumps(
                    {
                        "requirement_id": requirement_id,
                        "reason": "feishu task completed but local requirement not completed",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            ),
        )


def _nested_dict(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def _task_completed(task: dict[str, Any]) -> bool:
    value = str(task.get("completed_at") or "").strip()
    return bool(value) and value not in {"0", "None", "null"}


def _should_sync(requirement: Any) -> bool:
    return bool(
        requirement.mandatory
        or requirement.assignee_member_id
        or requirement.status in {"pending", "review", "assigned", "in_progress"}
    )


def _task_guid(settings: Settings, requirement_id: str) -> str:
    with connection(settings) as conn:
        row = conn.execute(
            "SELECT feishu_task_guid FROM opportunity_requirements WHERE id = ?",
            (requirement_id,),
        ).fetchone()
    return str(row["feishu_task_guid"] or "") if row else ""


def _record_task(settings: Settings, requirement_id: str, task_guid: str) -> None:
    with connection(settings) as conn:
        conn.execute(
            """
            UPDATE opportunity_requirements
            SET feishu_task_guid = ?, feishu_task_status = 'open', updated_at = datetime('now')
            WHERE id = ?
            """,
            (task_guid, requirement_id),
        )


def _idempotency_key(requirement_id: str) -> str:
    return hashlib.sha256(
        f"tendertrace:requirement-task:{requirement_id}".encode("utf-8")
    ).hexdigest()


def _task_description(requirement: Any) -> str:
    return "\n".join(
        item
        for item in (
            f"要求：{requirement.title}",
            f"类型：{requirement.requirement_type_label}",
            f"证据：{requirement.evidence_text}",
            f"定位：{requirement.source_locator}",
            f"来源：{requirement.source_url}",
        )
        if item
    )


def _due_timestamp_ms(due_at: str) -> str:
    text = str(due_at or "").strip()
    if not text:
        return ""
    normalized = text.replace("Z", "+00:00")
    value: datetime | None = None
    try:
        value = datetime.fromisoformat(normalized)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                value = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if value is None:
        return ""
    return str(int(value.timestamp() * 1000))


def _due_timestamp_seconds(due_at: str) -> str:
    milliseconds = _due_timestamp_ms(due_at)
    return str(int(milliseconds) // 1000) if milliseconds else ""


def _nested_string(value: dict[str, Any], *keys: str) -> str:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return str(current or "")
