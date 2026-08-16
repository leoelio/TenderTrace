from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
import time
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

from selectolax.parser import HTMLParser

from tendertrace.adapters.ccgp import (
    Attachment,
    Notice,
    _clean_spaces,
    _matches_bidql,
    _summarize,
)
from tendertrace.config import Settings
from tendertrace.fetching import FetchResult, FetchStats
from tendertrace.parsing import ContentSelection, select_main_content
from tendertrace.pipeline.artifacts import page_artifact_from_fetch


QIANLIMA_HOME_URL = "https://www.qianlima.com/"
QIANLIMA_SEARCH_URL = "https://search.qianlima.com/spxm/index.html"
QIANLIMA_MEMBER_SEARCH_URL = "https://search.vip.qianlima.com/"


@dataclass(frozen=True)
class QianlimaSessionStatus:
    site: str
    storage_state_path: str
    exists: bool
    size: int = 0
    modified_at: str | None = None
    validation: str = "missing"
    detail: str = "storage_state file is missing"
    cookie_count: int = 0
    origin_count: int = 0
    qianlima_cookie_count: int = 0
    qianlima_origin_count: int = 0

    @property
    def ready(self) -> bool:
        return self.validation == "ready"

    def to_dict(self) -> dict[str, object]:
        return {
            "site": self.site,
            "storage_state_path": self.storage_state_path,
            "exists": self.exists,
            "size": self.size,
            "modified_at": self.modified_at,
            "validation": self.validation,
            "detail": self.detail,
            "ready": self.ready,
            "cookie_count": self.cookie_count,
            "origin_count": self.origin_count,
            "qianlima_cookie_count": self.qianlima_cookie_count,
            "qianlima_origin_count": self.qianlima_origin_count,
        }


class QianlimaSessionVault:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.storage_state_path = settings.secrets_dir / "qianlima_storage_state.json"

    def has_storage_state(self) -> bool:
        return self.status().ready

    def status(self) -> QianlimaSessionStatus:
        if not self.storage_state_path.exists():
            return QianlimaSessionStatus(
                site="qianlima",
                storage_state_path=str(self.storage_state_path),
                exists=False,
            )
        stat = self.storage_state_path.stat()
        validation = _validate_storage_state(self.storage_state_path)
        return QianlimaSessionStatus(
            site="qianlima",
            storage_state_path=str(self.storage_state_path),
            exists=True,
            size=stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            **validation,
        )

    def live_probe(self, *, timeout_ms: int = 30000) -> dict[str, object]:
        status = self.status()
        if not status.ready:
            return {
                "status": "fail",
                "detail": f"storage_state is not ready: {status.validation}",
            }
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is not installed. Run: python -m pip install -e .[dev]"
            ) from exc

        try:
            with (
                sync_playwright() as playwright,
                closing(playwright.chromium.launch(headless=True)) as browser,
            ):
                context = browser.new_context(storage_state=str(self.storage_state_path))
                page = context.new_page()
                _block_static_assets(page)
                html, _, _, auth_failed = _load_rendered_page(
                    page,
                    build_member_search_url("招标"),
                    timeout_ms=timeout_ms,
                )
        except Exception as exc:
            return {"status": "fail", "detail": f"{type(exc).__name__}: {exc}"}

        if auth_failed or login_session_expired(html):
            return {
                "status": "fail",
                "detail": "saved qianlima login session expired; run login-qianlima again",
            }
        notices = parse_rendered_search(html)
        if notices:
            return {
                "status": "pass",
                "detail": f"loaded qianlima search page and parsed {len(notices)} candidate links",
            }
        return {
            "status": "warn",
            "detail": "loaded qianlima search page but parsed no candidate links",
        }

    def save_interactive_login(self) -> QianlimaSessionStatus:
        self.settings.ensure_directories()
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is not installed. Run: python -m pip install -e .[dev]"
            ) from exc

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto(QIANLIMA_HOME_URL, wait_until="domcontentloaded")
            input("请在打开的浏览器中完成千里马登录，然后回到终端按 Enter 保存登录态...")
            context.storage_state(path=str(self.storage_state_path))
            browser.close()
        return self.status()


