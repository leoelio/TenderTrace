from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import re
from typing import Any
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid4, uuid5

from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps
from tendertrace.retrieval import segment_for_fts


MEMORY_TYPES = {"note", "decision", "customer_signal", "competitor", "risk", "lesson"}


@dataclass(frozen=True)
class OrganizationWorkspace:
    id: str
    name: str
    feishu_chat_id: str
    status: str
    member_count: int
    memory_count: int
    created_by: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class OrganizationMemory:
    id: str
    workspace_id: str
    memory_type: str
    title: str
    content: str
    source_type: str
    source_message_id: str
    sender_open_id: str
    related_notice_id: str
    evidence_url: str
    created_by: str
    created_at: str
    updated_at: str
    score: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def create_workspace(
    settings: Settings,
    *,
    name: str,
    feishu_chat_id: str,
    members: list[dict[str, str]] | None = None,
    actor: str = "admin",
) -> OrganizationWorkspace:
    init_db(settings)
    normalized_name = " ".join(name.split())[:120]
    chat_id = feishu_chat_id.strip()
    if not normalized_name:
        raise ValueError("workspace name is required")
    if not chat_id:
        raise ValueError("feishu_chat_id is required")
    workspace_id = str(uuid5(NAMESPACE_URL, f"tendertrace:organization:{chat_id}"))
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO organization_workspaces(id, name, feishu_chat_id, created_by)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(feishu_chat_id) DO UPDATE SET
                name = excluded.name,
                status = 'active',
                updated_at = datetime('now')
            """,
            (workspace_id, normalized_name, chat_id, actor.strip()[:120] or "admin"),
        )
        row = conn.execute(
            "SELECT id FROM organization_workspaces WHERE feishu_chat_id = ?", (chat_id,)
        ).fetchone()
        assert row is not None
        workspace_id = str(row["id"])
        for member in members or []:
            _upsert_member(
                conn,
                workspace_id=workspace_id,
                member_open_id=str(member.get("open_id") or ""),
                member_name=str(member.get("name") or ""),
                role=str(member.get("role") or "member"),
                actor=actor,
            )
        _record_event(
            conn,
            workspace_id=workspace_id,
            action="workspace_created",
            actor=actor,
            payload={"name": normalized_name, "member_count": len(members or [])},
        )
        result = _workspace_row(conn, workspace_id)
    assert result is not None
    return _workspace_from_row(result)


def ensure_chat_workspace(
    settings: Settings,
    *,
    chat_id: str,
    sender_open_id: str,
    name: str = "飞书协作群",
) -> OrganizationWorkspace:
    workspace = workspace_by_chat(settings, chat_id)
    if workspace is None:
        workspace = create_workspace(
            settings,
            name=name,
            feishu_chat_id=chat_id,
            members=[{"open_id": sender_open_id, "role": "member"}],
            actor=sender_open_id or "feishu",
        )
    elif sender_open_id:
        add_members(
            settings,
            workspace.id,
            [{"open_id": sender_open_id, "role": "member"}],
            actor=sender_open_id,
        )
        workspace = get_workspace(settings, workspace.id) or workspace
    return workspace


def add_members(
    settings: Settings,
    workspace_id: str,
    members: list[dict[str, str]],
    *,
    actor: str = "admin",
) -> list[dict[str, str]]:
    if not members:
        raise ValueError("at least one member is required")
    with connection(settings) as conn:
        _require_workspace(conn, workspace_id)
        for member in members:
            _upsert_member(
                conn,
                workspace_id=workspace_id,
                member_open_id=str(member.get("open_id") or ""),
                member_name=str(member.get("name") or ""),
                role=str(member.get("role") or "member"),
                actor=actor,
            )
        conn.execute(
            "UPDATE organization_workspaces SET updated_at = datetime('now') WHERE id = ?",
            (workspace_id,),
        )
        _record_event(
            conn,
            workspace_id=workspace_id,
            action="members_added",
            actor=actor,
            payload={"member_open_ids": [str(item.get("open_id") or "") for item in members]},
        )
        rows = conn.execute(
            """
            SELECT member_open_id, member_name, role, status, created_at, updated_at
            FROM organization_members WHERE workspace_id = ? ORDER BY created_at
            """,
            (workspace_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def record_memory(
    settings: Settings,
    *,
    workspace_id: str,
    content: str,
    title: str = "",
    memory_type: str = "note",
    source_type: str = "web",
    source_message_id: str = "",
    sender_open_id: str = "",
    related_notice_id: str = "",
    evidence_url: str = "",
    actor: str = "admin",
) -> OrganizationMemory:
    normalized_content = " ".join(content.split())[:8000]
    normalized_title = " ".join(title.split())[:180] or normalized_content[:60]
    normalized_type = memory_type.strip() or "note"
    if not normalized_content:
        raise ValueError("memory content is required")
    if normalized_type not in MEMORY_TYPES:
        raise ValueError("unsupported organization memory type")
    if source_type not in {"web", "feishu_message", "feishu_card"}:
        raise ValueError("unsupported organization memory source")
    evidence_url = _validated_url(evidence_url)
    digest = hashlib.sha256(
        f"{normalized_type}|{normalized_title}|{normalized_content}|{related_notice_id.strip()}".encode(
            "utf-8"
        )
    ).hexdigest()
    memory_id = str(uuid4())
    with connection(settings) as conn:
        _require_workspace(conn, workspace_id)
        if related_notice_id and conn.execute(
            "SELECT 1 FROM notices WHERE id = ?", (related_notice_id.strip(),)
        ).fetchone() is None:
            raise LookupError("related opportunity not found")
        conn.execute(
            """
            INSERT OR IGNORE INTO organization_memories(
                id, workspace_id, memory_type, title, content, source_type,
                source_message_id, sender_open_id, related_notice_id, evidence_url,
                content_hash, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory_id,
                workspace_id,
                normalized_type,
                normalized_title,
                normalized_content,
                source_type,
                source_message_id.strip() or None,
                sender_open_id.strip() or None,
                related_notice_id.strip() or None,
                evidence_url or None,
                digest,
                actor.strip()[:120] or "admin",
            ),
        )
        row = conn.execute(
            """
            SELECT * FROM organization_memories
            WHERE workspace_id = ? AND (id = ? OR content_hash = ? OR source_message_id = ?)
            ORDER BY created_at LIMIT 1
            """,
            (workspace_id, memory_id, digest, source_message_id.strip()),
        ).fetchone()
        assert row is not None
        memory_id = str(row["id"])
        conn.execute("DELETE FROM organization_memories_fts WHERE memory_id = ?", (memory_id,))
        conn.execute(
            """
            INSERT INTO organization_memories_fts(memory_id, workspace_id, title, content)
            VALUES (?, ?, ?, ?)
            """,
            (
                memory_id,
                workspace_id,
                segment_for_fts(normalized_title),
                segment_for_fts(normalized_content),
            ),
        )
        _record_event(
            conn,
            workspace_id=workspace_id,
            memory_id=memory_id,
            action="memory_recorded",
            actor=actor,
            payload={"memory_type": normalized_type, "source_type": source_type},
        )
        result = conn.execute(
            "SELECT * FROM organization_memories WHERE id = ?", (memory_id,)
        ).fetchone()
    assert result is not None
    return _memory_from_row(result)


