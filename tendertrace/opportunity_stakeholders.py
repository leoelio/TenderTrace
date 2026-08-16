from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.workflow import OpportunityWorkflow


ROLE_LABELS = {
    "economic_buyer": "经济决策人",
    "technical_buyer": "技术决策人",
    "procurement": "采购执行人",
    "champion": "内部支持者",
    "end_user": "业务使用者",
    "blocker": "关键阻力人",
}

INFLUENCE_LABELS = {"low": "低", "medium": "中", "high": "高"}
STANCE_LABELS = {
    "supportive": "支持",
    "neutral": "中立",
    "unknown": "待确认",
    "resistant": "抵触",
}
RELATIONSHIP_LABELS = {
    "unknown": "未建立",
    "weak": "初步接触",
    "developing": "持续沟通",
    "strong": "稳定关系",
    "trusted": "深度信任",
}

STAGE_REQUIREMENTS = {
    "identified": (),
    "qualifying": (
        ("customer_contact", "客户联系人", frozenset(ROLE_LABELS) - {"blocker"}),
    ),
    "pursuing": (
        ("customer_contact", "客户联系人", frozenset(ROLE_LABELS) - {"blocker"}),
        ("decision_contact", "决策影响人", frozenset({"economic_buyer", "technical_buyer"})),
        ("champion", "内部支持者", frozenset({"champion"})),
    ),
    "bidding": (
        ("economic_buyer", "经济决策人", frozenset({"economic_buyer"})),
        ("technical_buyer", "技术决策人", frozenset({"technical_buyer"})),
        ("procurement", "采购执行人", frozenset({"procurement"})),
    ),
    "won": (
        ("end_user", "业务使用者", frozenset({"end_user"})),
    ),
    "lost": (),
    "archived": (),
}

RELATIONSHIP_SCORES = {
    "unknown": 0,
    "weak": 25,
    "developing": 50,
    "strong": 75,
    "trusted": 100,
}
INFLUENCE_WEIGHTS = {"low": 1, "medium": 2, "high": 3}


