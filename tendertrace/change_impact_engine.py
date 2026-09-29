from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3
from typing import Any
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps
from tendertrace.delivery.preferences import resolve_feishu_receiver
from tendertrace.integrations.feishu import FeishuClient, FeishuError


CHANGE_TYPE_LABELS = {
    "deadline": "截止时间",
    "amount": "金额预算",
    "qualification": "资格条件",
    "technical": "技术参数",
    "scoring": "评分办法",
    "attachment": "附件文件",
    "text": "一般文本",
}

IMPACT_STATUS_LABELS = {
    "unaffected": "不受影响",
    "suggested_review": "建议复核",
    "mandatory_review": "必须复核",
    "confirmed": "已确认",
}

MANDATORY_CHANGE_TYPES = {"deadline", "amount", "qualification", "technical", "scoring"}


def ensure_change_impact_round(
    conn: sqlite3.Connection,
    *,
    revision_id: str,
    notice_id: str,
    changed_fields: list[str] | tuple[str, ...],
    before: dict[str, Any],
    after: dict[str, Any],
    source_url: str,
    created_at: str = "",
) -> str:
    existing = conn.execute(
        "SELECT id FROM change_impact_rounds WHERE revision_id = ?", (revision_id,)
    ).fetchone()
    if existing is None:
        round_number = int(
            conn.execute(
                "SELECT COUNT(*) FROM change_impact_rounds WHERE notice_id = ?", (notice_id,)
            ).fetchone()[0]
        ) + 1
        events = _normalized_events(
            revision_id=revision_id,
            notice_id=notice_id,
            changed_fields=changed_fields,
            before=before,
            after=after,
            source_url=source_url,
            discovered_at=created_at,
        )
        severity = _round_severity(events)
        round_id = _stable_id("impact-round", revision_id)
        conn.execute(
            """
            INSERT INTO change_impact_rounds(
                id, revision_id, notice_id, round_number, severity, summary
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                round_id,
                revision_id,
                notice_id,
                round_number,
                severity,
                _round_summary(events),
            ),
        )
        for event in events:
            conn.execute(
                """
                INSERT OR IGNORE INTO change_impact_events(
                    id, round_id, revision_id, notice_id, field_name, change_type,
                    old_value_json, new_value_json, source_url, source_locator,
                    detection_method, confidence, discovered_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["id"], round_id, revision_id, notice_id, event["field_name"],
                    event["change_type"], json_dumps(event["old_value"]),
                    json_dumps(event["new_value"]), source_url, event["source_locator"],
                    event["detection_method"], event["confidence"],
                    created_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )
        conn.execute(
            """
            INSERT INTO change_impact_audit_events(
                id, round_id, notice_id, event_type, actor, note, payload_json
            ) VALUES (?, ?, ?, 'round_generated', 'system:change_impact', ?, ?)
            """,
            (
                str(uuid4()), round_id, notice_id, "变更冲击波分析已生成",
                json_dumps({"revision_id": revision_id, "event_count": len(events)}),
            ),
        )
    else:
        round_id = str(existing["id"])
    _reconcile_impacts(conn, round_id=round_id, notice_id=notice_id, revision_id=revision_id)
    return round_id


def get_change_impact(
    settings: Settings,
    notice_id: str,
    *,
    revision_id: str = "",
    affected_only: bool = False,
) -> dict[str, object] | None:
    init_db(settings)
    with connection(settings) as conn:
        revisions = conn.execute(
            """
            SELECT r.*, n.source_url
            FROM notice_revisions r JOIN notices n ON n.id = r.notice_id
            WHERE r.notice_id = ?
              AND (? = '' OR r.id = ?)
            ORDER BY r.created_at DESC, r.rowid DESC
            """,
            (notice_id, revision_id, revision_id),
        ).fetchall()
        if not revisions:
            notice = conn.execute("SELECT 1 FROM notices WHERE id = ?", (notice_id,)).fetchone()
            return None if notice is None else _empty_payload(notice_id)
        for revision in revisions:
            ensure_change_impact_round(
                conn,
                revision_id=str(revision["id"]),
                notice_id=notice_id,
                changed_fields=_json_list(revision["changed_fields_json"]),
                before=_json_object(revision["before_json"]),
                after=_json_object(revision["after_json"]),
                source_url=str(revision["source_url"] or ""),
                created_at=str(revision["created_at"] or ""),
            )
        rows = conn.execute(
            """
            SELECT * FROM change_impact_rounds
            WHERE notice_id = ? AND (? = '' OR revision_id = ?)
            ORDER BY round_number DESC
            """,
            (notice_id, revision_id, revision_id),
        ).fetchall()
        rounds = [_round_payload(conn, row, affected_only=affected_only) for row in rows]
    current = rounds[0]
    return {
        "notice_id": notice_id,
        "current_round": current,
        "rounds": rounds,
        "round_count": len(rounds),
        "filters": current["counts"],
        "affected_only": affected_only,
        "graph": _impact_graph(current),
    }


def confirm_change_impact_action(
    settings: Settings,
    notice_id: str,
    action_id: str,
    *,
    actor: str,
    note: str,
) -> dict[str, object]:
    actor = actor.strip()
    note = note.strip()
    if not actor or not note:
        raise ValueError("确认人和确认说明不能为空")
    confirmed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with connection(settings) as conn:
        action = conn.execute(
            "SELECT * FROM change_impact_actions WHERE id = ? AND notice_id = ?",
            (action_id, notice_id),
        ).fetchone()
        if action is None:
            raise LookupError("变更行动不存在")
        conn.execute(
            """
            UPDATE change_impact_actions
            SET status = 'confirmed', confirmed_by = ?, confirmation_note = ?,
                confirmed_at = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (actor, note, confirmed_at, action_id),
        )
        if action["impact_item_id"]:
            conn.execute(
                """
                UPDATE change_impact_items
                SET impact_status = 'confirmed', confirmed_by = ?, confirmation_note = ?,
                    confirmed_at = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (actor, note, confirmed_at, action["impact_item_id"]),
            )
        open_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM change_impact_actions WHERE round_id = ? AND status != 'confirmed'",
                (action["round_id"],),
            ).fetchone()[0]
        )
        if open_count == 0:
            conn.execute(
                """
                UPDATE change_impact_rounds
                SET status = 'confirmed', confirmed_by = ?, confirmation_note = ?, confirmed_at = ?
                WHERE id = ?
                """,
                (actor, note, confirmed_at, action["round_id"]),
            )
        conn.execute(
            """
            INSERT INTO change_impact_audit_events(
                id, round_id, action_id, notice_id, event_type, actor, note, payload_json
            ) VALUES (?, ?, ?, ?, 'action_confirmed', ?, ?, ?)
            """,
            (
                str(uuid4()), action["round_id"], action_id, notice_id, actor, note,
                json_dumps({"action_key": action["action_key"], "open_count": open_count}),
            ),
        )
    payload = get_change_impact(settings, notice_id, revision_id=str(action["revision_id"]))
    assert payload is not None
    return payload


