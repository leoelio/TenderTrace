from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from time import perf_counter
from typing import Any, Callable
from uuid import uuid4

from tendertrace.change_impact_engine import get_change_impact
from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps
from tendertrace.digital_twin import build_digital_twin
from tendertrace.evidence_microscope import build_evidence_microscope
from tendertrace.integrations.feishu import feishu_status
from tendertrace.integrations.feishu_bot import feishu_listener_status
from tendertrace.integrations.feishu_war_room import build_war_room_plan
from tendertrace.live_challenge import get_live_challenge
from tendertrace.sanitize import sanitize_for_output
from tendertrace.source_map import source_health


CASE_ROLES = {"main", "backup", "replay"}
SOURCE_TYPES = {"live_challenge", "opportunity"}
MODES = {"live", "verified_history", "replay"}
VIEWPORT_PROFILES = {
    "projector_1440": (1440, 900),
    "full_hd_1920": (1920, 1080),
}
TERMINAL_CHALLENGE_STATUSES = {
    "local_ready",
    "local_empty",
    "completed",
    "completed_with_errors",
    "cancelled",
    "failed",
}


def demo_reliability_overview(settings: Settings, *, rehearsal_limit: int = 20) -> dict[str, object]:
    init_db(settings)
    cases = list_demo_cases(settings)
    rehearsals = list_demo_rehearsals(settings, limit=rehearsal_limit)
    layout_audits = list_demo_layout_audits(settings)
    environment = demo_environment_status(settings)
    latest_three = rehearsals[:3]
    consecutive_passes = len(latest_three) == 3 and all(
        item["status"] == "passed" for item in latest_three
    )
    return {
        "status": "ready"
        if environment["critical_ready"] and len(cases) == 3
        else "attention",
        "environment": environment,
        "cases": cases,
        "rehearsals": rehearsals,
        "layout_audits": layout_audits,
        "summary": {
            "case_count": len(cases),
            "verified_replay_count": sum(bool(item["replay_verified"]) for item in cases),
            "rehearsal_count": len(rehearsals),
            "consecutive_passes": consecutive_passes,
            "layout_profiles_passed": sum(item["status"] == "passed" for item in layout_audits),
        },
        "protocol": {
            "replay_requires_real_record": True,
            "replay_requires_same_version": True,
            "mode_is_always_visible": True,
            "fallback_reason_is_required": True,
            "target_open_ms": 10_000,
        },
    }


def prepare_default_demo_cases(settings: Settings, *, actor: str = "admin") -> dict[str, object]:
    init_db(settings)
    actor_text = _controlled_text(actor, "actor", 40)
    with connection(settings) as conn:
        main_row = conn.execute(
            """
            SELECT n.id, n.title,
                   (SELECT COUNT(*) FROM opportunity_requirements r WHERE r.notice_id = n.id) AS requirements,
                   (SELECT COUNT(*) FROM evidence_items e WHERE e.notice_id = n.id) AS evidence
            FROM notices n
            WHERE n.source_site <> 'demo' AND n.source_url NOT LIKE '%example.com%'
            ORDER BY (requirements + evidence) DESC, n.last_seen_at DESC, n.rowid DESC
            LIMIT 1
            """
        ).fetchone()
        challenge_rows = conn.execute(
            """
            SELECT id FROM live_challenge_sessions
            WHERE status IN ('local_ready', 'completed', 'completed_with_errors')
              AND (local_result_count + online_result_count) > 0
            ORDER BY created_at DESC, rowid DESC
            LIMIT 10
            """
        ).fetchall()
        replay_row = conn.execute(
            """
            SELECT id, title FROM notices
            WHERE id = 'demo-feishu-war-room'
            LIMIT 1
            """
        ).fetchone()
    if main_row is None:
        raise ValueError("no public opportunity is available for the main demo case")

    backup_id = ""
    for row in challenge_rows:
        candidate = get_live_challenge(settings, str(row["id"]))
        results = list(candidate.get("results") or [])
        if results and all(
            str(item.get("source_site") or "") != "demo"
            and str(item.get("source_url") or "").startswith("https://")
            for item in results
        ):
            backup_id = str(row["id"])
            break
    if not backup_id:
        raise ValueError("no verified live challenge is available for the backup demo case")

    main = freeze_demo_case(
        settings,
        role="main",
        label=str(main_row["title"]),
        source_type="opportunity",
        source_id=str(main_row["id"]),
        actor=actor_text,
    )
    backup = freeze_demo_case(
        settings,
        role="backup",
        label="全球服务器机会现场检索",
        source_type="live_challenge",
        source_id=backup_id,
        actor=actor_text,
    )
    replay_source_id = str(replay_row["id"]) if replay_row else str(main_row["id"])
    replay_label = (
        "飞书战情室受控演练回放（明确标识）"
        if replay_row
        else f"{main_row['title']} · 同版本回放"
    )
    replay = freeze_demo_case(
        settings,
        role="replay",
        label=replay_label,
        source_type="opportunity",
        source_id=replay_source_id,
        actor=actor_text,
    )
    return {"cases": [main, backup, replay], "prepared": 3}


