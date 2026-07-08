from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Any

from tendertrace.adapters.ccgp import Notice, _clean_spaces, _matches_bidql
from tendertrace.config import Settings


QIANLIMA_HOME_URL = "https://www.qianlima.com/"
QIANLIMA_SEARCH_URL = "https://search.qianlima.com/spxm/index.html"


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
            raise RuntimeError("Playwright is not installed. Run: python -m pip install -e .[dev]") from exc

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(storage_state=str(self.storage_state_path))
                page = context.new_page()
                page.goto(QIANLIMA_SEARCH_URL, wait_until="domcontentloaded", timeout=timeout_ms)
                html = page.content()
                browser.close()
        except Exception as exc:
            return {"status": "fail", "detail": f"{type(exc).__name__}: {exc}"}

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
            raise RuntimeError("Playwright is not installed. Run: python -m pip install -e .[dev]") from exc

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
            raise RuntimeError("Playwright is not installed. Run: python -m pip install -e .[dev]") from exc

        keyword = _topic_keyword(bidql)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(storage_state=str(self.vault.storage_state_path))
            page = context.new_page()
            page.goto(QIANLIMA_SEARCH_URL, wait_until="domcontentloaded", timeout=self.timeout_ms)
            html = page.content()
            browser.close()
        notices = parse_rendered_search(html, keyword=keyword)[: max(max_pages, 1) * max_results]
        return [notice for notice in notices if _matches_bidql(notice, bidql)][:max_results]


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
        if source_url in seen:
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
