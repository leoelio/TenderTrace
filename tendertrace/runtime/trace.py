from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from tendertrace.config import Settings
from tendertrace.db import connection, json_dumps
from tendertrace.runtime.bus import RuntimeEvent


@dataclass(frozen=True)
class StoredEvent:
    run_id: str
    seq: int
    event_type: str
    node: str | None
    payload: dict[str, Any]
    created_at: str


class SqliteTraceStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def record(self, event: RuntimeEvent) -> StoredEvent:
        with connection(self.settings) as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM trace_events WHERE run_id = ?",
                (event.run_id,),
            ).fetchone()
            seq = int(row["next_seq"])
            conn.execute(
                """
                INSERT INTO trace_events(run_id, seq, event_type, node, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event.run_id,
                    seq,
                    event.event_type,
                    event.node,
                    json_dumps(event.payload),
                    event.created_at,
                ),
            )
        return StoredEvent(
            run_id=event.run_id,
            seq=seq,
            event_type=event.event_type,
            node=event.node,
            payload=event.payload,
            created_at=event.created_at,
        )

    def list_events(self, run_id: str) -> list[StoredEvent]:
        with connection(self.settings) as conn:
            rows = conn.execute(
                """
                SELECT run_id, seq, event_type, node, payload_json, created_at
                FROM trace_events
                WHERE run_id = ?
                ORDER BY seq
                """,
                (run_id,),
            ).fetchall()
        return [
            StoredEvent(
                run_id=row["run_id"],
                seq=row["seq"],
                event_type=row["event_type"],
                node=row["node"],
                payload=json.loads(row["payload_json"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