def dispatch_change_impact(
    settings: Settings,
    notice_id: str,
    round_id: str,
    *,
    actor: str,
    client: FeishuClient | None = None,
) -> dict[str, object]:
    actor = actor.strip()
    if not actor:
        raise ValueError("发送人不能为空")
    with connection(settings) as conn:
        round_row = conn.execute(
            "SELECT * FROM change_impact_rounds WHERE id = ? AND notice_id = ?",
            (round_id, notice_id),
        ).fetchone()
        if round_row is None:
            raise LookupError("复核轮次不存在")
        actions = conn.execute(
            """
            SELECT * FROM change_impact_actions
            WHERE round_id = ? AND status = 'confirmed'
            ORDER BY priority DESC, created_at
            """,
            (round_id,),
        ).fetchall()
        if not actions:
            raise ValueError("至少确认一项行动后才能同步飞书")
        event_rows = conn.execute(
            "SELECT * FROM change_impact_events WHERE round_id = ? ORDER BY discovered_at, rowid",
            (round_id,),
        ).fetchall()
        workflow = conn.execute(
            "SELECT * FROM opportunity_workflows WHERE notice_id = ?", (notice_id,)
        ).fetchone()
        notice = conn.execute("SELECT * FROM notices WHERE id = ?", (notice_id,)).fetchone()
    receiver_id, receiver_type = resolve_feishu_receiver(settings)
    if workflow is not None and str(workflow["owner_open_id"] or ""):
        receiver_id = str(workflow["owner_open_id"])
        receiver_type = "open_id"
    if not receiver_id:
        raise ValueError("未配置飞书接收目标")
    feishu = client or FeishuClient(settings)
    card = _build_change_card(round_row, event_rows, actions, notice)
    message_response: dict[str, Any] | None = None
    results = {"sent": 0, "skipped": 0, "failed": 0, "failures": []}
    pending_message = [row for row in actions if str(row["message_status"]) != "sent"]
    if pending_message:
        try:
            message_response = feishu.send_card(
                card, receive_id=receiver_id, receive_id_type=receiver_type or "chat_id"
            )
            message_id = _nested_string(message_response, "data", "message_id")
            _mark_channel(settings, [str(row["id"]) for row in pending_message], "message", "sent", message_id)
            results["sent"] += len(pending_message)
        except (FeishuError, ValueError) as exc:
            _mark_channel(settings, [str(row["id"]) for row in pending_message], "message", "failed", error=str(exc))
            results["failed"] += len(pending_message)
            results["failures"].append({"channel": "message", "error": str(exc)})
    else:
        results["skipped"] += len(actions)
    for action in actions:
        action_id = str(action["id"])
        if str(action["task_status"]) != "sent":
            try:
                task = feishu.create_task(
                    summary=f"变更复核：{action['title']}",
                    description=f"来源修订：{round_row['revision_id']}\n{round_row['summary']}",
                    client_token=str(action["idempotency_key"])[:100],
                    due_timestamp_ms=_due_ms(str(action["due_at"] or "")),
                    assignee_open_id=str(action["owner_id"] or ""),
                )
                _mark_channel(settings, [action_id], "task", "sent", _nested_string(task, "data", "task", "guid"))
                results["sent"] += 1
            except (FeishuError, ValueError) as exc:
                _mark_channel(settings, [action_id], "task", "failed", error=str(exc))
                results["failed"] += 1
                results["failures"].append({"channel": "task", "action_id": action_id, "error": str(exc)})
        else:
            results["skipped"] += 1
        if str(action["action_type"]) != "update_calendar":
            _mark_channel(settings, [action_id], "calendar", "not_applicable")
        elif str(action["calendar_status"]) != "sent" and settings.feishu_calendar_id:
            try:
                start, end = _calendar_window(event_rows, str(action["due_at"] or ""))
                event = feishu.create_calendar_event(
                    calendar_id=settings.feishu_calendar_id,
                    summary=f"更正后投标截止：{str(notice['title'] if notice else notice_id)}",
                    description=str(round_row["summary"]),
                    start_timestamp=start,
                    end_timestamp=end,
                    idempotency_key=f"ci-{str(action['idempotency_key'])[:60]}",
                )
                _mark_channel(settings, [action_id], "calendar", "sent", _nested_string(event, "data", "event", "event_id"))
                results["sent"] += 1
            except (FeishuError, ValueError) as exc:
                _mark_channel(settings, [action_id], "calendar", "failed", error=str(exc))
                results["failed"] += 1
                results["failures"].append({"channel": "calendar", "action_id": action_id, "error": str(exc)})
        elif str(action["calendar_status"]) == "sent":
            results["skipped"] += 1
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO change_impact_audit_events(
                id, round_id, notice_id, event_type, actor, note, payload_json
            ) VALUES (?, ?, ?, 'feishu_dispatch', ?, ?, ?)
            """,
            (str(uuid4()), round_id, notice_id, actor, "同步公告冲击波", json_dumps(results)),
        )
    payload = get_change_impact(settings, notice_id, revision_id=str(round_row["revision_id"]))
    return {"status": "partial" if results["failed"] else "sent", **results, "impact": payload}


def _reconcile_impacts(conn: sqlite3.Connection, *, round_id: str, notice_id: str, revision_id: str) -> None:
    events = conn.execute("SELECT * FROM change_impact_events WHERE round_id = ?", (round_id,)).fetchall()
    requirements = conn.execute(
        """
        SELECT requirement.*, member.member_open_id, member.member_name
        FROM opportunity_requirements requirement
        LEFT JOIN opportunity_team_members member ON member.id = requirement.assignee_member_id
        WHERE requirement.notice_id = ?
        """,
        (notice_id,),
    ).fetchall()
    workflow = conn.execute(
        "SELECT * FROM opportunity_workflows WHERE notice_id = ?", (notice_id,)
    ).fetchone()
    now = datetime.now(timezone.utc)
    due_at = (now + timedelta(hours=24)).isoformat(timespec="minutes")
    for event in events:
        change_type = str(event["change_type"])
        affected_types = _affected_requirement_types(change_type)
        for requirement in requirements:
            affected = str(requirement["requirement_type"]) in affected_types or change_type == "attachment"
            status = (
                "mandatory_review" if affected and change_type in MANDATORY_CHANGE_TYPES
                else "suggested_review" if affected
                else "unaffected"
            )
            item_id = _stable_id("impact-item", round_id, event["id"], "requirement", requirement["id"])
            _insert_impact_item(
                conn, item_id=item_id, round_id=round_id, event_id=str(event["id"]),
                revision_id=revision_id, notice_id=notice_id, target_type="requirement",
                target_id=str(requirement["id"]), target_title=str(requirement["title"]),
                impact_status=status, previous_status=str(requirement["status"]),
                reason=_impact_reason(change_type, affected),
                owner_id=str(requirement["member_open_id"] or ""),
                owner_name=str(requirement["member_name"] or ""),
                due_at=str(requirement["due_at"] or due_at),
            )
            if affected:
                _insert_action(
                    conn, round_id=round_id, item_id=item_id, revision_id=revision_id,
                    notice_id=notice_id, action_key=f"review:{requirement['id']}",
                    action_type="review_requirement", title=f"重新确认：{requirement['title']}",
                    priority="critical" if status == "mandatory_review" else "high",
                    owner_id=str(requirement["member_open_id"] or ""),
                    owner_name=str(requirement["member_name"] or ""), due_at=str(requirement["due_at"] or due_at),
                )
                matches = conn.execute(
                    "SELECT * FROM requirement_capability_matches WHERE requirement_id = ?",
                    (requirement["id"],),
                ).fetchall()
                for match in matches:
                    match_item = _stable_id("impact-item", round_id, event["id"], "capability_match", match["id"])
                    _insert_impact_item(
                        conn, item_id=match_item, round_id=round_id, event_id=str(event["id"]),
                        revision_id=revision_id, notice_id=notice_id, target_type="capability_match",
                        target_id=str(match["id"]), target_title=f"能力匹配：{requirement['title']}",
                        impact_status=status, previous_status=str(match["status"]),
                        reason="上游要求发生变化，原能力匹配结论需要复核。",
                        owner_id=str(requirement["member_open_id"] or ""),
                        owner_name=str(requirement["member_name"] or ""), due_at=due_at,
                    )
                    _insert_action(
                        conn, round_id=round_id, item_id=match_item, revision_id=revision_id,
                        notice_id=notice_id, action_key=f"match:{match['id']}",
                        action_type="review_capability", title=f"重算能力匹配：{requirement['title']}",
                        priority="high", owner_id=str(requirement["member_open_id"] or ""),
                        owner_name=str(requirement["member_name"] or ""), due_at=due_at,
                    )
        if change_type in MANDATORY_CHANGE_TYPES:
            owner_id = str(workflow["owner_open_id"] or "") if workflow else ""
            owner_name = str(workflow["owner_name"] or "") if workflow else ""
            for target_type, title, action_type in _workflow_targets(change_type):
                item_id = _stable_id("impact-item", round_id, event["id"], target_type, notice_id)
                _insert_impact_item(
                    conn, item_id=item_id, round_id=round_id, event_id=str(event["id"]),
                    revision_id=revision_id, notice_id=notice_id, target_type=target_type,
                    target_id=notice_id, target_title=title, impact_status="mandatory_review",
                    previous_status=_workflow_previous_status(workflow, target_type),
                    reason=_workflow_reason(change_type, target_type), owner_id=owner_id,
                    owner_name=owner_name, due_at=due_at,
                )
                _insert_action(
                    conn, round_id=round_id, item_id=item_id, revision_id=revision_id,
                    notice_id=notice_id, action_key=f"{action_type}:{notice_id}",
                    action_type=action_type, title=title, priority="critical",
                    owner_id=owner_id, owner_name=owner_name, due_at=due_at,
                )


def _insert_impact_item(conn: sqlite3.Connection, **value: str) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO change_impact_items(
            id, round_id, event_id, revision_id, notice_id, target_type, target_id,
            target_title, impact_status, previous_status, reason, owner_id, owner_name, due_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        tuple(value[key] for key in (
            "item_id", "round_id", "event_id", "revision_id", "notice_id", "target_type",
            "target_id", "target_title", "impact_status", "previous_status", "reason",
            "owner_id", "owner_name", "due_at",
        )),
    )


def _insert_action(conn: sqlite3.Connection, **value: str) -> None:
    idempotency_key = _stable_id("change-impact-action", value["revision_id"], value["action_key"])
    conn.execute(
        """
        INSERT OR IGNORE INTO change_impact_actions(
            id, round_id, impact_item_id, revision_id, notice_id, action_key,
            action_type, title, priority, owner_id, owner_name, due_at, idempotency_key
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _stable_id("action", value["round_id"], value["action_key"]), value["round_id"],
            value["item_id"], value["revision_id"], value["notice_id"], value["action_key"],
            value["action_type"], value["title"], value["priority"], value["owner_id"],
            value["owner_name"], value["due_at"], idempotency_key,
        ),
    )


