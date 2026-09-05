from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
from typing import Any

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.integrations.feishu import FeishuClient, FeishuError
from tendertrace.opportunity_requirements import list_requirements


@dataclass(frozen=True)
class RequirementSyncResult:
    status: str
    scanned_count: int
    created_count: int
    skipped_count: int
    failed_count: int
    failures: tuple[dict[str, str], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def sync_requirements_to_feishu(
    settings: Settings,
    notice_id: str,
    *,
    client: FeishuClient | None = None,
    limit: int = 100,
) -> RequirementSyncResult:
    """Idempotently create one Feishu Task v2 per actionable requirement.

    A stable ``client_token`` derived from the requirement id makes task creation
    idempotent at the Feishu side, and the stored ``feishu_task_guid`` makes it
    idempotent locally. This layer only *creates* external tasks; it never rewrites
    a requirement's status, evidence or human conclusions.
    """
    init_db(settings)
    requirements = list_requirements(settings, notice_id)
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


def _nested_string(value: dict[str, Any], *keys: str) -> str:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return str(current or "")