@dataclass(frozen=True)
class OpportunityStakeholder:
    id: str
    notice_id: str
    stakeholder_name: str
    organization_name: str
    job_title: str
    role: str
    role_label: str
    influence: str
    influence_label: str
    stance: str
    stance_label: str
    relationship_strength: str
    relationship_label: str
    owner_member_id: str
    owner_member_name: str
    next_action: str
    evidence_source: str
    evidence_url: str
    evidence_text: str
    status: str
    added_by: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def upsert_stakeholder(
    settings: Settings,
    *,
    notice_id: str,
    stakeholder_name: str,
    role: str,
    organization_name: str = "",
    job_title: str = "",
    influence: str = "medium",
    stance: str = "unknown",
    relationship_strength: str = "unknown",
    owner_member_id: str = "",
    next_action: str,
    evidence_source: str,
    evidence_url: str = "",
    evidence_text: str,
    actor: str = "admin",
) -> OpportunityStakeholder:
    init_db(settings)
    values = {
        "notice_id": notice_id.strip(),
        "stakeholder_name": stakeholder_name.strip(),
        "organization_name": organization_name.strip(),
        "job_title": job_title.strip(),
        "role": role.strip(),
        "influence": influence.strip(),
        "stance": stance.strip(),
        "relationship_strength": relationship_strength.strip(),
        "owner_member_id": owner_member_id.strip(),
        "next_action": next_action.strip(),
        "evidence_source": evidence_source.strip(),
        "evidence_url": evidence_url.strip(),
        "evidence_text": evidence_text.strip(),
    }
    _validate(values)
    stakeholder_key = _stakeholder_key(
        values["stakeholder_name"], values["organization_name"]
    )
    stakeholder_id = _stakeholder_id(
        values["notice_id"], stakeholder_key, values["role"]
    )
    with connection(settings) as conn:
        if conn.execute(
            "SELECT 1 FROM notices WHERE id = ?", (values["notice_id"],)
        ).fetchone() is None:
            raise LookupError("opportunity notice not found")
        if values["owner_member_id"] and conn.execute(
            "SELECT 1 FROM opportunity_team_members WHERE id = ? AND notice_id = ? AND status = 'active'",
            (values["owner_member_id"], values["notice_id"]),
        ).fetchone() is None:
            raise ValueError("owner_member_id must reference an active opportunity team member")
        conn.execute(
            """
            INSERT INTO opportunity_stakeholders(
                id, notice_id, stakeholder_key, stakeholder_name,
                organization_name, job_title, role, influence, stance,
                relationship_strength, owner_member_id, next_action,
                evidence_source, evidence_url, evidence_text, status, added_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
            ON CONFLICT(notice_id, stakeholder_key, role) DO UPDATE SET
                stakeholder_name = excluded.stakeholder_name,
                organization_name = excluded.organization_name,
                job_title = excluded.job_title,
                influence = excluded.influence,
                stance = excluded.stance,
                relationship_strength = excluded.relationship_strength,
                owner_member_id = excluded.owner_member_id,
                next_action = excluded.next_action,
                evidence_source = excluded.evidence_source,
                evidence_url = excluded.evidence_url,
                evidence_text = excluded.evidence_text,
                status = 'active',
                added_by = excluded.added_by,
                updated_at = datetime('now')
            """,
            (
                stakeholder_id,
                values["notice_id"],
                stakeholder_key,
                values["stakeholder_name"],
                values["organization_name"],
                values["job_title"],
                values["role"],
                values["influence"],
                values["stance"],
                values["relationship_strength"],
                values["owner_member_id"] or None,
                values["next_action"],
                values["evidence_source"],
                values["evidence_url"],
                values["evidence_text"],
                actor.strip() or "admin",
            ),
        )
        _record_event(
            conn,
            notice_id=values["notice_id"],
            action="stakeholder_upserted",
            actor=actor,
            payload={
                "stakeholder_id": stakeholder_id,
                "role": values["role"],
                "influence": values["influence"],
                "stance": values["stance"],
            },
        )
        row = _select_row(conn, stakeholder_id)
    assert row is not None
    return _from_row(row)


def remove_stakeholder(
    settings: Settings,
    *,
    notice_id: str,
    stakeholder_id: str,
    actor: str = "admin",
) -> OpportunityStakeholder:
    init_db(settings)
    with connection(settings) as conn:
        row = _select_row(conn, stakeholder_id, notice_id=notice_id, active_only=True)
        if row is None:
            raise LookupError("opportunity stakeholder not found")
        conn.execute(
            """
            UPDATE opportunity_stakeholders
            SET status = 'removed', updated_at = datetime('now')
            WHERE id = ?
            """,
            (stakeholder_id,),
        )
        _record_event(
            conn,
            notice_id=notice_id,
            action="stakeholder_removed",
            actor=actor,
            payload={"stakeholder_id": stakeholder_id, "role": str(row["role"] or "")},
        )
        updated = _select_row(conn, stakeholder_id)
    assert updated is not None
    return _from_row(updated)


def stakeholder_snapshots(
    settings: Settings,
    workflows: dict[str, OpportunityWorkflow],
) -> dict[str, dict[str, object]]:
    notice_ids = list(workflows)
    if not notice_ids:
        return {}
    placeholders = ",".join("?" for _ in notice_ids)
    with connection(settings) as conn:
        rows = conn.execute(
            f"""
            SELECT s.*, t.member_name AS owner_member_name
            FROM opportunity_stakeholders s
            LEFT JOIN opportunity_team_members t ON t.id = s.owner_member_id
            WHERE s.notice_id IN ({placeholders}) AND s.status = 'active'
            ORDER BY CASE s.influence WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                     s.created_at, s.stakeholder_name
            """,
            notice_ids,
        ).fetchall()
    by_notice: dict[str, list[OpportunityStakeholder]] = {
        notice_id: [] for notice_id in notice_ids
    }
    for row in rows:
        item = _from_row(row)
        by_notice.setdefault(item.notice_id, []).append(item)
    return {
        notice_id: stakeholder_summary(
            workflows[notice_id], by_notice.get(notice_id, [])
        )
        for notice_id in notice_ids
    }