def _normalized_events(**value: Any) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for field in value["changed_fields"]:
        old_value = value["before"].get(field)
        new_value = value["after"].get(field)
        change_types = _change_types(str(field), old_value, new_value)
        for change_type in change_types:
            events.append({
                "id": _stable_id("change-event", value["revision_id"], field, change_type),
                "field_name": str(field), "change_type": change_type,
                "old_value": old_value, "new_value": new_value,
                "source_locator": _source_locator(str(field), change_type),
                "detection_method": "rule" if str(field) not in {"content_text", "core_content"} else "rule_candidate",
                "confidence": 100 if str(field) not in {"content_text", "core_content"} else 88,
            })
    return events


def _change_types(field: str, before: object, after: object) -> list[str]:
    direct = {
        "bid_deadline": "deadline", "budget": "amount",
        "attachments": "attachment", "attachment_fingerprints": "attachment",
    }
    if field in direct:
        return [direct[field]]
    text = f"{_display(before)} {_display(after)}"
    matches: list[str] = []
    for change_type, keywords in (
        ("qualification", ("资格", "资质", "证书", "信用中国", "供应商条件")),
        ("technical", ("技术", "参数", "规格", "端口", "HDMI", "CPU", "尺寸", "型号")),
        ("scoring", ("评分", "得分", "分值", "评审", "加分")),
    ):
        if any(keyword.casefold() in text.casefold() for keyword in keywords):
            matches.append(change_type)
    return matches or ["text"]


