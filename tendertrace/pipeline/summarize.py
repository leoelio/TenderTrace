from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Iterable

from tendertrace.config import Settings
from tendertrace.llm.audit import record_model_audit
from tendertrace.llm.gateway import ModelGateway

_DIGIT_RE = re.compile(r"\d{2,}")


@dataclass(frozen=True)
class SummaryResult:
    summary: str
    source: str  # "extractive" | "model"
    fact_check_passed: bool
    checked_digits: tuple[str, ...]
    missing_digits: tuple[str, ...]
    key_facts: tuple[str, ...]
    model_status: str
    model_provider: str
    model_name: str
    factual_spans: tuple[dict[str, object], ...]
    semantic_grounding_score: float
    rejection_reason: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def summarize_notice_with_model(
    settings: Settings,
    *,
    title: str,
    content_text: str,
    core_content: str,
    gateway: ModelGateway | None = None,
    run_id: str | None = None,
    factual_spans: Iterable[dict[str, object]] | None = None,
) -> SummaryResult:
    """Produce a fact-gated summary for one notice.

    The model may only polish the extractive base. Its numeric claims and textual
    claims must both be grounded in source evidence; otherwise the extractive base
    is retained and the rejected model output is kept only in the audit trail.
    """
    base = _extractive_summary(content_text, core_content)
    source_text = " ".join(part for part in (title, content_text, core_content) if part)
    allowed_spans = _normalized_spans(factual_spans)
    model_gateway = gateway or ModelGateway(settings)
    result = model_gateway.generate_json(
        system=_SYSTEM_PROMPT,
        user=_prompt(title, content_text, core_content, allowed_spans),
    )
    if run_id:
        record_model_audit(
            settings,
            run_id=run_id,
            result=result,
            prompt_text=_prompt(title, content_text, core_content, allowed_spans),
        )

    if result.status != "ok" or not isinstance(result.parsed, dict):
        return SummaryResult(
            summary=base,
            source="extractive",
            fact_check_passed=True,
            checked_digits=(),
            missing_digits=(),
            key_facts=(),
            model_status=result.status,
            model_provider=result.provider,
            model_name=result.model,
            factual_spans=allowed_spans,
            semantic_grounding_score=1.0,
            rejection_reason="",
        )

    summary = str(result.parsed.get("summary") or "").strip()
    if not summary:
        return SummaryResult(
            summary=base,
            source="extractive",
            fact_check_passed=True,
            checked_digits=(),
            missing_digits=(),
            key_facts=(),
            model_status=result.status,
            model_provider=result.provider,
            model_name=result.model,
            factual_spans=allowed_spans,
            semantic_grounding_score=1.0,
            rejection_reason="empty_model_summary",
        )

    summary_digits = _digits(summary)
    source_digits = _digits(source_text)
    missing = tuple(digit for digit in summary_digits if digit not in source_digits)
    if missing:
        return SummaryResult(
            summary=base,
            source="extractive",
            fact_check_passed=False,
            checked_digits=summary_digits,
            missing_digits=missing,
            key_facts=(),
            model_status=result.status,
            model_provider=result.provider,
            model_name=result.model,
            factual_spans=allowed_spans,
            semantic_grounding_score=0.0,
            rejection_reason="unsupported_number",
        )

    key_facts_raw = result.parsed.get("key_facts")
    if isinstance(key_facts_raw, list):
        key_facts = tuple(str(item).strip() for item in key_facts_raw if str(item).strip())
    else:
        key_facts = ()
    grounding_score = _grounding_score(summary, source_text)
    unsupported_key_facts = tuple(
        item for item in key_facts if _grounding_score(item, source_text) < _MIN_GROUNDING_SCORE
    )
    if grounding_score < _MIN_GROUNDING_SCORE or unsupported_key_facts:
        return SummaryResult(
            summary=base,
            source="extractive",
            fact_check_passed=False,
            checked_digits=summary_digits,
            missing_digits=(),
            key_facts=(),
            model_status=result.status,
            model_provider=result.provider,
            model_name=result.model,
            factual_spans=allowed_spans,
            semantic_grounding_score=grounding_score,
            rejection_reason="unsupported_claim" if grounding_score < _MIN_GROUNDING_SCORE else "unsupported_key_fact",
        )
    return SummaryResult(
        summary=summary[:1200],
        source="model",
        fact_check_passed=True,
        checked_digits=summary_digits,
        missing_digits=(),
        key_facts=key_facts[:8],
        model_status=result.status,
        model_provider=result.provider,
        model_name=result.model,
        factual_spans=allowed_spans,
        semantic_grounding_score=grounding_score,
        rejection_reason="",
    )


def _extractive_summary(content_text: str, core_content: str) -> str:
    for value in (core_content, content_text):
        cleaned = _clean_spaces(value)
        if cleaned:
            return cleaned[:600]
    return "详情页正文暂未抽取到可用内容。"


def _digits(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_DIGIT_RE.findall(text or "")))


def _clean_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _prompt(
    title: str,
    content_text: str,
    core_content: str,
    factual_spans: tuple[dict[str, object], ...],
) -> str:
    anchors = "\n".join(
        f"- {span['kind']}: {span['value']}"
        for span in factual_spans[:16]
    ) or "- 无（不要补充缺失事实）"
    return (
        f"标题：{_clean_spaces(title)}\n"
        f"正文：{_clean_spaces(content_text)[:2000]}\n"
        f"抽取式摘要：{_clean_spaces(core_content)[:600]}\n"
        f"可引用事实锚点：\n{anchors}"
    )


_MIN_GROUNDING_SCORE = 0.78


def _normalized_spans(items: Iterable[dict[str, object]] | None) -> tuple[dict[str, object], ...]:
    values: list[dict[str, object]] = []
    for item in items or ():
        value = str(item.get("value") or "").strip()
        kind = str(item.get("kind") or "fact").strip()
        if value:
            values.append({"kind": kind, "value": value})
    return tuple(values[:32])


def _grounding_score(claim: str, source: str) -> float:
    claim_tokens = set(_grounding_tokens(claim))
    if not claim_tokens:
        return 1.0
    source_tokens = set(_grounding_tokens(source))
    return round(len(claim_tokens & source_tokens) / len(claim_tokens), 3)


def _grounding_tokens(value: str) -> list[str]:
    lowered = _clean_spaces(value).lower()
    ascii_tokens = re.findall(r"[a-z0-9][a-z0-9._/-]{1,}", lowered)
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", lowered))
    chinese_tokens = [chinese[index : index + 2] for index in range(max(0, len(chinese) - 1))]
    return ascii_tokens + (chinese_tokens or ([chinese] if chinese else []))


_SYSTEM_PROMPT = """You condense a Chinese procurement notice into a factual summary.
Return one strict JSON object only:
{"summary":"","key_facts":[]}
Rules:
- summary is 1-3 sentences covering project, purchaser, budget, deadline and scope.
- Preserve every amount, date and project number EXACTLY as written (do not round, convert or guess).
- Only state what the source text supports; if a fact is absent, omit it.
- Do not include URLs, markdown or explanations outside the JSON.
"""
