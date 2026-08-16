from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from tendertrace.config import Settings
from tendertrace.retrieval import parse_date


@dataclass(frozen=True)
class QualificationPolicy:
    minimum_opportunity_score: int = 65
    minimum_credibility: int = 60
    minimum_completeness: int = 55
    minimum_requirement_coverage: int = 40
    minimum_team_coverage: int = 60
    minimum_stakeholder_coverage: int = 50

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class QualificationGate:
    key: str
    label: str
    status: str
    actual: str
    requirement: str
    blocks: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["blocks"] = list(self.blocks)
        return value


@dataclass(frozen=True)
class QualificationAssessment:
    score: int
    status: str
    recommended_decision: str
    gates: tuple[QualificationGate, ...]
    blockers: dict[str, tuple[str, ...]]
    evaluated_at: str
    policy: QualificationPolicy

    def to_dict(self) -> dict[str, object]:
        return {
            "score": self.score,
            "status": self.status,
            "recommended_decision": self.recommended_decision,
            "gates": [gate.to_dict() for gate in self.gates],
            "blockers": {key: list(values) for key, values in self.blockers.items()},
            "evaluated_at": self.evaluated_at,
            "policy": asdict(self.policy),
        }


def policy_from_settings(settings: Settings) -> QualificationPolicy:
    return QualificationPolicy(
        minimum_opportunity_score=settings.qualification_min_opportunity_score,
        minimum_credibility=settings.qualification_min_credibility,
        minimum_completeness=settings.qualification_min_completeness,
        minimum_requirement_coverage=settings.qualification_min_requirement_coverage,
        minimum_team_coverage=settings.qualification_min_team_coverage,
        minimum_stakeholder_coverage=settings.qualification_min_stakeholder_coverage,
    )


def assess_qualification(
    opportunity: dict[str, Any],
    workflow: dict[str, Any] | None = None,
    *,
    as_of: date | None = None,
    policy: QualificationPolicy | None = None,
) -> QualificationAssessment:
    workflow = workflow or {}
    policy = policy or QualificationPolicy()
    intelligence = _mapping(opportunity.get("intelligence"))
    scores = _mapping(intelligence.get("scores"))
    requirement_review = _mapping(intelligence.get("requirement_review"))
    reference = as_of or date.today()
    deadline = parse_date(str(opportunity.get("bid_deadline") or ""))
    deadline_known = deadline is not None
    deadline_open = bool(deadline and deadline >= reference)
    owner = str(workflow.get("owner_open_id") or workflow.get("owner_name") or "").strip()
    purchaser = str(opportunity.get("purchaser") or "").strip()
    opportunity_score = _score(intelligence.get("score"))
    credibility = _score(scores.get("credibility"))
    completeness = _score(scores.get("completeness"))
    requirement_coverage = _score(requirement_review.get("coverage_score"))
    team = _mapping(opportunity.get("team"))
    team_coverage = _score(team.get("coverage_score")) if team else 100
    stakeholder_map = _mapping(opportunity.get("stakeholder_map"))
    stakeholder_coverage = (
        _score(stakeholder_map.get("coverage_score")) if stakeholder_map else 100
    )
    gates = (
        _gate(
            "owner",
            "机会负责人",
            bool(owner),
            "已认领" if owner else "未认领",
            "进入机会确认前必须明确负责人",
            ("pursue", "approve_bid"),
        ),
        _gate(
            "purchaser",
            "采购主体",
            bool(purchaser),
            purchaser or "未识别",
            "进入机会确认前需识别采购主体",
            ("pursue", "approve_bid"),
        ),
        _gate(
            "credibility",
            "信息可信度",
            credibility >= policy.minimum_credibility,
            f"{credibility}/100",
            f"至少 {policy.minimum_credibility}/100",
            ("approve_bid",),
        ),
        _gate(
            "completeness",
            "信息完整度",
            completeness >= policy.minimum_completeness,
            f"{completeness}/100",
            f"至少 {policy.minimum_completeness}/100",
            ("approve_bid",),
        ),
        _gate(
            "deadline",
            "投标窗口",
            deadline_known and deadline_open,
            deadline.isoformat() if deadline else "未识别",
            "必须识别且尚未截止",
            ("approve_bid",),
        ),
        _gate(
            "opportunity_score",
            "综合机会评分",
            opportunity_score >= policy.minimum_opportunity_score,
            f"{opportunity_score}/100",
            f"至少 {policy.minimum_opportunity_score}/100",
            ("approve_bid",),
        ),
        _gate(
            "requirement_coverage",
            "需求覆盖率",
            requirement_coverage >= policy.minimum_requirement_coverage,
            f"{requirement_coverage}/100",
            f"建议至少 {policy.minimum_requirement_coverage}/100",
            (),
        ),
        _gate(
            "team_coverage",
            "核心团队覆盖",
            team_coverage >= policy.minimum_team_coverage,
            f"{team_coverage}/100",
            f"至少 {policy.minimum_team_coverage}/100",
            ("approve_bid",),
        ),
        _gate(
            "stakeholder_coverage",
            "关键关系覆盖",
            stakeholder_coverage >= policy.minimum_stakeholder_coverage,
            f"{stakeholder_coverage}/100",
            f"至少 {policy.minimum_stakeholder_coverage}/100",
            ("approve_bid",),
        ),
    )
    blockers = {
        action: tuple(gate.label for gate in gates if action in gate.blocks and gate.status != "passed")
        for action in ("pursue", "approve_bid")
    }
    approve_blockers = blockers["approve_bid"]
    expired = bool(deadline and deadline < reference)
    recommended = "no_go" if expired else "go" if not approve_blockers else "hold"
    return QualificationAssessment(
        score=opportunity_score,
        status="ready" if not approve_blockers else "blocked",
        recommended_decision=recommended,
        gates=gates,
        blockers=blockers,
        evaluated_at=reference.isoformat(),
        policy=policy,
    )


def action_blockers(
    assessment: dict[str, Any],
    action: str,
) -> list[str]:
    blockers = _mapping(assessment.get("blockers"))
    values = blockers.get(action)
    if not isinstance(values, list):
        return []
    return [str(value) for value in values if str(value).strip()]


def _gate(
    key: str,
    label: str,
    passed: bool,
    actual: str,
    requirement: str,
    blocks: tuple[str, ...],
) -> QualificationGate:
    return QualificationGate(
        key=key,
        label=label,
        status="passed" if passed else "blocked",
        actual=actual,
        requirement=requirement,
        blocks=blocks,
    )


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _score(value: object) -> int:
    try:
        return max(0, min(int(float(value)), 100))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