def _affected_requirement_types(change_type: str) -> set[str]:
    return {
        "deadline": {"deadline"}, "amount": {"scoring", "commercial"},
        "qualification": {"qualification", "disqualification"},
        "technical": {"technical"}, "scoring": {"scoring"},
        "attachment": {"qualification", "deadline", "scoring", "disqualification", "attachment", "technical", "commercial"},
        "text": set(),
    }[change_type]


def _workflow_targets(change_type: str) -> list[tuple[str, str, str]]:
    targets = [
        ("readiness", "重新计算投标准备度", "recalculate_readiness"),
        ("decision", "重新确认 Go / Hold / No-Go 决策", "reconfirm_decision"),
    ]
    if change_type == "deadline":
        targets[0:0] = [
            ("workflow_task", "调整依赖任务与截止时间", "update_task"),
            ("calendar", "更新投标日历与提醒", "update_calendar"),
        ]
    return targets


def _round_payload(conn: sqlite3.Connection, row: sqlite3.Row, *, affected_only: bool) -> dict[str, object]:
    events = [_event_payload(item) for item in conn.execute(
        "SELECT * FROM change_impact_events WHERE round_id = ? ORDER BY discovered_at, rowid", (row["id"],)
    ).fetchall()]
    sql = """
        SELECT item.*, event.change_type, event.field_name
        FROM change_impact_items item JOIN change_impact_events event ON event.id = item.event_id
        WHERE item.round_id = ?
    """
    if affected_only:
        sql += " AND item.impact_status != 'unaffected'"
    sql += " ORDER BY CASE item.impact_status WHEN 'mandatory_review' THEN 1 WHEN 'suggested_review' THEN 2 WHEN 'confirmed' THEN 3 ELSE 4 END, item.created_at"
    items = [_item_payload(item) for item in conn.execute(sql, (row["id"],)).fetchall()]
    actions = [_action_payload(item) for item in conn.execute(
        "SELECT * FROM change_impact_actions WHERE round_id = ? ORDER BY CASE priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2 ELSE 3 END, created_at", (row["id"],)
    ).fetchall()]
    audit = [dict(item) for item in conn.execute(
        "SELECT * FROM change_impact_audit_events WHERE round_id = ? ORDER BY created_at DESC, rowid DESC", (row["id"],)
    ).fetchall()]
    target_statuses: dict[tuple[str, str], str] = {}
    status_rank = {"unaffected": 0, "suggested_review": 1, "mandatory_review": 2, "confirmed": 3}
    for item in items:
        key = (str(item["target_type"]), str(item["target_id"]))
        current = target_statuses.get(key, "unaffected")
        if status_rank.get(str(item["impact_status"]), 0) > status_rank.get(current, 0):
            target_statuses[key] = str(item["impact_status"])
        elif key not in target_statuses:
            target_statuses[key] = str(item["impact_status"])
    counts = {key: sum(status == key for status in target_statuses.values()) for key in IMPACT_STATUS_LABELS}
    counts["affected"] = counts["mandatory_review"] + counts["suggested_review"] + counts["confirmed"]
    counts["all"] = len(target_statuses)
    counts["relations"] = len(items)
    return {
        **dict(row), "events": events, "items": items, "actions": actions,
        "audit": audit, "counts": counts,
        "change_types": list(dict.fromkeys(event["change_type"] for event in events)),
    }


