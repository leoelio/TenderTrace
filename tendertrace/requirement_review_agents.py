from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.llm.audit import record_model_audit
from tendertrace.llm.gateway import ModelCallResult, ModelGateway, model_status
from tendertrace.opportunity_requirements import OpportunityRequirement, list_requirements
from tendertrace.requirement_review_board import (
    RequirementReviewCase,
    list_requirement_review_cases,
    sync_requirement_review_cases,
)


AGENT_DECISIONS = ("accept", "reject", "escalate")

AGENT_DECISION_LABELS = {
    "accept": "同意有效",
    "reject": "建议退回",
    "escalate": "建议升级",
}

# Each agent reviews the same evidence-backed requirement from a distinct angle.
# The prompts deliberately ask for evidence-based reasoning: an agent must point
# back to the requirement's source text instead of free-form summarizing.
AGENT_PERSONAS: dict[str, dict[str, str]] = {
    "project_control": {
        "label": "项目统筹审查",
        "focus": (
            "投标截止、交付窗口、资源依赖与推进门禁是否可执行，是否存在会导致项目失控的时序或责任缺口。"
        ),
    },
    "compliance": {
        "label": "合规审查",
        "focus": (
            "资格条件与废标条款是否完整、可执行，是否存在与招标法规冲突或表述不清之处。"
        ),
    },
    "technical": {
        "label": "技术评审",
        "focus": (
            "技术参数、性能、接口、配置与方案要求是否明确、可度量，是否存在含糊或自相矛盾。"
        ),
    },
    "commercial": {
        "label": "商务评审",
        "focus": (
            "评分项、报价、预算与商务条件是否清晰、是否可能影响投标决策或报价策略。"
        ),
    },
    "evidence_audit": {
        "label": "证据审计",
        "focus": (
            "要求标题与结论是否真的被'证据原文'所支持，原文能否定位回招标文件/公告。"
        ),
    },
}


@dataclass(frozen=True)
class ReviewAgentOpinion:
    id: str
    review_id: str
    notice_id: str
    requirement_id: str
    requirement_key: str
    agent_role: str
    agent_label: str
    decision: str
    decision_label: str
    confidence: int
    rationale: str
    concerns: tuple[str, ...]
    model_status: str
    model_provider: str
    model_name: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_review_agents(
    settings: Settings,
    notice_id: str,
    *,
    run_id: str | None = None,
    gateway: ModelGateway | None = None,
    limit: int = 50,
) -> dict[str, object]:
    """Run independent agent personas over pending review cases.

    This is the multi-agent layer on top of the rule-based review board. It never
    resolves a case or rewrites a requirement status: it only records evidence-based
    opinions and an aggregated *suggestion* (with disagreement detection) so a human
    can make the final call. When the model is disabled or unavailable it degrades
    to ``rule_only`` and records no opinions.
    """
    init_db(settings)
    sync_requirement_review_cases(settings, notice_id)
    cases = list_requirement_review_cases(settings, notice_id)
    requirements = {item.id: item for item in list_requirements(settings, notice_id)}
    pending = [case for case in cases if case.status == "pending"][: max(1, min(int(limit), 200))]

    model_gateway = gateway or ModelGateway(settings)
    status = model_status(settings)
    mode = (
        "multi_agent"
        if (settings.model_enhancement_enabled and status.configured and status.mode != "disabled")
        else "rule_only"
    )

    opinion_count = 0
    skipped_count = 0
    failed_count = 0
    for case in pending:
        requirement = requirements.get(case.requirement_id)
        if requirement is None:
            continue
        for agent_role, persona in AGENT_PERSONAS.items():
            opinion, result = _run_agent(
                settings,
                model_gateway,
                case,
                requirement,
                agent_role,
                persona,
                run_id=run_id,
            )
            if opinion is None:
                if result.status == "failed":
                    failed_count += 1
                else:
                    skipped_count += 1
                continue
            _persist_opinion(settings, case, agent_role, opinion)
            opinion_count += 1

    return {
        "status": "finished",
        "mode": mode,
        "scanned_case_count": len(pending),
        "opinion_count": opinion_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
        "suggestions": review_agent_suggestions(settings, notice_id),
    }