def freeze_demo_case(
    settings: Settings,
    *,
    role: object,
    label: object,
    source_type: object,
    source_id: object,
    actor: object = "admin",
) -> dict[str, object]:
    init_db(settings)
    role_text = str(role or "").strip().lower()
    if role_text not in CASE_ROLES:
        raise ValueError(f"role must be one of: {', '.join(sorted(CASE_ROLES))}")
    source_type_text = str(source_type or "").strip().lower()
    if source_type_text not in SOURCE_TYPES:
        raise ValueError(f"source_type must be one of: {', '.join(sorted(SOURCE_TYPES))}")
    label_text = _controlled_text(label, "label", 100)
    source_id_text = _controlled_text(source_id, "source_id", 180)
    actor_text = _controlled_text(actor, "actor", 40)
    snapshot = _build_source_snapshot(settings, source_type_text, source_id_text)
    snapshot_text = _stable_json(snapshot)
    snapshot_hash = _sha256(snapshot_text)
    case_id = f"demo-reliability-{role_text}"
    artifact_id = str(uuid4())
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO demo_reliability_cases(
                id, role, label, source_type, source_id, source_version,
                snapshot_hash, snapshot_json, data_as_of, evidence_kind,
                verification_status, verified_at, created_by, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'verified', datetime('now'), ?, datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
                role = excluded.role,
                label = excluded.label,
                source_type = excluded.source_type,
                source_id = excluded.source_id,
                source_version = excluded.source_version,
                snapshot_hash = excluded.snapshot_hash,
                snapshot_json = excluded.snapshot_json,
                data_as_of = excluded.data_as_of,
                evidence_kind = excluded.evidence_kind,
                verification_status = 'verified',
                verified_at = datetime('now'),
                created_by = excluded.created_by,
                updated_at = datetime('now')
            """,
            (
                case_id,
                role_text,
                label_text,
                source_type_text,
                source_id_text,
                str(snapshot["source_version"]),
                snapshot_hash,
                snapshot_text,
                str(snapshot["data_as_of"]),
                str(snapshot["evidence_kind"]),
                actor_text,
            ),
        )
        conn.execute(
            """
            INSERT INTO demo_replay_artifacts(
                id, case_id, source_type, source_id, source_version,
                snapshot_hash, request_json, result_json, receipt_json, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact_id,
                case_id,
                source_type_text,
                source_id_text,
                str(snapshot["source_version"]),
                snapshot_hash,
                json_dumps(snapshot.get("request") or {}),
                snapshot_text,
                json_dumps(
                    {
                        "status": "captured_from_database",
                        "source_version": snapshot["source_version"],
                        "snapshot_hash": snapshot_hash,
                        "synthetic": False,
                    }
                ),
                str(snapshot["data_as_of"]),
            ),
        )
    return get_demo_case(settings, case_id)


