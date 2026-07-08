from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any

from tendertrace.adapters.ccgp import Attachment, Notice
from tendertrace.pipeline.dedup import canonicalize_url, clean_text


ATTACHMENT_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar")


@dataclass(frozen=True)
class EvidenceResult:
    notices: list[Notice]
    stats: dict[str, object]


def attach_evidence(notices: list[Notice]) -> EvidenceResult:
    enriched = [_with_evidence(notice) for notice in notices]
    warnings = sum(1 for notice in enriched if notice.fields.get("evidence_status") != "passed")
    return EvidenceResult(
        notices=enriched,
        stats={
            "evidence_checked": len(enriched),
            "evidence_passed": len(enriched) - warnings,
            "evidence_warnings": warnings,
        },
    )


def _with_evidence(notice: Notice) -> Notice:
    attachments = _normalized_attachments(notice)
    evidence_text = _evidence_text(notice)
    excerpt = _excerpt(notice, evidence_text)
    snapshot_sha256 = _sha256(evidence_text)
    fact_checks = _fact_checks(notice, evidence_text)
    quality_score = _quality_score(fact_checks)
    status = "passed" if all(item["status"] == "passed" for item in fact_checks) else "warning"
    evidence = {
        "source_url": notice.source_url,
        "canonical_url": canonicalize_url(notice.source_url),
        "snapshot_sha256": snapshot_sha256,
        "excerpt": excerpt,
        "attachments": _attachment_dicts(notice, attachments),
        "related_sources": _related_sources(notice),
        "fact_checks": fact_checks,
        "quality_score": quality_score,
        "status": status,
    }
    fields = {
        **notice.fields,
        "evidence": evidence,
        "evidence_status": status,
        "evidence_score": quality_score,
        "snapshot_sha256": snapshot_sha256,
        "attachment_types": sorted(
            {
                _attachment_type(attachment.url)
                for attachment in attachments
                if _attachment_type(attachment.url)
            }
        ),
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
        attachments=attachments,
        fields=fields,
    )


def _fact_checks(notice: Notice, evidence_text: str) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    checks.append(
        {
            "field": "source_url",
            "status": "passed" if notice.source_url.startswith(("http://", "https://")) else "warning",
            "score": 1.0 if notice.source_url.startswith(("http://", "https://")) else 0.4,
            "evidence": notice.source_url,
        }
    )
    checks.append(
        {
            "field": "detail_text",
            "status": "passed" if clean_text(notice.content_text) else "warning",
            "score": 1.0 if clean_text(notice.content_text) else 0.5,
            "evidence": _excerpt(notice, evidence_text),
        }
    )
    title_score = _grounding_score(notice.title, evidence_text)
    checks.append(
        {
            "field": "title",
            "status": "passed" if title_score >= 0.8 else "warning",
            "score": title_score,
            "evidence": notice.title,
        }
    )
    core_score = _grounding_score(notice.core_content, evidence_text)
    checks.append(
        {
            "field": "core_content",
            "status": "passed" if not notice.core_content or core_score >= 0.65 else "warning",
            "score": core_score,
            "evidence": _excerpt(notice, evidence_text),
        }
    )
    return checks


def _grounding_score(summary: str, evidence_text: str) -> float:
    summary = clean_text(summary)
    evidence_text = clean_text(evidence_text)
    if not summary:
        return 1.0
    if summary and summary in evidence_text:
        return 1.0
    summary_tokens = set(_tokens(summary))
    if not summary_tokens:
        return 0.0
    evidence_tokens = set(_tokens(evidence_text))
    return round(len(summary_tokens & evidence_tokens) / len(summary_tokens), 3)


def _tokens(value: str) -> list[str]:
    lowered = value.lower()
    ascii_tokens = re.findall(r"[a-z0-9]{2,}", lowered)
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", value))
    chinese_tokens = [chinese[index : index + 2] for index in range(max(len(chinese) - 1, 0))]
    if chinese and not chinese_tokens:
        chinese_tokens = [chinese]
    return ascii_tokens + chinese_tokens


