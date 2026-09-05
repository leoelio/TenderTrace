from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection, init_db


@dataclass(frozen=True)
class OpportunityCollaborationNote:
    id: str
    notice_id: str
    content: str
    actor: str
    channel: str
    source_message_id: str
    created_at: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def list_collaboration_notes(
    settings: Settings,
    notice_id: str,
    *,
    limit: int = 50,
) -> list[OpportunityCollaborationNote]:
    init_db(settings)
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT id, notice_id, content, actor, channel, source_message_id, created_at
            FROM opportunity_collaboration_notes
            WHERE notice_id = ?
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
            """,
            (notice_id, max(1, min(int(limit), 200))),
        ).fetchall()
    return [_from_row(row) for row in rows]


def record_collaboration_note(
    settings: Settings,
    *,
    notice_id: str,
    content: str,
    actor: str,
    channel: str,
    source_message_id: str = "",
) -> OpportunityCollaborationNote:
    normalized_content = " ".join(content.split())
    normalized_actor = " ".join(actor.split())
    if not normalized_content:
        raise ValueError("collaboration note content is required")
    if not normalized_actor:
        raise ValueError("collaboration note actor is required")
    if channel not in {"web", "feishu_group", "api"}:
        raise ValueError("unsupported collaboration note channel")
    init_db(settings)
    note_id = str(uuid4())
    with connection(settings) as conn:
        if source_message_id:
            existing = conn.execute(
                """
                SELECT id, notice_id, content, actor, channel, source_message_id, created_at
                FROM opportunity_collaboration_notes
                WHERE source_message_id = ?
                """,
                (source_message_id,),
            ).fetchone()
            if existing is not None:
                return _from_row(existing)
        conn.execute(
            """
            INSERT INTO opportunity_collaboration_notes(
                id, notice_id, content, actor, channel, source_message_id
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (note_id, notice_id, normalized_content[:2000], normalized_actor[:120], channel, source_message_id or None),
        )
        conn.execute(
            """
            INSERT INTO opportunity_events(id, notice_id, action, actor_open_id, payload_json)
            VALUES (?, ?, 'collaboration_note_recorded', ?, ?)
            """,
            (
                str(uuid4()),
                notice_id,
                normalized_actor[:120],
                json.dumps(
                    {"channel": channel, "note_id": note_id, "source_message_id": source_message_id},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            ),
        )
        row = conn.execute(
            """
            SELECT id, notice_id, content, actor, channel, source_message_id, created_at
            FROM opportunity_collaboration_notes WHERE id = ?
            """,
            (note_id,),
        ).fetchone()
    assert row is not None
    return _from_row(row)


def _from_row(row: object) -> OpportunityCollaborationNote:
    return OpportunityCollaborationNote(
        id=str(row["id"]),
        notice_id=str(row["notice_id"]),
        content=str(row["content"]),
        actor=str(row["actor"]),
        channel=str(row["channel"]),
        source_message_id=str(row["source_message_id"] or ""),
        created_at=str(row["created_at"]),
    )