def list_review_opinions(settings: Settings, notice_id: str) -> list[ReviewAgentOpinion]:
    init_db(settings)
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT opinion.*, requirement.requirement_key
            FROM requirement_review_opinions opinion
            JOIN opportunity_requirements requirement ON requirement.id = opinion.requirement_id
            WHERE opinion.notice_id = ?
            ORDER BY opinion.review_id, opinion.agent_role
            """,
            (notice_id,),
        ).fetchall()
    return [_from_row(row) for row in rows]


def review_agent_suggestions(settings: Settings, notice_id: str) -> list[dict[str, object]]:
    """Aggregate stored agent opinions into a per-case advisory suggestion."""
    opinions = list_review_opinions(settings, notice_id)
    by_review: dict[str, list[ReviewAgentOpinion]] = {}
    for opinion in opinions:
        by_review.setdefault(opinion.review_id, []).append(opinion)

    suggestions: list[dict[str, object]] = []
    for review_id, items in by_review.items():
        votes = Counter(item.decision for item in items)
        top_decision, _ = votes.most_common(1)[0]
        unanimous = len(set(votes)) == 1 and len(items) >= 2
        if unanimous:
            suggestion = top_decision
            consensus = "unanimous"
        elif len(items) == 1:
            suggestion = top_decision
            consensus = "single"
        else:
            suggestion = "escalate"
            consensus = "split"
        suggestions.append(
            {
                "review_id": review_id,
                "requirement_key": items[0].requirement_key,
                "suggestion": suggestion,
                "suggestion_label": AGENT_DECISION_LABELS.get(suggestion, suggestion),
                "consensus": consensus,
                "disagreement": consensus == "split",
                "votes": dict(votes),
                "opinion_count": len(items),
            }
        )
    return suggestions


def _run_agent(
    settings: Settings,
    gateway: ModelGateway,
    case: RequirementReviewCase,
    requirement: OpportunityRequirement,
    agent_role: str,
    persona: dict[str, str],
    *,
    run_id: str | None,
) -> tuple[dict[str, Any] | None, ModelCallResult]:
    prompt = _prompt_for_case(case, requirement, agent_role, persona)
    result = gateway.generate_json(system=_system_prompt(agent_role, persona), user=prompt)
    if run_id:
        record_model_audit(settings, run_id=run_id, result=result, prompt_text=prompt)
    if result.status != "ok" or not isinstance(result.parsed, dict):
        return None, result
    opinion = _normalize_opinion(result.parsed)
    if opinion is None:
        return None, result
    return {
        **opinion,
        "model_status": result.status,
        "model_provider": result.provider,
        "model_name": result.model,
    }, result


def _normalize_opinion(parsed: dict[str, Any]) -> dict[str, Any] | None:
    decision = str(parsed.get("decision") or "").strip().lower()
    if decision not in AGENT_DECISIONS:
        return None
    confidence = _coerce_confidence(parsed.get("confidence"))
    rationale = str(parsed.get("rationale") or "").strip()
    concerns_raw = parsed.get("concerns")
    if isinstance(concerns_raw, list):
        concerns = tuple(str(item).strip() for item in concerns_raw if str(item).strip())
    else:
        concerns = tuple(str(concerns_raw).strip().splitlines()) if str(concerns_raw or "").strip() else ()
    return {
        "decision": decision,
        "confidence": confidence,
        "rationale": rationale[:1200],
        "concerns": concerns[:8],
    }


def _coerce_confidence(value: object) -> int:
    try:
        confidence = int(round(float(value)))
    except (TypeError, ValueError):
        confidence = 0
    return max(0, min(100, confidence))


def _persist_opinion(
    settings: Settings,
    case: RequirementReviewCase,
    agent_role: str,
    opinion: dict[str, Any],
) -> None:
    opinion_id = _opinion_id(case.id, agent_role)
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO requirement_review_opinions(
                id, review_id, notice_id, requirement_id, agent_role, decision,
                confidence, rationale, concerns_json, model_status, model_provider, model_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(review_id, agent_role) DO UPDATE SET
                decision = excluded.decision,
                confidence = excluded.confidence,
                rationale = excluded.rationale,
                concerns_json = excluded.concerns_json,
                model_status = excluded.model_status,
                model_provider = excluded.model_provider,
                model_name = excluded.model_name,
                updated_at = datetime('now')
            """,
            (
                opinion_id,
                case.id,
                case.notice_id,
                case.requirement_id,
                agent_role,
                opinion["decision"],
                int(opinion["confidence"]),
                opinion["rationale"],
                json.dumps(list(opinion["concerns"]), ensure_ascii=False, sort_keys=True),
                opinion["model_status"],
                opinion["model_provider"],
                opinion["model_name"],
            ),
        )


