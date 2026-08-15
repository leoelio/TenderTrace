from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.utils import parsedate_to_datetime
import json
from threading import Lock
import time
from typing import Any

import httpx


class FetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class FetchPolicy:
    headers: dict[str, str] = field(default_factory=dict)
    timeout: float = 20.0
    max_retries: int = 1
    backoff_seconds: float = 0.2
    max_backoff_seconds: float = 30.0
    follow_redirects: bool = True
    blocked_statuses: tuple[int, ...] = (403, 429)
    retry_statuses: tuple[int, ...] = (408, 409, 425, 429, 500, 502, 503, 504)
    blocked_markers: tuple[str, ...] = (
        "captcha",
        "cloudflare",
        "turnstile",
        "security check",
        "access denied",
        "verify you are human",
        "验证码",
        "访问过于频繁",
        "请登录",
    )
    browser_fallback: bool = False
    browser_timeout_ms: int = 30000
    browser_network_idle_timeout_ms: int = 5000
    browser_block_resource_types: tuple[str, ...] = ("image", "media", "font")


@dataclass
class FetchStats:
    requests: int = 0
    succeeded: int = 0
    failed: int = 0
    blocked: int = 0
    retries: int = 0
    browser_fallbacks: int = 0
    total_elapsed_ms: int = 0
    status_codes: dict[str, int] = field(default_factory=dict)
    last_error: str = ""

    def record(self, result: "FetchResult") -> None:
        self.requests += 1
        self.total_elapsed_ms += result.elapsed_ms
        if result.attempt_count > 1:
            self.retries += result.attempt_count - 1
        if result.fetcher == "playwright":
            self.browser_fallbacks += 1
        if result.status_code:
            key = str(result.status_code)
            self.status_codes[key] = self.status_codes.get(key, 0) + 1
        if result.blocked:
            self.blocked += 1
        if result.ok:
            self.succeeded += 1
        else:
            self.failed += 1
            self.last_error = result.error or f"HTTP {result.status_code}"

    def to_dict(self) -> dict[str, object]:
        avg_elapsed = int(self.total_elapsed_ms / self.requests) if self.requests else 0
        return {
            "requests": self.requests,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "blocked": self.blocked,
            "retries": self.retries,
            "browser_fallbacks": self.browser_fallbacks,
            "avg_elapsed_ms": avg_elapsed,
            "status_codes": dict(sorted(self.status_codes.items())),
            "last_error": self.last_error,
        }


@dataclass(frozen=True)
class FetchResult:
    url: str
    final_url: str
    method: str
    status_code: int
    text: str
    content_type: str
    fetched_at: str
    elapsed_ms: int
    attempt_count: int
    fetcher: str = "httpx"
    blocked: bool = False
    error: str = ""
    retry_after_seconds: float | None = None

    @property
    def ok(self) -> bool:
        return not self.error and not self.blocked and 200 <= self.status_code < 400

    def raise_for_status(self) -> None:
        if self.ok:
            return
        if self.error:
            raise FetchError(self.error)
        if self.blocked:
            raise FetchError(f"blocked response from {self.final_url or self.url}")
        raise FetchError(f"HTTP {self.status_code} for {self.final_url or self.url}")

    def json(self) -> Any:
        return json.loads(self.text)


