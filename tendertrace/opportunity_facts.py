from __future__ import annotations

from dataclasses import replace
import json
import re
from typing import Any
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid4, uuid5

from tendertrace.adapters.ccgp import Notice
from tendertrace.config import Settings
from tendertrace.db import connection, json_dumps
from tendertrace.retrieval import parse_date


FACT_FIELDS = {
    "purchaser": "采购主体",
    "project_no": "项目编号",
    "budget": "预算",
    "bid_deadline": "投标截止",
    "region": "地区",
}


def upsert_verified_facts(
    settings: Settings,
    *,
    notice_id: str,
    facts: dict[str, object],
    source_url: str,
    evidence_text: str = "",
    note: str = "",
    actor: str = "admin",
    channel: str = "web",
) -> list[dict[str, object]]:
    notice_id = notice_id.strip()
    source_url = _validated_source_url(source_url)
    normalized = {
        field: _validated_value(field, value)
        for field, value in facts.items()
        if field in FACT_FIELDS and str(value or "").strip()
    }
    unknown = sorted(set(facts) - set(FACT_FIELDS))
    if unknown:
        raise ValueError(f"unsupported fact fields: {', '.join(unknown)}")
    if not normalized:
        raise ValueError("at least one supported fact value is required")
    evidence_text = evidence_text.strip()[:2000]
    note = note.strip()[:1000]
    actor = actor.strip()[:120] or "admin"
    channel = channel.strip()[:40] or "web"
    with connection(settings) as conn:
        notice = conn.execute(
            "SELECT id FROM notices WHERE id = ?",
            (notice_id,),
        ).fetchone()
        if notice is None:
            raise LookupError("opportunity not found")
        existing_rows = conn.execute(
            """
            SELECT id, notice_id, field_name, field_value, source_url, evidence_text,
                   note, actor, channel, created_at, updated_at
            FROM opportunity_fact_overrides
            WHERE notice_id = ?
            ORDER BY updated_at DESC, field_name ASC
            """,
            (notice_id,),
        ).fetchall()
        before = {str(row["field_name"]): str(row["field_value"]) for row in existing_rows}
        existing = {str(row["field_name"]): row for row in existing_rows}
        unchanged = all(
            field in existing
            and str(existing[field]["field_value"]) == value
            and str(existing[field]["source_url"]) == source_url
            and str(existing[field]["evidence_text"] or "") == evidence_text
            and str(existing[field]["note"] or "") == note
            and str(existing[field]["actor"] or "") == actor
            and str(existing[field]["channel"] or "") == channel
            for field, value in normalized.items()
        )
        if unchanged:
            return [_row_payload(row) for row in existing_rows]
        for field, value in normalized.items():
            override_id = str(
                uuid5(NAMESPACE_URL, f"tendertrace:opportunity-fact:{notice_id}:{field}")
            )
            conn.execute(
                """
                INSERT INTO opportunity_fact_overrides(
                    id, notice_id, field_name, field_value, source_url,
                    evidence_text, note, actor, channel
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(notice_id, field_name) DO UPDATE SET
                    field_value = excluded.field_value,
                    source_url = excluded.source_url,
                    evidence_text = excluded.evidence_text,
                    note = excluded.note,
                    actor = excluded.actor,
                    channel = excluded.channel,
                    updated_at = datetime('now')
                """,
                (
                    override_id,
                    notice_id,
                    field,
                    value,
                    source_url,
                    evidence_text,
                    note,
                    actor,
                    channel,
                ),
            )
        conn.execute(
            """
            INSERT INTO opportunity_events(
                id, notice_id, action, from_stage, to_stage, actor_open_id, payload_json
            ) VALUES (?, ?, 'facts_verified', NULL, NULL, ?, ?)
            """,
            (
                str(uuid4()),
                notice_id,
                actor,
                json_dumps(
                    {
                        "channel": channel,
                        "before": {field: before.get(field, "") for field in normalized},
                        "after": normalized,
                        "source_url": source_url,
                        "evidence_text": evidence_text,
                        "note": note,
                    }
                ),
            ),
        )
        rows = conn.execute(
            """
            SELECT id, notice_id, field_name, field_value, source_url, evidence_text,
                   note, actor, channel, created_at, updated_at
            FROM opportunity_fact_overrides
            WHERE notice_id = ?
            ORDER BY updated_at DESC, field_name ASC
            """,
            (notice_id,),
        ).fetchall()
    return [_row_payload(row) for row in rows]


