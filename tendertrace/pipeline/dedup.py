from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from tendertrace.adapters.ccgp import Attachment, Notice


TRACKING_QUERY_KEYS = {
    "from",
    "spm",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}

TITLE_SUFFIXES = (
    "公开招标公告",
    "竞争性磋商公告",
    "竞争性谈判公告",
    "询价公告",
    "采购公告",
    "招标公告",
    "中标公告",
    "成交公告",
    "结果公告",
    "更正公告",
)

NOISE_PATTERNS = (
    r"打印本页",
    r"关闭窗口",
    r"返回顶部",
    r"分享到：?.*",
    r"友情提示[:：].*",
    r"温馨提示[:：].*",
    r"免责声明[:：].*",
    r"版权(?:所有)?[:：].*",
)

PROJECT_NO_PATTERNS = (
    r"(?:项目编号|项目代码|招标编号|采购编号|项目号|采购计划编号)\s*[:：]\s*([A-Za-z0-9][A-Za-z0-9\-_/（）()第号\.]{3,80})",
    r"(?:编号)\s*[:：]\s*([A-Za-z0-9][A-Za-z0-9\-_/（）()第号\.]{3,80})",
)


@dataclass(frozen=True)
class DedupResult:
    notices: list[Notice]
    clusters: list[dict[str, object]]
    stats: dict[str, object]


def canonicalize_url(value: str) -> str:
    if not value:
        return ""
    parsed = urlsplit(value.strip())
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    query = [
        (key, val)
        for key, val in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS and not key.lower().startswith("utm_")
    ]
    return urlunsplit((scheme, netloc, parsed.path or "/", urlencode(sorted(query)), ""))


def clean_text(value: str) -> str:
    if not value:
        return ""
    text = value.replace("\xa0", " ")
    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_title(value: str) -> str:
    text = clean_text(value)
    for suffix in TITLE_SUFFIXES:
        text = text.replace(suffix, "")
    text = re.sub(r"[【】\[\]（）()《》<>「」『』,，.。:：;；!！?？\s_\-]+", "", text)
    return text.lower()


def extract_project_no(text: str) -> str:
    cleaned = clean_text(text)
    for pattern in PROJECT_NO_PATTERNS:
        match = re.search(pattern, cleaned)
        if not match:
            continue
        value = match.group(1)
        value = re.split(r"[\s,，。；;、]+", value, maxsplit=1)[0]
        return value.strip("：:，,。；;")
    return ""


def simhash64(text: str) -> str:
    tokens = _tokens(text)
    if not tokens:
        return "0" * 16
    weights = [0] * 64
    for token in tokens:
        digest = int(hashlib.sha1(token.encode("utf-8")).hexdigest()[:16], 16)
        for bit in range(64):
            weights[bit] += 1 if digest & (1 << bit) else -1
    value = 0
    for bit, weight in enumerate(weights):
        if weight > 0:
            value |= 1 << bit
    return f"{value:016x}"