def search_memories(
    settings: Settings,
    *,
    workspace_id: str,
    query: str = "",
    memory_type: str = "",
    limit: int = 50,
) -> list[OrganizationMemory]:
    query = " ".join(query.split())[:300]
    if memory_type and memory_type not in MEMORY_TYPES:
        raise ValueError("unsupported organization memory type")
    bounded = max(1, min(int(limit), 200))
    with connection(settings) as conn:
        _require_workspace(conn, workspace_id)
        params: list[object] = [workspace_id]
        type_clause = ""
        if memory_type:
            type_clause = "AND m.memory_type = ?"
            params.append(memory_type)
        if query:
            terms = [term for term in segment_for_fts(query).split() if re.search(r"[\w\u4e00-\u9fff]", term)]
            expression = " OR ".join(f'"{term.replace(chr(34), "")}"' for term in terms[:20])
            if expression:
                rows = conn.execute(
                    f"""
                    SELECT m.*, bm25(organization_memories_fts) AS score
                    FROM organization_memories_fts f
                    JOIN organization_memories m ON m.id = f.memory_id
                    WHERE f.workspace_id = ? AND organization_memories_fts MATCH ? {type_clause}
                    ORDER BY score, m.created_at DESC LIMIT ?
                    """,
                    [workspace_id, expression, *params[1:], bounded],
                ).fetchall()
            else:
                rows = []
        else:
            rows = conn.execute(
                f"""
                SELECT m.*, 0.0 AS score FROM organization_memories m
                WHERE m.workspace_id = ? {type_clause}
                ORDER BY m.created_at DESC LIMIT ?
                """,
                [*params, bounded],
            ).fetchall()
    return [_memory_from_row(row, score=float(row["score"] or 0)) for row in rows]


def get_memory(
    settings: Settings,
    *,
    workspace_id: str,
    memory_id: str,
) -> OrganizationMemory | None:
    with connection(settings) as conn:
        row = conn.execute(
            "SELECT * FROM organization_memories WHERE id = ? AND workspace_id = ?",
            (memory_id.strip(), workspace_id.strip()),
        ).fetchone()
    return _memory_from_row(row) if row else None


def record_conversion(
    settings: Settings,
    *,
    workspace_id: str,
    memory_id: str,
    target_type: str,
    target_id: str,
    actor: str,
) -> None:
    with connection(settings) as conn:
        _require_workspace(conn, workspace_id)
        if conn.execute(
            "SELECT 1 FROM organization_memories WHERE id = ? AND workspace_id = ?",
            (memory_id.strip(), workspace_id.strip()),
        ).fetchone() is None:
            raise LookupError("organization memory not found")
        _record_event(
            conn,
            workspace_id=workspace_id,
            memory_id=memory_id,
            action="memory_converted",
            actor=actor,
            payload={"target_type": target_type, "target_id": target_id},
        )