class QianlimaAdapter:
    name = "qianlima"

    def __init__(self, *, vault: QianlimaSessionVault, timeout_ms: int = 30000) -> None:
        self.vault = vault
        self.timeout_ms = timeout_ms
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
        }

    def collect(
        self,
        bidql: dict[str, Any],
        *,
        max_pages: int = 1,
        max_results: int = 10,
    ) -> list[Notice]:
        if not self.vault.has_storage_state():
            return []
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is not installed. Run: python -m pip install -e .[dev]"
            ) from exc

        keyword = _topic_keyword(bidql)
        stats = FetchStats()
        try:
            with (
                sync_playwright() as playwright,
                closing(playwright.chromium.launch(headless=True)) as browser,
            ):
                context = browser.new_context(storage_state=str(self.vault.storage_state_path))
                page = context.new_page()
                _block_static_assets(page)
                started = time.monotonic()
                search_url = build_member_search_url(keyword)
                html, final_url, status_code, auth_failed = _load_rendered_page(
                    page,
                    search_url,
                    timeout_ms=self.timeout_ms,
                )
                session_expired = auth_failed or login_session_expired(html)
                search_result = _rendered_fetch_result(
                    search_url,
                    final_url=final_url,
                    html=html,
                    elapsed_ms=_elapsed_ms(started),
                    status_code=status_code,
                    blocked=session_expired,
                    error="qianlima member APIs rejected saved session" if auth_failed else "",
                )
                stats.record(search_result)
                if session_expired:
                    raise RuntimeError(
                        "qianlima login session expired; run login-qianlima again"
                    )
                candidates = parse_rendered_search(html)[: max(max_pages, 1) * max_results]
                enriched: list[Notice] = []
                for notice in candidates:
                    started = time.monotonic()
                    try:
                        detail_html, detail_url, detail_status, _ = _load_rendered_page(
                            page,
                            notice.source_url,
                            timeout_ms=self.timeout_ms,
                        )
                        fetch_result = _rendered_fetch_result(
                            notice.source_url,
                            final_url=detail_url,
                            html=detail_html,
                            elapsed_ms=_elapsed_ms(started),
                            status_code=detail_status,
                        )
                        stats.record(fetch_result)
                        enriched.append(parse_rendered_detail(notice, detail_html, fetch_result))
                    except Exception as exc:
                        stats.record(
                            FetchResult(
                                url=notice.source_url,
                                final_url=notice.source_url,
                                method="GET",
                                status_code=0,
                                text="",
                                content_type="text/html",
                                fetched_at=_now_iso(),
                                elapsed_ms=_elapsed_ms(started),
                                attempt_count=1,
                                fetcher="playwright",
                                error=f"{type(exc).__name__}: {exc}",
                            )
                        )
                        enriched.append(
                            Notice(
                                **{
                                    **notice.to_dict(),
                                    "attachments": notice.attachments,
                                    "fields": {**notice.fields, "detail_error": str(exc)},
                                }
                            )
                        )
        finally:
            self.last_fetch_stats = stats.to_dict()
        return [notice for notice in enriched if _matches_bidql(notice, bidql)][:max_results]


def build_member_search_url(keyword: str) -> str:
    term = keyword.strip()
    if not term:
        return QIANLIMA_MEMBER_SEARCH_URL
    return f"{QIANLIMA_MEMBER_SEARCH_URL}?{urlencode({'keywords': term})}"


def parse_rendered_search(html: str, *, keyword: str = "") -> list[Notice]:
    from selectolax.parser import HTMLParser

    parser = HTMLParser(html)
    notices: list[Notice] = []
    seen: set[str] = set()
    for anchor in parser.css("a"):
        href = anchor.attributes.get("href") or ""
        title = _clean_spaces(anchor.text())
        if not href or not title or len(title) < 8:
            continue
        if keyword and keyword not in title:
            continue
        if href.startswith("//"):
            source_url = f"https:{href}"
        elif href.startswith("http"):
            source_url = href
        else:
            source_url = f"https://search.qianlima.com{href}"
        if not _is_notice_url(source_url) or source_url in seen:
            continue
        seen.add(source_url)
        notice_id = hashlib.sha1(source_url.encode("utf-8")).hexdigest()[:16]
        notices.append(
            Notice(
                id=notice_id,
                source_site="qianlima",
                title=title,
                publish_time="",
                region="",
                purchaser="",
                source_url=source_url,
                core_content="千里马会员登录态页面采集结果，详情字段需在登录态详情页中继续补全。",
                fields={
                    "cluster_key": f"qianlima:{notice_id}",
                    "collector": "playwright",
                    "login_state": "storage_state",
                },
            )
        )
    return notices