def list_demo_cases(settings: Settings) -> list[dict[str, object]]:
    init_db(settings)
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT * FROM demo_reliability_cases
            ORDER BY CASE role WHEN 'main' THEN 1 WHEN 'backup' THEN 2 ELSE 3 END
            """
        ).fetchall()
    return [_case_payload(settings, row) for row in rows]


def get_demo_case(settings: Settings, case_id: str) -> dict[str, object]:
    init_db(settings)
    with connection(settings) as conn:
        row = conn.execute(
            "SELECT * FROM demo_reliability_cases WHERE id = ? OR role = ?",
            (str(case_id), str(case_id)),
        ).fetchone()
    if row is None:
        raise ValueError("demo reliability case not found")
    return _case_payload(settings, row)


def run_demo_rehearsal(
    settings: Settings,
    *,
    case_id: object,
    requested_mode: object = "live",
    browser_online: object = True,
    viewport_width: object = 1440,
    viewport_height: object = 900,
    scenario: object = "standard",
    actor: object = "judge",
) -> dict[str, object]:
    init_db(settings)
    case = get_demo_case(settings, _controlled_text(case_id, "case_id", 80))
    mode = str(requested_mode or "live").strip().lower()
    if mode not in MODES:
        raise ValueError(f"requested_mode must be one of: {', '.join(sorted(MODES))}")
    online = _bool_value(browser_online)
    width = _bounded_int(viewport_width, "viewport_width", 320, 7680)
    height = _bounded_int(viewport_height, "viewport_height", 320, 4320)
    scenario_text = _controlled_text(scenario, "scenario", 40)
    actor_text = _controlled_text(actor, "actor", 40)
    rehearsal_id = str(uuid4())
    started = perf_counter()
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO demo_rehearsals(
                id, case_id, requested_mode, actual_mode, scenario, status,
                browser_online, viewport_width, viewport_height, actor
            ) VALUES (?, ?, ?, '', ?, 'running', ?, ?, ?, ?)
            """,
            (
                rehearsal_id,
                case["id"],
                mode,
                scenario_text,
                int(online),
                width,
                height,
                actor_text,
            ),
        )

    events: list[dict[str, object]] = []

    def step(key: str, label: str, action: Callable[[], tuple[str, str, dict[str, object]]]):
        step_started = perf_counter()
        try:
            status, detail, receipt = action()
        except Exception as exc:  # recorded and returned as an auditable failed step
            status = "failed"
            detail = f"{type(exc).__name__}: {exc}"
            receipt = {}
        duration_ms = max(0, round((perf_counter() - step_started) * 1000))
        event = {
            "id": str(uuid4()),
            "rehearsal_id": rehearsal_id,
            "seq": len(events) + 1,
            "step_key": key,
            "label": label,
            "status": status,
            "duration_ms": duration_ms,
            "detail": detail,
            "receipt": receipt,
        }
        events.append(event)
        with connection(settings) as conn:
            conn.execute(
                """
                INSERT INTO demo_rehearsal_events(
                    id, rehearsal_id, seq, step_key, label, status,
                    duration_ms, detail, receipt_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["id"], rehearsal_id, event["seq"], key, label,
                    status, duration_ms, detail, json_dumps(receipt),
                ),
            )
        return status, receipt

    environment: dict[str, object] = {}
    selected: dict[str, object] = {}
    actual_mode = mode
    switch_reason = ""

    def environment_action():
        nonlocal environment
        environment = demo_environment_status(settings, browser_online=online)
        status = "passed" if environment["critical_ready"] else "failed"
        return status, str(environment["summary"]), {"checks": environment["checks"]}

    step("environment", "环境预检", environment_action)

    def integrity_action():
        verified = _verify_case_snapshot(case)
        replay = _verified_replay(settings, str(case["id"]), str(case["source_version"]))
        status = "passed" if verified and replay is not None else "failed"
        return status, "冻结快照与同版本真实回放可验证" if status == "passed" else "快照或回放校验失败", {
            "snapshot_verified": verified,
            "replay_verified": replay is not None,
        }

    step("integrity", "案例与回放完整性", integrity_action)

    def select_mode_action():
        nonlocal actual_mode, switch_reason, selected
        frozen = _json_object(case.get("snapshot"))
        replay = _verified_replay(settings, str(case["id"]), str(case["source_version"]))
        if mode == "verified_history":
            actual_mode = "verified_history"
            selected = frozen
        elif mode == "replay":
            if replay is None:
                raise ValueError("same-version verified replay is unavailable")
            actual_mode = "replay"
            selected = _json_object(replay["result_json"])
        elif not online:
            if replay is None:
                raise ValueError("browser is offline and no verified replay is available")
            actual_mode = "replay"
            switch_reason = "浏览器离线，已切换到同版本真实回放"
            selected = _json_object(replay["result_json"])
        else:
            try:
                current = _build_source_snapshot(
                    settings,
                    str(case["source_type"]),
                    str(case["source_id"]),
                )
                if str(current["source_version"]) == str(case["source_version"]):
                    actual_mode = "live"
                    selected = current
                else:
                    actual_mode = "verified_history"
                    switch_reason = "当前数据版本已变化，已打开冻结的已验证历史记录"
                    selected = frozen
            except Exception as exc:
                if replay is None:
                    raise
                actual_mode = "replay"
                switch_reason = f"实时读取失败，已切换到同版本真实回放：{type(exc).__name__}"
                selected = _json_object(replay["result_json"])
        if actual_mode != mode and not switch_reason:
            switch_reason = f"请求{mode}，实际使用{actual_mode}"
        return "passed", switch_reason or f"已打开{actual_mode}", {
            "requested_mode": mode,
            "actual_mode": actual_mode,
            "switch_reason": switch_reason,
            "data_as_of": selected.get("data_as_of"),
        }

    step("mode", "模式选择与故障切换", select_mode_action)

    def links_action():
        links = list(selected.get("action_links") or [])
        valid = [item for item in links if _safe_action_url(str(item.get("url") or ""))]
        return (
            "passed" if valid else "failed",
            f"{len(valid)} 个可重复入口可用" if valid else "没有可用的一键入口",
            {"links": valid},
        )

    step("actions", "关键动作入口", links_action)

    def projection_action():
        profile = _viewport_profile(width, height)
        return (
            "passed" if profile else "failed",
            f"目标投屏 {width}×{height} · {profile or '未支持'}",
            {"profile": profile, "width": width, "height": height},
        )

    step("projection", "投屏规格", projection_action)

    opened_in_ms = max(0, round((perf_counter() - started) * 1000))
    passed = all(item["status"] == "passed" for item in events) and opened_in_ms < 10_000
    with connection(settings) as conn:
        conn.execute(
            """
            UPDATE demo_rehearsals
            SET actual_mode = ?, switch_reason = ?, status = ?, opened_in_ms = ?,
                completed_at = datetime('now')
            WHERE id = ?
            """,
            (
                actual_mode,
                switch_reason,
                "passed" if passed else "failed",
                opened_in_ms,
                rehearsal_id,
            ),
        )
    return {
        "rehearsal": get_demo_rehearsal(settings, rehearsal_id),
        "case": case,
        "display": _display_snapshot(selected),
        "environment": environment,
        "target_open_ms": 10_000,
    }


def get_demo_rehearsal(settings: Settings, rehearsal_id: str) -> dict[str, object]:
    with connection(settings) as conn:
        row = conn.execute(
            "SELECT * FROM demo_rehearsals WHERE id = ?",
            (str(rehearsal_id),),
        ).fetchone()
        if row is None:
            raise ValueError("demo rehearsal not found")
        events = conn.execute(
            "SELECT * FROM demo_rehearsal_events WHERE rehearsal_id = ? ORDER BY seq",
            (str(rehearsal_id),),
        ).fetchall()
    return _rehearsal_payload(row, events)


def list_demo_rehearsals(settings: Settings, *, limit: int = 20) -> list[dict[str, object]]:
    bounded = max(1, min(int(limit), 100))
    with connection(settings) as conn:
        rows = conn.execute(
            "SELECT * FROM demo_rehearsals ORDER BY started_at DESC, rowid DESC LIMIT ?",
            (bounded,),
        ).fetchall()
        result = []
        for row in rows:
            events = conn.execute(
                "SELECT * FROM demo_rehearsal_events WHERE rehearsal_id = ? ORDER BY seq",
                (str(row["id"]),),
            ).fetchall()
            result.append(_rehearsal_payload(row, events))
    return result


def record_demo_layout_audit(
    settings: Settings,
    *,
    profile: object,
    viewport_width: object,
    viewport_height: object,
    scroll_width: object,
    critical_overflows: object,
    user_agent: object = "",
) -> dict[str, object]:
    profile_text = str(profile or "").strip()
    if profile_text not in VIEWPORT_PROFILES:
        raise ValueError(f"profile must be one of: {', '.join(VIEWPORT_PROFILES)}")
    width = _bounded_int(viewport_width, "viewport_width", 320, 7680)
    height = _bounded_int(viewport_height, "viewport_height", 320, 4320)
    expected = VIEWPORT_PROFILES[profile_text]
    if (width, height) != expected:
        raise ValueError("viewport dimensions do not match the selected profile")
    measured_scroll = _bounded_int(scroll_width, "scroll_width", 0, 20000)
    overflows = [str(item)[:120] for item in critical_overflows] if isinstance(critical_overflows, list) else []
    status = "passed" if measured_scroll <= width and not overflows else "failed"
    audit_id = str(uuid4())
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO demo_layout_audits(
                id, profile, viewport_width, viewport_height, scroll_width,
                critical_overflows_json, status, user_agent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                audit_id,
                profile_text,
                width,
                height,
                measured_scroll,
                json_dumps(overflows),
                status,
                _controlled_text(user_agent, "user_agent", 300, required=False),
            ),
        )
    return {
        "id": audit_id,
        "profile": profile_text,
        "viewport_width": width,
        "viewport_height": height,
        "scroll_width": measured_scroll,
        "critical_overflows": overflows,
        "status": status,
        "measurement": "same_origin_browser_dom",
    }


def list_demo_layout_audits(settings: Settings) -> list[dict[str, object]]:
    init_db(settings)
    items: list[dict[str, object]] = []
    with connection(settings) as conn:
        for profile, (width, height) in VIEWPORT_PROFILES.items():
            row = conn.execute(
                """
                SELECT * FROM demo_layout_audits
                WHERE profile = ? ORDER BY created_at DESC, rowid DESC LIMIT 1
                """,
                (profile,),
            ).fetchone()
            items.append(
                {
                    "profile": profile,
                    "viewport_width": width,
                    "viewport_height": height,
                    "status": str(row["status"]) if row else "not_checked",
                    "scroll_width": int(row["scroll_width"] or 0) if row else 0,
                    "critical_overflows": _json_list(row["critical_overflows_json"]) if row else [],
                    "measurement": "same_origin_browser_dom" if row else "",
                    "user_agent_present": bool(str(row["user_agent"] or "")) if row else False,
                    "created_at": str(row["created_at"]) if row else "",
                }
            )
    return items


def demo_environment_status(
    settings: Settings,
    *,
    browser_online: bool | None = None,
) -> dict[str, object]:
    init_db(settings)
    checks: list[dict[str, object]] = []
    checks.append(_check("service", "本地服务", "ready", "API运行中，静态页面可由当前进程提供"))
    try:
        with connection(settings) as conn:
            quick_check = str(conn.execute("PRAGMA quick_check").fetchone()[0])
            notice_count = int(conn.execute("SELECT COUNT(*) FROM notices").fetchone()[0])
            latest_index = str(
                conn.execute("SELECT COALESCE(MAX(last_seen_at), '') FROM notices").fetchone()[0]
                or ""
            )
        checks.append(_check("database", "SQLite数据库", "ready" if quick_check == "ok" else "blocked", f"quick_check={quick_check}"))
        checks.append(_check("local_index", "本地证据索引", "ready" if notice_count else "blocked", f"{notice_count} 条公告 · 最近索引 {latest_index or '无'}"))
    except Exception as exc:
        notice_count = 0
        checks.append(_check("database", "SQLite数据库", "blocked", f"{type(exc).__name__}: {exc}"))
        checks.append(_check("local_index", "本地证据索引", "blocked", "数据库不可读"))

    health = source_health(settings)
    health_counts = {
        status: sum(item.get("health_status") == status for item in health.values())
        for status in ("healthy", "degraded", "unhealthy", "unknown")
    }
    source_status = "ready" if health_counts["healthy"] else "attention" if notice_count else "blocked"
    checks.append(_check(
        "sources",
        "公开数据源",
        source_status,
        f"健康 {health_counts['healthy']} · 降级 {health_counts['degraded']} · 异常 {health_counts['unhealthy']} · 未观测 {health_counts['unknown']}",
    ))

    feishu = feishu_status(settings).to_dict()
    listener = feishu_listener_status(settings)
    feishu_ready = bool(feishu.get("configured") and listener.get("running"))
    feishu_status_text = "ready" if feishu_ready else "attention"
    checks.append(_check(
        "feishu",
        "飞书连接",
        feishu_status_text,
        "消息应用与长连接运行中" if feishu_ready else "飞书不可用时演示自动使用本地证据与真实回放",
    ))

    if browser_online is None:
        checks.append(_check("browser", "浏览器网络", "client_check", "等待浏览器上报在线状态"))
    else:
        checks.append(_check(
            "browser",
            "浏览器网络",
            "ready" if browser_online else "attention",
            "在线，可执行实时动作" if browser_online else "离线，将使用同版本真实回放",
        ))

    critical_keys = {"service", "database", "local_index"}
    critical_ready = all(
        item["status"] == "ready" for item in checks if item["key"] in critical_keys
    )
    return {
        "status": "ready" if critical_ready else "blocked",
        "critical_ready": critical_ready,
        "checks": checks,
        "summary": f"核心检查 {'通过' if critical_ready else '未通过'}；外部依赖异常时可降级到本地回放",
        "source_health_counts": health_counts,
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def _build_source_snapshot(settings: Settings, source_type: str, source_id: str) -> dict[str, object]:
    if source_type == "live_challenge":
        challenge = get_live_challenge(settings, source_id)
        if str(challenge.get("status") or "") not in TERMINAL_CHALLENGE_STATUSES:
            raise ValueError("live challenge must be terminal before it can be frozen")
        results = list(challenge.get("results") or [])
        data_as_of = max(
            [str(item.get("indexed_at") or item.get("recorded_at") or "") for item in results]
            + [str(challenge.get("completed_at") or challenge.get("created_at") or "")]
        )
        evidence_kind = "public_record" if results and all(
            str(item.get("source_site") or "") != "demo"
            and "example.com" not in str(item.get("source_url") or "")
            for item in results
        ) else "controlled_fixture"
        action_links = [
            {"key": "challenge", "label": "打开评委挑战", "url": "/?view=challengeView"},
            *[
                {"key": f"source_{index}", "label": f"原文 {index}", "url": str(item.get("source_url") or "")}
                for index, item in enumerate(results[:5], start=1)
                if str(item.get("source_url") or "").startswith(("http://", "https://"))
            ],
        ]
        stable_challenge = dict(challenge)
        source_version = _sha256(_stable_json(stable_challenge))
        return _clean_json({
            "schema": "tendertrace_demo_snapshot_v1",
            "source_type": source_type,
            "source_id": source_id,
            "source_version": source_version,
            "data_as_of": data_as_of,
            "evidence_kind": evidence_kind,
            "captured_from_database": True,
            "synthetic": False,
            "request": {
                "category": challenge.get("category"),
                "region": challenge.get("region"),
                "time_window": challenge.get("time_window"),
                "keyword": challenge.get("keyword"),
            },
            "result": challenge,
            "action_links": action_links,
        })

    change_impact = get_change_impact(settings, source_id) or {}
    evidence = build_evidence_microscope(settings, source_id) or {}
    war_room = build_war_room_plan(settings, source_id)
    twin = build_digital_twin(settings, source_id)
    if twin is None:
        raise ValueError("opportunity not found")
    project = twin.get("project") if isinstance(twin.get("project"), dict) else {}
    source_url = str(project.get("source_url") or "")
    source_site = str(project.get("source_site") or "")
    evidence_kind = "controlled_fixture" if source_site == "demo" or "example.com" in source_url else "public_record"
    source_version = str((twin.get("snapshot") or {}).get("state_hash") or "")
    if not source_version:
        source_version = _sha256(_stable_json(twin))
    data_as_of = str((twin.get("refresh") or {}).get("data_as_of") or twin.get("generated_at") or "")
    action_links = [
        {"key": "digital_twin", "label": "打开项目数字档案", "url": f"/?view=opportunityView&opportunity={source_id}"},
    ]
    if source_url.startswith(("http://", "https://")):
        action_links.append({"key": "source", "label": "打开公告原文", "url": source_url})
    return _clean_json({
        "schema": "tendertrace_demo_snapshot_v1",
        "source_type": source_type,
        "source_id": source_id,
        "source_version": source_version,
        "data_as_of": data_as_of,
        "evidence_kind": evidence_kind,
        "captured_from_database": True,
        "synthetic": False,
        "request": {"notice_id": source_id},
        "result": {
            "digital_twin": twin,
            "change_impact": change_impact,
            "evidence_microscope": evidence,
            "war_room_plan": war_room,
        },
        "action_links": action_links,
    })


def _display_snapshot(snapshot: dict[str, object]) -> dict[str, object]:
    source_type = str(snapshot.get("source_type") or "")
    result = _json_object(snapshot.get("result"))
    if source_type == "live_challenge":
        results = list(result.get("results") or [])
        return {
            "source_type": source_type,
            "title": str(result.get("normalized_query") or "现场检索挑战"),
            "data_as_of": snapshot.get("data_as_of"),
            "evidence_kind": snapshot.get("evidence_kind"),
            "metrics": [
                {"label": "本地结果", "value": int(result.get("local_result_count") or 0)},
                {"label": "联网新增", "value": int(result.get("online_result_count") or 0)},
                {"label": "本地响应", "value": f"{int(result.get('local_duration_ms') or 0)} ms"},
            ],
            "items": [
                {
                    "title": item.get("title"),
                    "meta": f"{item.get('source_site') or ''} · {item.get('publish_time') or ''}",
                    "status": item.get("verification_status"),
                    "url": item.get("source_url"),
                }
                for item in results[:8]
            ],
            "action_links": snapshot.get("action_links") or [],
        }
    twin = _json_object(result.get("digital_twin"))
    counts = _json_object(twin.get("counts"))
    scores = _json_object(twin.get("scores"))
    change = _json_object(result.get("change_impact"))
    war_room = _json_object(result.get("war_room_plan"))
    return {
        "source_type": source_type,
        "title": str(twin.get("title") or "项目数字档案"),
        "data_as_of": snapshot.get("data_as_of"),
        "evidence_kind": snapshot.get("evidence_kind"),
        "metrics": [
            {"label": "招标要求", "value": int(counts.get("requirements") or 0)},
            {"label": "证据项", "value": int(counts.get("evidence_items") or 0)},
            {"label": "机会价值", "value": _score_value(scores.get("opportunity_value"))},
            {"label": "战情室预检", "value": f"{war_room.get('preflight_ready_count') or 0}/{len(war_room.get('preflight') or [])}"},
        ],
        "items": [
            {"title": "公告变更影响", "meta": str((change.get("summary") or {}).get("headline") or "已保存当前影响快照"), "status": "verified"},
            {"title": "证据显微镜", "meta": f"{counts.get('evidence_items') or 0} 个证据项", "status": "verified"},
            {"title": "飞书战情室", "meta": str(war_room.get("status") or "local_plan"), "status": "verified"},
        ],
        "action_links": snapshot.get("action_links") or [],
    }


def _case_payload(settings: Settings, row: Any) -> dict[str, object]:
    snapshot = _json_object(row["snapshot_json"])
    replay = _verified_replay(settings, str(row["id"]), str(row["source_version"]))
    return {
        "id": str(row["id"]),
        "role": str(row["role"]),
        "label": str(row["label"]),
        "source_type": str(row["source_type"]),
        "source_id": str(row["source_id"]),
        "source_version": str(row["source_version"]),
        "snapshot_hash": str(row["snapshot_hash"]),
        "data_as_of": str(row["data_as_of"]),
        "evidence_kind": str(row["evidence_kind"]),
        "verification_status": str(row["verification_status"]),
        "verified_at": str(row["verified_at"]),
        "created_by": str(row["created_by"]),
        "updated_at": str(row["updated_at"]),
        "snapshot_verified": _verify_case_snapshot({"snapshot": snapshot, "snapshot_hash": row["snapshot_hash"]}),
        "replay_verified": replay is not None,
        "replay_artifact_id": str(replay["id"]) if replay else "",
        "display": _display_snapshot(snapshot),
        "snapshot": snapshot,
    }


def _verified_replay(settings: Settings, case_id: str, source_version: str) -> Any | None:
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT * FROM demo_replay_artifacts
            WHERE case_id = ? AND source_version = ?
            ORDER BY verified_at DESC, rowid DESC
            """,
            (case_id, source_version),
        ).fetchall()
    for row in rows:
        if _sha256(str(row["result_json"])) == str(row["snapshot_hash"]):
            return row
    return None


