from __future__ import annotations

from dataclasses import asdict, dataclass

from tendertrace.config import Settings
from tendertrace.db import connection, init_db


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
        classification = classify_notice_type(
            str(row["title"] or ""),
            str(row["content_text"] or ""),
            str(row["core_content"] or ""),
        )
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
