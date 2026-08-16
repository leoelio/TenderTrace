from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from typing import Any, Callable

from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps
from tendertrace.integrations.feishu import FeishuClient, FeishuError


ACTIVE_SOURCE_INCIDENT_STATUSES = (
    "open",
    "overdue",
    "recovered_pending_close",
    "verification_failed",
)


@dataclass(frozen=True)
class SourceIncident:
    artifact_key: str
    status: str
    severity: str
    issue_count: int
    source_sites: tuple[str, ...]
    feishu_task_guid: str
    assigned: bool
    due_at: str
    task_completed_at: str
    synced_at: str
    resolved_at: str
    last_error: str
    created_at: str
    updated_at: str

    def safe_dict(self) -> dict[str, object]:
        value = asdict(self)
        value.pop("feishu_task_guid", None)
        value["source_sites"] = list(self.source_sites)
        value["task_configured"] = bool(self.feishu_task_guid)
        return value


@dataclass(frozen=True)
class SourceIncidentSyncResult:
    status: str
    scanned_count: int
    updated_count: int
    resolved_count: int
    verification_failed_count: int
    overdue_count: int
    recovered_count: int
    failed_count: int
    failures: tuple[dict[str, str], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def upsert_source_incident(
    settings: Settings,
    *,
    snapshot: dict[str, object],
    artifact_key: str,
    task_guid: str,
    assigned: bool,
    due_at: datetime,
) -> SourceIncident:
    init_db(settings)
    issues = [item for item in snapshot.get("issues") or [] if isinstance(item, dict)]
    source_sites = tuple(
        dict.fromkeys(str(item.get("site") or "").strip() for item in issues)
    )
    source_sites = tuple(site for site in source_sites if site)
    severity = "critical" if any(item.get("severity") == "critical" for item in issues) else "warning"
    due_text = due_at.isoformat(timespec="seconds")
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO source_incidents(
                artifact_key, status, severity, issue_count, source_sites_json,
                snapshot_json, feishu_task_guid, assigned, due_at
            ) VALUES (?, 'open', ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(artifact_key) DO UPDATE SET
                status = CASE
                    WHEN source_incidents.status = 'resolved' THEN 'verification_failed'
                    ELSE source_incidents.status
                END,
                severity = excluded.severity,
                issue_count = excluded.issue_count,
                source_sites_json = excluded.source_sites_json,
                snapshot_json = excluded.snapshot_json,
                feishu_task_guid = excluded.feishu_task_guid,
                assigned = excluded.assigned,
                due_at = excluded.due_at,
                resolved_at = CASE
                    WHEN source_incidents.status = 'resolved' THEN NULL
                    ELSE source_incidents.resolved_at
                END,
                last_error = NULL,
                updated_at = datetime('now')
            """,
            (
                artifact_key,
                severity,
                len(issues),
                json_dumps(source_sites),
                json_dumps(snapshot),
                task_guid,
                int(assigned),
                due_text,
            ),
        )
        row = conn.execute(
            "SELECT * FROM source_incidents WHERE artifact_key = ?",
            (artifact_key,),
        ).fetchone()
    return _from_row(row)


def list_source_incidents(
    settings: Settings,
    *,
    statuses: tuple[str, ...] | None = None,
    limit: int = 20,
) -> list[SourceIncident]:
    init_db(settings)
    params: list[object] = []
    where = ""
    if statuses:
        placeholders = ",".join("?" for _ in statuses)
        where = f"WHERE status IN ({placeholders})"
        params.extend(statuses)
    params.append(max(1, min(int(limit), 200)))
    with connection(settings) as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM source_incidents
            {where}
            ORDER BY updated_at DESC, created_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
    return [_from_row(row) for row in rows]


def sync_source_incidents(
    settings: Settings,
    *,
    limit: int = 100,
    client: FeishuClient | None = None,
    snapshot_loader: Callable[..., dict[str, object]] | None = None,
    now: datetime | None = None,
) -> SourceIncidentSyncResult:
    reference = _as_utc(now or datetime.now(timezone.utc))
    incidents = list_source_incidents(
        settings,
        statuses=ACTIVE_SOURCE_INCIDENT_STATUSES,
        limit=limit,
    )
    if not incidents:
        return SourceIncidentSyncResult("skipped", 0, 0, 0, 0, 0, 0, 0)
    if snapshot_loader is None:
        from tendertrace.integrations.feishu_source_alerts import build_source_alert_snapshot

        snapshot_loader = build_source_alert_snapshot
    snapshot = snapshot_loader(settings, now=reference)
    current_issues = [item for item in snapshot.get("issues") or [] if isinstance(item, dict)]
    current_issue_sites = {
        str(item.get("site") or "").strip() for item in current_issues if item.get("site")
    }
    feishu = client or FeishuClient(settings)
    updated_count = 0
    resolved_count = 0
    verification_failed_count = 0
    overdue_count = 0
    recovered_count = 0
    failures: list[dict[str, str]] = []
    for incident in incidents:
        try:
            task = _task(feishu.get_task(incident.feishu_task_guid))
            completed_at = _timestamp_ms(task.get("completed_at"))
            due = task.get("due")
            remote_due = _timestamp_ms(due.get("timestamp")) if isinstance(due, dict) else None
            due_at = remote_due or _parse_datetime(incident.due_at)
            source_recovered = not set(incident.source_sites).intersection(current_issue_sites)
            status = _incident_status(
                completed_at=completed_at,
                due_at=due_at,
                source_recovered=source_recovered,
                now=reference,
            )
            _update_incident(
                settings,
                incident.artifact_key,
                status=status,
                completed_at=completed_at,
                synced_at=reference,
            )
            updated_count += int(status != incident.status)
            resolved_count += int(status == "resolved")
            verification_failed_count += int(status == "verification_failed")
            overdue_count += int(status == "overdue")
            recovered_count += int(status == "recovered_pending_close")
        except (FeishuError, ValueError, TypeError) as exc:
            error = f"{type(exc).__name__}: {exc}"[:500]
            _record_sync_failure(settings, incident.artifact_key, error, reference)
            failures.append({"artifact_key": incident.artifact_key, "error": error})
    return SourceIncidentSyncResult(
        status="partial" if failures else "finished",
        scanned_count=len(incidents),
        updated_count=updated_count,
        resolved_count=resolved_count,
        verification_failed_count=verification_failed_count,
        overdue_count=overdue_count,
        recovered_count=recovered_count,
        failed_count=len(failures),
        failures=tuple(failures),
    )


def _incident_status(
    *,
    completed_at: datetime | None,
    due_at: datetime | None,
    source_recovered: bool,
    now: datetime,
) -> str:
    if completed_at is not None:
        return "resolved" if source_recovered else "verification_failed"
    if source_recovered:
        return "recovered_pending_close"
    if due_at is not None and due_at < now:
        return "overdue"
    return "open"


def _update_incident(
    settings: Settings,
    artifact_key: str,
    *,
    status: str,
    completed_at: datetime | None,
    synced_at: datetime,
) -> None:
    resolved_at = synced_at.isoformat(timespec="seconds") if status == "resolved" else None
    with connection(settings) as conn:
        conn.execute(
            """
            UPDATE source_incidents
            SET status = ?, task_completed_at = ?, synced_at = ?, resolved_at = ?,
                last_error = NULL, updated_at = datetime('now')
            WHERE artifact_key = ?
            """,
            (
                status,
                completed_at.isoformat(timespec="seconds") if completed_at else None,
                synced_at.isoformat(timespec="seconds"),
                resolved_at,
                artifact_key,
            ),
        )


def _record_sync_failure(
    settings: Settings,
    artifact_key: str,
    error: str,
    synced_at: datetime,
) -> None:
    with connection(settings) as conn:
        conn.execute(
            """
            UPDATE source_incidents
            SET synced_at = ?, last_error = ?, updated_at = datetime('now')
            WHERE artifact_key = ?
            """,
            (synced_at.isoformat(timespec="seconds"), error, artifact_key),
        )


def _task(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    task = data.get("task") if isinstance(data, dict) else None
    if not isinstance(task, dict):
        raise ValueError("Feishu task is missing in response")
    return task


def _timestamp_ms(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text or text == "0":
        return None
    try:
        return datetime.fromtimestamp(int(text) / 1000, tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _from_row(row) -> SourceIncident:
    try:
        source_sites = tuple(str(value) for value in json.loads(row["source_sites_json"]))
    except (TypeError, ValueError, json.JSONDecodeError):
        source_sites = ()
    return SourceIncident(
        artifact_key=str(row["artifact_key"]),
        status=str(row["status"]),
        severity=str(row["severity"]),
        issue_count=int(row["issue_count"] or 0),
        source_sites=source_sites,
        feishu_task_guid=str(row["feishu_task_guid"] or ""),
        assigned=bool(row["assigned"]),
        due_at=str(row["due_at"] or ""),
        task_completed_at=str(row["task_completed_at"] or ""),
        synced_at=str(row["synced_at"] or ""),
        resolved_at=str(row["resolved_at"] or ""),
        last_error=str(row["last_error"] or ""),
        created_at=str(row["created_at"] or ""),
        updated_at=str(row["updated_at"] or ""),
    )