def _verify_case_snapshot(case: dict[str, object]) -> bool:
    snapshot = _json_object(case.get("snapshot"))
    return bool(snapshot and _sha256(_stable_json(snapshot)) == str(case.get("snapshot_hash") or ""))


def _rehearsal_payload(row: Any, events: list[Any]) -> dict[str, object]:
    return {
        "id": str(row["id"]),
        "case_id": str(row["case_id"]),
        "requested_mode": str(row["requested_mode"]),
        "actual_mode": str(row["actual_mode"]),
        "switch_reason": str(row["switch_reason"] or ""),
        "scenario": str(row["scenario"]),
        "status": str(row["status"]),
        "browser_online": bool(row["browser_online"]),
        "viewport_width": int(row["viewport_width"] or 0),
        "viewport_height": int(row["viewport_height"] or 0),
        "opened_in_ms": int(row["opened_in_ms"] or 0),
        "actor": str(row["actor"]),
        "started_at": str(row["started_at"]),
        "completed_at": str(row["completed_at"] or ""),
        "events": [
            {
                "seq": int(event["seq"]),
                "step_key": str(event["step_key"]),
                "label": str(event["label"]),
                "status": str(event["status"]),
                "duration_ms": int(event["duration_ms"] or 0),
                "detail": str(event["detail"] or ""),
                "receipt": _json_object(event["receipt_json"]),
            }
            for event in events
        ],
    }


