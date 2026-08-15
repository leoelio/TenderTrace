from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import socket
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit

import httpx


class UnsafeUrlError(ValueError):
    pass


Resolver = Callable[..., list[tuple[Any, ...]]]


@dataclass(frozen=True)
class PublicFetchResult:
    url: str
    final_url: str
    status_code: int
    content_type: str
    data: bytes


def ensure_public_http_url(
    url: str,
    *,
    resolve: bool = True,
    resolver: Resolver = socket.getaddrinfo,
) -> str:
    value = str(url or "").strip()
    try:
        parsed = urlsplit(value)
        port = parsed.port or (443 if parsed.scheme.casefold() == "https" else 80)
    except ValueError as exc:
        raise UnsafeUrlError("URL has an invalid port or authority") from exc
    if parsed.scheme.casefold() not in {"http", "https"}:
        raise UnsafeUrlError("only HTTP and HTTPS URLs are allowed")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("URLs containing credentials are not allowed")
    hostname = (parsed.hostname or "").rstrip(".").casefold()
    if not hostname:
        raise UnsafeUrlError("URL hostname is required")
    if hostname == "localhost" or hostname.endswith(
        (".localhost", ".local", ".internal", ".home.arpa")
    ):
        raise UnsafeUrlError("local network hostnames are not allowed")
    direct_ip = _ip_address(hostname)
    if direct_ip is not None:
        _require_global_ip(direct_ip)
        return value
    if not resolve:
        return value
    try:
        addresses = resolver(hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise UnsafeUrlError(f"hostname cannot be resolved: {hostname}") from exc
    resolved_ips = {
        _ip_address(str(address[4][0]))
        for address in addresses
        if len(address) > 4 and address[4]
    }
    resolved_ips.discard(None)
    if not resolved_ips:
        raise UnsafeUrlError(f"hostname has no usable address: {hostname}")
    for address in resolved_ips:
        _require_global_ip(address)
    return value


def fetch_public_bytes(
    url: str,
    *,
    max_bytes: int,
    timeout: float = 8.0,
    max_redirects: int = 5,
    headers: dict[str, str] | None = None,
    resolver: Resolver = socket.getaddrinfo,
    http_client_factory=httpx.Client,
) -> PublicFetchResult:
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    original_url = ensure_public_http_url(url, resolver=resolver)
    current_url = original_url
    with http_client_factory(
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,
        headers=headers or {},
    ) as client:
        for redirect_count in range(max_redirects + 1):
            ensure_public_http_url(current_url, resolver=resolver)
            with client.stream("GET", current_url) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        response.raise_for_status()
                    if redirect_count >= max_redirects:
                        raise httpx.TooManyRedirects(
                            "public fetch exceeded redirect limit",
                            request=response.request,
                        )
                    current_url = ensure_public_http_url(
                        urljoin(str(response.url), location),
                        resolver=resolver,
                    )
                    continue
                response.raise_for_status()
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > max_bytes:
                    raise ValueError(f"response exceeds {max_bytes} bytes")
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError(f"response exceeds {max_bytes} bytes")
                    chunks.append(chunk)
                return PublicFetchResult(
                    url=original_url,
                    final_url=str(response.url),
                    status_code=response.status_code,
                    content_type=response.headers.get("content-type", ""),
                    data=b"".join(chunks),
                )
    raise RuntimeError("public fetch did not return a response")


def _ip_address(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def _require_global_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    if not address.is_global:
        raise UnsafeUrlError(f"non-public network address is not allowed: {address}")