def hamming_distance(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def title_similarity(left: str, right: str) -> float:
    left_tokens = set(_char_bigrams(left))
    right_tokens = set(_char_bigrams(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def clean_and_cluster_notices(notices: list[Notice]) -> DedupResult:
    cleaned = [_prepare_notice(notice) for notice in notices]
    clusters: list[list[Notice]] = []
    for notice in cleaned:
        for cluster in clusters:
            if any(_same_cluster(notice, existing) for existing in cluster):
                cluster.append(notice)
                break
        else:
            clusters.append([notice])

    merged = [_merge_cluster(cluster) for cluster in clusters]
    cluster_dicts = [_cluster_summary(notice) for notice in merged]
    return DedupResult(
        notices=merged,
        clusters=cluster_dicts,
        stats={
            "raw_count": len(notices),
            "cleaned_count": len(cleaned),
            "cluster_count": len(merged),
            "duplicates_removed": len(cleaned) - len(merged),
        },
    )


def _prepare_notice(notice: Notice) -> Notice:
    content = clean_text(notice.content_text)
    core = clean_text(notice.core_content)
    full_text = " ".join(part for part in (notice.title, content, core) if part)
    fields = {
        **notice.fields,
        "canonical_url": canonicalize_url(notice.source_url),
        "title_norm": normalize_title(notice.title),
        "project_no": extract_project_no(full_text),
        "simhash64": simhash64(full_text),
    }
    fields.setdefault("cluster_key", f"{notice.source_site}:{notice.id}")
    return Notice(
        id=notice.id,
        source_site=notice.source_site,
        title=clean_text(notice.title),
        publish_time=notice.publish_time,
        region=clean_text(notice.region),
        purchaser=clean_text(notice.purchaser),
        source_url=notice.source_url,
        content_text=content,
        core_content=core,
        attachments=notice.attachments,
        fields=fields,
    )


def _same_cluster(left: Notice, right: Notice) -> bool:
    left_project = str(left.fields.get("project_no") or "")
    right_project = str(right.fields.get("project_no") or "")
    if left_project and right_project and left_project == right_project:
        return True
    if left.fields.get("canonical_url") and left.fields.get("canonical_url") == right.fields.get("canonical_url"):
        return True
    left_title = str(left.fields.get("title_norm") or "")
    right_title = str(right.fields.get("title_norm") or "")
    if left_title and left_title == right_title and _publish_date(left) == _publish_date(right):
        return True
    if _publish_date(left) != _publish_date(right):
        return False
    if title_similarity(left_title, right_title) < 0.86:
        return False
    return hamming_distance(str(left.fields["simhash64"]), str(right.fields["simhash64"])) <= 10


def _merge_cluster(cluster: list[Notice]) -> Notice:
    primary = max(cluster, key=lambda item: len(item.content_text) + len(item.core_content))
    attachments = _merge_attachments(cluster)
    source_sites = sorted({item.source_site for item in cluster})
    related_sources = [
        {
            "source_site": item.source_site,
            "source_url": item.source_url,
            "title": item.title,
            "publish_time": item.publish_time,
        }
        for item in cluster
    ]
    fields = {
        **primary.fields,
        "cluster_key": _cluster_key(cluster),
        "duplicate_count": len(cluster),
        "source_sites": source_sites,
        "related_sources": related_sources,
    }
    return Notice(
        id=primary.id,
        source_site=primary.source_site,
        title=primary.title,
        publish_time=primary.publish_time,
        region=primary.region,
        purchaser=primary.purchaser,
        source_url=primary.source_url,
        content_text=primary.content_text,
        core_content=primary.core_content,
        attachments=attachments,
        fields=fields,
    )


def _cluster_key(cluster: list[Notice]) -> str:
    projects = [str(item.fields.get("project_no") or "") for item in cluster]
    project = next((item for item in projects if item), "")
    if project and len(cluster) > 1:
        return f"project:{project.lower()}"
    if len(cluster) > 1:
        title = str(cluster[0].fields.get("title_norm") or "")
        date = _publish_date(cluster[0])
        return f"title:{_sha1_short(title + ':' + date)}"
    return str(cluster[0].fields.get("cluster_key") or f"{cluster[0].source_site}:{cluster[0].id}")


def _cluster_summary(notice: Notice) -> dict[str, object]:
    return {
        "cluster_key": notice.fields.get("cluster_key"),
        "title_norm": notice.fields.get("title_norm"),
        "project_no": notice.fields.get("project_no"),
        "simhash64": notice.fields.get("simhash64"),
        "source_sites": notice.fields.get("source_sites", [notice.source_site]),
        "duplicate_count": notice.fields.get("duplicate_count", 1),
    }


def _merge_attachments(cluster: list[Notice]) -> list[Attachment]:
    seen: set[str] = set()
    merged: list[Attachment] = []
    for notice in cluster:
        for attachment in notice.attachments:
            key = canonicalize_url(attachment.url)
            if key in seen:
                continue
            seen.add(key)
            merged.append(attachment)
    return merged


def _tokens(text: str) -> list[str]:
    lowered = text.lower()
    alnum = re.findall(r"[a-z0-9]{2,}", lowered)
    chinese = re.findall(r"[\u4e00-\u9fff]", text)
    return alnum + _char_bigrams("".join(chinese))


def _char_bigrams(value: str) -> list[str]:
    if len(value) < 2:
        return [value] if value else []
    return [value[index : index + 2] for index in range(len(value) - 1)]


def _publish_date(notice: Notice) -> str:
    return notice.publish_time[:10]


def _sha1_short(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]