def _opinion_id(review_id: str, agent_role: str) -> str:
    return hashlib.sha256(f"{review_id}|{agent_role}".encode("utf-8")).hexdigest()[:24]


def _system_prompt(agent_role: str, persona: dict[str, str]) -> str:
    return (
        "You are an independent tender-requirement review agent. "
        "Return one strict JSON object only:\n"
        '{"decision":"accept|reject|escalate","confidence":0,"rationale":"","concerns":[]}\n'
        "Rules:\n"
        "- decision accept means the requirement is valid and clear enough to act on.\n"
        "- decision reject means the requirement is ambiguous, contradictory or unsupported.\n"
        "- decision escalate means the evidence is insufficient for a confident call.\n"
        "- Base every conclusion on the provided evidence text and locator, never on guesswork.\n"
        "- Do not include URLs, markdown or explanations outside the JSON.\n"
        f"- Your review angle: {persona['label']}（{agent_role}）。{persona['focus']}\n"
    )


def _prompt_for_case(
    case: RequirementReviewCase,
    requirement: OpportunityRequirement,
    agent_role: str,
    persona: dict[str, str],
) -> str:
    payload = {
        "agent_role": agent_role,
        "agent_angle": persona["label"],
        "review_reason": case.reason,
        "assigned_reviewer_role": case.reviewer_role,
        "requirement": {
            "requirement_key": requirement.requirement_key,
            "requirement_type": requirement.requirement_type,
            "title": requirement.title,
            "evidence_text": requirement.evidence_text,
            "source_locator": requirement.source_locator,
            "source_url": requirement.source_url,
            "mandatory": requirement.mandatory,
            "confidence": requirement.confidence,
            "status": requirement.status,
        },
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _from_row(row: Any) -> ReviewAgentOpinion:
    decision = str(row["decision"] or "")
    agent_role = str(row["agent_role"])
    try:
        concerns = tuple(json.loads(str(row["concerns_json"] or "[]")))
    except json.JSONDecodeError:
        concerns = ()
    return ReviewAgentOpinion(
        id=str(row["id"]),
        review_id=str(row["review_id"]),
        notice_id=str(row["notice_id"]),
        requirement_id=str(row["requirement_id"]),
        requirement_key=str(row["requirement_key"]),
        agent_role=agent_role,
        agent_label=AGENT_PERSONAS.get(agent_role, {}).get("label", agent_role),
        decision=decision,
        decision_label=AGENT_DECISION_LABELS.get(decision, decision),
        confidence=int(row["confidence"] or 0),
        rationale=str(row["rationale"] or ""),
        concerns=concerns,
        model_status=str(row["model_status"] or ""),
        model_provider=str(row["model_provider"] or ""),
        model_name=str(row["model_name"] or ""),
        created_at=str(row["created_at"] or ""),
        updated_at=str(row["updated_at"] or ""),
    )
