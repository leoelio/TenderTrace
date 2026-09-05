from __future__ import annotations

from dataclasses import asdict, dataclass
import re

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
) -> SummaryResult:
    """Produce a fact-gated summary for one notice.

    The model may only *polish* the extractive base; every 2+ digit sequence in its
    output must also appear in the source text. Any missing digit (amount, date or
    project number the model introduced) makes the result fall back to the extractive
    base, so a hallucinated number never reaches a report.
    """
    base = _extractive_summary(content_text, core_content)
    source_text = " ".join(part for part in (title, content_text, core_content) if part)
    model_gateway = gateway or ModelGateway(settings)
    result = model_gateway.generate_json(
        system=_SYSTEM_PROMPT,
        user=_prompt(title, content_text, core_content),
    )
    if run_id:
        record_model_audit(settings, run_id=run_id, result=result, prompt_text=_prompt(title, content_text, core_content))

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
        )

    key_facts_raw = result.parsed.get("key_facts")
    if isinstance(key_facts_raw, list):
        key_facts = tuple(str(item).strip() for item in key_facts_raw if str(item).strip())
    else:
        key_facts = ()
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


def _prompt(title: str, content_text: str, core_content: str) -> str:
    return (
        f"标题：{_clean_spaces(title)}\n"
        f"正文：{_clean_spaces(content_text)[:2000]}\n"
        f"抽取式摘要：{_clean_spaces(core_content)[:600]}"
    )


_SYSTEM_PROMPT = """You condense a Chinese procurement notice into a factual summary.
Return one strict JSON object only:
{"summary":"","key_facts":[]}
Rules:
- summary is 1-3 sentences covering project, purchaser, budget, deadline and scope.
- Preserve every amount, date and project number EXACTLY as written (do not round, convert or guess).
- Only state what the source text supports; if a fact is absent, omit it.
- Do not include URLs, markdown or explanations outside the JSON.
"""
