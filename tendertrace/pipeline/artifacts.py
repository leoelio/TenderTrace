from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import re

from tendertrace.fetching import FetchResult


@dataclass(frozen=True)
class PageArtifact:
    source_site: str
    source_url: str
    final_url: str
    status_code: int
    fetcher: str
    content_sha256: str
    content_length: int
    text_excerpt: str
    blocked: bool
    error: str
    fetched_at: str
    elapsed_ms: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def page_artifact_from_fetch(source_site: str, result: FetchResult) -> dict[str, object]:
    text = result.text or ""
    return PageArtifact(
        source_site=source_site,
        source_url=result.url,
        final_url=result.final_url,
        status_code=result.status_code,
        fetcher=result.fetcher,
        content_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest() if text else "",
        content_length=len(text),
        text_excerpt=_clean_excerpt(text),
        blocked=result.blocked,
        error=result.error,
        fetched_at=result.fetched_at,
        elapsed_ms=result.elapsed_ms,
    ).to_dict()


def _clean_excerpt(html_or_text: str, *, limit: int = 600) -> str:
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", html_or_text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
    return text[:limit]