def _event_payload(row: sqlite3.Row) -> dict[str, object]:
    value = dict(row)
    value["change_type_label"] = CHANGE_TYPE_LABELS.get(str(row["change_type"]), str(row["change_type"]))
    value["old_value"] = _json_value(row["old_value_json"])
    value["new_value"] = _json_value(row["new_value_json"])
    return value


def _item_payload(row: sqlite3.Row) -> dict[str, object]:
    value = dict(row)
    value["impact_status_label"] = IMPACT_STATUS_LABELS.get(str(row["impact_status"]), str(row["impact_status"]))
    value["change_type_label"] = CHANGE_TYPE_LABELS.get(str(row["change_type"]), str(row["change_type"]))
    return value


def _action_payload(row: sqlite3.Row) -> dict[str, object]:
    value = dict(row)
    value["delivery_status"] = {
        "message": row["message_status"], "task": row["task_status"], "calendar": row["calendar_status"],
    }
    return value


def _impact_graph(round_payload: dict[str, object]) -> dict[str, object]:
    events = round_payload["events"]
    items = round_payload["items"]
    actions = round_payload["actions"]
    nodes: list[dict[str, object]] = []
    edges: list[dict[str, str]] = []
    for event in events:
        nodes.append({"id": event["id"], "layer": "change", "label": event["change_type_label"], "status": "changed"})
    for item in items:
        nodes.append({"id": item["id"], "layer": item["target_type"], "label": item["target_title"], "status": item["impact_status"]})
        edges.append({"from": item["event_id"], "to": item["id"]})
    for action in actions:
        nodes.append({"id": action["id"], "layer": "action", "label": action["title"], "status": action["status"]})
        if action["impact_item_id"]:
            edges.append({"from": action["impact_item_id"], "to": action["id"]})
    return {"nodes": nodes, "edges": edges, "layer_order": ["change", "requirement", "capability_match", "readiness", "workflow_task", "calendar", "decision", "action"]}


