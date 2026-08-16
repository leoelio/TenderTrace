from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from typing import Any

from tendertrace.config import Settings
from tendertrace.db import connection
from tendertrace.delivery.ledger import record_delivery_attempt
from tendertrace.delivery.preferences import resolve_feishu_receiver
from tendertrace.integrations.feishu import FeishuClient, FeishuError
from tendertrace.notice_changes import NoticeRevision, list_notice_revisions
from tendertrace.workflow import OpportunityWorkflow, workflow_snapshots


FIELD_LABELS = {
    "attachment_fingerprints": "附件内容",
    "attachments": "附件列表",
    "bid_deadline": "投标截止",
    "budget": "预算",
    "content_text": "公告正文",
    "core_content": "核心内容",
    "project_no": "项目编号",
    "publish_time": "发布时间",
    "purchaser": "采购主体",
    "region": "地区",
    "source_url": "来源链接",
    "title": "标题",
}


@dataclass(frozen=True)
class NoticeChangeDeliveryResult:
    status: str
    revision_count: int
    receiver_count: int
    message_count: int
    sent_count: int
    skipped_count: int
    failed_count: int
    failures: tuple[dict[str, str], ...]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["failures"] = list(self.failures)
        return value


def send_opportunity_change_alerts(
    settings: Settings,
    *,
    client: FeishuClient | None = None,
    limit: int = 100,
) -> NoticeChangeDeliveryResult:
    target_count = min(max(limit, 1), 500)
    default_receiver = resolve_feishu_receiver(settings)
    groups: dict[tuple[str, str], list[tuple[NoticeRevision, OpportunityWorkflow]]] = {}
    skipped_count = 0
    scanned_count = 0
    pending_count = 0
    offset = 0
    while pending_count < target_count:
        revisions = list_notice_revisions(settings, limit=200, offset=offset)
        if not revisions:
            break
        scanned_count += len(revisions)
        offset += len(revisions)
        workflows = workflow_snapshots(settings, [item.notice_id for item in revisions])
        candidates: list[
            tuple[NoticeRevision, OpportunityWorkflow, str, str, str]
        ] = []
        for revision in revisions:
            workflow = workflows[revision.notice_id]
            if workflow.stage in {"won", "lost", "archived"}:
                skipped_count += 1
                continue
            receive_id = workflow.owner_open_id or default_receiver[0] or ""
            receive_type = (
                "open_id" if workflow.owner_open_id else default_receiver[1] or "chat_id"
            )
            if not receive_id:
                skipped_count += 1
                continue
            artifact_key = _artifact_key(revision.id, receive_id, receive_type)
            candidates.append(
                (revision, workflow, receive_id, receive_type, artifact_key)
            )
        sent_keys = _sent_artifact_keys(
            settings,
            [candidate[4] for candidate in candidates],
        )
        for revision, workflow, receive_id, receive_type, artifact_key in candidates:
            if artifact_key in sent_keys:
                skipped_count += 1
                continue
            groups.setdefault((receive_id, receive_type), []).append((revision, workflow))
            pending_count += 1
            if pending_count >= target_count:
                break
        if len(revisions) < 200:
            break
    if not groups:
        return NoticeChangeDeliveryResult(
            status="skipped",
            revision_count=scanned_count,
            receiver_count=0,
            message_count=0,
            sent_count=0,
            skipped_count=skipped_count,
            failed_count=0,
            failures=(),
        )

    feishu = client or FeishuClient(settings)
    sent_count = 0
    message_count = 0
    failed_count = 0
    failures: list[dict[str, str]] = []
    for (receive_id, receive_type), items in groups.items():
        for chunk in _chunks(items, 10):
            card = build_notice_change_card(chunk)
            try:
                response = feishu.send_card(
                    card,
                    receive_id=receive_id,
                    receive_id_type=receive_type,
                )
                message_id = _nested_string(response, "data", "message_id")
                message_count += 1
                for revision, _workflow in chunk:
                    record_delivery_attempt(
                        settings,
                        channel="feishu",
                        artifact_type="opportunity_notice_change",
                        artifact_key=_artifact_key(revision.id, receive_id, receive_type),
                        status="sent",
                        external_id=message_id or None,
                    )
                    sent_count += 1
            except (FeishuError, ValueError) as exc:
                for revision, _workflow in chunk:
                    record_delivery_attempt(
                        settings,
                        channel="feishu",
                        artifact_type="opportunity_notice_change",
                        artifact_key=_artifact_key(revision.id, receive_id, receive_type),
                        status="failed",
                        error=str(exc),
                    )
                    failed_count += 1
                failures.append(
                    {
                        "receiver_type": receive_type,
                        "revision_count": str(len(chunk)),
                        "error": str(exc),
                    }
                )
    status = "partial" if sent_count and failures else "failed" if failures else "sent"
    return NoticeChangeDeliveryResult(
        status=status,
        revision_count=scanned_count,
        receiver_count=len(groups),
        message_count=message_count,
        sent_count=sent_count,
        skipped_count=skipped_count,
        failed_count=failed_count,
        failures=tuple(failures),
    )