def parse_rendered_detail(
    notice: Notice,
    html: str,
    fetch_result: FetchResult | None = None,
) -> Notice:
    parser = HTMLParser(html)
    selection = _select_content(parser)
    content = selection.text
    title = _detail_title(parser) or notice.title
    text = " ".join(part for part in (title, content) if part)
    source_url = fetch_result.final_url if fetch_result is not None else notice.source_url
    fields = {
        **notice.fields,
        "collector": "playwright",
        "login_state": "storage_state",
        "content_length": len(content),
        "content_selector": selection.selector,
        "content_fallback": selection.fallback_used,
        "detail_url": source_url,
    }
    if fetch_result is not None:
        fields["page_artifact"] = page_artifact_from_fetch(notice.source_site, fetch_result)
    return Notice(
        id=notice.id,
        source_site=notice.source_site,
        title=title,
        publish_time=_extract_publish_time(text) or notice.publish_time,
        region=_extract_region(text) or notice.region,
        purchaser=_extract_label(
            text, ("采购人", "招标人", "采购单位", "业主单位", "Purchaser", "Buyer")
        )
        or notice.purchaser,
        source_url=source_url,
        content_text=content,
        core_content=_summarize(content) if content else notice.core_content,
        attachments=_extract_attachments(parser, source_url),
        fields=fields,
    )


def _select_content(parser: HTMLParser) -> ContentSelection:
    return select_main_content(
        parser,
        (
            "#content",
            "#detail",
            ".detail",
            ".detail-content",
            ".article",
            ".article-content",
            ".content",
            ".main",
        ),
    )


def _detail_title(parser: HTMLParser) -> str:
    for selector in ("h1", ".title", ".article-title", "title"):
        node = parser.css_first(selector)
        if node is None:
            continue
        title = _clean_spaces(node.text())
        if len(title) >= 4:
            return title
    return ""


def _extract_attachments(parser: HTMLParser, detail_url: str) -> list[Attachment]:
    attachments: list[Attachment] = []
    for anchor in parser.css("a"):
        href = anchor.attributes.get("href") or ""
        text = _clean_spaces(anchor.text())
        if not href:
            continue
        lowered = href.lower()
        if not (
            any(
                ext in lowered for ext in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar")
            )
            or "附件" in text
            or "下载" in text
        ):
            continue
        attachments.append(
            Attachment(name=text or href.rsplit("/", 1)[-1], url=urljoin(detail_url, href))
        )
    return attachments


def _extract_publish_time(text: str) -> str:
    match = re.search(
        r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?(?:\s+(\d{1,2}:\d{2}))?",
        text,
    )
    if not match:
        return ""
    date_part = f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    time_part = match.group(4)
    return f"{date_part} {time_part}" if time_part else date_part


def _extract_label(text: str, labels: tuple[str, ...]) -> str:
    joined = "|".join(re.escape(label) for label in labels)
    match = re.search(rf"(?:{joined})\s*[:：]\s*([^。\n；;]{{2,80}})", text, flags=re.IGNORECASE)
    return _clean_spaces(match.group(1)) if match else ""


def _extract_region(text: str) -> str:
    labeled = _extract_label(text, ("地区", "区域", "省份", "Region"))
    if labeled:
        return labeled
    for region in (
        "北京",
        "上海",
        "天津",
        "重庆",
        "安徽",
        "浙江",
        "江苏",
        "广东",
        "河南",
        "四川",
        "山东",
        "湖北",
        "湖南",
        "福建",
        "陕西",
        "河北",
    ):
        if region in text:
            return region
    return ""


def _rendered_fetch_result(
    url: str,
    *,
    final_url: str,
    html: str,
    elapsed_ms: int,
    status_code: int = 200,
    blocked: bool | None = None,
    error: str = "",
) -> FetchResult:
    return FetchResult(
        url=url,
        final_url=final_url,
        method="GET",
        status_code=status_code,
        text=html,
        content_type="text/html",
        fetched_at=_now_iso(),
        elapsed_ms=elapsed_ms,
        attempt_count=1,
        fetcher="playwright",
        blocked=login_session_expired(html) if blocked is None else blocked,
        error=error,
    )