def list_workspaces(settings: Settings, *, limit: int = 100) -> list[OrganizationWorkspace]:
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT w.*,
                   COUNT(DISTINCT CASE WHEN om.status = 'active' THEN om.member_open_id END) member_count,
                   COUNT(DISTINCT mem.id) memory_count
            FROM organization_workspaces w
            LEFT JOIN organization_members om ON om.workspace_id = w.id
            LEFT JOIN organization_memories mem ON mem.workspace_id = w.id
            WHERE w.status = 'active'
            GROUP BY w.id ORDER BY w.updated_at DESC LIMIT ?
            """,
            (max(1, min(int(limit), 200)),),
        ).fetchall()
    return [_workspace_from_row(row) for row in rows]


def get_workspace(settings: Settings, workspace_id: str) -> OrganizationWorkspace | None:
    with connection(settings) as conn:
        row = _workspace_row(conn, workspace_id)
    return _workspace_from_row(row) if row else None


def workspace_by_chat(settings: Settings, chat_id: str) -> OrganizationWorkspace | None:
    with connection(settings) as conn:
        row = conn.execute(
            "SELECT id FROM organization_workspaces WHERE feishu_chat_id = ? AND status = 'active'",
            (chat_id.strip(),),
        ).fetchone()
        result = _workspace_row(conn, str(row["id"])) if row else None
    return _workspace_from_row(result) if result else None


def _upsert_member(conn, *, workspace_id: str, member_open_id: str, member_name: str, role: str, actor: str) -> None:
    member_open_id = member_open_id.strip()
    if not member_open_id:
        raise ValueError("member open_id is required")
    role = role.strip() or "member"
    if role not in {"owner", "member", "partner", "observer"}:
        raise ValueError("unsupported organization member role")
    conn.execute(
        """
        INSERT INTO organization_members(
            workspace_id, member_open_id, member_name, role, added_by
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(workspace_id, member_open_id) DO UPDATE SET
            member_name = CASE WHEN excluded.member_name = '' THEN member_name ELSE excluded.member_name END,
            role = excluded.role, status = 'active', updated_at = datetime('now')
        """,
        (workspace_id, member_open_id, member_name.strip()[:120], role, actor.strip()[:120] or "admin"),
    )


def _workspace_row(conn, workspace_id: str):
    return conn.execute(
        """
        SELECT w.*,
               (SELECT COUNT(*) FROM organization_members om WHERE om.workspace_id = w.id AND om.status = 'active') member_count,
               (SELECT COUNT(*) FROM organization_memories mem WHERE mem.workspace_id = w.id) memory_count
        FROM organization_workspaces w WHERE w.id = ?
        """,
        (workspace_id,),
    ).fetchone()


def _require_workspace(conn, workspace_id: str) -> None:
    if conn.execute(
        "SELECT 1 FROM organization_workspaces WHERE id = ? AND status = 'active'",
        (workspace_id.strip(),),
    ).fetchone() is None:
        raise LookupError("organization workspace not found")


def _record_event(conn, *, workspace_id: str, action: str, actor: str, payload: dict[str, Any], memory_id: str = "") -> None:
    conn.execute(
        """
        INSERT INTO organization_memory_events(
            id, workspace_id, memory_id, action, actor_open_id, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (str(uuid4()), workspace_id, memory_id or None, action, actor.strip()[:120], json_dumps(payload)),
    )


def _validated_url(value: str) -> str:
    value = value.strip()[:2000]
    if not value:
        return ""
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("evidence_url must be an HTTP(S) URL")
    return value


def _workspace_from_row(row) -> OrganizationWorkspace:
    return OrganizationWorkspace(
        id=str(row["id"]), name=str(row["name"]), feishu_chat_id=str(row["feishu_chat_id"]),
        status=str(row["status"]), member_count=int(row["member_count"] or 0),
        memory_count=int(row["memory_count"] or 0), created_by=str(row["created_by"] or ""),
        created_at=str(row["created_at"] or ""), updated_at=str(row["updated_at"] or ""),
    )


def _memory_from_row(row, *, score: float = 0.0) -> OrganizationMemory:
    return OrganizationMemory(
        id=str(row["id"]), workspace_id=str(row["workspace_id"]),
        memory_type=str(row["memory_type"]), title=str(row["title"]), content=str(row["content"]),
        source_type=str(row["source_type"]), source_message_id=str(row["source_message_id"] or ""),
        sender_open_id=str(row["sender_open_id"] or ""), related_notice_id=str(row["related_notice_id"] or ""),
        evidence_url=str(row["evidence_url"] or ""), created_by=str(row["created_by"] or ""),
        created_at=str(row["created_at"] or ""), updated_at=str(row["updated_at"] or ""), score=score,
    )
