from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from selectolax.parser import HTMLParser

from tendertrace.adapters.ccgp import Notice, _clean_spaces
from tendertrace.fetching import FetchPolicy, ManagedFetcher


WORLD_BANK_API = "https://search.worldbank.org/api/v2/procnotices"
WORLD_BANK_NOTICE_URL = "https://projects.worldbank.org/en/projects-operations/procurement-detail"


def build_search_url(term: str, *, offset: int, rows: int) -> str:
    return f"{WORLD_BANK_API}?{urlencode({'format': 'json', 'qterm': term, 'os': offset, 'rows': rows})}"


def parse_notices(payload: dict[str, Any]) -> list[Notice]:
    records = payload.get("procnotices")
    if not isinstance(records, list):
        return []
    notices: list[Notice] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        notice_id = str(record.get("id") or "").strip()
        title = _clean_spaces(
            str(record.get("bid_description") or record.get("project_name") or "")
        )
        if not notice_id or not title:
            continue
        content = _html_text(str(record.get("notice_text") or ""))
        country = _clean_spaces(str(record.get("project_ctry_name") or ""))
        purchaser = _clean_spaces(
            str(record.get("contact_organization") or record.get("project_name") or "")
        )
        deadline = str(record.get("submission_deadline_date") or "")[:10]
        notices.append(
            Notice(
                id=notice_id,
                source_site="worldbank",
                title=title,
                publish_time=_iso_date(str(record.get("noticedate") or "")),
                region=country,
                purchaser=purchaser,
                source_url=f"{WORLD_BANK_NOTICE_URL}/{notice_id}",
                content_text=content,
                core_content=(content or title)[:600],
                fields={
                    "cluster_key": f"worldbank:{notice_id}",
                    "notice_type": str(record.get("notice_type") or ""),
                    "project_id": str(record.get("project_id") or ""),
                    "project_name": str(record.get("project_name") or ""),
                    "procurement_method": str(record.get("procurement_method_name") or ""),
                    "deadline": deadline,
                    "language": str(record.get("notice_lang_name") or ""),
                    "authority": "World Bank Group",
                },
            )
        )
    return notices


class WorldBankAdapter:
    name = "worldbank"

    def __init__(self, *, timeout: float = 20.0) -> None:
        self.policy = FetchPolicy(
            headers={"User-Agent": "TenderTrace/0.1 (+procurement-intelligence)"},
            timeout=timeout,
            max_retries=2,
        )
        self.last_fetch_stats: dict[str, object] = {}

    def supports(self, bidql: dict[str, Any]) -> bool:
        return bidql.get("region", {}).get("scope") in {"global", "worldbank"}

    def collect(
        self, bidql: dict[str, Any], *, max_pages: int = 1, max_results: int = 10
    ) -> list[Notice]:
        terms = _source_terms(bidql)
        if not terms:
            return []
        page_size = min(max(max_results, 10), 50)
        notices: list[Notice] = []
        seen: set[str] = set()
        with ManagedFetcher(self.policy) as fetcher:
            try:
                for page in range(max_pages):
                    response = fetcher.get(
                        build_search_url(terms[0], offset=page * page_size, rows=page_size)
                    )
                    response.raise_for_status()
                    for notice in parse_notices(response.json()):
                        if (
                            notice.id in seen
                            or not _in_window(notice.publish_time, bidql)
                            or not _matches_terms(notice, terms)
                        ):
                            continue
                        seen.add(notice.id)
                        notices.append(notice)
                        if len(notices) >= max_results:
                            return notices
            finally:
                self.last_fetch_stats = fetcher.stats.to_dict()
        return notices


def _source_terms(bidql: dict[str, Any]) -> list[str]:
    values = bidql.get("topic", {}).get("source_terms") or []
    return [str(value).strip() for value in values if str(value).strip()]


def _html_text(value: str) -> str:
    return _clean_spaces(HTMLParser(value).text(separator=" ")) if value else ""


def _iso_date(value: str) -> str:
    for fmt in ("%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value[:11], fmt).date().isoformat()
        except ValueError:
            continue
    return value[:10]


def _in_window(publish_time: str, bidql: dict[str, Any]) -> bool:
    window = bidql.get("time", {}).get("resolved_window")
    if not isinstance(window, dict) or not window.get("from") or not window.get("to"):
        return True
    return str(window["from"]) <= publish_time[:10] <= str(window["to"])


def _matches_terms(notice: Notice, terms: list[str]) -> bool:
    haystack = f"{notice.title} {notice.content_text} {notice.core_content}".casefold()
    return any(term.casefold() in haystack for term in terms)