class ManagedFetcher:
    def __init__(
        self,
        policy: FetchPolicy | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.policy = policy or FetchPolicy()
        self.transport = transport
        self.stats = FetchStats()
        self._client: httpx.Client | None = None
        self._stats_lock = Lock()

    def __enter__(self) -> "ManagedFetcher":
        self._client = httpx.Client(
            headers=self.policy.headers,
            timeout=self.policy.timeout,
            follow_redirects=self.policy.follow_redirects,
            transport=self.transport,
        )
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def get(self, url: str, **kwargs: Any) -> FetchResult:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> FetchResult:
        return self.request("POST", url, **kwargs)

    def request(self, method: str, url: str, **kwargs: Any) -> FetchResult:
        if self._client is None:
            raise RuntimeError("ManagedFetcher must be used as a context manager")
        result = self._request_http(method, url, **kwargs)
        if self._should_try_browser(method, result):
            browser_result = self._request_browser(url, attempt_count=result.attempt_count)
            result = browser_result if browser_result.ok else result
        self._record(result)
        return result

    def batch_get(self, urls: list[str], *, max_workers: int = 4) -> list[FetchResult]:
        if not urls:
            return []
        workers = max(1, min(max_workers, len(urls)))
        results: list[FetchResult | None] = [None] * len(urls)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(self.get, url): index for index, url in enumerate(urls)}
            for future in as_completed(futures):
                results[futures[future]] = future.result()
        return [result for result in results if result is not None]

    def _record(self, result: FetchResult) -> None:
        with self._stats_lock:
            self.stats.record(result)

    def _request_http(self, method: str, url: str, **kwargs: Any) -> FetchResult:
        assert self._client is not None
        attempts = max(1, self.policy.max_retries + 1)
        last: FetchResult | None = None
        for attempt in range(1, attempts + 1):
            started = time.monotonic()
            try:
                response = self._client.request(method, url, **kwargs)
                result = _result_from_response(
                    method=method,
                    url=url,
                    response=response,
                    elapsed_ms=_elapsed_ms(started),
                    attempt_count=attempt,
                    policy=self.policy,
                    fetcher="httpx",
                )
            except httpx.HTTPError as exc:
                result = FetchResult(
                    url=url,
                    final_url=url,
                    method=method.upper(),
                    status_code=0,
                    text="",
                    content_type="",
                    fetched_at=_now_iso(),
                    elapsed_ms=_elapsed_ms(started),
                    attempt_count=attempt,
                    error=f"{type(exc).__name__}: {exc}",
                )
            last = result
            if not _should_retry(result, self.policy) or attempt >= attempts:
                break
            retry_delay = max(
                self.policy.backoff_seconds * (2 ** (attempt - 1)),
                result.retry_after_seconds or 0.0,
            )
            time.sleep(min(retry_delay, self.policy.max_backoff_seconds))
        return last or FetchResult(
            url=url,
            final_url=url,
            method=method.upper(),
            status_code=0,
            text="",
            content_type="",
            fetched_at=_now_iso(),
            elapsed_ms=0,
            attempt_count=0,
            error="request was not attempted",
        )

    def _should_try_browser(self, method: str, result: FetchResult) -> bool:
        if not self.policy.browser_fallback or method.upper() != "GET":
            return False
        if result.ok and not _looks_like_empty_js_shell(result.text):
            return False
        return bool(result.blocked or result.error or _looks_like_empty_js_shell(result.text))

    def _request_browser(self, url: str, *, attempt_count: int) -> FetchResult:
        started = time.monotonic()
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            return _browser_error(url, started, attempt_count, exc)
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(extra_http_headers=self.policy.headers)
                page = context.new_page()
                blocked_types = set(self.policy.browser_block_resource_types)
                if blocked_types:
                    page.route(
                        "**/*",
                        lambda route: (
                            route.abort()
                            if route.request.resource_type in blocked_types
                            else route.continue_()
                        ),
                    )
                response = page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=self.policy.browser_timeout_ms,
                )
                try:
                    page.wait_for_load_state(
                        "networkidle",
                        timeout=self.policy.browser_network_idle_timeout_ms,
                    )
                except PlaywrightTimeoutError:
                    pass
                text = page.content()
                final_url = page.url
                status = response.status if response is not None else 0
                browser.close()
        except Exception as exc:
            return _browser_error(url, started, attempt_count, exc)
        blocked = _is_blocked(status, text, self.policy)
        return FetchResult(
            url=url,
            final_url=final_url,
            method="GET",
            status_code=status,
            text=text,
            content_type="text/html",
            fetched_at=_now_iso(),
            elapsed_ms=_elapsed_ms(started),
            attempt_count=attempt_count + 1,
            fetcher="playwright",
            blocked=blocked,
        )


def _result_from_response(
    *,
    method: str,
    url: str,
    response: httpx.Response,
    elapsed_ms: int,
    attempt_count: int,
    policy: FetchPolicy,
    fetcher: str,
) -> FetchResult:
    text = response.text
    status = response.status_code
    return FetchResult(
        url=url,
        final_url=str(response.url),
        method=method.upper(),
        status_code=status,
        text=text,
        content_type=response.headers.get("content-type", ""),
        fetched_at=_now_iso(),
        elapsed_ms=elapsed_ms,
        attempt_count=attempt_count,
        fetcher=fetcher,
        blocked=_is_blocked(status, text, policy),
        retry_after_seconds=_retry_after_seconds(response.headers.get("retry-after")),
    )


def _browser_error(url: str, started: float, attempt_count: int, exc: Exception) -> FetchResult:
    return FetchResult(
        url=url,
        final_url=url,
        method="GET",
        status_code=0,
        text="",
        content_type="",
        fetched_at=_now_iso(),
        elapsed_ms=_elapsed_ms(started),
        attempt_count=attempt_count + 1,
        fetcher="playwright",
        error=f"{type(exc).__name__}: {exc}",
    )


def _should_retry(result: FetchResult, policy: FetchPolicy) -> bool:
    if result.status_code in policy.retry_statuses:
        return True
    return bool(result.error or result.blocked)


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        target = parsedate_to_datetime(value)
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        return max(0.0, (target - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


def _is_blocked(status_code: int, text: str, policy: FetchPolicy) -> bool:
    if status_code in policy.blocked_statuses:
        return True
    sample = (text or "")[:5000].lower()
    return any(marker.lower() in sample for marker in policy.blocked_markers)


def _looks_like_empty_js_shell(text: str) -> bool:
    stripped = (text or "").strip()
    if len(stripped) < 80:
        return True
    lowered = stripped.lower()
    return "<script" in lowered and len(_strip_tags(stripped)) < 80


def _strip_tags(text: str) -> str:
    import re

    return re.sub(r"<[^>]+>", " ", text)


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