def build_notice_change_card(
    items: list[tuple[NoticeRevision, OpportunityWorkflow]],
) -> dict[str, Any]:
    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"检测到 **{len(items)}** 条机会公告发生变化，请复核投标边界与计划。",
            },
        }
    ]
    for revision, workflow in items:
        labels = "、".join(
            FIELD_LABELS.get(field, field) for field in revision.changed_fields[:5]
        )
        details = "\n".join(_change_lines(revision)[:3])
        elements.extend(
            (
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**{revision.title or '未命名机会'}**\n"
                            f"**阶段** {workflow.stage_label}   **负责人** "
                            f"{workflow.owner_name or '待认领'}\n"
                            f"**变更** {labels or '公告内容'}   **检测时间** {revision.created_at}\n"
                            f"{details}"
                        ),
                    },
                },
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "lark_md",
                            "content": f"[查看最新公告]({revision.source_url})",
                        }
                    ],
                },
            )
        )
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "orange",
            "title": {"tag": "plain_text", "content": "机会公告变更提醒"},
        },
        "elements": elements,
    }


def _change_lines(revision: NoticeRevision) -> list[str]:
    lines: list[str] = []
    for field in revision.changed_fields:
        label = FIELD_LABELS.get(field, field)
        if field in {"content_text", "core_content", "attachment_fingerprints"}:
            lines.append(f"- {label}已更新")
            continue
        before = _display(revision.before.get(field))
        after = _display(revision.after.get(field))
        lines.append(f"- {label}：{before or '未提供'} → {after or '未提供'}")
    return lines


def _display(value: object) -> str:
    if isinstance(value, list):
        return f"{len(value)} 项"
    if isinstance(value, dict):
        return str(value.get("excerpt") or "内容已更新")[:80]
    text = str(value or "").strip()
    return f"{text[:77]}..." if len(text) > 80 else text


def _chunks(
    items: list[tuple[NoticeRevision, OpportunityWorkflow]],
    size: int,
) -> list[list[tuple[NoticeRevision, OpportunityWorkflow]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _artifact_key(revision_id: str, receive_id: str, receive_type: str) -> str:
    digest = hashlib.sha256(
        f"{revision_id}|{receive_type}|{receive_id}".encode("utf-8")
    ).hexdigest()[:24]
    return f"opportunity_notice_change:{digest}"


def _sent_artifact_keys(settings: Settings, artifact_keys: list[str]) -> set[str]:
    if not artifact_keys:
        return set()
    placeholders = ",".join("?" for _ in artifact_keys)
    with connection(settings) as conn:
        rows = conn.execute(
            f"""
            SELECT DISTINCT artifact_key FROM delivery_attempts
            WHERE channel = 'feishu'
              AND artifact_type = 'opportunity_notice_change'
              AND artifact_key IN ({placeholders})
              AND status = 'sent'
            """,
            artifact_keys,
        ).fetchall()
    return {str(row["artifact_key"]) for row in rows}


def _nested_string(payload: object, *keys: str) -> str:
    value = payload
    for key in keys:
        if not isinstance(value, dict):
            return ""
        value = value.get(key)
    return str(value or "")
