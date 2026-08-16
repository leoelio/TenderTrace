from __future__ import annotations

from dataclasses import asdict, dataclass

from tendertrace.config import Settings
from tendertrace.integrations.feishu import FeishuClient, FeishuError
from tendertrace.opportunity_team import mark_team_sync, pending_task_members
from tendertrace.workflow import get_workflow


@dataclass(frozen=True)
class TeamSyncResult:
    status: str
    added_count: int
    removed_count: int
    failed_count: int
    message: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def sync_opportunity_team(
    settings: Settings,
    notice_id: str,
    *,
    client: FeishuClient | None = None,
) -> TeamSyncResult:
    workflow = get_workflow(settings, notice_id)
    if not workflow.feishu_task_guid:
        return TeamSyncResult("pending", 0, 0, 0, "机会尚未创建飞书任务")
    feishu = client or FeishuClient(settings)
    added = pending_task_members(settings, notice_id)
    removed = [
        member
        for member in pending_task_members(settings, notice_id, removed=True)
        if member.feishu_task_guid
    ]
    added_count = _sync_members(
        settings,
        members=added,
        task_guid=workflow.feishu_task_guid,
        operation=lambda ids: feishu.add_task_members(
            workflow.feishu_task_guid,
            assignee_open_ids=ids,
            role="follower",
        ),
    )
    removed_count = _sync_members(
        settings,
        members=removed,
        task_guid=workflow.feishu_task_guid,
        operation=lambda ids: feishu.remove_task_members(
            workflow.feishu_task_guid,
            member_open_ids=ids,
            role="follower",
        ),
    )
    failed_count = len(added) + len(removed) - added_count - removed_count
    status = "synced" if not failed_count else "partial"
    return TeamSyncResult(
        status,
        added_count,
        removed_count,
        failed_count,
        "团队成员已同步" if status == "synced" else "部分成员同步失败，可重试",
    )


def _sync_members(
    settings: Settings,
    *,
    members,
    task_guid: str,
    operation,
) -> int:
    if not members:
        return 0
    member_ids = [member.id for member in members]
    try:
        operation([member.member_open_id for member in members])
    except FeishuError as exc:
        mark_team_sync(
            settings,
            member_ids=member_ids,
            status="failed",
            task_guid=task_guid,
            error=str(exc),
        )
        return 0
    mark_team_sync(
        settings,
        member_ids=member_ids,
        status="synced",
        task_guid=task_guid,
    )
    return len(members)
