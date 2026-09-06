from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection, init_db


HUMAN_OPINION_CHANNELS = {"web", "feishu_group"}


@dataclass(frozen=True)
class HumanReviewOpinion:
    id: str
    notice_id: str
    requirement_id: str
    requirement_key: str
    content: str
    actor: str
    channel: str
    source_message_id: str
    created_at: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def record_human_review_opinion(
    settings: Settings,
    *,
    notice_id: str,
    requirement_id: str,
    content: str,
    actor: str,
    channel: str,
    source_message_id: str = "",
) -> HumanReviewOpinion:
    init_db(settings)
    normalized_notice_id = notice_id.strip()
    normalized_requirement_id = requirement_id.strip()
    normalized_content = " ".join(content.split())[:2000]
    normalized_actor = " ".join(actor.split())[:120]
    normalized_channel = channel.strip()
    if not normalized_notice_id or not normalized_requirement_id:
        raise ValueError("notice_id and requirement_id are required")
    if not normalized_content:
        raise ValueError("review opinion content is required")
    if not normalized_actor:
        raise ValueError("review opinion actor is required")
    if normalized_channel not in HUMAN_OPINION_CHANNELS:
        raise ValueError("unsupported review opinion channel")
    with connection(settings) as conn:
        requirement = conn.execute(
            """
            SELECT id, requirement_key FROM opportunity_requirements
            WHERE id = ? AND notice_id = ?
            """,
            (normalized_requirement_id, normalized_notice_id),
        ).fetchone()
        if requirement is None:
            raise LookupError("opportunity requirement not found")
        opinion_id = str(uuid4())
        inserted = conn.execute(
            """
            INSERT OR IGNORE INTO requirement_review_human_opinions(
                id, notice_id, requirement_id, content, actor, channel, source_message_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                opinion_id,
                normalized_notice_id,
                normalized_requirement_id,
                normalized_content,
                normalized_actor,
                normalized_channel,
                source_message_id.strip() or None,
            ),
        ).rowcount
        row = conn.execute(
            """
            SELECT opinion.*, requirement.requirement_key
            FROM requirement_review_human_opinions opinion
            JOIN opportunity_requirements requirement ON requirement.id = opinion.requirement_id
            WHERE opinion.id = ? OR (
                opinion.source_message_id = ? AND ? <> ''
            )
            ORDER BY opinion.created_at DESC
            LIMIT 1
            """,
            (opinion_id, source_message_id.strip(), source_message_id.strip()),
        ).fetchone()
        if row is None:
            raise RuntimeError("human review opinion was not persisted")
        if inserted:
            conn.execute(
                """
                INSERT INTO opportunity_events(id, notice_id, action, actor_open_id, payload_json)
                VALUES (?, ?, 'requirement_review_human_opinion', ?, ?)
                """,
                (
                    str(uuid4()),
                    normalized_notice_id,
                    normalized_actor,
                    json.dumps(
                        {
                            "opinion_id": str(row["id"]),
                            "requirement_id": normalized_requirement_id,
                            "requirement_key": str(requirement["requirement_key"]),
                            "channel": normalized_channel,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                ),
            )
    return _from_row(row)


def list_human_review_opinions(settings: Settings, notice_id: str) -> list[HumanReviewOpinion]:
    init_db(settings)
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT opinion.*, requirement.requirement_key
            FROM requirement_review_human_opinions opinion
            JOIN opportunity_requirements requirement ON requirement.id = opinion.requirement_id
            WHERE opinion.notice_id = ?
            ORDER BY opinion.created_at, opinion.rowid
            """,
            (notice_id.strip(),),
        ).fetchall()
    return [_from_row(row) for row in rows]


def find_requirement_by_key(
    settings: Settings,
    *,
    notice_id: str,
    requirement_key: str,
) -> dict[str, str] | None:
    init_db(settings)
    with connection(settings) as conn:
        row = conn.execute(
            """
            SELECT id, requirement_key FROM opportunity_requirements
            WHERE notice_id = ? AND requirement_key = ?
            """,
            (notice_id.strip(), requirement_key.strip()),
        ).fetchone()
    if row is None:
        return None
    return {"id": str(row["id"]), "requirement_key": str(row["requirement_key"])}


def _from_row(row: Any) -> HumanReviewOpinion:
    return HumanReviewOpinion(
        id=str(row["id"]),
        notice_id=str(row["notice_id"]),
        requirement_id=str(row["requirement_id"]),
        requirement_key=str(row["requirement_key"]),
        content=str(row["content"]),
        actor=str(row["actor"]),
        channel=str(row["channel"]),
        source_message_id=str(row["source_message_id"] or ""),
        created_at=str(row["created_at"]),
    )