def _build_change_card(round_row: sqlite3.Row, events: list[sqlite3.Row], actions: list[sqlite3.Row], notice: sqlite3.Row | None) -> dict[str, Any]:
    event_lines = "\n".join(
        f"- **{CHANGE_TYPE_LABELS.get(str(event['change_type']), event['change_type'])}**：{_display(_json_value(event['old_value_json']))} → {_display(_json_value(event['new_value_json']))}"
        for event in events[:6]
    )
    action_lines = "\n".join(f"- {action['title']} · {action['owner_name'] or '待认领'}" for action in actions[:8])
    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": "orange", "title": {"tag": "plain_text", "content": "公告冲击波 · 待执行行动"}},
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**{str(notice['title'] if notice else '投标机会')}**\n第 {round_row['round_number']} 轮复核 · {round_row['summary']}"}},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**变更前后**\n{event_lines}"}},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**已确认行动**\n{action_lines}"}},
            {"tag": "note", "elements": [{"tag": "plain_text", "content": f"修订号：{round_row['revision_id']} · 已保留幂等键与回执，可失败重试"}]},
        ],
    }


def _mark_channel(settings: Settings, action_ids: list[str], channel: str, status: str, external_id: str = "", error: str = "") -> None:
    if not action_ids:
        return
    status_column = {"message": "message_status", "task": "task_status", "calendar": "calendar_status"}[channel]
    id_column = {"message": "message_id", "task": "task_guid", "calendar": "calendar_event_id"}[channel]
    placeholders = ",".join("?" for _ in action_ids)
    with connection(settings) as conn:
        conn.execute(
            f"""
            UPDATE change_impact_actions
            SET {status_column} = ?, {id_column} = CASE WHEN ? != '' THEN ? ELSE {id_column} END,
                retry_count = retry_count + CASE WHEN ? = 'failed' THEN 1 ELSE 0 END,
                last_error = ?, last_attempt_at = ?, updated_at = datetime('now')
            WHERE id IN ({placeholders})
            """,
            (status, external_id, external_id, status, error, datetime.now(timezone.utc).isoformat(timespec="seconds"), *action_ids),
        )