def load_fact_overrides(
    settings: Settings,
    notice_ids: list[str],
) -> dict[str, list[dict[str, object]]]:
    wanted = {str(value) for value in notice_ids if str(value).strip()}
    if not wanted:
        return {}
    ordered_ids = sorted(wanted)
    placeholders = ", ".join("?" for _notice_id in ordered_ids)
    with connection(settings) as conn:
        rows = conn.execute(
            f"""
            SELECT id, notice_id, field_name, field_value, source_url, evidence_text,
                   note, actor, channel, created_at, updated_at
            FROM opportunity_fact_overrides
            WHERE notice_id IN ({placeholders})
            ORDER BY updated_at DESC, field_name ASC
            """,
            ordered_ids,
        ).fetchall()
    result: dict[str, list[dict[str, object]]] = {notice_id: [] for notice_id in wanted}
    for row in rows:
        notice_id = str(row["notice_id"])
        if notice_id in wanted:
            result[notice_id].append(_row_payload(row))
    return result


def load_fact_audit(
    settings: Settings,
    notice_id: str,
    *,
    limit: int = 20,
) -> list[dict[str, object]]:
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT id, actor_open_id, payload_json, created_at
            FROM opportunity_events
            WHERE notice_id = ? AND action = 'facts_verified'
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
            """,
            (notice_id, max(1, min(int(limit), 100))),
        ).fetchall()
    return [
        {
            "id": str(row["id"]),
            "actor": str(row["actor_open_id"] or ""),
            "payload": _json_object(row["payload_json"]),
            "created_at": str(row["created_at"] or ""),
        }
        for row in rows
    ]


def apply_fact_overrides(
    notice: Notice,
    overrides: list[dict[str, object]],
) -> Notice:
    if not overrides:
        return notice
    values = {
        str(item.get("field_name") or ""): str(item.get("field_value") or "")
        for item in overrides
    }
    fields = dict(notice.fields)
    structured = dict(fields.get("structured_fields") or {})
    provenance = dict(fields.get("structured_field_evidence") or {})
    for item in overrides:
        field = str(item.get("field_name") or "")
        value = str(item.get("field_value") or "")
        if field not in FACT_FIELDS or not value:
            continue
        structured[field] = value
        provenance[field] = {
            "value": value,
            "source_url": str(item.get("source_url") or ""),
            "evidence_text": str(item.get("evidence_text") or ""),
            "origin": "verified_override",
            "actor": str(item.get("actor") or ""),
            "updated_at": str(item.get("updated_at") or ""),
        }
    fields.update(
        {
            "structured_fields": structured,
            "structured_field_evidence": provenance,
            "fact_overrides": overrides,
            "verified_fact_count": len(overrides),
        }
    )
    return replace(
        notice,
        purchaser=values.get("purchaser") or notice.purchaser,
        region=values.get("region") or notice.region,
        fields=fields,
    )


def _validated_value(field: str, value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        raise ValueError(f"{field} value is required")
    if len(text) > 500:
        raise ValueError(f"{field} value is too long")
    if field == "bid_deadline" and parse_date(text) is None:
        raise ValueError("bid_deadline must contain a valid date")
    if field == "budget" and not re.search(r"\d", text):
        raise ValueError("budget must contain a numeric amount")
    return text


def _validated_source_url(value: str) -> str:
    text = value.strip()
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("source_url must be an absolute HTTP(S) URL")
    return text[:2000]


def _row_payload(row: Any) -> dict[str, object]:
    return {
        "id": str(row["id"]),
        "notice_id": str(row["notice_id"]),
        "field_name": str(row["field_name"]),
        "field_label": FACT_FIELDS.get(str(row["field_name"]), str(row["field_name"])),
        "field_value": str(row["field_value"]),
        "source_url": str(row["source_url"]),
        "evidence_text": str(row["evidence_text"] or ""),
        "note": str(row["note"] or ""),
        "actor": str(row["actor"] or ""),
        "channel": str(row["channel"] or ""),
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }


def _json_object(value: object) -> dict[str, object]:
    try:
        payload = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
