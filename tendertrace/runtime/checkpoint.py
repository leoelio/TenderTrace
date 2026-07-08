from __future__ import annotations

from dataclasses import dataclass
import json

from tendertrace.config import Settings
from tendertrace.db import connection, json_dumps
from tendertrace.runtime.state import RunState


@dataclass(frozen=True)
class Checkpoint:
    run_id: str
    seq: int
    node: str
    state: RunState
    status: str


class SqliteCheckpointer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def save(self, *, node: str, state: RunState, status: str = "completed") -> Checkpoint:
        with connection(self.settings) as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM run_checkpoints WHERE run_id = ?",
                (state.run_id,),
            ).fetchone()
            seq = int(row["next_seq"])
            conn.execute(
                """
                INSERT INTO run_checkpoints(run_id, seq, node, state_json, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (state.run_id, seq, node, json_dumps(state.to_dict()), status),
            )
        return Checkpoint(run_id=state.run_id, seq=seq, node=node, state=state, status=status)

    def latest(self, run_id: str) -> Checkpoint | None:
        with connection(self.settings) as conn:
            row = conn.execute(
                """
                SELECT run_id, seq, node, state_json, status
                FROM run_checkpoints
                WHERE run_id = ?
                ORDER BY seq DESC
                LIMIT 1
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return Checkpoint(
            run_id=row["run_id"],
            seq=row["seq"],
            node=row["node"],
            state=RunState.from_dict(json.loads(row["state_json"])),
            status=row["status"],
        )

    def list(self, run_id: str) -> list[Checkpoint]:
        with connection(self.settings) as conn:
            rows = conn.execute(
                """
                SELECT run_id, seq, node, state_json, status
                FROM run_checkpoints
                WHERE run_id = ?
                ORDER BY seq
                """,
                (run_id,),
            ).fetchall()
        return [
            Checkpoint(
                run_id=row["run_id"],
                seq=row["seq"],
                node=row["node"],
                state=RunState.from_dict(json.loads(row["state_json"])),
                status=row["status"],
            )
            for row in rows
        ]