def _calendar_window(events: list[sqlite3.Row], due_at: str) -> tuple[str, str]:
    deadline = ""
    for event in events:
        if str(event["change_type"]) == "deadline":
            deadline = str(_json_value(event["new_value_json"]) or "")
            break
    parsed = _parse_datetime(deadline) or _parse_datetime(due_at) or (datetime.now(timezone.utc) + timedelta(days=1))
    return str(int((parsed - timedelta(minutes=30)).timestamp())), str(int(parsed.timestamp()))


def _due_ms(value: str) -> str:
    parsed = _parse_datetime(value)
    return str(int(parsed.timestamp() * 1000)) if parsed else ""


def _parse_datetime(value: str) -> datetime | None:
    text = value.strip().replace("年", "-").replace("月", "-").replace("日", " ").replace("时", ":").replace("分", "")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _impact_reason(change_type: str, affected: bool) -> str:
    if not affected:
        return f"{CHANGE_TYPE_LABELS[change_type]}未命中该要求，保留原状态。"
    return {
        "deadline": "截止时间发生变化，需重新核对时限与依赖安排。",
        "amount": "金额发生变化，需重新核对报价、评分与投入判断。",
        "qualification": "资格条件发生变化，需重新核对资质与废标风险。",
        "technical": "技术参数发生变化，需重新核对产品证据与响应结论。",
        "scoring": "评分办法发生变化，需重新核对得分证据与策略。",
        "attachment": "附件发生变化，需回看原文与附件证据。",
        "text": "正文候选变化仅建议复核，人工确认前不改写业务状态。",
    }[change_type]


