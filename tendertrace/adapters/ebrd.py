from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

from selectolax.parser import HTMLParser

from tendertrace.adapters.ccgp import Attachment, Notice, _clean_spaces, _summarize
from tendertrace.fetching import FetchError, FetchPolicy, FetchResult, ManagedFetcher
from tendertrace.pipeline.artifacts import page_artifact_from_fetch


EBRD_NOTICES_URL = "https://ecepp.ebrd.com/delta/noticeSearchResults.html"
EBRD_AUTHORITY = "European Bank for Reconstruction and Development"


def parse_notices(html: str) -> list[Notice]:
    notices: list[Notice] = []
    for anchor in HTMLParser(html).css('a[href*="viewNotice.html?displayNoticeId="]'):
        row = anchor.parent.parent if anchor.parent is not None else None
        cells = row.css("td") if row is not None else []
        if len(cells) < 7:
            continue
        source_url = urljoin(EBRD_NOTICES_URL, anchor.attributes.get("href", ""))
        notice_id = _notice_id(source_url)
        title = _clean_spaces(anchor.text(separator=" "))
        notice_type = _clean_spaces(cells[1].text(separator=" "))
        description = _clean_spaces(cells[2].text(separator=" "))
        publish_time = _iso_date(cells[3].text(separator=" "))
        deadline_text = _clean_spaces(cells[4].text(separator=" "))
        deadline = _iso_date(deadline_text)
        response_status = _clean_spaces(cells[5].text(separator=" "))
        metadata = _metadata(cells[9].text(separator=" ") if len(cells) > 9 else "")
        if not notice_id or not title or not publish_time:
            continue
        country = metadata.get("country") or title.partition(":")[0]
        purchaser = metadata.get("purchaser") or EBRD_AUTHORITY
        content = " | ".join(
            value
            for value in (
                title,
                notice_type,
                description,
                f"Published: {publish_time}",
                f"Deadline: {deadline_text}" if deadline_text else "",
                metadata.get("project_name", ""),
                metadata.get("procurement_method", ""),
                purchaser,
            )
            if value
        )
        notices.append(
            Notice(
                id=notice_id,
                source_site="ebrd",
                title=title,
                publish_time=publish_time,
                region=country,
                purchaser=purchaser,
                source_url=source_url,
                content_text=content,
                core_content=content[:600],
                fields={
                    "cluster_key": f"ebrd:{notice_id}",
                    "reference": notice_id,
                    "notice_type": notice_type,
                    "deadline": deadline,
                    "deadline_text": deadline_text,
                    "response_status": response_status,
                    "landing_page": EBRD_NOTICES_URL,
                    "authority": EBRD_AUTHORITY,
                    **metadata,
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
    heading = parser.css_first(".entry-title")
    container = heading.parent if heading is not None else parser.css_first("#noticepreviewtable")
    content = _clean_spaces(container.text(separator=" ")) if container is not None else ""
    detail_fields = _detail_fields(parser)
    fields = {**notice.fields, **detail_fields, "content_length": len(content)}
    if fetch_result is not None:
        fields["page_artifact"] = page_artifact_from_fetch(notice.source_site, fetch_result)
    purchaser = detail_fields.get("client_name") or notice.purchaser
    region = detail_fields.get("country") or notice.region
    return Notice(
        id=notice.id,
        source_site=notice.source_site,
        title=notice.title,
        publish_time=notice.publish_time,
        region=region,
        purchaser=purchaser,
        source_url=notice.source_url,
        content_text=content or notice.content_text,
        core_content=_summarize(content) if content else notice.core_content,
        attachments=_attachments(container, notice.source_url),
        fields=fields,
    )


class EbrdAdapter:
    name = "ebrd"

    def __init__(self, *, timeout: float = 30.0) -> None:
        blocked_markers = tuple(
            marker for marker in FetchPolicy().blocked_markers if marker != "cloudflare"
        )
        self.policy = FetchPolicy(
            headers={"User-Agent": "TenderTrace/0.1 (+procurement-intelligence)"},
            timeout=timeout,
            max_retries=2,
            blocked_markers=blocked_markers,
        )
        self.last_fetch_stats: dict[str, object] = {}

    def supports(self, bidql: dict[str, Any]) -> bool:
        return bidql.get("region", {}).get("scope") in {"global", "ebrd"}

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
                response = fetcher.get(EBRD_NOTICES_URL)
                response.raise_for_status()
                notices = [
                    notice
                    for notice in parse_notices(response.text)
                    if _in_window(notice.publish_time, bidql)
                    and _matches_terms(notice, terms)
                ][:max_results]
                return _enrich(fetcher, notices)
            finally:
                self.last_fetch_stats = fetcher.stats.to_dict()


def _enrich(fetcher: ManagedFetcher, notices: list[Notice]) -> list[Notice]:
    if not notices:
        return []
    enriched: list[Notice] = []
    details = fetcher.batch_get([notice.source_url for notice in notices])
    for notice, detail in zip(notices, details, strict=True):
        try:
            detail.raise_for_status()
            enriched.append(enrich_from_detail(notice, detail.text, detail))
        except FetchError as exc:
            enriched.append(
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
                    fields={**notice.fields, "detail_error": str(exc)},
                )
            )
    return enriched


def _notice_id(source_url: str) -> str:
    values = parse_qs(urlparse(source_url).query).get("displayNoticeId") or []
    return str(values[0]).strip() if values else ""


def _iso_date(value: str) -> str:
    cleaned = _clean_spaces(value).replace("UK Time", "").strip()
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def _metadata(value: str) -> dict[str, str]:
    parts = [part.strip() for part in _clean_spaces(value).strip("[]").split(",")]
    if len(parts) < 7:
        return {}
    return {
        "project_name": parts[0],
        "project_id": parts[1],
        "country": parts[2],
        "procurement_type": parts[3],
        "procurement_method": parts[4],
        "purchaser": parts[5],
        "business_sector": parts[6],
    }


def _detail_fields(parser: HTMLParser) -> dict[str, str]:
    fields: dict[str, str] = {}
    table = parser.css_first("#oppoverviewtable")
    if table is None:
        return fields
    names = {
        "Project Name": "project_name",
        "EBRD Project ID": "project_id",
        "Country": "country",
        "Client Name": "client_name",
        "ECEPP ID": "ecepp_id",
        "Procurement Exercise Name": "procurement_exercise_name",
        "Type of Procurement": "procurement_type",
        "Procurement Method": "procurement_method",
        "Business Sector": "business_sector",
        "Notice Type": "notice_type",
        "Publication Date": "publication_date_text",
    }
    for row in table.css("tr"):
        cells = row.css("td")
        if len(cells) < 2:
            continue
        label = _clean_spaces(cells[0].text(separator=" ")).rstrip(":")
        key = names.get(label)
        if key:
            fields[key] = _clean_spaces(cells[1].text(separator=" "))
    return fields


def _attachments(container, page_url: str) -> list[Attachment]:
    if container is None:
        return []
    attachments: list[Attachment] = []
    seen: set[str] = set()
    for anchor in container.css("a[href]"):
        href = anchor.attributes.get("href") or ""
        path = href.casefold().split("?", 1)[0]
        if not path.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip")):
            continue
        url = urljoin(page_url, href)
        if url in seen:
            continue
        seen.add(url)
        attachments.append(
            Attachment(
                name=_clean_spaces(anchor.text(separator=" ")) or url.rsplit("/", 1)[-1],
                url=url,
            )
        )
    return attachments


def _source_terms(bidql: dict[str, Any]) -> list[str]:
    values = bidql.get("topic", {}).get("source_terms") or []
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _in_window(publish_time: str, bidql: dict[str, Any]) -> bool:
    window = bidql.get("time", {}).get("resolved_window")
    if not isinstance(window, dict) or not window.get("from") or not window.get("to"):
        return True
    return str(window["from"]) <= publish_time <= str(window["to"])


def _matches_terms(notice: Notice, terms: list[str]) -> bool:
    haystack = f"{notice.title} {notice.content_text} {notice.core_content}".casefold()
    return any(term.casefold() in haystack for term in terms)
