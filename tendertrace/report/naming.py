from __future__ import annotations

from datetime import datetime
import hashlib
import re


_ILLEGAL = re.compile(r'[\\/:*?"<>|\r\n]+')


def safe_report_filename(query: str, now: datetime, *, max_stem_length: int = 120) -> str:
    clean = _ILLEGAL.sub("_", query).strip(" ._") or "招投标信息汇总"
    stamp = now.strftime("%Y%m%d%H%M")
    suffix = f"_{stamp}.docx"
    if len(clean) + len(suffix) > max_stem_length:
        digest = hashlib.sha1(query.encode("utf-8")).hexdigest()[:6]
        keep = max_stem_length - len(suffix) - len(digest) - 1
        clean = f"{clean[:keep]}_{digest}"
    return f"{clean}{suffix}"

