from __future__ import annotations

from dataclasses import asdict
from datetime import date
import re
from typing import Any
from urllib.parse import urljoin

from selectolax.parser import HTMLParser

from tendertrace.adapters.ccgp import (
    Attachment,
    Notice,
    _clean_spaces,
    _matches_bidql,
    _summarize,
)
from tendertrace.fetching import FetchError, FetchPolicy, FetchResult, ManagedFetcher
from tendertrace.parsing import ContentSelection, select_main_content
from tendertrace.pipeline.artifacts import page_artifact_from_fetch


GGZY_BASE_URL = "https://www.ggzy.gov.cn"
GGZY_LIST_API = f"{GGZY_BASE_URL}/information/pubTradingInfo/getTradList"
GGZY_DEAL_LIST_URL = f"{GGZY_BASE_URL}/deal/dealList.html"


def _topic_keywords(bidql: dict[str, Any]) -> list[str]:
    keywords: list[str] = []
    core = bidql.get("topic", {}).get("core", [])
    for item in core:
        value = str(item).strip()
        if value:
            keywords.append(value)
    expanded = bidql.get("topic", {}).get("expanded", [])
    for item in expanded:
        if isinstance(item, dict) and item.get("term"):
            value = str(item["term"]).strip()
        elif item:
            value = str(item).strip()
        else:
            value = ""
        if value:
            keywords.append(value)
    return list(dict.fromkeys(keywords))[:5]


def _topic_keyword(bidql: dict[str, Any]) -> str:
    keywords = _topic_keywords(bidql)
    return keywords[0] if keywords else ""


def build_search_body(
    bidql: dict[str, Any],
    *,
    page: int = 1,
    keyword: str | None = None,
) -> dict[str, str]:
    body = {
        "SOURCE_TYPE": "1",
        "PAGENUMBER": str(page),
    }
    window = bidql.get("time", {}).get("resolved_window")
    if (
        isinstance(window, dict)
        and window.get("from")
        and window.get("to")
        and _site_accepts_window(window)
    ):
        body["TIMEBEGIN"] = str(window["from"])
        body["TIMEEND"] = str(window["to"])
    else:
        body["DEAL_TIME"] = "02"
    adcode = bidql.get("region", {}).get("adcode")
    if adcode:
        body["DEAL_PROVINCE"] = str(adcode)
    search_keyword = _topic_keyword(bidql) if keyword is None else keyword
    if search_keyword:
        body["FINDTXT"] = search_keyword
    return body


def _site_accepts_window(window: dict[str, Any]) -> bool:
    try:
        start = date.fromisoformat(str(window["from"]))
        end = date.fromisoformat(str(window["to"]))
    except (KeyError, ValueError):
        return False
    return 0 <= (end - start).days <= 366


def parse_records(records: list[dict[str, Any]]) -> list[Notice]:
    notices: list[Notice] = []
    for record in records:
        title = _clean_spaces(str(record.get("title") or ""))
        notice_id = str(record.get("id") or "")
        url = str(record.get("url") or "")
        if not title or not notice_id or not url:
            continue
        source_url = urljoin(GGZY_BASE_URL, url)
        platform = _clean_spaces(str(record.get("transactionSourcesPlatformText") or ""))
        province = _clean_spaces(str(record.get("provinceText") or ""))
        business_type = _clean_spaces(str(record.get("businessTypeText") or ""))
        information_type = _clean_spaces(str(record.get("informationTypeText") or ""))
        notices.append(
            Notice(
                id=notice_id,
                source_site="ggzy",
                title=title,
                publish_time=_clean_spaces(str(record.get("publishTime") or "")),
                region=province,
                purchaser=platform or province,
                source_url=source_url,
                core_content=_clean_spaces(
                    " ".join(part for part in (business_type, information_type) if part)
                ),
                fields={
                    "cluster_key": f"ggzy:{notice_id}",
                    "business_type": business_type,
                    "information_type": information_type,
                    "platform": platform,
                    "raw": record,
                },
            )
        )
    return notices


def _detail_body_path(html: str) -> str | None:
    match = re.search(r"showDetail\([^)]*'(?P<path>/information/deal/html/b/[^']+\.html)'", html)
    return match.group("path") if match else None


def _extract_content(parser: HTMLParser) -> str:
    return _select_content(parser).text


def _select_content(parser: HTMLParser) -> ContentSelection:
    return select_main_content(
        parser,
        ("#mycontent", ".detail_content", ".detail", "#noticeArea", ".content"),
    )


def _extract_attachments(parser: HTMLParser, detail_url: str) -> list[Attachment]:
    attachments: list[Attachment] = []
    for anchor in parser.css("a"):
        href = anchor.attributes.get("href")
        text = _clean_spaces(anchor.text())
        if not href:
            continue
        lowered = href.lower()
        if not any(
            ext in lowered for ext in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar")
        ):
            continue
        attachments.append(
            Attachment(name=text or href.rsplit("/", 1)[-1], url=urljoin(detail_url, href))
        )
    return attachments


