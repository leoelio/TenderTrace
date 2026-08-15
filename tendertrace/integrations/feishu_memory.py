from __future__ import annotations

from typing import Any


def build_memory_weekly_card(report: dict[str, object]) -> dict[str, Any]:
    period = _mapping(report.get("period"))
    summary = _mapping(report.get("summary"))
    advice = _mapping(report.get("generated_advice"))
    plan = [item for item in report.get("recommendation_plan") or [] if isinstance(item, dict)]
    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**周期** {period.get('from', '-')} 至 {period.get('to', '-')}\n"
                    f"**完成运行** {summary.get('runs_finished', 0)} · "
                    f"**下载** {summary.get('downloads', 0)} · "
                    f"**新增订阅** {summary.get('subscriptions_created', 0)}"
                ),
            },
        },
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**{advice.get('headline') or '本周行动建议'}**\n"
                    f"{advice.get('summary') or '继续积累真实使用记录。'}"
                ),
            },
        },
        {"tag": "hr"},
    ]
    actionable = [
        item
        for item in plan
        if str(item.get("feedback_status") or "pending") not in {"completed", "dismissed"}
    ][:3]
    for index, item in enumerate(actionable, start=1):
        status = str(item.get("feedback_status") or "pending")
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**{index}. {item.get('title') or '建议'}**"
                        f"{_status_suffix(status)}\n"
                        f"{item.get('reason') or ''}\n"
                        f"**下一步** {item.get('action') or ''}"
                    ),
                },
            }
        )
        elements.append(
            {
                "tag": "action",
                "actions": _advice_actions(
                    str(item.get("id") or ""),
                    str(report.get("user_id") or "admin"),
                    status,
                ),
            }
        )
    if not actionable:
        elements.append(
            {
                "tag": "note",
                "elements": [
                    {"tag": "plain_text", "content": "当前建议均已处理，等待新的行为证据。"}
                ],
            }
        )
    return {
        "config": {"wide_screen_mode": True, "update_multi": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "TenderTrace 使用与机会周报"},
        },
        "elements": elements,
    }


def _advice_actions(advice_id: str, user_id: str, status: str) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if status == "pending":
        actions.append(_button("采纳建议", "memory_advice_accept", advice_id, user_id, "primary"))
    if status in {"pending", "accepted"}:
        actions.append(_button("标记完成", "memory_advice_complete", advice_id, user_id, "default"))
        actions.append(_button("忽略", "memory_advice_dismiss", advice_id, user_id, "default"))
    return actions


def _button(
    label: str,
    action: str,
    advice_id: str,
    user_id: str,
    button_type: str,
) -> dict[str, Any]:
    return {
        "tag": "button",
        "text": {"tag": "plain_text", "content": label},
        "type": button_type,
        "value": {
            "action": action,
            "advice_id": advice_id,
            "user_id": user_id,
        },
    }


def _status_suffix(status: str) -> str:
    return " · 已采纳" if status == "accepted" else ""


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
