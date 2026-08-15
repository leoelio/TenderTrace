from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
import hashlib
import re
from typing import Any
from urllib.parse import urljoin

from selectolax.parser import HTMLParser

from tendertrace.fetching import FetchError, FetchPolicy, FetchResult, ManagedFetcher
from tendertrace.parsing import ContentSelection, select_main_content
from tendertrace.pipeline.artifacts import page_artifact_from_fetch


CCGP_LIST_URLS = (
    "https://www.ccgp.gov.cn/cggg/zygg/gkzb/",
    "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/",
)


@dataclass(frozen=True)
class Attachment:
    name: str
    url: str


@dataclass(frozen=True)
class Notice:
    id: str
    source_site: str
    title: str
    publish_time: str
    region: str
    purchaser: str
    source_url: str
    content_text: str = ""
    core_content: str = ""
    attachments: list[Attachment] = field(default_factory=list)
    fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["attachments"] = [asdict(item) for item in self.attachments]
        return value


def _clean_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def _parse_publish_time(value: str) -> datetime | None:
    value = _clean_spaces(value)
    for fmt in ("%Y-%m-%d %H:%M", "%Y年%m月%d日 %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _date_in_window(publish_time: str, window: dict[str, str] | None) -> bool:
    if not window:
        return True
    parsed = _parse_publish_time(publish_time)
    if parsed is None:
        return False
    start = date.fromisoformat(window["from"])
    end = date.fromisoformat(window["to"])
    return start <= parsed.date() <= end


def _topic_terms(bidql: dict[str, Any]) -> list[str]:
    terms = list(bidql.get("topic", {}).get("core", []))
    for item in bidql.get("topic", {}).get("expanded", []):
        term = item.get("term") if isinstance(item, dict) else str(item)
        if term:
            terms.append(term)
    return list(dict.fromkeys(terms))


def _matches_bidql(notice: Notice, bidql: dict[str, Any]) -> bool:
    region = bidql.get("region", {}).get("province")
    region_aliases = bidql.get("region", {}).get("aliases", [])
    city = bidql.get("region", {}).get("city")
    city_aliases = bidql.get("region", {}).get("city_aliases", [])
    haystack = f"{notice.title} {notice.region} {notice.purchaser} {notice.content_text}"
    if city and city_aliases and not any(alias and alias in haystack for alias in city_aliases):
        return False
    if (
        region
        and notice.region != region
        and not any(alias and alias in haystack for alias in region_aliases)
    ):
        return False
    if not _date_in_window(notice.publish_time, bidql.get("time", {}).get("resolved_window")):
        return False
    negatives = bidql.get("topic", {}).get("negative", [])
    if any(term in notice.title for term in negatives):
        return False
    terms = _topic_terms(bidql)
    return not terms or any(term in haystack for term in terms)


def _make_notice_id(source_url: str) -> str:
    return hashlib.sha1(source_url.encode("utf-8")).hexdigest()[:16]


def parse_list_page(html: str, page_url: str) -> list[Notice]:
    parser = HTMLParser(html)
    notices: list[Notice] = []
    for item in parser.css("ul.c_list_bid li"):
        anchor = item.css_first("a")
        if anchor is None:
            continue
        title = _clean_spaces(anchor.text())
        source_url = urljoin(page_url, anchor.attributes.get("href", ""))
        text = _clean_spaces(item.text(separator=" "))
        match = re.search(
            r"发布时间：\s*(?P<time>.*?)\s*地域：\s*(?P<region>.*?)\s*采购人：\s*(?P<purchaser>.*)$",
            text,
        )
        if not title or not source_url or match is None:
            continue
        notices.append(
            Notice(
                id=_make_notice_id(source_url),
                source_site="ccgp",
                title=title,
                publish_time=_clean_spaces(match.group("time")),
                region=_clean_spaces(match.group("region")),
                purchaser=_clean_spaces(match.group("purchaser")),
                source_url=source_url,
            )
        )
    return notices


def _extract_content(parser: HTMLParser) -> str:
    return _select_content(parser).text


def _select_content(parser: HTMLParser) -> ContentSelection:
    return select_main_content(
        parser,
        ("#noticeArea", ".vF_detail_content", "#detail", ".detail_content", ".content"),
    )


def _extract_attachments(parser: HTMLParser, detail_url: str) -> list[Attachment]:
    attachments: list[Attachment] = []
    for anchor in parser.css("a"):
        href = anchor.attributes.get("href")
        text = _clean_spaces(anchor.text())
        if not href:
            continue
        lowered = href.lower()
        if not (
            any(
                ext in lowered for ext in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar")
            )
            or "附件" in text
        ):
            continue
        attachments.append(
            Attachment(name=text or href.rsplit("/", 1)[-1], url=urljoin(detail_url, href))
        )
    return attachments


def _summarize(content: str) -> str:
    if not content:
        return "详情页正文暂未抽取到可用内容。"
    sentences = re.split(r"(?<=[。；;])\s*", content)
    selected: list[str] = []
    anchors = ("项目概况", "项目编号", "项目名称", "预算", "开标", "递交投标文件", "采购需求")
    for sentence in sentences:
        if any(anchor in sentence for anchor in anchors):
            selected.append(sentence)
        if len(selected) >= 3:
            break
    if not selected:
        selected = [content[:260]]
    return _clean_spaces(" ".join(selected))[:600]


def enrich_from_detail(
    notice: Notice, html: str, fetch_result: FetchResult | None = None
) -> Notice:
    parser = HTMLParser(html)
    selection = _select_content(parser)
    content = selection.text
    fields = {**notice.fields, "content_length": len(content)}
    fields["content_selector"] = selection.selector
    fields["content_fallback"] = selection.fallback_used
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
        core_content=_summarize(content),
        attachments=_extract_attachments(parser, notice.source_url),
        fields=fields,
    )


class CcgpAdapter:
    name = "ccgp"

    def __init__(self, *, timeout: float = 20.0) -> None:
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126 Safari/537.36"
            ),
            "Referer": "https://www.ccgp.gov.cn/",
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
        }

    def list_urls(self, max_pages: int) -> list[str]:
        urls: list[str] = []
        for base in CCGP_LIST_URLS:
            urls.append(base)
            for page in range(1, max_pages):
                urls.append(urljoin(base, f"index_{page}.htm"))
        return urls

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
        candidates: list[Notice] = []
        for page_url in self.list_urls(max_pages):
            response = fetcher.get(page_url)
            response.raise_for_status()
            candidates.extend(parse_list_page(response.text, page_url))
        matched = [notice for notice in candidates if _matches_bidql(notice, bidql)]
        enriched: list[Notice] = []
        batch = matched[:max_results]
        detail_results = fetcher.batch_get([notice.source_url for notice in batch])
        for notice, detail in zip(batch, detail_results, strict=True):
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
                        core_content=f"详情页抓取失败：{type(exc).__name__}",
                        fields={"detail_error": str(exc)},
                    )
                )
        return enriched
