from __future__ import annotations

from dataclasses import asdict, dataclass
import json

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.llm.audit import record_model_audit
from tendertrace.llm.gateway import ModelGateway


NOTICE_TYPE_LABELS = {
    "tender": "招标/采购",
    "award": "中标/成交",
    "cancelled": "废标/流标/终止",
    "correction": "更正/澄清/变更",
    "other": "其他",
}

# Result-like notices should be excluded from tender-discovery queries. This is the
# semantic upgrade of the negative-keyword LIKE filter: instead of scanning text for
# "中标/成交/废标" tokens, a notice is classified once and filtered by its type.
EXCLUDED_FROM_TENDER_SEARCH = frozenset({"award", "cancelled", "correction"})

# Ordered: the first category whose keyword matches wins. Cancellation/correction
# come before tender so that "招标失败公告" and "采购更正公告" are not mistaken for
# fresh tender notices.
_TYPE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cancelled", ("废标", "流标", "终止公告", "采购失败", "招标失败", "项目终止", "终止采购", "废标公告")),
    ("correction", ("更正", "澄清", "变更公告", "补遗", "延期", "答疑", "修改公告")),
    ("award", ("中标", "成交公告", "结果公告", "中标候选人", "中标公示", "成交公示", "中标结果", "成交通知", "中标公告", "成交结果")),
    ("tender", ("招标公告", "采购公告", "询价", "竞争性磋商", "竞争性谈判", "资格预审", "比选", "磋商公告", "谈判公告", "招标", "采购")),
)


@dataclass(frozen=True)
class NoticeTypeResult:
    notice_type: str
    label: str
    confidence: int
    matched_term: str
    matched_in: str
    exclude_from_tender_search: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def classify_notice_type(
    title: str,
    content_text: str = "",
    core_content: str = "",
) -> NoticeTypeResult:
    """Deterministic rule-based notice classification.

    Returns the first matching category; ``other`` with low confidence when nothing
    matches. The classifier is deterministic so the same text always yields the same
    type, which keeps re-ingestion idempotent.
    """
    matched = _match_in(title)
    if matched is not None:
        notice_type, term = matched
        return _result(notice_type, term, "title", 95)
    matched = _match_in(" ".join(part for part in (content_text, core_content) if part))
    if matched is not None:
        notice_type, term = matched
        return _result(notice_type, term, "content", 75)
    return _result("other", "", "", 20)


def classify_notice_type_with_model(
    settings: Settings,
    title: str,
    content_text: str = "",
    core_content: str = "",
    *,
    gateway: ModelGateway | None = None,
    run_id: str | None = None,
) -> NoticeTypeResult:
    """Rule-first classification with an optional model fallback.

    The model is only consulted when the deterministic rules return ``other``, and it
    may only pick one of the known categories. If the model is unavailable or
    disagrees, the rule result is returned unchanged.
    """
    rule_result = classify_notice_type(title, content_text, core_content)
    if rule_result.notice_type != "other":
        return rule_result

    model_gateway = gateway or ModelGateway(settings)
    prompt = _prompt_for_notice(title, content_text, core_content)
    result = model_gateway.generate_json(system=_SYSTEM_PROMPT, user=prompt)
    if run_id:
        record_model_audit(settings, run_id=run_id, result=result, prompt_text=prompt)
    if result.status != "ok" or not isinstance(result.parsed, dict):
        return rule_result

    predicted = str(result.parsed.get("notice_type") or "").strip().lower()
    if predicted not in NOTICE_TYPE_LABELS or predicted == "other":
        return rule_result
    return _result(predicted, "model", "model", 55)


def classify_and_persist_notice(settings: Settings, notice_id: str) -> NoticeTypeResult | None:
    init_db(settings)
    with connection(settings) as conn:
        row = conn.execute(
            "SELECT title, content_text, core_content FROM notices WHERE id = ?",
            (notice_id,),
        ).fetchone()
        if row is None:
            return None
        classification = classify_notice_type(
            str(row["title"] or ""),
            str(row["content_text"] or ""),
            str(row["core_content"] or ""),
        )
        conn.execute(
            """
            UPDATE notices
            SET notice_type = ?, notice_type_label = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (classification.notice_type, classification.label, notice_id),
        )
    return classification


def classify_notices(
    settings: Settings,
    *,
    limit: int = 500,
    only_unclassified: bool = True,
    with_model: bool = False,
    gateway: ModelGateway | None = None,
) -> dict[str, object]:
    """Batch-classify notices and persist the type. Returns a per-type histogram."""
    init_db(settings)
    with connection(settings) as conn:
        where = "WHERE notice_type = 'other'" if only_unclassified else ""
        rows = conn.execute(
            f"SELECT id, title, content_text, core_content FROM notices {where} LIMIT ?",
            (max(1, min(int(limit), 2000)),),
        ).fetchall()

    by_type: dict[str, int] = {}
    for row in rows:
        title = str(row["title"] or "")
        content_text = str(row["content_text"] or "")
        core_content = str(row["core_content"] or "")
        if with_model:
            classification = classify_notice_type_with_model(
                settings,
                title,
                content_text,
                core_content,
                gateway=gateway,
            )
        else:
            classification = classify_notice_type(title, content_text, core_content)
        by_type[classification.notice_type] = by_type.get(classification.notice_type, 0) + 1
        with connection(settings) as conn:
            conn.execute(
                "UPDATE notices SET notice_type = ?, notice_type_label = ? WHERE id = ?",
                (classification.notice_type, classification.label, str(row["id"])),
            )
    return {
        "status": "finished",
        "scanned_count": len(rows),
        "by_type": by_type,
    }


def _match_in(text: str) -> tuple[str, str] | None:
    if not text:
        return None
    for notice_type, keywords in _TYPE_KEYWORDS:
        for keyword in keywords:
            if keyword in text:
                return notice_type, keyword
    return None


def _result(
    notice_type: str,
    matched_term: str,
    matched_in: str,
    confidence: int,
) -> NoticeTypeResult:
    return NoticeTypeResult(
        notice_type=notice_type,
        label=NOTICE_TYPE_LABELS.get(notice_type, notice_type),
        confidence=confidence,
        matched_term=matched_term,
        matched_in=matched_in,
        exclude_from_tender_search=notice_type in EXCLUDED_FROM_TENDER_SEARCH,
    )


def _prompt_for_notice(title: str, content_text: str, core_content: str) -> str:
    payload = {
        "title": title,
        "content_text": (content_text or "")[:1200],
        "core_content": (core_content or "")[:600],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


_SYSTEM_PROMPT = """You classify a Chinese procurement notice into one category.
Return one strict JSON object only:
{"notice_type":"tender|award|cancelled|correction|other"}
Rules:
- tender = a call for bids or procurement (招标/采购/询价/磋商/谈判/资格预审).
- award = an award or result notice (中标/成交/结果/中标候选人).
- cancelled = cancellation or failure (废标/流标/终止/失败).
- correction = a correction or clarification (更正/澄清/变更/补遗/延期).
- other = none of the above.
- Base the decision only on the provided text; do not invent facts.
"""
