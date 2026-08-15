from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urljoin

from selectolax.parser import HTMLParser

from tendertrace.adapters.ccgp import Attachment, Notice, _clean_spaces, _summarize
from tendertrace.fetching import FetchError, FetchPolicy, FetchResult, ManagedFetcher
from tendertrace.pipeline.artifacts import page_artifact_from_fetch


UNGM_BASE_URL = "https://www.ungm.org"
UNGM_SEARCH_URL = f"{UNGM_BASE_URL}/Public/Notice/Search"


def build_search_body(
    bidql: dict[str, Any],
    *,
    page: int = 0,
    term: str = "",
    page_size: int = 15,
) -> dict[str, object]:
    window = bidql.get("time", {}).get("resolved_window")
    published_from = ""
    published_to = ""
    if isinstance(window, dict):
        published_from = _format_search_date(window.get("from"))
        published_to = _format_search_date(window.get("to"))
    return {
        "PageIndex": page,
        "PageSize": max(1, min(page_size, 100)),
        "Title": term,
        "Description": "",
        "Reference": "",
        "PublishedFrom": published_from,
        "PublishedTo": published_to,
        "DeadlineFrom": "",
        "DeadlineTo": "",
        "Countries": [],
        "Agencies": [],
        "UNSPSCs": [],
        "NoticeTypes": [],
        "SortField": "DatePublished",
        "SortAscending": False,
        "isPicker": False,
        "IsSustainable": False,
        "IsActive": False,
        "NoticeDisplayType": "",
        "NoticeSearchTotalLabelId": "noticeSearchTotal",
        "TypeOfCompetitions": [],
    }


def parse_search_results(html: str) -> list[Notice]:
    parser = HTMLParser(html)
    notices: list[Notice] = []
    for row in parser.css(".dataRow[data-noticeid]"):
        notice_id = _clean_spaces(row.attributes.get("data-noticeid", ""))
        title_node = row.css_first(".resultTitle .ungm-title")
        cells = row.css(".tableCell")
        if not notice_id or title_node is None or len(cells) < 8:
            continue
        title = _clean_spaces(title_node.text(separator=" "))
        if not title:
            continue
        deadline_node = row.css_first(".deadline span")
        deadline = _clean_spaces(deadline_node.text(separator=" ")) if deadline_node else ""
        published = _normalize_published_date(cells[3].text(separator=" "))
        purchaser = _clean_spaces(cells[4].text(separator=" "))
        notice_type = _clean_spaces(cells[5].text(separator=" "))
        reference = _clean_spaces(cells[6].text(separator=" "))
        region = _clean_spaces(cells[7].text(separator=" "))
        source_url = f"{UNGM_BASE_URL}/Public/Notice/{notice_id}"
        notices.append(
            Notice(
                id=f"ungm-{notice_id}",
                source_site="ungm",
                title=title,
                publish_time=published,
                region=region,
                purchaser=purchaser,
                source_url=source_url,
                content_text=" ".join(
                    value for value in (title, purchaser, notice_type, reference, region) if value
                ),
                core_content=title,
                fields={
                    "reference": reference,
                    "deadline": deadline,
                    "notice_type": notice_type,
                    "source_authority": "United Nations Global Marketplace",
                    "source_tier": "official",
                },
            )
        )
    return notices


def enrich_from_detail(
    notice: Notice,
    html: str,
    fetch_result: FetchResult | None = None,
) -> Notice:
    parser = HTMLParser(html)
    content = _description_text(parser)
    attachments = _attachments(parser, notice.source_url)
    fields = dict(notice.fields)
    fields["content_length"] = len(content)
    if fetch_result is not None:
        fields["page_artifact"] = page_artifact_from_fetch(notice.source_site, fetch_result)
    return Notice(
        id=notice.id,
        source_site=notice.source_site,
        title=notice.title,
        publish_time=notice.publish_time,
        region=notice.region,
        purchaser=notice.purchaser,
        source_url=notice.source_url,
        content_text=content or notice.content_text,
        core_content=_summarize(content) if content else notice.core_content,
        attachments=attachments,
        fields=fields,
    )


class UngmAdapter:
    name = "ungm"

    def __init__(self, *, timeout: float = 20.0) -> None:
        self.policy = FetchPolicy(
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
                ),
                "Referer": f"{UNGM_BASE_URL}/Public/Notice",
            },
            timeout=timeout,
            max_retries=2,
        )
        self.last_fetch_stats: dict[str, object] = {}

    def supports(self, bidql: dict[str, Any]) -> bool:
        return bidql.get("region", {}).get("scope") == "global"

    def collect(
        self,
        bidql: dict[str, Any],
        *,
        max_pages: int = 1,
        max_results: int = 10,
    ) -> list[Notice]:
        terms = _source_terms(bidql) or [""]
        notices: list[Notice] = []
        seen: set[str] = set()
        with ManagedFetcher(self.policy) as fetcher:
            try:
                for term in terms[:3]:
                    for page in range(max_pages):
                        response = fetcher.post(
                            UNGM_SEARCH_URL,
                            json=build_search_body(
                                bidql,
                                page=page,
                                term=term,
                                page_size=min(max(max_results, 15), 100),
                            ),
                        )
                        response.raise_for_status()
                        batch = parse_search_results(response.text)
                        if not batch:
                            break
                        for notice in batch:
                            if notice.id in seen:
                                continue
                            seen.add(notice.id)
                            notices.append(notice)
                            if len(notices) >= max_results:
                                return _enrich(fetcher, notices)
                return _enrich(fetcher, notices)
            finally:
                self.last_fetch_stats = fetcher.stats.to_dict()


def _enrich(fetcher: ManagedFetcher, notices: list[Notice]) -> list[Notice]:
    results: list[Notice] = []
    details = fetcher.batch_get([notice.source_url for notice in notices])
    for notice, detail in zip(notices, details, strict=True):
        try:
            detail.raise_for_status()
            results.append(enrich_from_detail(notice, detail.text, detail))
        except FetchError as exc:
            fields = {**notice.fields, "detail_error": str(exc)}
            results.append(
                Notice(
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
            )
    return results


def _description_text(parser: HTMLParser) -> str:
    for title in parser.css(".ungm-list-item .title"):
        if _clean_spaces(title.text(separator=" ")).casefold() != "description":
            continue
        parent = title.parent
        text = _clean_spaces(parent.text(separator=" ")) if parent is not None else ""
        return text.removeprefix("Description").strip()
    return ""


def _attachments(parser: HTMLParser, page_url: str) -> list[Attachment]:
    values: list[Attachment] = []
    seen: set[str] = set()
    for anchor in parser.css(".ungm-panel a[href]"):
        href = anchor.attributes.get("href", "")
        lowered = href.casefold().split("?", 1)[0]
        if not lowered.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip")):
            continue
        url = urljoin(page_url, href)
        if url in seen:
            continue
        seen.add(url)
        values.append(
            Attachment(
                name=_clean_spaces(anchor.text(separator=" ")) or url.rsplit("/", 1)[-1],
                url=url,
            )
        )
    return values


def _source_terms(bidql: dict[str, Any]) -> list[str]:
    values = bidql.get("topic", {}).get("source_terms") or []
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _format_search_date(value: object) -> str:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").strftime("%d-%b-%y")
    except ValueError:
        return ""


def _normalize_published_date(value: str) -> str:
    text = _clean_spaces(value)
    for fmt in ("%d-%b-%Y", "%d-%b-%y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text
