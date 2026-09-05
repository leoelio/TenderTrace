from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Callable
from urllib.parse import quote

from tendertrace.config import Settings
from tendertrace.db import connection
from tendertrace.delivery.ledger import record_delivery_attempt
from tendertrace.delivery.preferences import resolve_feishu_receiver
from tendertrace.integrations.feishu import FeishuClient, FeishuError
from tendertrace.opportunity import get_opportunity
from tendertrace.requirement_review_agents import review_agent_suggestions
from tendertrace.requirement_review_board import (
    RequirementReviewCase,
    list_requirement_review_cases,
    requirement_review_summary,
)


@dataclass(frozen=True)
class ReviewBoardDeliveryResult:
    status: str
    notice_id: str
    pending_count: int
    suggestion_count: int
    artifact_key: str
    message_id: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def send_requirement_review_digest(
    settings: Settings,
    notice_id: str,
    *,
    receive_id: str | None = None,
    receive_id_type: str | None = None,
    force: bool = False,
    client: FeishuClient | None = None,
    opportunity_loader: Callable[[Settings, str], dict[str, object] | None] = get_opportunity,
    case_loader: Callable[[Settings, str], list[RequirementReviewCase]] = list_requirement_review_cases,
    summary_loader: Callable[[Settings, str], dict[str, object]] = requirement_review_summary,
    suggestion_loader: Callable[[Settings, str], list[dict[str, object]]] = review_agent_suggestions,
) -> ReviewBoardDeliveryResult:
    opportunity = opportunity_loader(settings, notice_id)
    if opportunity is None:
        raise LookupError("opportunity not found")
    cases = case_loader(settings, notice_id)
    summary = summary_loader(settings, notice_id)
    suggestions = suggestion_loader(settings, notice_id)
    if not cases:
        return ReviewBoardDeliveryResult(
            status="skipped",
            notice_id=notice_id,
            pending_count=0,
            suggestion_count=0,
            artifact_key="",
            reason="review board has no cases",
        )
    target_id, target_type = resolve_feishu_receiver(
        settings,
        receive_id=receive_id,
        receive_id_type=receive_id_type,
    )
    artifact_key = _artifact_key(notice_id, cases, suggestions, target_id, target_type)
    pending_count = int(summary.get("pending_count") or 0)
    if not force and _already_sent(settings, artifact_key):
        return ReviewBoardDeliveryResult(
            status="skipped",
            notice_id=notice_id,
            pending_count=pending_count,
            suggestion_count=len(suggestions),
            artifact_key=artifact_key,
            reason="same review board state already sent",
        )
    feishu = client or FeishuClient(settings)
    try:
        response = feishu.send_card(
            build_requirement_review_card(settings, opportunity, cases, summary, suggestions),
            receive_id=target_id,
            receive_id_type=target_type,
        )
        message_id = _nested_string(response, "data", "message_id")
        record_delivery_attempt(
            settings,
            channel="feishu",
            artifact_type="requirement_review_board",
            artifact_key=artifact_key,
            status="sent",
            external_id=message_id or None,
        )
    except (FeishuError, ValueError) as exc:
        record_delivery_attempt(
            settings,
            channel="feishu",
            artifact_type="requirement_review_board",
            artifact_key=artifact_key,
            status="failed",
            error=str(exc),
        )
        raise
    return ReviewBoardDeliveryResult(
        status="sent",
        notice_id=notice_id,
        pending_count=pending_count,
        suggestion_count=len(suggestions),
        artifact_key=artifact_key,
        message_id=message_id,
    )


def build_requirement_review_card(
    settings: Settings,
    opportunity: dict[str, object],
    cases: list[RequirementReviewCase],
    summary: dict[str, object],
    suggestions: list[dict[str, object]],
) -> dict[str, object]:
    notice_id = _text(opportunity.get("notice_id"))
    pending = int(summary.get("pending_count") or 0)
    resolved = int(summary.get("resolved_count") or 0)
    elements: list[dict[str, object]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**{_text(opportunity.get('title'), '未命名机会')}**\n"
                    f"待人工裁决 {pending} 项 · 已裁决 {resolved} 项 · "
                    f"AI 建议 {len(suggestions)} 项"
                ),
            },
        },
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "**待会审要求**\n" + "\n".join(_case_line(item) for item in cases[:8]),
            },
        },
    ]
    if suggestions:
        elements.extend(
            [
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**AI 会审建议（仅辅助人工裁决）**\n"
                        + "\n".join(_suggestion_line(item) for item in suggestions[:6]),
                    },
                },
            ]
        )
    if notice_id:
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "type": "primary",
                        "text": {"tag": "plain_text", "content": "打开会审档案"},
                        "url": (
                            f"{settings.public_base_url}/?view=opportunityView&"
                            f"opportunity={quote(notice_id, safe='')}"
                        ),
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
                    "content": (
                        f"群内补充依据请发送：项目意见 {notice_id}：内容。"
                        "意见会进入同一机会审计链，人工裁决仍须在档案中确认。"
                    ),
                }
            ],
        }
    )
    return {
        "config": {"wide_screen_mode": True, "update_multi": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "TenderTrace 五角色会审"},
        },
        "elements": elements,
    }


def _case_line(item: RequirementReviewCase) -> str:
    state = "待裁决" if item.status == "pending" else item.decision_label or "已裁决"
    return f"• {item.requirement_key} · {item.reviewer_role_label} · {state} · {item.reason}"


def _suggestion_line(item: dict[str, object]) -> str:
    label = _text(item.get("suggestion_label"), "待判断")
    consensus = {"unanimous": "一致", "single": "单一意见", "split": "存在分歧"}.get(
        _text(item.get("consensus")),
        "待判断",
    )
    return (
        f"• {_text(item.get('requirement_key'), '未命名要求')} · {label} · "
        f"{consensus} · {int(item.get('opinion_count') or 0)} 位 Agent"
    )


def _artifact_key(
    notice_id: str,
    cases: list[RequirementReviewCase],
    suggestions: list[dict[str, object]],
    receive_id: str,
    receive_id_type: str,
) -> str:
    state = {
        "notice_id": notice_id,
        "cases": [(item.id, item.status, item.updated_at) for item in cases],
        "suggestions": suggestions,
    }
    digest = hashlib.sha256(json.dumps(state, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    receiver_scope = hashlib.sha256(f"{receive_id_type}:{receive_id}".encode("utf-8")).hexdigest()[:12]
    return f"requirement_review_board:{notice_id}:{receiver_scope}:{digest}"


def _already_sent(settings: Settings, artifact_key: str) -> bool:
    with connection(settings) as conn:
        row = conn.execute(
            """
            SELECT 1 FROM delivery_attempts
            WHERE channel = 'feishu' AND artifact_type = 'requirement_review_board'
              AND artifact_key = ? AND status = 'sent'
            LIMIT 1
            """,
            (artifact_key,),
        ).fetchone()
    return row is not None


def _nested_string(payload: dict[str, Any], *keys: str) -> str:
    value: object = payload
    for key in keys:
        if not isinstance(value, dict):
            return ""
        value = value.get(key)
    return str(value or "")


def _text(value: object, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default
