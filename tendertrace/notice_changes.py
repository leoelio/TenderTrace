from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
import sqlite3
from typing import Any, Iterable
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection, json_dumps


TRACKED_FIELDS = (
    "title",
    "publish_time",
    "region",
    "purchaser",
    "project_no",
    "budget",
    "bid_deadline",
    "source_url",
    "content_text",
    "core_content",
    "attachments",
    "attachment_fingerprints",
)


@dataclass(frozen=True)
class NoticeRevision:
    id: str
    notice_id: str
    title: str
    source_url: str
    change_hash: str
    changed_fields: tuple[str, ...]
    before: dict[str, Any]
    after: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["changed_fields"] = list(self.changed_fields)
        return value


def notice_change_payload(
    *,
    title: object,
    publish_time: object,
    region: object,
    purchaser: object,
    source_url: object,
    content_text: object,
    core_content: object,
    attachments: object,
    fields: object,
) -> dict[str, object]:
    field_map = fields if isinstance(fields, dict) else {}
    structured = field_map.get("structured_fields")
    structured = structured if isinstance(structured, dict) else {}
    snapshots = field_map.get("attachment_snapshots")
    snapshots = snapshots if isinstance(snapshots, list) else []
    return {
        "title": _text(title),
        "publish_time": _text(publish_time),
        "region": _text(region),
        "purchaser": _text(purchaser),
        "project_no": _text(field_map.get("project_no") or structured.get("project_no")),
        "budget": _text(field_map.get("budget") or structured.get("budget")),
        "bid_deadline": _text(
            field_map.get("bid_deadline") or structured.get("bid_deadline")
        ),
        "source_url": _text(source_url),
        "content_text": _text(content_text),
        "core_content": _text(core_content),
        "attachments": _attachments(attachments),
        "attachment_fingerprints": sorted(
            {
                _text(item.get("sha256"))
                for item in snapshots
                if isinstance(item, dict) and _text(item.get("sha256"))
            }
        ),
    }


def notice_change_payload_from_row(row: sqlite3.Row) -> dict[str, object]:
    return notice_change_payload(
        title=row["title"],
        publish_time=row["publish_time"],
        region=row["region"],
        purchaser=row["purchaser"],
        source_url=row["source_url"],
        content_text=row["content_text"],
        core_content=row["core_content"],
        attachments=_json_value(row["attachments_json"], []),
        fields=_json_value(row["fields_json"], {}),
    )


def record_notice_revision(
    conn: sqlite3.Connection,
    *,
    notice_id: str,
    before: dict[str, object],
    after: dict[str, object],
) -> NoticeRevision | None:
    changed_fields = tuple(
        field for field in TRACKED_FIELDS if before.get(field) != after.get(field)
    )
    if not changed_fields:
        return None
    before_changed = {field: _audit_value(before.get(field)) for field in changed_fields}
    after_changed = {field: _audit_value(after.get(field)) for field in changed_fields}
    change_hash = hashlib.sha256(
        json_dumps(
            {
                "notice_id": notice_id,
                "before": before_changed,
                "after": after_changed,
            }
        ).encode("utf-8")
    ).hexdigest()
    revision_id = str(uuid4())
    conn.execute(
        """
        INSERT INTO notice_revisions(
            id, notice_id, change_hash, changed_fields_json, before_json, after_json
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            revision_id,
            notice_id,
            change_hash,
            json_dumps(changed_fields),
            json_dumps(before_changed),
            json_dumps(after_changed),
        ),
    )
    row = conn.execute(
        """
        SELECT r.*, n.title, n.source_url
        FROM notice_revisions r
        JOIN notices n ON n.id = r.notice_id
        WHERE r.id = ?
        """,
        (revision_id,),
    ).fetchone()
    return _from_row(row)


def list_notice_revisions(
    settings: Settings,
    *,
    notice_id: str = "",
    limit: int = 100,
    offset: int = 0,
) -> list[NoticeRevision]:
    where = "WHERE r.notice_id = ?" if notice_id else ""
    params: tuple[object, ...] = (
        (notice_id, min(max(limit, 1), 500), max(offset, 0))
        if notice_id
        else (min(max(limit, 1), 500), max(offset, 0))
    )
    with connection(settings) as conn:
        rows = conn.execute(
            f"""
            SELECT r.*, n.title, n.source_url
            FROM notice_revisions r
            JOIN notices n ON n.id = r.notice_id
            {where}
            ORDER BY r.created_at DESC, r.rowid DESC
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()
    return [_from_row(row) for row in rows]


def notice_change_summaries(
    settings: Settings,
    notice_ids: Iterable[str],
) -> dict[str, dict[str, object]]:
    unique_ids = list(dict.fromkeys(value for value in notice_ids if value))
    if not unique_ids:
        return {}
    placeholders = ",".join("?" for _ in unique_ids)
    with connection(settings) as conn:
        rows = conn.execute(
            f"""
            WITH ranked AS (
                SELECT r.*,
                       COUNT(*) OVER (PARTITION BY notice_id) AS change_count,
                       ROW_NUMBER() OVER (
                           PARTITION BY notice_id
                           ORDER BY created_at DESC, rowid DESC
                       ) AS revision_rank
                FROM notice_revisions r
                WHERE notice_id IN ({placeholders})
            )
            SELECT * FROM ranked WHERE revision_rank = 1
            """,
            unique_ids,
        ).fetchall()
    return {
        str(row["notice_id"]): {
            "count": int(row["change_count"] or 0),
            "latest_at": str(row["created_at"] or ""),
            "changed_fields": _string_list(row["changed_fields_json"]),
            "before": _json_value(row["before_json"], {}),
            "after": _json_value(row["after_json"], {}),
        }
        for row in rows
    }


def _from_row(row: sqlite3.Row) -> NoticeRevision:
    return NoticeRevision(
        id=str(row["id"]),
        notice_id=str(row["notice_id"]),
        title=str(row["title"] or ""),
        source_url=str(row["source_url"] or ""),
        change_hash=str(row["change_hash"] or ""),
        changed_fields=tuple(_string_list(row["changed_fields_json"])),
        before=_dict_value(row["before_json"]),
        after=_dict_value(row["after_json"]),
        created_at=str(row["created_at"] or ""),
    )


def _attachments(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    normalized = {
        (_text(item.get("name")), _text(item.get("url")))
        for item in value
        if isinstance(item, dict) and (_text(item.get("name")) or _text(item.get("url")))
    }
    return [{"name": name, "url": url} for name, url in sorted(normalized)]


def _audit_value(value: object) -> object:
    if isinstance(value, str) and len(value) > 2000:
        return {
            "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
            "excerpt": value[:500],
        }
    return value


def _text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _json_value(value: object, default: object) -> object:
    if not isinstance(value, str):
        return value if value is not None else default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _dict_value(value: object) -> dict[str, Any]:
    parsed = _json_value(value, {})
    return parsed if isinstance(parsed, dict) else {}


def _string_list(value: object) -> list[str]:
    parsed = _json_value(value, [])
    return [str(item) for item in parsed] if isinstance(parsed, list) else []
