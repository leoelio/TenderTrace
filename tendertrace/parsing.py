from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from selectolax.parser import HTMLParser


@dataclass(frozen=True)
class ContentSelection:
    text: str
    selector: str
    fallback_used: bool


def select_main_content(
    parser: HTMLParser,
    selectors: Iterable[str],
    *,
    min_chars: int = 40,
) -> ContentSelection:
    for selector in selectors:
        node = parser.css_first(selector)
        if node is None:
            continue
        text = _node_text(node)
        if len(text) >= min_chars:
            return ContentSelection(text=text, selector=selector, fallback_used=False)
    return _largest_text_block(parser)


def _largest_text_block(parser: HTMLParser) -> ContentSelection:
    best_text = ""
    best_selector = "fallback:body"
    for selector in ("article", "main", "section", "div", "td"):
        for node in parser.css(selector):
            text = _node_text(node)
            if len(text) > len(best_text):
                best_text = text
                best_selector = f"fallback:{selector}"
    if best_text:
        return ContentSelection(text=best_text, selector=best_selector, fallback_used=True)
    return ContentSelection(
        text=_clean_spaces(parser.text(separator=" ")),
        selector="fallback:document",
        fallback_used=True,
    )


def _node_text(node) -> str:
    for bad in node.css("script,style,noscript,nav,header,footer"):
        bad.decompose()
    return _clean_spaces(node.text(separator=" "))


def _clean_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()
