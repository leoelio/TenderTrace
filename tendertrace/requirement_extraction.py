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
    "scoring": re.compile(r"(?:(?:评分|评审).{0,100}(?:分|权重|满分)|(?:占|得|扣|满分)\s*\d+(?:\.\d+)?\s*分)", re.I),
    "disqualification": re.compile(r"(?:废标|无效投标|无效响应|否决投标|不予受理|不得提供虚假|不接受联合体|不允许合同转让)", re.I),
    "attachment": re.compile(r"(?:(?:投标文件|响应文件|申请文件).{0,120}(?:(?:须|应当|应).{0,80}(?:提供|附)|详见附件)|(?:须|应当|应)?提供.{0,60}(?:投标文件|响应文件|申请文件)|(?:上传|递交|提交)(?!投标文件截止).{0,60}(?:投标文件|响应文件|申请文件)|(?:授权委托书|声明函|承诺函).{0,80}(?:须|应当|应).{0,80}(?:包含|提供|加盖)|(?:提供|附).{0,80}(?:证书|许可证|注册证|备案凭证|检测报告|合同复印件|证明材料))", re.I),
    "technical": re.compile(r"(?:技术参数|技术要求|功能要求|性能指标).{0,120}(?:须|应当|应|不低于|支持)", re.I),
    "commercial": re.compile(r"(?:报价|付款|质保|交付|服务期|合同).{0,120}(?:须|应当|应|不得|不超过)", re.I),
}

TYPE_PREFIXES = {
    "qualification": "QUAL",
    "deadline": "DEADLINE",
    "scoring": "SCORE",
    "disqualification": "DISQ",
    "attachment": "ATTACH",
    "technical": "TECH",
    "commercial": "COMM",
}


def extract_and_save_requirements(settings: Settings, notice_id: str) -> dict[str, object]:
    init_db(settings)
    sources = _requirement_sources(settings, notice_id)
    if not sources:
        with connection(settings) as conn:
            exists = conn.execute("SELECT 1 FROM notices WHERE id = ?", (notice_id,)).fetchone()
        if exists is None:
            raise LookupError("opportunity notice not found")
        return {
            "status": "needs_manual_input",
            "candidate_count": 0,
            "created_or_updated_count": 0,
            "preserved_count": 0,
            "fallback": "ocr_or_manual_required",
            "message": "公告或附件没有可可靠读取的文本，请先执行 OCR 或人工录入；系统未生成虚假要求。",
        }
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
            "superseded",
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
            weight=candidate["weight"],
            status="pending",
            source_revision_id=candidate["source_revision_id"],
            extraction_mode="rules",
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
    with connection(settings) as conn:
        revision = conn.execute(
            "SELECT id FROM notice_revisions WHERE notice_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (notice_id,),
        ).fetchone()
    source_revision_id = str(revision["id"] or "") if revision else "source-baseline"
    sources = [
        {
            "text": " ".join(
                part for part in (str(row["content_text"] or ""), str(row["core_content"] or "")) if part
            ),
            "source_url": str(row["source_url"] or ""),
            "source_locator": "公告正文片段",
            "source_revision_id": source_revision_id,
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
                        "source_revision_id": str(snapshot.get("revision_id") or source_revision_id),
                    }
                )
    return [source for source in sources if source["text"] and source["source_url"]]


def _candidates(sources: list[dict[str, str]]) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    seen: set[str] = set()
    for source in sources:
        for sentence_index, sentence in enumerate(_sentences(source["text"]), start=1):
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
                        "source_locator": f"{source['source_locator']} · 第{sentence_index}条",
                        "source_revision_id": source.get("source_revision_id", "source-baseline"),
                        "mandatory": _is_mandatory(requirement_type, sentence),
                        "confidence": _confidence(requirement_type),
                        "weight": _weight(sentence),
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
    return {
        "deadline": 92,
        "disqualification": 88,
        "qualification": 82,
        "scoring": 80,
        "attachment": 80,
        "technical": 76,
        "commercial": 76,
    }[requirement_type]


def _weight(sentence: str) -> float:
    match = re.search(r"(?:满分|分值|权重|计)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*(?:分|%)", sentence)
    return min(float(match.group(1)), 100) if match else 0
