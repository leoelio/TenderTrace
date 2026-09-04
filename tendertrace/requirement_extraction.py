from __future__ import annotations

import hashlib
import json
import re

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.opportunity_requirements import list_requirements, upsert_requirement


TYPE_PATTERNS = {
    "qualification": re.compile(r"(?:投标人|供应商).{0,100}(?:须|应当|应|具有|资格)", re.I),
    "deadline": re.compile(r"(?:投标.*截止|递交.*截止|提交.*截止|响应文件.*截止)", re.I),
    "scoring": re.compile(r"(?:评分|评审).{0,100}(?:分|权重|满分)", re.I),
    "disqualification": re.compile(r"(?:废标|无效投标|否决投标|不予受理|不得提供虚假)", re.I),
    "attachment": re.compile(r"(?:投标文件|响应文件|申请文件).{0,100}(?:须|应当|应).{0,100}(?:提供|附)", re.I),
}

TYPE_PREFIXES = {
    "qualification": "QUAL",
    "deadline": "DEADLINE",
    "scoring": "SCORE",
    "disqualification": "DISQ",
    "attachment": "ATTACH",
}


def extract_and_save_requirements(settings: Settings, notice_id: str) -> dict[str, object]:
    init_db(settings)
    sources = _requirement_sources(settings, notice_id)
    if not sources:
        raise LookupError("opportunity notice not found")
    candidates = _candidates(sources)
    existing = {item.requirement_key: item for item in list_requirements(settings, notice_id)}
    created_or_updated_count = 0
    preserved_count = 0
    for candidate in candidates:
        previous = existing.get(candidate["requirement_key"])
        if previous is not None and previous.status in {
            "confirmed",
            "assigned",
            "in_progress",
            "review",
            "completed",
        }:
            preserved_count += 1
            continue
        upsert_requirement(
            settings,
            notice_id=notice_id,
            requirement_key=candidate["requirement_key"],
            requirement_type=candidate["requirement_type"],
            title=candidate["title"],
            evidence_text=candidate["evidence_text"],
            source_url=candidate["source_url"],
            source_locator=candidate["source_locator"],
            mandatory=candidate["mandatory"],
            confidence=candidate["confidence"],
            status="pending",
            actor="rules:requirement_extraction",
        )
        created_or_updated_count += 1
    return {
        "status": "finished",
        "candidate_count": len(candidates),
        "created_or_updated_count": created_or_updated_count,
        "preserved_count": preserved_count,
    }


def _requirement_sources(settings: Settings, notice_id: str) -> list[dict[str, str]]:
    with connection(settings) as conn:
        row = conn.execute(
            "SELECT source_url, content_text, core_content, fields_json FROM notices WHERE id = ?",
            (notice_id,),
        ).fetchone()
    if row is None:
        return []
    sources = [
        {
            "text": " ".join(
                part for part in (str(row["content_text"] or ""), str(row["core_content"] or "")) if part
            ),
            "source_url": str(row["source_url"] or ""),
            "source_locator": "公告正文片段",
        }
    ]
    try:
        fields = json.loads(str(row["fields_json"] or "{}"))
    except json.JSONDecodeError:
        fields = {}
    snapshots = fields.get("attachment_snapshots") if isinstance(fields, dict) else []
    if isinstance(snapshots, list):
        for snapshot in snapshots:
            if not isinstance(snapshot, dict):
                continue
            excerpt = str(snapshot.get("text_excerpt") or "").strip()
            source_url = str(snapshot.get("url") or row["source_url"] or "").strip()
            name = str(snapshot.get("name") or "附件").strip()
            if excerpt and source_url:
                sources.append(
                    {
                        "text": excerpt,
                        "source_url": source_url,
                        "source_locator": f"附件：{name} 文本摘要",
                    }
                )
    return [source for source in sources if source["text"] and source["source_url"]]


def _candidates(sources: list[dict[str, str]]) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    seen: set[str] = set()
    for source in sources:
        for sentence in _sentences(source["text"]):
            for requirement_type, pattern in TYPE_PATTERNS.items():
                if not pattern.search(sentence):
                    continue
                key = _requirement_key(requirement_type, source["source_url"], sentence)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(
                    {
                        "requirement_key": key,
                        "requirement_type": requirement_type,
                        "title": _title(sentence),
                        "evidence_text": sentence,
                        "source_url": source["source_url"],
                        "source_locator": source["source_locator"],
                        "mandatory": _is_mandatory(requirement_type, sentence),
                        "confidence": _confidence(requirement_type),
                    }
                )
    return candidates[:40]


def _sentences(text: str) -> list[str]:
    return [
        _clean(sentence)
        for sentence in re.split(r"[。；;\n]+", text)
        if len(_clean(sentence)) >= 6
    ]


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" ，,。；;")


def _requirement_key(requirement_type: str, source_url: str, sentence: str) -> str:
    digest = hashlib.sha256(f"{requirement_type}|{source_url}|{sentence}".encode("utf-8")).hexdigest()
    return f"{TYPE_PREFIXES[requirement_type]}-{digest[:8].upper()}"


def _title(sentence: str) -> str:
    return sentence if len(sentence) <= 120 else f"{sentence[:117]}..."


def _is_mandatory(requirement_type: str, sentence: str) -> bool:
    return requirement_type in {"deadline", "disqualification"} or bool(
        re.search(r"(?:必须|须|应当|不得|否则)", sentence)
    )


def _confidence(requirement_type: str) -> int:
    return {"deadline": 92, "disqualification": 88, "qualification": 82, "scoring": 80, "attachment": 80}[requirement_type]
