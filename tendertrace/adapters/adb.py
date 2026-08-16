from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from selectolax.parser import HTMLParser

from tendertrace.adapters.ccgp import Attachment, Notice, _clean_spaces
from tendertrace.fetching import FetchPolicy, ManagedFetcher


ADB_NOTICES_URL = "https://www.adb.org/business/institutional-procurement/notices"
ADB_AUTHORITY = "Asian Development Bank"


def parse_notices(html: str) -> list[Notice]:
    notices: list[Notice] = []
    for row in HTMLParser(html).css("table tbody tr"):
        cells = row.css("td")
        anchor = row.css_first("td a[href]")
        if len(cells) < 3 or anchor is None:
            continue
        title = _clean_spaces(anchor.text(separator=" "))
        document_url = urljoin(ADB_NOTICES_URL, anchor.attributes.get("href", ""))
        notice_id = _notice_id(document_url)
        start_date = _iso_date(cells[1].text(separator=" "))
        deadline_text = _clean_spaces(cells[2].text(separator=" "))
        deadline = _iso_date(deadline_text)
        if not notice_id or not title or not start_date or not document_url:
            continue
        detail = _clean_spaces(cells[0].text(separator=" "))
        content = " | ".join(
            value
            for value in (
                detail,
                f"Published: {start_date}",
                f"Deadline: {deadline_text}",
            )
            if value
        )
        notices.append(
            Notice(
                id=notice_id,
                source_site="adb",
                title=title,
                publish_time=start_date,
                region="Asia-Pacific",
                purchaser=ADB_AUTHORITY,
                source_url=document_url,
                content_text=content,
                core_content=content[:600],
                attachments=[Attachment(name=title, url=document_url)],
                fields={
                    "cluster_key": f"adb:{notice_id}",
                    "notice_type": title.partition(":")[0],
                    "deadline": deadline,
                    "deadline_text": deadline_text,
                    "document_url": document_url,
                    "landing_page": ADB_NOTICES_URL,
                    "authority": ADB_AUTHORITY,
                },
            )
        )
    return notices


class AdbAdapter:
    name = "adb"

    def __init__(self, *, timeout: float = 20.0) -> None:
        blocked_markers = tuple(
            marker for marker in FetchPolicy().blocked_markers if marker != "cloudflare"
        )
        self.policy = FetchPolicy(
            headers={
                "User-Agent": "TenderTrace/0.1 (+procurement-intelligence)",
            },
            timeout=timeout,
            max_retries=2,
            blocked_markers=blocked_markers,
        )
        self.last_fetch_stats: dict[str, object] = {}

    def supports(self, bidql: dict[str, Any]) -> bool:
        return bidql.get("region", {}).get("scope") in {"global", "adb"}

    def collect(
        self,
        bidql: dict[str, Any],
        *,
        max_pages: int = 1,
        max_results: int = 10,
    ) -> list[Notice]:
        if max_pages < 1 or max_results < 1:
            return []
        terms = _source_terms(bidql)
        if not terms:
            return []
        with ManagedFetcher(self.policy) as fetcher:
            try:
                response = fetcher.get(ADB_NOTICES_URL)
                response.raise_for_status()
                return [
                    notice
                    for notice in parse_notices(response.text)
                    if _in_window(notice.publish_time, bidql)
                    and _matches_terms(notice, terms)
                ][:max_results]
            finally:
                self.last_fetch_stats = fetcher.stats.to_dict()


def _notice_id(document_url: str) -> str:
    path = PurePosixPath(urlparse(document_url).path)
    return path.stem.strip()


def _iso_date(value: str) -> str:
    cleaned = _clean_spaces(value)
    match = re.search(r"\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b", cleaned)
    candidate = match.group(0) if match else cleaned
    for fmt in ("%d %B %Y", "%d %b %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(candidate, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def _source_terms(bidql: dict[str, Any]) -> list[str]:
    values = bidql.get("topic", {}).get("source_terms") or []
    return [str(value).strip() for value in values if str(value).strip()]


def _in_window(publish_time: str, bidql: dict[str, Any]) -> bool:
    window = bidql.get("time", {}).get("resolved_window")
    if not isinstance(window, dict) or not window.get("from") or not window.get("to"):
        return True
    return str(window["from"]) <= publish_time <= str(window["to"])


def _matches_terms(notice: Notice, terms: list[str]) -> bool:
    haystack = f"{notice.title} {notice.content_text} {notice.core_content}".casefold()
    return any(term.casefold() in haystack for term in terms)
