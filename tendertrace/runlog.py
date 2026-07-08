from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection, json_dumps


@dataclass(frozen=True)
class OutboxMessage:
    id: str
    run_id: str
    subscription_id: str | None
    docx_path: str
    status: str
    created_at: str


def start_run(
    settings: Settings,
    *,
    run_id: str,
    original_query: str,
    mode: str,
    subscription_id: str | None = None,
    window_start: str | None = None,
    window_end: str | None = None,
) -> None:
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO runs(
                id, subscription_id, original_query, mode, status, window_start, window_end
            )
            VALUES (?, ?, ?, ?, 'running', ?, ?)
            """,
            (run_id, subscription_id, original_query, mode, window_start, window_end),
        )


def finish_run(
    settings: Settings,
    *,
    run_id: str,
    status: str,
    output_docx_path: Path | str | None,
    stats: dict[str, Any],
    error: str | None = None,
) -> None:
    with connection(settings) as conn:
        conn.execute(
            """
            UPDATE runs
            SET status = ?,
                finished_at = datetime('now'),
                output_docx_path = ?,
                stats_json = ?,
                error = ?
            WHERE id = ?
            """,
            (
                status,
                str(output_docx_path) if output_docx_path else None,
                json_dumps(stats),
                error,
                run_id,
            ),
        )


def register_outbox_message(
    settings: Settings,
    *,
    run_id: str,
    docx_path: Path | str,
    subscription_id: str | None = None,
    message_id: str | None = None,
) -> OutboxMessage:
    item_id = message_id or str(uuid4())
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO outbox_messages(id, run_id, subscription_id, docx_path, status)
            VALUES (?, ?, ?, ?, 'ready')
            """,
            (item_id, run_id, subscription_id, str(docx_path)),
        )
        row = conn.execute(
            """
            SELECT id, run_id, subscription_id, docx_path, status, created_at
            FROM outbox_messages
            WHERE id = ?
            """,
            (item_id,),
        ).fetchone()
    return OutboxMessage(
        id=row["id"],
        run_id=row["run_id"],
        subscription_id=row["subscription_id"],
        docx_path=row["docx_path"],
        status=row["status"],
        created_at=row["created_at"],
    )


def list_outbox_messages(settings: Settings) -> list[OutboxMessage]:
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT id, run_id, subscription_id, docx_path, status, created_at
            FROM outbox_messages
            ORDER BY created_at DESC
            """
        ).fetchall()
    return [
        OutboxMessage(
            id=row["id"],
            run_id=row["run_id"],
            subscription_id=row["subscription_id"],
            docx_path=row["docx_path"],
            status=row["status"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_run(settings: Settings, run_id: str) -> dict[str, Any] | None:
    with connection(settings) as conn:
        row = conn.execute(
            """
            SELECT id, subscription_id, original_query, mode, status, window_start, window_end,
                   started_at, finished_at, output_docx_path, stats_json, error
            FROM runs
            WHERE id = ?
            """,
            (run_id,),
        ).fetchone()
    if row is None:
        return None
    value = dict(row)
    value["stats"] = json.loads(value.pop("stats_json"))
    return value
