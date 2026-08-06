from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from tendertrace.adapters.ccgp import Notice
from tendertrace.pipeline.dedup import extract_project_no


@dataclass(frozen=True)
class StructuredFieldsResult:
    notices: list[Notice]
    stats: dict[str, object]


@dataclass(frozen=True)
class FieldHit:
    value: str
    evidence_text: str


def extract_structured_fields(notices: list[Notice]) -> StructuredFieldsResult:
    enriched = [_with_structured_fields(notice) for notice in notices]
    field_counts: dict[str, int] = {}
    for notice in enriched:
        structured = notice.fields.get("structured_fields")
        if not isinstance(structured, dict):
            continue
        for key, value in structured.items():
            if key == "confidence" or not value:
                continue
            field_counts[key] = field_counts.get(key, 0) + 1
    return StructuredFieldsResult(
        notices=enriched,
        stats={
            "structured_notices": len(enriched),
            "structured_field_hits": sum(field_counts.values()),
            "structured_field_counts": field_counts,
        },
    )


def _with_structured_fields(notice: Notice) -> Notice:
    text = _source_text(notice)
    project_no_hit = _project_no_hit(text, str(notice.fields.get("project_no") or ""))
    budget_hit = _first_hit(text, BUDGET_PATTERNS)
    deadline_hit = _first_hit(text, BID_DEADLINE_PATTERNS)
    opening_hit = _first_hit(text, OPENING_TIME_PATTERNS)
    structured = {
        "project_no": project_no_hit.value if project_no_hit else "",
        "purchaser": notice.purchaser,
        "region": notice.region,
        "publish_time": notice.publish_time,
        "budget": budget_hit.value if budget_hit else "",
        "bid_deadline": deadline_hit.value if deadline_hit else "",
        "opening_time": opening_hit.value if opening_hit else "",
        "attachment_count": len(notice.attachments),
    }
    evidence = _field_evidence(
        notice,
        {
            "project_no": project_no_hit,
            "budget": budget_hit,
            "bid_deadline": deadline_hit,
            "opening_time": opening_hit,
        },
    )
    confidence = {
        key: _confidence(value) for key, value in structured.items() if key != "attachment_count"
    }
    fields = {
        **notice.fields,
        "structured_fields": {**structured, "confidence": confidence},
        "structured_field_evidence": evidence,
    }
    return Notice(
        id=notice.id,
        source_site=notice.source_site,
        title=notice.title,
        publish_time=notice.publish_time,
        region=notice.region,
        purchaser=notice.purchaser,
        source_url=notice.source_url,
        content_text=notice.content_text,
        core_content=notice.core_content,
        attachments=notice.attachments,
        fields=fields,
    )


BUDGET_PATTERNS = (
    r"(?:预算金额|预算|最高限价|采购预算)\s*[:：]?\s*([0-9][0-9,，.]*\s*(?:万元|元|人民币|million|RMB|CNY)[^。；;\n]{0,40})",
    r"(?:budget|ceiling price)\s*[:：]?\s*([0-9][0-9,，.]*\s*(?:million\s*(?:RMB|CNY|yuan)?|RMB|CNY|yuan))",
)

PROJECT_NO_PATTERNS = (
    r"(?:project\s*(?:no|number|code)|tender\s*(?:no|number))\s*[:：#]?\s*([A-Za-z0-9][A-Za-z0-9\-_/().]{3,80})",
)

BID_DEADLINE_PATTERNS = (
    r"(?:投标截止时间|递交投标文件截止时间|响应文件提交截止时间|提交投标文件截止时间)\s*[:：]?\s*([^。；;\n]{6,60})",
    r"(?:bid deadline|submission deadline)\s*[:：]?\s*([0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2}(?:\s+[0-9]{1,2}:[0-9]{2})?)",
)

OPENING_TIME_PATTERNS = (
    r"(?:开标时间|开启时间|响应文件开启时间)\s*[:：]?\s*([^。；;\n]{6,60})",
    r"(?:opening time|bid opening)\s*[:：]?\s*([0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2}(?:\s+[0-9]{1,2}:[0-9]{2})?)",
)


def _source_text(notice: Notice) -> str:
    attachments = notice.fields.get("attachment_snapshots")
    attachment_text = ""
    if isinstance(attachments, list):
        attachment_text = " ".join(
            str(item.get("text_excerpt") or "") for item in attachments if isinstance(item, dict)
        )
    return " ".join(
        part
        for part in (
            notice.title,
            notice.content_text,
            notice.core_content,
            attachment_text,
        )
        if part
    )


def _first_match(text: str, patterns: tuple[str, ...]) -> str:
    hit = _first_hit(text, patterns)
    return hit.value if hit else ""


def _first_hit(text: str, patterns: tuple[str, ...]) -> FieldHit | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = _clean_value(match.group(1))
            return FieldHit(value=value, evidence_text=_snippet(text, match.start(), match.end()))
    return None


def _project_no_hit(text: str, existing: str) -> FieldHit | None:
    if existing:
        index = text.find(existing)
        return FieldHit(value=existing, evidence_text=_snippet_for_value(text, existing, index))
    value = extract_project_no(text)
    if value:
        index = text.find(value)
        return FieldHit(value=value, evidence_text=_snippet_for_value(text, value, index))
    return _first_hit(text, PROJECT_NO_PATTERNS)


def _field_evidence(
    notice: Notice,
    hits: dict[str, FieldHit | None],
) -> dict[str, dict[str, object]]:
    evidence: dict[str, dict[str, object]] = {}
    for field, hit in hits.items():
        if hit is None or not hit.value:
            continue
        evidence[field] = {
            "value": hit.value,
            "evidence_text": hit.evidence_text,
            "source_url": notice.source_url,
            "confidence": _confidence(hit.value),
        }
    return evidence


def _snippet_for_value(text: str, value: str, index: int) -> str:
    if index < 0:
        return value
    return _snippet(text, index, index + len(value))


def _snippet(text: str, start: int, end: int, *, radius: int = 80) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return _clean_value(text[left:right])


def _clean_value(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" ，,。；;.")


def _confidence(value: Any) -> float:
    return 0.86 if str(value or "").strip() else 0.0
