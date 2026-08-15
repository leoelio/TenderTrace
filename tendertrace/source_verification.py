from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import re
import socket
import time

import httpx
from selectolax.parser import HTMLParser

from tendertrace.parsing import select_main_content
from tendertrace.public_http import Resolver, UnsafeUrlError, fetch_public_bytes


@dataclass(frozen=True)
class SourceVerification:
    status: str
    source_url: str
    final_url: str = ""
    status_code: int = 0
    content_type: str = ""
    snapshot_sha256: str = ""
    text_excerpt: str = ""
    selector: str = ""
    fetched_bytes: int = 0
    elapsed_ms: int = 0
    error: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def verify_source_url(
    url: str,
    *,
    max_bytes: int = 1_500_000,
    timeout: float = 10.0,
    resolver: Resolver = socket.getaddrinfo,
    http_client_factory=httpx.Client,
) -> SourceVerification:
    started = time.monotonic()
    try:
        fetched = fetch_public_bytes(
            url,
            max_bytes=max_bytes,
            timeout=timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/126 Safari/537.36"
                )
            },
            resolver=resolver,
            http_client_factory=http_client_factory,
        )
    except UnsafeUrlError:
        raise
    except Exception as exc:
        return SourceVerification(
            status="failed",
            source_url=url,
            elapsed_ms=_elapsed_ms(started),
            error=f"{type(exc).__name__}: {exc}",
        )
    text, selector = _extract_text(fetched.data, fetched.content_type)
    return SourceVerification(
        status="verified" if len(text) >= 20 else "reachable",
        source_url=url,
        final_url=fetched.final_url,
        status_code=fetched.status_code,
        content_type=fetched.content_type,
        snapshot_sha256=hashlib.sha256(fetched.data).hexdigest(),
        text_excerpt=text[:5000],
        selector=selector,
        fetched_bytes=len(fetched.data),
        elapsed_ms=_elapsed_ms(started),
    )


def _extract_text(data: bytes, content_type: str) -> tuple[str, str]:
    lowered = content_type.casefold()
    if "html" not in lowered and "text/" not in lowered:
        return "", ""
    text = data.decode(_charset(content_type), errors="replace")
    if "html" not in lowered:
        return _clean_text(text), "text-response"
    parser = HTMLParser(text)
    selected = select_main_content(
        parser,
        ("article", "main", "#content", ".content", ".article-content", ".detail"),
    )
    return selected.text, selected.selector


def _charset(content_type: str) -> str:
    match = re.search(r"charset=([A-Za-z0-9._-]+)", content_type, flags=re.IGNORECASE)
    return match.group(1) if match else "utf-8"


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