def _workflow_reason(change_type: str, target_type: str) -> str:
    return f"{CHANGE_TYPE_LABELS[change_type]}变化沿影响链传导至{target_type}，需要负责人确认。"


def _workflow_previous_status(workflow: sqlite3.Row | None, target_type: str) -> str:
    if workflow is None:
        return "not_created" if target_type in {"workflow_task", "calendar"} else "pending"
    return {
        "workflow_task": str(workflow["feishu_task_status"] or "not_created"),
        "calendar": "created" if workflow["feishu_event_id"] else "not_created",
        "decision": str(workflow["decision"] or "pending"),
        "readiness": str(workflow["qualification_status"] or "pending"),
    }.get(target_type, "pending")


def _round_severity(events: list[dict[str, Any]]) -> str:
    types = {event["change_type"] for event in events}
    if types & {"deadline", "qualification", "technical", "scoring"}:
        return "critical"
    if types & {"amount", "attachment"}:
        return "high"
    return "normal"


def _round_summary(events: list[dict[str, Any]]) -> str:
    labels = list(dict.fromkeys(CHANGE_TYPE_LABELS[event["change_type"]] for event in events))
    return f"识别 {len(events)} 个字段级变更，涉及{'、'.join(labels)}；已生成受影响对象和负责人行动清单。"


def _source_locator(field: str, change_type: str) -> str:
    if field == "bid_deadline":
        return "更正公告/提交投标文件截止时间与开标时间"
    if field in {"content_text", "core_content"} and change_type == "technical":
        return "更正公告/采购需求/技术参数"
    if field in {"attachments", "attachment_fingerprints"}:
        return "更正公告/附件列表"
    return f"更正公告/{field}"


def _stable_id(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:32]


def _json_value(raw: object) -> object:
    try:
        return json.loads(str(raw))
    except (TypeError, ValueError):
        return raw


def _json_object(raw: object) -> dict[str, Any]:
    value = _json_value(raw)
    return value if isinstance(value, dict) else {}


def _json_list(raw: object) -> list[str]:
    value = _json_value(raw)
    return [str(item) for item in value] if isinstance(value, list) else []


def _display(value: object) -> str:
    if isinstance(value, dict):
        value = value.get("excerpt") or value.get("sha256") or "内容已更新"
    if isinstance(value, list):
        return f"{len(value)} 项"
    text = str(value or "未提供").replace("\n", " ").strip()
    return text if len(text) <= 90 else f"{text[:87]}..."


def _nested_string(payload: object, *keys: str) -> str:
    value = payload
    for key in keys:
        if not isinstance(value, dict):
            return ""
        value = value.get(key)
    return str(value or "")


def _empty_payload(notice_id: str) -> dict[str, object]:
    return {
        "notice_id": notice_id, "current_round": None, "rounds": [], "round_count": 0,
        "filters": {"all": 0, "affected": 0, **{key: 0 for key in IMPACT_STATUS_LABELS}},
        "affected_only": False, "graph": {"nodes": [], "edges": [], "layer_order": []},
    }