def stakeholder_summary(
    workflow: OpportunityWorkflow,
    stakeholders: list[OpportunityStakeholder],
) -> dict[str, object]:
    requirements = STAGE_REQUIREMENTS.get(workflow.stage, ())
    covered_roles = {item.role for item in stakeholders}
    missing = [
        {"key": key, "label": label}
        for key, label, roles in requirements
        if not covered_roles.intersection(roles)
    ]
    coverage_score = (
        round((len(requirements) - len(missing)) / len(requirements) * 100)
        if requirements
        else 0
        if workflow.stage == "identified" and not stakeholders
        else 100
    )
    relationship_score = _relationship_score(stakeholders)
    risks = _relationship_risks(stakeholders, missing)
    actions = _strategy_actions(stakeholders, missing)
    stakeholder_payloads = []
    for stakeholder in stakeholders:
        payload = stakeholder.to_dict()
        if not stakeholder.owner_member_name and workflow.owner_name:
            payload["owner_member_name"] = workflow.owner_name
            payload["owner_source"] = "opportunity_owner"
        else:
            payload["owner_source"] = "team_member" if stakeholder.owner_member_name else ""
        stakeholder_payloads.append(payload)
    return {
        "stakeholder_count": len(stakeholders),
        "coverage_score": coverage_score,
        "relationship_score": relationship_score,
        "status": (
            "not_started"
            if workflow.stage == "identified" and not stakeholders
            else "ready"
            if not missing
            else "incomplete"
        ),
        "status_label": (
            "关系尚未建档"
            if workflow.stage == "identified" and not stakeholders
            else "关键关系已覆盖"
            if not missing
            else "关键关系待补"
        ),
        "required_roles": [label for _key, label, _roles in requirements],
        "missing_roles": [item["label"] for item in missing],
        "risk_level": _risk_level(risks),
        "risks": risks,
        "strategy_actions": actions,
        "stakeholders": stakeholder_payloads,
    }


def _validate(values: dict[str, str]) -> None:
    for field in (
        "notice_id",
        "stakeholder_name",
        "next_action",
        "evidence_source",
        "evidence_text",
    ):
        if not values[field]:
            raise ValueError(f"{field} is required")
    for field, allowed in (
        ("role", ROLE_LABELS),
        ("influence", INFLUENCE_LABELS),
        ("stance", STANCE_LABELS),
        ("relationship_strength", RELATIONSHIP_LABELS),
    ):
        if values[field] not in allowed:
            raise ValueError(f"unsupported stakeholder {field}: {values[field]}")
    if values["evidence_url"]:
        parsed = urlparse(values["evidence_url"])
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("evidence_url must be an absolute HTTP(S) URL")


def _relationship_score(stakeholders: list[OpportunityStakeholder]) -> int:
    if not stakeholders:
        return 0
    weighted = sum(
        RELATIONSHIP_SCORES[item.relationship_strength]
        * INFLUENCE_WEIGHTS[item.influence]
        for item in stakeholders
    )
    weights = sum(INFLUENCE_WEIGHTS[item.influence] for item in stakeholders)
    return round(weighted / weights) if weights else 0


def _relationship_risks(
    stakeholders: list[OpportunityStakeholder],
    missing: list[dict[str, str]],
) -> list[dict[str, str]]:
    risks = [
        {
            "level": "warning",
            "type": "coverage_gap",
            "message": f"当前阶段尚未识别{item['label']}",
        }
        for item in missing
    ]
    for stakeholder in stakeholders:
        if stakeholder.stance == "resistant" or stakeholder.role == "blocker":
            risks.append(
                {
                    "level": "critical" if stakeholder.influence == "high" else "warning",
                    "type": "relationship_resistance",
                    "message": f"{stakeholder.stakeholder_name}对当前机会存在阻力",
                }
            )
        elif stakeholder.influence == "high" and stakeholder.stance == "unknown":
            risks.append(
                {
                    "level": "warning",
                    "type": "unknown_stance",
                    "message": f"高影响关键人{stakeholder.stakeholder_name}立场尚未确认",
                }
            )
    return risks


def _strategy_actions(
    stakeholders: list[OpportunityStakeholder],
    missing: list[dict[str, str]],
) -> list[str]:
    actions = [f"识别并验证{item['label']}，补充可追溯关系证据" for item in missing]
    actions.extend(
        item.next_action
        for item in stakeholders
        if item.stance in {"resistant", "unknown"} or item.relationship_strength in {"unknown", "weak"}
    )
    return list(dict.fromkeys(value for value in actions if value))[:6]


def _risk_level(risks: list[dict[str, str]]) -> str:
    if any(item["level"] == "critical" for item in risks):
        return "critical"
    if risks:
        return "warning"
    return "normal"


def _from_row(row: Any) -> OpportunityStakeholder:
    role = str(row["role"] or "")
    influence = str(row["influence"] or "medium")
    stance = str(row["stance"] or "unknown")
    relationship = str(row["relationship_strength"] or "unknown")
    return OpportunityStakeholder(
        id=str(row["id"]),
        notice_id=str(row["notice_id"]),
        stakeholder_name=str(row["stakeholder_name"] or ""),
        organization_name=str(row["organization_name"] or ""),
        job_title=str(row["job_title"] or ""),
        role=role,
        role_label=ROLE_LABELS.get(role, role),
        influence=influence,
        influence_label=INFLUENCE_LABELS.get(influence, influence),
        stance=stance,
        stance_label=STANCE_LABELS.get(stance, stance),
        relationship_strength=relationship,
        relationship_label=RELATIONSHIP_LABELS.get(relationship, relationship),
        owner_member_id=str(row["owner_member_id"] or ""),
        owner_member_name=str(row["owner_member_name"] or ""),
        next_action=str(row["next_action"] or ""),
        evidence_source=str(row["evidence_source"] or ""),
        evidence_url=str(row["evidence_url"] or ""),
        evidence_text=str(row["evidence_text"] or ""),
        status=str(row["status"] or "active"),
        added_by=str(row["added_by"] or ""),
        created_at=str(row["created_at"] or ""),
        updated_at=str(row["updated_at"] or ""),
    )


def _select_row(
    conn,
    stakeholder_id: str,
    *,
    notice_id: str = "",
    active_only: bool = False,
):
    conditions = ["s.id = ?"]
    params: list[str] = [stakeholder_id]
    if notice_id:
        conditions.append("s.notice_id = ?")
        params.append(notice_id)
    if active_only:
        conditions.append("s.status = 'active'")
    return conn.execute(
        f"""
        SELECT s.*, t.member_name AS owner_member_name
        FROM opportunity_stakeholders s
        LEFT JOIN opportunity_team_members t ON t.id = s.owner_member_id
        WHERE {' AND '.join(conditions)}
        """,
        params,
    ).fetchone()


def _stakeholder_key(name: str, organization: str) -> str:
    raw = f"{name.casefold()}|{organization.casefold()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _stakeholder_id(notice_id: str, stakeholder_key: str, role: str) -> str:
    raw = f"{notice_id}|{stakeholder_key}|{role}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _record_event(
    conn,
    *,
    notice_id: str,
    action: str,
    actor: str,
    payload: dict[str, object],
) -> None:
    conn.execute(
        """
        INSERT INTO opportunity_events(id, notice_id, action, actor_open_id, payload_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            str(uuid4()),
            notice_id,
            action,
            actor.strip() or "admin",
            json.dumps(payload, ensure_ascii=False),
        ),
    )
