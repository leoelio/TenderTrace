from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from urllib.parse import urljoin, urlsplit

from selectolax.parser import HTMLParser

from tendertrace.pipeline.dedup import canonicalize_url


ATTACHMENT_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar")


@dataclass(frozen=True)
class DiscoveredLink:
    url: str
    text: str
    kind: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class LinkExtractor:
    allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()
    domains: tuple[str, ...] = ()
    extensions: tuple[str, ...] = ATTACHMENT_EXTENSIONS
    same_domain: bool = True

    def extract(self, html: str, base_url: str) -> list[DiscoveredLink]:
        parser = HTMLParser(html)
        base_host = urlsplit(base_url).netloc.lower()
        seen: set[str] = set()
        links: list[DiscoveredLink] = []
        for anchor in parser.css("a"):
            href = (anchor.attributes.get("href") or "").strip()
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue
            absolute = canonicalize_url(urljoin(base_url, href))
            if not _allowed_domain(absolute, base_host, self.domains, self.same_domain):
                continue
            if self.allow and not any(
                re.search(pattern, absolute, flags=re.I) for pattern in self.allow
            ):
                continue
            if self.deny and any(re.search(pattern, absolute, flags=re.I) for pattern in self.deny):
                continue
            if absolute in seen:
                continue
            seen.add(absolute)
            text = _clean_text(anchor.text())
            links.append(
                DiscoveredLink(url=absolute, text=text, kind=_kind(absolute, self.extensions))
            )
        return links


def _allowed_domain(url: str, base_host: str, domains: tuple[str, ...], same_domain: bool) -> bool:
    host = urlsplit(url).netloc.lower()
    if domains:
        return any(host == domain or host.endswith(f".{domain}") for domain in domains)
    if same_domain:
        return host == base_host
    return True


def _kind(url: str, extensions: tuple[str, ...]) -> str:
    path = urlsplit(url).path.lower()
    if any(path.endswith(ext) for ext in extensions):
        return "attachment"
    return "detail"


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()
