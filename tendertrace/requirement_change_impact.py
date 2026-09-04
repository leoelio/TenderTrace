from __future__ import annotations

from tendertrace.config import Settings
from tendertrace.notice_changes import notice_change_summaries
from tendertrace.opportunity_requirements import OpportunityRequirement, list_requirements


FULL_REVIEW_FIELDS = {
    "attachments",
    "attachment_fingerprints",
    "content_text",
    "core_content",
    "project_no",
    "purchaser",
    "title",
}


def requirement_change_impact(settings: Settings, notice_id: str) -> dict[str, object]:
    summary = notice_change_summaries(settings, [notice_id]).get(notice_id, {})
    changed_fields = [str(value) for value in summary.get("changed_fields", [])]
    requirements = list_requirements(settings, notice_id)
    affected = _affected_requirements(requirements, changed_fields)
    return {
        "changed_fields": changed_fields,
        "review_required": bool(affected),
        "affected_count": len(affected),
        "items": [_impact_item(item, changed_fields) for item in affected],
    }


def _affected_requirements(
    requirements: list[OpportunityRequirement],
    changed_fields: list[str],
) -> list[OpportunityRequirement]:
    fields = set(changed_fields)
    if not fields:
        return []
    if fields & FULL_REVIEW_FIELDS:
        return requirements
    affected_types: set[str] = set()
    if "bid_deadline" in fields:
        affected_types.add("deadline")
    if "budget" in fields:
        affected_types.add("scoring")
    return [item for item in requirements if item.requirement_type in affected_types]


def _impact_item(requirement: OpportunityRequirement, changed_fields: list[str]) -> dict[str, object]:
    fields = set(changed_fields)
    if fields & {"attachments", "attachment_fingerprints"}:
        reason = "附件或附件内容发生变化，需回看原文证据。"
    elif fields & {"content_text", "core_content", "title"}:
        reason = "公告正文发生变化，需复核该要求是否仍然有效。"
    elif "bid_deadline" in fields:
        reason = "投标截止时间变化，需复核该时限与相关安排。"
    elif "budget" in fields:
        reason = "预算变化，需复核评分、报价与投入判断。"
    else:
        reason = "项目关键信息发生变化，需回看原文证据。"
    return {
        "id": requirement.id,
        "requirement_key": requirement.requirement_key,
        "title": requirement.title,
        "status": requirement.status,
        "status_label": requirement.status_label,
        "review_status": "review",
        "review_status_label": "待复核",
        "reason": reason,
    }