def _evidence_text(notice: Notice) -> str:
    attachment_text = " ".join(
        str(record.get("text_excerpt") or "")
        for record in _attachment_records(notice)
        if isinstance(record, dict)
    )
    return clean_text(
        " ".join(
            part
            for part in (
                notice.title,
                notice.publish_time,
                notice.region,
                notice.purchaser,
                notice.content_text,
                notice.core_content,
                attachment_text,
            )
            if part
        )
    )


def _excerpt(notice: Notice, evidence_text: str) -> str:
    content = clean_text(notice.content_text) or evidence_text
    anchors = [
        str(notice.fields.get("project_no") or ""),
        "项目编号",
        "项目概况",
        "预算",
        "采购",
        "招标",
    ]
    for anchor in anchors:
        if anchor and anchor in content:
            index = content.find(anchor)
            start = max(index - 80, 0)
            return content[start : start + 420].strip()
    return content[:420].strip()


def _related_sources(notice: Notice) -> list[dict[str, str]]:
    seen: set[str] = set()
    sources: list[dict[str, str]] = []
    related = notice.fields.get("related_sources")
    if isinstance(related, list):
        for item in related:
            if not isinstance(item, dict):
                continue
            url = str(item.get("source_url") or "")
            key = canonicalize_url(url)
            if key in seen:
                continue
            seen.add(key)
            sources.append(
                {
                    "source_site": str(item.get("source_site") or ""),
                    "source_url": url,
                    "title": str(item.get("title") or ""),
                    "publish_time": str(item.get("publish_time") or ""),
                }
            )
    current_key = canonicalize_url(notice.source_url)
    if current_key not in seen:
        sources.insert(
            0,
            {
                "source_site": notice.source_site,
                "source_url": notice.source_url,
                "title": notice.title,
                "publish_time": notice.publish_time,
            },
        )
    return sources


def _normalized_attachments(notice: Notice) -> list[Attachment]:
    merged: list[Attachment] = []
    seen: set[str] = set()
    for attachment in [*notice.attachments, *_inline_attachments(notice)]:
        key = canonicalize_url(attachment.url)
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(attachment)
    return merged


def _inline_attachments(notice: Notice) -> list[Attachment]:
    text = " ".join(part for part in (notice.content_text, notice.core_content) if part)
    attachments: list[Attachment] = []
    for match in re.finditer(r"https?://[^\s\"'<>]+", text, flags=re.IGNORECASE):
        url = match.group(0).rstrip("。；;，,)")
        if _attachment_type(url):
            attachments.append(Attachment(name=url.rsplit("/", 1)[-1], url=url))
    return attachments


def _attachment_dicts(notice: Notice, attachments: list[Attachment]) -> list[dict[str, Any]]:
    records = {
        canonicalize_url(str(record.get("url") or "")): record
        for record in _attachment_records(notice)
        if isinstance(record, dict)
    }
    values: list[dict[str, Any]] = []
    for attachment in attachments:
        record = records.get(canonicalize_url(attachment.url), {})
        values.append(
            {
                "name": attachment.name,
                "url": attachment.url,
                "type": _attachment_type(attachment.url),
                "status": str(record.get("status") or ""),
                "path": str(record.get("path") or ""),
                "sha256": str(record.get("sha256") or ""),
                "bytes": int(record.get("bytes") or 0),
                "text_excerpt": str(record.get("text_excerpt") or ""),
                "text_length": int(record.get("text_length") or 0),
                "error": str(record.get("error") or ""),
            }
        )
    return values


def _attachment_type(url: str) -> str:
    lowered = url.lower().split("?", 1)[0]
    for suffix in ATTACHMENT_EXTENSIONS:
        if lowered.endswith(suffix):
            return suffix.lstrip(".")
    return ""


def attachment_type(url: str) -> str:
    return _attachment_type(url)


def _attachment_records(notice: Notice) -> list[dict[str, Any]]:
    records = notice.fields.get("attachment_snapshots")
    if not isinstance(records, list):
        return []
    return [item for item in records if isinstance(item, dict)]


def _quality_score(fact_checks: list[dict[str, Any]]) -> float:
    if not fact_checks:
        return 0.0
    total = sum(float(item.get("score") or 0.0) for item in fact_checks)
    return round(total / len(fact_checks), 3)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
