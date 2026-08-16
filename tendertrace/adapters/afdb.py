from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urljoin

from selectolax.parser import HTMLParser

from tendertrace.adapters.ccgp import Attachment, Notice, _clean_spaces, _make_notice_id, _summarize
from tendertrace.fetching import FetchError, FetchPolicy, FetchResult, ManagedFetcher
from tendertrace.pipeline.artifacts import page_artifact_from_fetch


AFDB_SOLICITATIONS_URL = (
    "https://www.afdb.org/en/about-us/corporate-procurement/"
    "procurement-notices/current-solicitations"
)
AFDB_AUTHORITY = "African Development Bank Group"


def parse_solicitations(html: str) -> list[Notice]:
    notices: list[Notice] = []
    for card in HTMLParser(html).css(".view-content .col-md-4"):
        anchor = card.css_first(".views-field-title a[href]")
        reference_node = card.css_first(
            ".views-field-field-procurement-reference .field-content"
        )
        published_node = card.css_first(
            ".views-field-field-procurement-pub-date .field-content"
        )
        deadline_node = card.css_first(
            ".views-field-field-procurement-end-date .field-content"
        )
        if anchor is None or published_node is None:
            continue
        title = _clean_spaces(anchor.text(separator=" "))
        source_url = urljoin(AFDB_SOLICITATIONS_URL, anchor.attributes.get("href", ""))
        reference = _clean_spaces(reference_node.text(separator=" ")) if reference_node else ""
        publish_time = _iso_date(published_node.text(separator=" "))
        deadline_text = _clean_spaces(deadline_node.text(separator=" ")) if deadline_node else ""
        deadline = _iso_date(deadline_text)
        if not title or not source_url or not publish_time:
            continue
        content = " | ".join(
            value
            for value in (
                title,
                f"Reference: {reference}" if reference else "",
                f"Published: {publish_time}",
                f"Deadline: {deadline_text}" if deadline_text else "",
            )
            if value
        )
        notices.append(
            Notice(
                id=_make_notice_id(source_url),
                source_site="afdb",
                title=title,
                publish_time=publish_time,
                region="Africa",
                purchaser=AFDB_AUTHORITY,
                source_url=source_url,
                content_text=content,
                core_content=content[:600],
                fields={
                    "cluster_key": f"afdb:{reference or _make_notice_id(source_url)}",
                    "reference": reference,
                    "deadline": deadline,
                    "deadline_text": deadline_text,
                    "notice_type": _notice_type(reference),
                    "landing_page": AFDB_SOLICITATIONS_URL,
                    "authority": AFDB_AUTHORITY,
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
    body = parser.css_first(".field-name-body")
    content = _clean_spaces(body.text(separator=" ")) if body is not None else ""
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
        attachments=_attachments(parser, notice.source_url),
        fields=fields,
    )


class AfdbAdapter:
    name = "afdb"

    def __init__(self, *, timeout: float = 20.0) -> None:
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
        return bidql.get("region", {}).get("scope") in {"global", "afdb"}

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
        notices: list[Notice] = []
        seen: set[str] = set()
        with ManagedFetcher(self.policy) as fetcher:
            try:
                for page in range(max_pages):
                    response = fetcher.get(_page_url(page))
                    response.raise_for_status()
                    batch = parse_solicitations(response.text)
                    if not batch:
                        break
                    for notice in batch:
                        if (
                            notice.id in seen
                            or not _in_window(notice.publish_time, bidql)
                            or not _matches_terms(notice, terms)
                        ):
                            continue
                        seen.add(notice.id)
                        notices.append(notice)
                        if len(notices) >= max_results:
                            return _enrich(fetcher, notices)
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


def _attachments(parser: HTMLParser, page_url: str) -> list[Attachment]:
    attachments: list[Attachment] = []
    seen: set[str] = set()
    for anchor in parser.css("article a[href]"):
        href = anchor.attributes.get("href", "")
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


def _page_url(page: int) -> str:
    return AFDB_SOLICITATIONS_URL if page == 0 else f"{AFDB_SOLICITATIONS_URL}?page={page}"


def _iso_date(value: str) -> str:
    text = _clean_spaces(value)
    for fmt in ("%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:11], fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def _notice_type(reference: str) -> str:
    parts = reference.split("/")
    return parts[1] if len(parts) > 1 else ""


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