def enrich_from_detail(
    notice: Notice,
    html: str,
    detail_url: str | None = None,
    fetch_result: FetchResult | None = None,
) -> Notice:
    parser = HTMLParser(html)
    selection = _select_content(parser)
    content = selection.text
    final_url = detail_url or notice.source_url
    original_anchor = parser.css_first("span.detail_url a")
    original_url = original_anchor.attributes.get("href") if original_anchor is not None else ""
    fields = {**notice.fields, "content_length": len(content)}
    fields["content_selector"] = selection.selector
    fields["content_fallback"] = selection.fallback_used
    if original_url:
        fields["original_url"] = original_url
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
        content_text=content,
        core_content=_summarize(content) if content else notice.core_content,
        attachments=_extract_attachments(parser, final_url),
        fields=fields,
    )


def _notice_with_detail_error(notice: Notice, exc: Exception) -> Notice:
    fields = {**notice.fields, "detail_error": str(exc)}
    return Notice(
        **{
            **asdict(notice),
            "attachments": notice.attachments,
            "fields": fields,
        }
    )


class GgzyAdapter:
    name = "ggzy"

    def __init__(self, *, timeout: float = 20.0) -> None:
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126 Safari/537.36"
            ),
            "Referer": GGZY_DEAL_LIST_URL,
        }
        self.timeout = timeout
        self.policy = FetchPolicy(
            headers=self.headers,
            timeout=timeout,
            max_retries=2,
            browser_fallback=True,
        )
        self.last_fetch_stats: dict[str, object] = {}

    def supports(self, bidql: dict[str, Any]) -> bool:
        return bidql.get("region", {}).get("scope") not in {
            "global",
            "eu",
            "worldbank",
            "uk",
            "idb",
            "adb",
            "afdb",
            "ebrd",
        }

    def collect(
        self, bidql: dict[str, Any], *, max_pages: int = 1, max_results: int = 10
    ) -> list[Notice]:
        with ManagedFetcher(self.policy) as fetcher:
            try:
                return self._collect_with_fetcher(
                    fetcher,
                    bidql,
                    max_pages=max_pages,
                    max_results=max_results,
                )
            finally:
                self.last_fetch_stats = fetcher.stats.to_dict()

    def _collect_with_fetcher(
        self,
        fetcher: ManagedFetcher,
        bidql: dict[str, Any],
        *,
        max_pages: int,
        max_results: int,
    ) -> list[Notice]:
        matched: list[Notice] = []
        seen: set[str] = set()
        keywords = _topic_keywords(bidql)
        search_terms = keywords or [""]
        matched.extend(
            self._collect_matching(
                fetcher,
                bidql,
                search_terms=search_terms,
                max_pages=max_pages,
                max_results=max_results,
                seen=seen,
            )
        )
        if not matched and keywords:
            matched.extend(
                self._collect_matching(
                    fetcher,
                    bidql,
                    search_terms=[""],
                    max_pages=max_pages,
                    max_results=max_results,
                    seen=seen,
                )
            )

        batch = matched[:max_results]
        enriched_by_index: list[Notice | None] = [None] * len(batch)
        body_jobs: list[tuple[int, Notice, str]] = []
        detail_results = fetcher.batch_get([notice.source_url for notice in batch])
        for index, (notice, detail) in enumerate(zip(batch, detail_results, strict=True)):
            try:
                detail.raise_for_status()
                body_path = _detail_body_path(detail.text)
                if body_path:
                    body_url = urljoin(GGZY_BASE_URL, body_path)
                    body_jobs.append((index, notice, body_url))
                else:
                    enriched_by_index[index] = enrich_from_detail(
                        notice, detail.text, notice.source_url, detail
                    )
            except (FetchError, RuntimeError) as exc:
                enriched_by_index[index] = _notice_with_detail_error(notice, exc)
        body_results = fetcher.batch_get([body_url for _, _, body_url in body_jobs])
        for (index, notice, body_url), body in zip(body_jobs, body_results, strict=True):
            try:
                body.raise_for_status()
                enriched_by_index[index] = enrich_from_detail(notice, body.text, body_url, body)
            except (FetchError, RuntimeError) as exc:
                enriched_by_index[index] = _notice_with_detail_error(notice, exc)
        return [notice for notice in enriched_by_index if notice is not None]

    def _collect_matching(
        self,
        fetcher: ManagedFetcher,
        bidql: dict[str, Any],
        *,
        search_terms: list[str],
        max_pages: int,
        max_results: int,
        seen: set[str],
    ) -> list[Notice]:
        matched: list[Notice] = []
        for keyword in search_terms:
            for page in range(1, max_pages + 1):
                response = fetcher.post(
                    GGZY_LIST_API,
                    data=build_search_body(bidql, page=page, keyword=keyword),
                )
                response.raise_for_status()
                payload = response.json()
                code = payload.get("code")
                if code == 829:
                    raise RuntimeError("ggzy search requires captcha verification")
                if code != 200:
                    raise RuntimeError(f"ggzy search failed: {payload.get('message') or code}")
                records = payload.get("data", {}).get("records") or []
                for notice in parse_records(records):
                    if notice.id in seen or not _matches_bidql(notice, bidql):
                        continue
                    seen.add(notice.id)
                    matched.append(notice)
                    if len(matched) >= max_results:
                        return matched
        return matched