def _check(key: str, label: str, status: str, detail: str) -> dict[str, object]:
    return {"key": key, "label": label, "status": status, "detail": detail}


def _viewport_profile(width: int, height: int) -> str:
    for profile, dimensions in VIEWPORT_PROFILES.items():
        if dimensions == (width, height):
            return profile
    return ""


def _safe_action_url(value: str) -> bool:
    return bool(value.startswith("/") or value.startswith("http://") or value.startswith("https://"))


def _score_value(value: object) -> int:
    if isinstance(value, dict):
        return int(value.get("score") or value.get("value") or 0)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _controlled_text(value: object, field: str, max_length: int, *, required: bool = True) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if required and not text:
        raise ValueError(f"{field} is required")
    if len(text) > max_length:
        raise ValueError(f"{field} is too long")
    if any(ord(char) < 32 for char in text):
        raise ValueError(f"{field} contains control characters")
    return text


def _bounded_int(value: object, field: str, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if not minimum <= parsed <= maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return parsed


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off", ""}


def _stable_json(value: object) -> str:
    return json.dumps(
        _clean_json(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _clean_json(value: object) -> Any:
    sanitized = sanitize_for_output(value)
    return json.loads(json.dumps(sanitized, ensure_ascii=False, default=str))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_object(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []
