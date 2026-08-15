from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from typing import Any
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.qualification import action_blockers


STAGES = {
    "identified": "线索识别",
    "qualifying": "机会确认",
    "pursuing": "策略制定",
    "bidding": "投标准备",
    "won": "已中标",
    "lost": "未中标",
    "archived": "已归档",
}

ACTION_STAGE = {
    "claim": "qualifying",
    "pursue": "pursuing",
    "prepare_bid": "bidding",
    "mark_won": "won",
    "mark_lost": "lost",
    "archive": "archived",
}

DECISION_ACTION = {
    "approve_bid": "go",
    "hold": "hold",
    "reject": "no_go",
}

ACTION_FROM_STAGES = {
    "claim": {"identified", "qualifying"},
    "pursue": {"qualifying", "pursuing"},
    "approve_bid": {"pursuing", "bidding"},
    "prepare_bid": {"pursuing", "bidding"},
    "mark_won": {"bidding"},
    "mark_lost": {"bidding"},
    "hold": {"identified", "qualifying", "pursuing", "bidding"},
    "reject": {"identified", "qualifying", "pursuing", "bidding"},
    "archive": {"identified", "qualifying", "pursuing", "bidding", "won", "lost"},
}


class WorkflowGateError(ValueError):
    def __init__(self, action: str, reasons: list[str]) -> None:
        self.action = action
        self.reasons = tuple(reasons)
        super().__init__(f"阶段门禁未通过：{'、'.join(reasons)}")


@dataclass(frozen=True)
class OpportunityWorkflow:
    notice_id: str
    stage: str
    stage_label: str
    owner_open_id: str
    owner_name: str
    next_action: str
    due_at: str
    feishu_task_guid: str
    feishu_event_id: str
    feishu_message_id: str
    qualification_score: int
    qualification_status: str
    decision: str
    decision_reason: str
    decision_by: str
    decision_at: str
    stage_changed_at: str
    updated_by: str
    updated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def get_workflow(settings: Settings, notice_id: str) -> OpportunityWorkflow:
    init_db(settings)
    with connection(settings) as conn:
        row = conn.execute(
            "SELECT * FROM opportunity_workflows WHERE notice_id = ?", (notice_id,)
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO opportunity_workflows(notice_id) VALUES (?)", (notice_id,)
            )
            row = conn.execute(
                "SELECT * FROM opportunity_workflows WHERE notice_id = ?", (notice_id,)
            ).fetchone()
    assert row is not None
    return _from_row(row)


def workflow_snapshots(
    settings: Settings,
    notice_ids: list[str],
) -> dict[str, OpportunityWorkflow]:
    unique_ids = list(dict.fromkeys(notice_id for notice_id in notice_ids if notice_id))
    if not unique_ids:
        return {}
    placeholders = ",".join("?" for _ in unique_ids)
    with connection(settings) as conn:
        rows = conn.execute(
            f"SELECT * FROM opportunity_workflows WHERE notice_id IN ({placeholders})",
            unique_ids,
        ).fetchall()
    found = {str(row["notice_id"]): _from_row(row) for row in rows}
    return {
        notice_id: found.get(notice_id, _default_workflow(notice_id))
        for notice_id in unique_ids
    }


def update_workflow(
    settings: Settings,
    notice_id: str,
    *,
    stage: str | None = None,
    owner_open_id: str | None = None,
    owner_name: str | None = None,
    next_action: str | None = None,
    due_at: str | None = None,
    feishu_task_guid: str | None = None,
    feishu_event_id: str | None = None,
    feishu_message_id: str | None = None,
    qualification_score: int | None = None,
    qualification_status: str | None = None,
    decision: str | None = None,
    decision_reason: str | None = None,
    decision_by: str | None = None,
    decision_at: str | None = None,
    updated_by: str | None = None,
) -> OpportunityWorkflow:
    current = get_workflow(settings, notice_id)
    target_stage = stage or current.stage
    if target_stage not in STAGES:
        raise ValueError(f"unsupported opportunity stage: {target_stage}")
    values = {
        "stage": target_stage,
        "owner_open_id": current.owner_open_id if owner_open_id is None else owner_open_id,
        "owner_name": current.owner_name if owner_name is None else owner_name,
        "next_action": current.next_action if next_action is None else next_action,
        "due_at": current.due_at if due_at is None else due_at,
        "feishu_task_guid": (
            current.feishu_task_guid if feishu_task_guid is None else feishu_task_guid
        ),
        "feishu_event_id": (
            current.feishu_event_id if feishu_event_id is None else feishu_event_id
        ),
        "feishu_message_id": (
            current.feishu_message_id if feishu_message_id is None else feishu_message_id
        ),
        "qualification_score": (
            current.qualification_score
            if qualification_score is None
            else max(0, min(int(qualification_score), 100))
        ),
        "qualification_status": (
            current.qualification_status
            if qualification_status is None
            else qualification_status
        ),
        "decision": current.decision if decision is None else decision,
        "decision_reason": (
            current.decision_reason if decision_reason is None else decision_reason
        ),
        "decision_by": current.decision_by if decision_by is None else decision_by,
        "decision_at": current.decision_at if decision_at is None else decision_at,
        "stage_changed_at": (
            current.stage_changed_at
            if target_stage == current.stage
            else datetime.now(timezone.utc).isoformat(timespec="seconds")
        ),
        "updated_by": current.updated_by if updated_by is None else updated_by,
    }
    with connection(settings) as conn:
        conn.execute(
            """
            UPDATE opportunity_workflows
            SET stage = ?, owner_open_id = ?, owner_name = ?, next_action = ?, due_at = ?,
                feishu_task_guid = ?, feishu_event_id = ?, feishu_message_id = ?,
                qualification_score = ?, qualification_status = ?, decision = ?,
                decision_reason = ?, decision_by = ?, decision_at = ?,
                stage_changed_at = ?, updated_by = ?, updated_at = datetime('now')
            WHERE notice_id = ?
            """,
            (*values.values(), notice_id),
        )
    return get_workflow(settings, notice_id)


def apply_action(
    settings: Settings,
    notice_id: str,
    action: str,
    *,
    actor_open_id: str = "",
    actor_name: str = "",
    qualification: dict[str, Any] | None = None,
    decision_reason: str = "",
    payload: dict[str, Any] | None = None,
) -> OpportunityWorkflow:
    if action not in ACTION_STAGE and action not in DECISION_ACTION:
        raise ValueError(f"unsupported opportunity action: {action}")
    current = get_workflow(settings, notice_id)
    allowed_stages = ACTION_FROM_STAGES[action]
    if current.stage not in allowed_stages:
        raise WorkflowGateError(
            action,
            [f"当前阶段“{current.stage_label}”不能执行该操作"],
        )
    qualification = qualification or {}
    blockers = action_blockers(qualification, action)
    if blockers:
        raise WorkflowGateError(action, blockers)
    if action == "prepare_bid" and current.decision != "go":
        raise WorkflowGateError(action, ["投标决策尚未通过 Go 审批"])
    owner = actor_open_id if action == "claim" and actor_open_id else None
    owner_name = actor_name if action == "claim" and actor_name else None
    decision = DECISION_ACTION.get(action)
    target_stage = ACTION_STAGE.get(action, current.stage)
    if action == "reject":
        target_stage = "archived"
    qualification_score = _qualification_score(qualification) if qualification else None
    qualification_status = str(qualification.get("status") or "pending") if qualification else None
    decision_at = datetime.now().astimezone().isoformat(timespec="seconds") if decision else None
    recorded_reason = decision_reason
    if decision and not recorded_reason:
        recorded_reason = {
            "go": "资格门禁通过，批准进入投标准备",
            "hold": "暂缓投入，等待补齐信息或资源",
            "no_go": "当前不进入投标流程",
        }[decision]
    updated = update_workflow(
        settings,
        notice_id,
        stage=target_stage,
        owner_open_id=owner,
        owner_name=owner_name,
        qualification_score=qualification_score,
        qualification_status=qualification_status,
        decision=decision,
        decision_reason=recorded_reason if decision else None,
        decision_by=(actor_name or actor_open_id) if decision else None,
        decision_at=decision_at,
        updated_by=actor_open_id or actor_name,
    )
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO opportunity_events(
                id, notice_id, action, from_stage, to_stage, actor_open_id, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                notice_id,
                action,
                current.stage,
                updated.stage,
                actor_open_id,
                json.dumps(payload or {}, ensure_ascii=False),
            ),
        )
    return updated


def _from_row(row: Any) -> OpportunityWorkflow:
    stage = str(row["stage"] or "identified")
    return OpportunityWorkflow(
        notice_id=str(row["notice_id"]),
        stage=stage,
        stage_label=STAGES.get(stage, stage),
        owner_open_id=str(row["owner_open_id"] or ""),
        owner_name=str(row["owner_name"] or ""),
        next_action=str(row["next_action"] or ""),
        due_at=str(row["due_at"] or ""),
        feishu_task_guid=str(row["feishu_task_guid"] or ""),
        feishu_event_id=str(row["feishu_event_id"] or ""),
        feishu_message_id=str(row["feishu_message_id"] or ""),
        qualification_score=int(row["qualification_score"] or 0),
        qualification_status=str(row["qualification_status"] or "pending"),
        decision=str(row["decision"] or "pending"),
        decision_reason=str(row["decision_reason"] or ""),
        decision_by=str(row["decision_by"] or ""),
        decision_at=str(row["decision_at"] or ""),
        stage_changed_at=str(row["stage_changed_at"] or ""),
        updated_by=str(row["updated_by"] or ""),
        updated_at=str(row["updated_at"] or datetime.now().isoformat(timespec="seconds")),
    )


def _default_workflow(notice_id: str) -> OpportunityWorkflow:
    return OpportunityWorkflow(
        notice_id=notice_id,
        stage="identified",
        stage_label=STAGES["identified"],
        owner_open_id="",
        owner_name="",
        next_action="",
        due_at="",
        feishu_task_guid="",
        feishu_event_id="",
        feishu_message_id="",
        qualification_score=0,
        qualification_status="pending",
        decision="pending",
        decision_reason="",
        decision_by="",
        decision_at="",
        stage_changed_at="",
        updated_by="",
        updated_at="",
    )


def _qualification_score(qualification: dict[str, Any]) -> int:
    try:
        return max(0, min(int(qualification.get("score") or 0), 100))
    except (TypeError, ValueError):
        return 0
