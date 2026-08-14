from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection


@dataclass(frozen=True)
class DeliveryAttempt:
    id: str
    channel: str
    artifact_type: str
    artifact_key: str
    run_id: str | None
    subscription_id: str | None
    status: str
    external_id: str | None
    error: str | None
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def record_delivery_attempt(
    settings: Settings,
    *,
    channel: str,
    artifact_type: str,
    artifact_key: str,
    status: str,
    run_id: str | None = None,
    subscription_id: str | None = None,
    external_id: str | None = None,
    error: str | None = None,
) -> DeliveryAttempt:
    attempt_id = str(uuid4())
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO delivery_attempts(
                id, channel, artifact_type, artifact_key, run_id, subscription_id,
                status, external_id, error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attempt_id,
                channel,
                artifact_type,
                artifact_key,
                run_id,
                subscription_id,
                status,
                external_id,
                error,
            ),
        )
        row = conn.execute(
            "SELECT * FROM delivery_attempts WHERE id = ?",
            (attempt_id,),
        ).fetchone()
    return _from_row(row)


def list_delivery_attempts(
    settings: Settings,
    *,
    channel: str | None = None,
    limit: int = 100,
) -> list[DeliveryAttempt]:
    where = "WHERE channel = ?" if channel else ""
    params: tuple[object, ...] = (channel, min(max(limit, 1), 500)) if channel else (
        min(max(limit, 1), 500),
    )
    with connection(settings) as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM delivery_attempts
            {where}
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [_from_row(row) for row in rows]


def _from_row(row) -> DeliveryAttempt:
    return DeliveryAttempt(
        id=row["id"],
        channel=row["channel"],
        artifact_type=row["artifact_type"],
        artifact_key=row["artifact_key"],
        run_id=row["run_id"],
        subscription_id=row["subscription_id"],
        status=row["status"],
        external_id=row["external_id"],
        error=row["error"],
        created_at=row["created_at"],
    )
