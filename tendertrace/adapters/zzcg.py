from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import httpx
from selectolax.parser import HTMLParser

from tendertrace.adapters.ccgp import Notice, _clean_spaces, _matches_bidql, _make_notice_id
from tendertrace.fetching import FetchPolicy, ManagedFetcher
from tendertrace.intent.region import parse_region


ZZCG_HOME = "https://www.zzcg.gov.cn/"
ZZCG_LIST_URLS = (
    "https://www.zzcg.gov.cn/zbgg/index.jhtml",
    "https://www.zzcg.gov.cn/jggg/index.jhtml",
)
ZZCG_AUTHORITY = "中共中央直属机关采购中心"


def parse_list_page(html: str, page_url: str) -> list[Notice]:
    notices: list[Notice] = []
    parser = HTMLParser(html)
    for item in parser.css("li"):
        anchor = item.css_first("a[href]")
        date_node = item.css_first("span.Gray")
        if anchor is None or date_node is None:
            continue
        title = _clean_spaces(anchor.text(separator=" "))
        publish_time = _clean_spaces(date_node.text())[:10]
        source_url = urljoin(page_url, anchor.attributes.get("href", ""))
        if not title or not publish_time or ".jhtml" not in source_url:
            continue
        region_match = parse_region(title).value
        region = str(region_match.get("city") or region_match.get("province") or "全国")
        notice_type = "结果公告" if "/jggg/" in source_url else "采购公告"
        metadata = (
            f"项目：{title}；公告类型：{notice_type}；发布时间：{publish_time}；"
            f"发布机构：{ZZCG_AUTHORITY}"
        )
        notice_id = _make_notice_id(source_url)
        notices.append(
            Notice(
                id=notice_id,
                source_site="zzcg",
                title=title,
                publish_time=publish_time,
                region=region,
                purchaser="",
                source_url=source_url,
                content_text=metadata,
                core_content=metadata,
                fields={
                    "cluster_key": f"zzcg:{notice_id}",
                    "authority": ZZCG_AUTHORITY,
                    "notice_type": notice_type,
                    "content_format": "official_image_notice",
                    "landing_page": page_url,
                },
            )
        )
    return notices


class ZzcgAdapter:
    name = "zzcg"

    def __init__(
        self,
        *,
        timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.policy = FetchPolicy(
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
                ),
                "Referer": ZZCG_HOME,
            },
            timeout=timeout,
            max_retries=2,
        )
        self.transport = transport
        self.last_fetch_stats: dict[str, object] = {}

    def supports(self, bidql: dict[str, Any]) -> bool:
        return bidql.get("region", {}).get("scope") not in {
            "global", "eu", "worldbank", "uk", "idb", "adb", "afdb", "ebrd",
            "canada", "ukraine",
        }

    def list_urls(self, max_pages: int) -> list[str]:
        urls: list[str] = []
        for base in ZZCG_LIST_URLS:
            urls.append(base)
            for page in range(2, max_pages + 1):
                urls.append(urljoin(base, f"index_{page}.jhtml"))
        return urls

    def collect(
        self,
        bidql: dict[str, Any],
        *,
        max_pages: int = 1,
        max_results: int = 10,
    ) -> list[Notice]:
        if max_pages < 1 or max_results < 1:
            return []
        with ManagedFetcher(self.policy, transport=self.transport) as fetcher:
            try:
                notices: list[Notice] = []
                for page_url in self.list_urls(max_pages):
                    response = fetcher.get(page_url)
                    response.raise_for_status()
                    notices.extend(parse_list_page(response.text, page_url))
                return [notice for notice in notices if _matches_bidql(notice, bidql)][
                    :max_results
                ]
            finally:
                self.last_fetch_stats = fetcher.stats.to_dict()
