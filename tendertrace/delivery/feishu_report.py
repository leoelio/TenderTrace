from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from tendertrace.config import Settings
from tendertrace.delivery.ledger import record_delivery_attempt
from tendertrace.delivery.preferences import resolve_feishu_receiver
from tendertrace.integrations.feishu import FeishuClient, FeishuError


@dataclass(frozen=True)
class FeishuReportDelivery:
    status: str
    file_name: str
    attempt_id: str
    message_id: str | None = None
    error: str | None = None
    digest_status: str = "skipped"
    digest_message_id: str | None = None
    digest_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def deliver_report_to_feishu(
    settings: Settings,
    *,
    docx_path: Path | str,
    run_id: str | None = None,
    subscription_id: str | None = None,
    receive_id: str | None = None,
    receive_id_type: str | None = None,
    report_summary: dict[str, object] | None = None,
    client: FeishuClient | None = None,
) -> FeishuReportDelivery:
    path = Path(docx_path)
    receive_id, receive_id_type = resolve_feishu_receiver(
        settings,
        receive_id=receive_id,
        receive_id_type=receive_id_type,
    )
    try:
        feishu = client or FeishuClient(settings)
        payload = feishu.send_file(
            path,
            receive_id=receive_id,
            receive_id_type=receive_id_type,
        )
        data = payload.get("data")
        message_id = str(data.get("message_id") or "") if isinstance(data, dict) else ""
        attempt = record_delivery_attempt(
            settings,
            channel="feishu",
            artifact_type="report",
            artifact_key=path.name,
            run_id=run_id,
            subscription_id=subscription_id,
            status="sent",
            external_id=message_id or None,
        )
        digest_status, digest_message_id, digest_error = _send_report_digest(
            settings,
            feishu=feishu,
            path=path,
            run_id=run_id,
            subscription_id=subscription_id,
            receive_id=receive_id,
            receive_id_type=receive_id_type,
            report_summary=report_summary,
        )
        return FeishuReportDelivery(
            status="sent",
            file_name=path.name,
            attempt_id=attempt.id,
            message_id=message_id or None,
            digest_status=digest_status,
            digest_message_id=digest_message_id,
            digest_error=digest_error,
        )
    except (FeishuError, OSError) as exc:
        attempt = record_delivery_attempt(
            settings,
            channel="feishu",
            artifact_type="report",
            artifact_key=path.name,
            run_id=run_id,
            subscription_id=subscription_id,
            status="failed",
            error=str(exc),
        )
        return FeishuReportDelivery(
            status="failed",
            file_name=path.name,
            attempt_id=attempt.id,
            error=str(exc),
        )


def build_report_digest_card(
    settings: Settings,
    *,
    file_name: str,
    report_summary: dict[str, object] | None = None,
) -> dict[str, Any]:
    summary = report_summary or {}
    query = _plain(summary.get("query"), default="本次招投标检索")
    notice_count = _positive_int(summary.get("notice_count"))
    evidence_passed = _positive_int(summary.get("evidence_passed"))
    source_sites = _string_list(summary.get("source_sites"), limit=8)
    highlights = _highlights(summary.get("highlights"))
    mode = "增量更新" if summary.get("incremental") else "完整检索"
    source_text = "、".join(source_sites) if source_sites else "以报告来源表为准"
    lines = [
        f"**查询**：{query}",
        f"**结果**：{notice_count} 条 · 证据通过 {evidence_passed} 条 · {mode}",
        f"**来源覆盖**：{source_text}",
        "Word 完整报告已作为同一会话附件发送，可直接打开阅读。",
    ]
    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": "\n".join(lines)},
        }
    ]
    if highlights:
        elements.extend(
            [
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**优先查看**\n" + "\n".join(highlights),
                    },
                },
            ]
        )
    if settings.public_base_url:
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "type": "primary",
                        "text": {"tag": "plain_text", "content": "打开机会台账"},
                        "url": f"{settings.public_base_url}/?view=opportunityView",
                    }
                ],
            }
        )
    elements.append(
        {
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": f"报告文件：{file_name}。进入机会台账后可发起要求会审并在群内回写协作意见。",
                }
            ],
        }
    )
    return {
        "config": {"wide_screen_mode": True, "update_multi": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "TenderTrace 招投标检索简报"},
        },
        "elements": elements,
    }


def _send_report_digest(
    settings: Settings,
    *,
    feishu: FeishuClient,
    path: Path,
    run_id: str | None,
    subscription_id: str | None,
    receive_id: str,
    receive_id_type: str,
    report_summary: dict[str, object] | None,
) -> tuple[str, str | None, str | None]:
    try:
        response = feishu.send_card(
            build_report_digest_card(
                settings,
                file_name=path.name,
                report_summary=report_summary,
            ),
            receive_id=receive_id,
            receive_id_type=receive_id_type,
        )
        data = response.get("data")
        message_id = str(data.get("message_id") or "") if isinstance(data, dict) else ""
        record_delivery_attempt(
            settings,
            channel="feishu",
            artifact_type="report_digest",
            artifact_key=f"{path.name}:digest",
            run_id=run_id,
            subscription_id=subscription_id,
            status="sent",
            external_id=message_id or None,
        )
        return "sent", message_id or None, None
    except (FeishuError, OSError, AttributeError) as exc:
        record_delivery_attempt(
            settings,
            channel="feishu",
            artifact_type="report_digest",
            artifact_key=f"{path.name}:digest",
            run_id=run_id,
            subscription_id=subscription_id,
            status="failed",
            error=str(exc),
        )
        return "failed", None, str(exc)


def _plain(value: object, *, default: str) -> str:
    text = " ".join(str(value or "").split())
    return text[:240] or default


def _positive_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _string_list(value: object, *, limit: int) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return list(dict.fromkeys(_plain(item, default="") for item in value if _plain(item, default="")))[:limit]


def _highlights(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    lines: list[str] = []
    for item in value[:3]:
        if not isinstance(item, dict):
            continue
        title = _plain(item.get("title"), default="")
        if not title:
            continue
        source = _plain(item.get("source"), default="")
        published = _plain(item.get("published"), default="")
        extra = " · ".join(part for part in (source, published) if part)
        lines.append(f"• {title}{f' · {extra}' if extra else ''}")
    return lines