def login_session_expired(html: str) -> bool:
    sample = _clean_spaces(HTMLParser(html or "").text(separator=" ")).casefold()
    return any(
        marker in sample
        for marker in (
            "登录状态超时",
            "登录已过期",
            "请重新登录",
            "login session expired",
        )
    )


def _is_notice_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    if host != "qianlima.com" and not host.endswith(".qianlima.com"):
        return False
    return bool(re.search(r"(?:/bid-\d+\.html$|/notice/[^?#]+)", parsed.path, re.IGNORECASE))


def _block_static_assets(page) -> None:
    page.route(
        "**/*",
        lambda route: (
            route.abort()
            if route.request.resource_type in {"image", "media", "font"}
            else route.continue_()
        ),
    )


def qianlima_auth_failure(status_code: int, url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    return bool(
        status_code in {401, 403}
        and (host == "qianlima.com" or host.endswith(".qianlima.com"))
        and parsed.path.startswith("/rest/")
    )


def _load_rendered_page(
    page,
    url: str,
    *,
    timeout_ms: int,
) -> tuple[str, str, int, bool]:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    auth_failed = False

    def capture_auth_failure(response) -> None:
        nonlocal auth_failed
        if qianlima_auth_failure(response.status, response.url):
            auth_failed = True

    page.on("response", capture_auth_failure)
    try:
        response = page.goto(url, wait_until="commit", timeout=timeout_ms)
        try:
            page.wait_for_function(
                "document.readyState !== 'loading'",
                timeout=max(1000, min(timeout_ms, 8000)),
            )
        except PlaywrightTimeoutError:
            pass
        try:
            page.wait_for_function(
                """
                () => {
                  const text = document.body?.innerText || '';
                  return Boolean(
                    document.querySelector('a[href*="/bid-"]') ||
                    text.includes('未找到') ||
                    text.includes('登录状态超时') ||
                    text.includes('请重新登录')
                  );
                }
                """,
                timeout=max(1000, min(timeout_ms, 6000)),
            )
        except PlaywrightTimeoutError:
            pass
        return (
            page.content(),
            page.url,
            response.status if response is not None else 0,
            auth_failed,
        )
    finally:
        page.remove_listener("response", capture_auth_failure)


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _topic_keyword(bidql: dict[str, Any]) -> str:
    core = bidql.get("topic", {}).get("core", [])
    if core:
        return str(core[0])
    return ""


def _validate_storage_state(path) -> dict[str, object]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return _validation("unreadable", f"cannot read storage_state: {exc}")
    if not raw.strip():
        return _validation("empty", "storage_state file is empty")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return _validation("invalid_json", "storage_state is not valid JSON")
    if not isinstance(payload, dict):
        return _validation("invalid_shape", "storage_state root must be a JSON object")
    cookies = payload.get("cookies")
    origins = payload.get("origins")
    if not isinstance(cookies, list) or not isinstance(origins, list):
        return _validation("invalid_shape", "storage_state must contain cookies and origins lists")

    qianlima_cookies = [
        cookie
        for cookie in cookies
        if isinstance(cookie, dict) and "qianlima.com" in str(cookie.get("domain") or "")
    ]
    qianlima_origins = [
        origin
        for origin in origins
        if isinstance(origin, dict) and "qianlima.com" in str(origin.get("origin") or "")
    ]
    counts = {
        "cookie_count": len(cookies),
        "origin_count": len(origins),
        "qianlima_cookie_count": len(qianlima_cookies),
        "qianlima_origin_count": len(qianlima_origins),
    }
    if not cookies and not origins:
        return _validation("empty_state", "storage_state has no cookies or origins", **counts)
    if not qianlima_cookies and not qianlima_origins:
        return _validation("domain_missing", "storage_state has no qianlima.com entries", **counts)
    return _validation("ready", "qianlima storage_state structure is ready", **counts)


def _validation(validation: str, detail: str, **counts: object) -> dict[str, object]:
    return {
        "validation": validation,
        "detail": detail,
        "cookie_count": int(counts.get("cookie_count") or 0),
        "origin_count": int(counts.get("origin_count") or 0),
        "qianlima_cookie_count": int(counts.get("qianlima_cookie_count") or 0),
        "qianlima_origin_count": int(counts.get("qianlima_origin_count") or 0),
    }
