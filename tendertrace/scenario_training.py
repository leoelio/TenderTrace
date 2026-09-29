from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
import re
from typing import Any
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps
from tendertrace.integrations.feishu import FeishuClient, FeishuError


SCORING_VERSION = "training-rubric-v1"
PHASES = ("opening", "fundamentals", "evidence", "change", "action", "summary")
MODES = {"learning", "preparation"}
DIFFICULTIES = {"guided", "standard", "pressure"}
SCENARIO_TYPES = {
    "roadshow_pitch": "七分钟脱稿答辩",
    "technical_clarification": "技术标澄清",
    "correction_response": "更正公告应急",
    "partner_negotiation": "合作方风险谈判",
}
DIMENSIONS = {
    "fact_accuracy": "事实准确",
    "evidence_citation": "证据引用",
    "risk_awareness": "风险意识",
    "action_completeness": "行动完整",
    "expression_clarity": "表达清晰",
}
ABSOLUTE_CLAIMS = ("完全满足", "百分之百", "肯定", "一定能", "没有风险", "毫无风险", "已经影响")
UNCERTAINTY_WORDS = ("待核验", "当前证据", "尚未确认", "可能", "需复核", "不等于", "边界")
RISK_WORDS = ("风险", "缺口", "变更", "冲突", "不确定", "待核验", "依赖", "逾期")
ACTION_WORDS = ("负责人", "截止", "核验", "重排", "复核", "提交", "确认", "同步", "任务")
EVIDENCE_PATTERN = re.compile(r"(?:NOTICE|REQ|REV|EVID|COMPANY):[A-Za-z0-9_.:-]+")


def seed_default_training_scenarios(
    settings: Settings,
    *,
    actor: str = "training-curator",
) -> dict[str, object]:
    """Create four approved scenarios from at least three real local notices."""
    init_db(settings)
    actor = _required(actor, "actor", 80)
    with connection(settings) as conn:
        notices = _select_case_notices(conn)
        if len(notices) < 3:
            raise ValueError("at least three real notices are required to seed training scenarios")
        assignments = (
            ("roadshow_pitch", notices[0]),
            ("technical_clarification", notices[1]),
            ("correction_response", notices[2]),
            ("partner_negotiation", notices[3] if len(notices) > 3 else notices[0]),
        )
        created = 0
        for scenario_type, notice in assignments:
            snapshot = _notice_snapshot(conn, notice)
            scenario_key = f"direction18:{scenario_type}:{notice['id']}"
            scenario_id = hashlib.sha256(scenario_key.encode()).hexdigest()[:24]
            questions = _build_questions(scenario_type, snapshot)
            before = conn.total_changes
            conn.execute(
                """
                INSERT INTO training_scenarios(
                    id, notice_id, scenario_key, title, project_alias, scenario_type,
                    target_roles_json, allowed_modes_json, difficulty, estimated_minutes,
                    state_machine_json, questions_json, source_snapshot_json,
                    approval_status, approved_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'standard', 7, ?, ?, ?, 'approved', ?)
                ON CONFLICT(scenario_key) DO UPDATE SET
                    title = excluded.title,
                    project_alias = excluded.project_alias,
                    target_roles_json = excluded.target_roles_json,
                    state_machine_json = excluded.state_machine_json,
                    questions_json = excluded.questions_json,
                    source_snapshot_json = excluded.source_snapshot_json,
                    approval_status = 'approved',
                    approved_by = excluded.approved_by,
                    approved_at = datetime('now'),
                    updated_at = datetime('now')
                """,
                (
                    scenario_id,
                    str(notice["id"]),
                    scenario_key,
                    SCENARIO_TYPES[scenario_type],
                    _project_alias(notice, scenario_type),
                    scenario_type,
                    json_dumps(_target_roles(scenario_type)),
                    json_dumps(["learning", "preparation"]),
                    json_dumps(list(PHASES)),
                    json_dumps(questions),
                    json_dumps(snapshot),
                    actor,
                ),
            )
            created += int(conn.total_changes > before)
            for question in questions:
                rubric_id = hashlib.sha256(
                    f"{scenario_id}|{question['id']}|{SCORING_VERSION}".encode()
                ).hexdigest()[:24]
                conn.execute(
                    """
                    INSERT INTO training_rubrics(
                        id, scenario_id, question_id, version, target_competency,
                        reference_facts_json, allowed_evidence_json, scoring_rules_json,
                        follow_up_conditions_json, stop_conditions_json, approved_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(scenario_id, question_id, version) DO UPDATE SET
                        target_competency = excluded.target_competency,
                        reference_facts_json = excluded.reference_facts_json,
                        allowed_evidence_json = excluded.allowed_evidence_json,
                        scoring_rules_json = excluded.scoring_rules_json,
                        follow_up_conditions_json = excluded.follow_up_conditions_json,
                        stop_conditions_json = excluded.stop_conditions_json,
                        approved_by = excluded.approved_by,
                        approved_at = datetime('now')
                    """,
                    (
                        rubric_id,
                        scenario_id,
                        str(question["id"]),
                        SCORING_VERSION,
                        str(question["competency"]),
                        json_dumps(question["reference_facts"]),
                        json_dumps(question["allowed_evidence"]),
                        json_dumps(question["scoring_rules"]),
                        json_dumps(question["follow_up_conditions"]),
                        json_dumps(question["stop_conditions"]),
                        actor,
                    ),
                )
    return {
        "created_or_updated": created,
        "scenario_count": 4,
        "project_count": len({str(item[1]["id"]) for item in assignments}),
        "scenario_types": list(SCENARIO_TYPES),
        "scoring_version": SCORING_VERSION,
    }


def list_training_scenarios(settings: Settings) -> dict[str, object]:
    init_db(settings)
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT scenario.*, notice.source_url
            FROM training_scenarios scenario
            JOIN notices notice ON notice.id = scenario.notice_id
            WHERE scenario.approval_status = 'approved'
            ORDER BY scenario.created_at, scenario.scenario_type
            """
        ).fetchall()
    items = [_scenario_payload(row, include_questions=False) for row in rows]
    return {
        "items": items,
        "count": len(items),
        "project_count": len({str(item["notice_id"]) for item in items}),
        "scenario_type_count": len({str(item["scenario_type"]) for item in items}),
        "rules": _rules_payload(),
    }


def get_training_scenario(settings: Settings, scenario_id: str) -> dict[str, object]:
    init_db(settings)
    with connection(settings) as conn:
        row = conn.execute(
            """
            SELECT scenario.*, notice.source_url
            FROM training_scenarios scenario
            JOIN notices notice ON notice.id = scenario.notice_id
            WHERE scenario.id = ?
            """,
            (str(scenario_id),),
        ).fetchone()
    if row is None:
        raise LookupError("training scenario not found")
    return _scenario_payload(row, include_questions=True)


def create_training_session(
    settings: Settings,
    scenario_id: str,
    *,
    mode: str,
    role: str,
    difficulty: str = "standard",
    participant_key: str = "local-user",
    participant_display: str = "本地学员",
    sample_kind: str = "live",
) -> dict[str, object]:
    scenario = get_training_scenario(settings, scenario_id)
    mode = str(mode).strip().lower()
    difficulty = str(difficulty).strip().lower()
    if mode not in MODES:
        raise ValueError("mode must be learning or preparation")
    if difficulty not in DIFFICULTIES:
        raise ValueError("difficulty must be guided, standard, or pressure")
    role = _required(role, "role", 80)
    participant_key = _required(participant_key, "participant_key", 120)
    participant_display = _required(participant_display, "participant_display", 80)
    if role not in scenario["target_roles"]:
        raise ValueError("role is not approved for this scenario")
    if sample_kind not in {"live", "approved_transcript", "manual_validation"}:
        raise ValueError("unsupported sample_kind")
    session_id = str(uuid4())
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO training_sessions(
                id, scenario_id, notice_id, mode, role, difficulty,
                participant_key, participant_display, sample_kind, scoring_version,
                source_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                scenario_id,
                str(scenario["notice_id"]),
                mode,
                role,
                difficulty,
                participant_key,
                participant_display,
                sample_kind,
                SCORING_VERSION,
                _stable_hash(scenario["source_snapshot"]),
            ),
        )
    return get_training_session(settings, session_id, participant_key=participant_key)


def begin_training_session(
    settings: Settings,
    session_id: str,
    *,
    participant_key: str,
) -> dict[str, object]:
    with connection(settings) as conn:
        session = _owned_session(conn, session_id, participant_key)
        if str(session["status"]) not in {"ready", "active"}:
            raise ValueError("training session cannot be started")
        if str(session["status"]) == "ready":
            questions = _scenario_questions(conn, str(session["scenario_id"]))
            conn.execute(
                """
                UPDATE training_sessions
                SET status = 'active', current_phase = 'opening', current_question_index = 0,
                    started_at = datetime('now'), updated_at = datetime('now')
                WHERE id = ?
                """,
                (session_id,),
            )
            _insert_turn(conn, session_id, 1, questions[0])
    return get_training_session(settings, session_id, participant_key=participant_key)


def get_training_hint(
    settings: Settings,
    session_id: str,
    *,
    participant_key: str,
) -> dict[str, object]:
    with connection(settings) as conn:
        session = _owned_session(conn, session_id, participant_key)
        if str(session["mode"]) != "learning":
            raise ValueError("hints are available only in learning mode")
        turn = _open_turn(conn, session_id)
        if turn is None:
            raise ValueError("there is no active question")
        question = _question_by_id(conn, str(session["scenario_id"]), str(turn["question_id"]))
        hints = list(question.get("hints") or [])
        level = min(int(turn["hint_level"]) + 1, len(hints))
        conn.execute("UPDATE training_turns SET hint_level = ? WHERE id = ?", (level, turn["id"]))
    return {
        "session_id": session_id,
        "question_id": str(turn["question_id"]),
        "hint_level": level,
        "hint": hints[level - 1] if level else "暂无更多提示",
        "reference_revealed": level >= len(hints) and bool(hints),
    }


def submit_training_answer(
    settings: Settings,
    session_id: str,
    *,
    participant_key: str,
    answer: str,
    evidence_refs: list[str] | None = None,
    model_evaluation: dict[str, object] | None = None,
) -> dict[str, object]:
    answer = _required(answer, "answer", 5000)
    submitted_refs = [str(item).strip() for item in (evidence_refs or []) if str(item).strip()]
    submitted_refs.extend(EVIDENCE_PATTERN.findall(answer))
    submitted_refs = list(dict.fromkeys(submitted_refs))
    with connection(settings) as conn:
        session = _owned_session(conn, session_id, participant_key)
        if str(session["status"]) != "active":
            raise ValueError("training session is not active")
        turn = _open_turn(conn, session_id)
        if turn is None:
            raise ValueError("there is no active question")
        question = _question_by_id(conn, str(session["scenario_id"]), str(turn["question_id"]))
        allowed = {str(item["id"]) for item in question.get("allowed_evidence", [])}
        valid_refs = [item for item in submitted_refs if item in allowed]
        score = _score_answer(answer, question, valid_refs)
        model_payload = _model_evaluation_payload(model_evaluation, score)
        feedback = _feedback_payload(
            answer,
            question,
            score,
            valid_refs,
            mode=str(session["mode"]),
        )
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        conn.execute(
            """
            UPDATE training_turns
            SET answer = ?, first_answer = CASE WHEN first_answer = '' THEN ? ELSE first_answer END,
                evidence_refs_json = ?, rule_score_json = ?, model_evaluation_json = ?,
                feedback_json = ?, answered_at = ?
            WHERE id = ? AND answered_at IS NULL
            """,
            (
                answer,
                answer,
                json_dumps(valid_refs),
                json_dumps(score),
                json_dumps(model_payload),
                json_dumps(feedback),
                now,
                turn["id"],
            ),
        )
        questions = _scenario_questions(conn, str(session["scenario_id"]))
        current_index = int(session["current_question_index"])
        requires_follow_up = bool(feedback["follow_up_required"])
        is_follow_up = str(turn["question_id"]).endswith(":followup")
        if requires_follow_up and not is_follow_up:
            follow_up = dict(question)
            follow_up["id"] = f"{question['id']}:followup"
            follow_up["phase"] = "evidence"
            follow_up["prompt"] = str(question["follow_up_conditions"]["prompt"])
            next_sequence = int(turn["sequence"]) + 1
            _insert_turn(conn, session_id, next_sequence, follow_up)
            conn.execute(
                "UPDATE training_sessions SET current_phase = 'evidence', updated_at = datetime('now') WHERE id = ?",
                (session_id,),
            )
        else:
            next_index = current_index + 1
            if next_index >= len(questions):
                conn.execute(
                    """
                    UPDATE training_sessions
                    SET status = 'completed', current_phase = 'summary',
                        current_question_index = ?, finished_at = datetime('now'),
                        updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (len(questions), session_id),
                )
                _finalize_result(conn, session_id)
            else:
                next_question = questions[next_index]
                next_sequence = int(turn["sequence"]) + 1
                _insert_turn(conn, session_id, next_sequence, next_question)
                conn.execute(
                    """
                    UPDATE training_sessions
                    SET current_phase = ?, current_question_index = ?, updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (str(next_question["phase"]), next_index, session_id),
                )
    return get_training_session(settings, session_id, participant_key=participant_key)


def get_training_session(
    settings: Settings,
    session_id: str,
    *,
    participant_key: str,
    manager: bool = False,
) -> dict[str, object]:
    init_db(settings)
    with connection(settings) as conn:
        if manager:
            row = conn.execute("SELECT * FROM training_sessions WHERE id = ?", (session_id,)).fetchone()
            if row is None:
                raise LookupError("training session not found")
        else:
            row = _owned_session(conn, session_id, participant_key)
        scenario = conn.execute(
            "SELECT * FROM training_scenarios WHERE id = ?", (row["scenario_id"],)
        ).fetchone()
        turns = conn.execute(
            "SELECT * FROM training_turns WHERE session_id = ? ORDER BY sequence", (session_id,)
        ).fetchall()
        result = conn.execute(
            "SELECT * FROM training_results WHERE session_id = ?", (session_id,)
        ).fetchone()
    assert scenario is not None
    questions = _json_list(scenario["questions_json"])
    current = next((item for item in reversed(turns) if item["answered_at"] is None), None)
    return {
        "id": str(row["id"]),
        "scenario_id": str(row["scenario_id"]),
        "notice_id": str(row["notice_id"]),
        "scenario_title": str(scenario["title"]),
        "project_alias": str(scenario["project_alias"]),
        "mode": str(row["mode"]),
        "role": str(row["role"]),
        "difficulty": str(row["difficulty"]),
        "participant_display": str(row["participant_display"]),
        "sample_kind": str(row["sample_kind"]),
        "status": str(row["status"]),
        "current_phase": str(row["current_phase"]),
        "current_question_index": int(row["current_question_index"]),
        "question_count": len(questions),
        "scoring_version": str(row["scoring_version"]),
        "started_at": str(row["started_at"] or ""),
        "finished_at": str(row["finished_at"] or ""),
        "current_question": _turn_payload(current, mode=str(row["mode"])) if current else None,
        "turns": [_turn_payload(item, mode=str(row["mode"])) for item in turns],
        "result": _result_payload(result) if result else None,
        "privacy": {
            "personal_result_isolated": True,
            "manager_sees_team_aggregate": True,
            "not_for_performance_decision": True,
        },
        "formal_project_read_only": True,
    }


def list_training_sessions(
    settings: Settings,
    *,
    participant_key: str,
    manager: bool = False,
    limit: int = 50,
) -> dict[str, object]:
    init_db(settings)
    with connection(settings) as conn:
        if manager:
            rows = conn.execute(
                "SELECT * FROM training_sessions ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 200)),)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM training_sessions WHERE participant_key = ? ORDER BY created_at DESC LIMIT ?",
                (participant_key, max(1, min(limit, 200))),
            ).fetchall()
    return {
        "items": [
            {
                "id": str(row["id"]),
                "scenario_id": str(row["scenario_id"]),
                "mode": str(row["mode"]),
                "role": str(row["role"]),
                "status": str(row["status"]),
                "participant_display": str(row["participant_display"]),
                "created_at": str(row["created_at"]),
                "finished_at": str(row["finished_at"] or ""),
            }
            for row in rows
        ],
        "count": len(rows),
        "scope": "team" if manager else "personal",
    }


def team_training_readiness(settings: Settings) -> dict[str, object]:
    init_db(settings)
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT result.dimension_scores_json, result.weaknesses_json,
                   result.total_score, session.participant_key, session.sample_kind
            FROM training_results result
            JOIN training_sessions session ON session.id = result.session_id
            WHERE session.sample_kind IN ('live', 'manual_validation')
            """
        ).fetchall()
    dimensions = {key: [] for key in DIMENSIONS}
    weakness_counts: dict[str, int] = {}
    participants = set()
    for row in rows:
        participants.add(str(row["participant_key"]))
        scores = _json_object(row["dimension_scores_json"])
        for key in DIMENSIONS:
            dimensions[key].append(int(scores.get(key) or 0))
        for item in _json_list(row["weaknesses_json"]):
            label = str(item.get("label") if isinstance(item, dict) else item)
            weakness_counts[label] = weakness_counts.get(label, 0) + 1
    return {
        "participant_count": len(participants),
        "completed_session_count": len(rows),
        "dimension_averages": {
            key: round(sum(values) / len(values)) if values else None
            for key, values in dimensions.items()
        },
        "common_weaknesses": [
            {"label": label, "count": count}
            for label, count in sorted(weakness_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
        ],
        "privacy_note": "团队仅展示聚合薄弱点；个人成绩不作为绩效结论。",
        "sample_limit": "仅统计 live 与 manual_validation；自动基准样本不计入真人准备度。",
    }


def sync_training_remediation_task(
    settings: Settings,
    result_id: str,
    task_id: str,
    *,
    assignee_open_id: str = "",
    client: FeishuClient | None = None,
) -> dict[str, object]:
    with connection(settings) as conn:
        row = conn.execute(
            """
            SELECT result.*, session.participant_display, scenario.title scenario_title
            FROM training_results result
            JOIN training_sessions session ON session.id = result.session_id
            JOIN training_scenarios scenario ON scenario.id = session.scenario_id
            WHERE result.id = ?
            """,
            (result_id,),
        ).fetchone()
        if row is None:
            raise LookupError("training result not found")
        tasks = _json_list(row["remediation_tasks_json"])
        task = next((item for item in tasks if str(item.get("id")) == task_id), None)
        if task is None:
            raise LookupError("training remediation task not found")
        if task.get("feishu_task_guid"):
            return {"status": "reused", "task": task}
    feishu = client or FeishuClient(settings)
    due = datetime.now().astimezone() + timedelta(days=7)
    try:
        response = feishu.create_task(
            summary=f"训练补强：{task['title']}"[:3000],
            description="\n".join(
                (
                    f"训练场景：{row['scenario_title']}",
                    f"学员：{row['participant_display']}",
                    f"补强依据：{task['basis']}",
                    f"训练结果ID：{result_id}",
                )
            ),
            client_token=hashlib.sha256(f"tendertrace:training:{task_id}".encode()).hexdigest(),
            due_timestamp_ms=str(int(due.timestamp() * 1000)),
            assignee_open_id=assignee_open_id,
        )
        guid = _nested_string(response, "data", "task", "guid")
        if not guid:
            raise ValueError("Feishu training task guid is missing")
    except (FeishuError, ValueError, TypeError) as exc:
        raise ValueError(str(exc)) from exc
    task["feishu_task_guid"] = guid
    task["feishu_status"] = "open"
    task["feishu_receipt"] = response
    with connection(settings) as conn:
        conn.execute(
            "UPDATE training_results SET remediation_tasks_json = ?, updated_at = datetime('now') WHERE id = ?",
            (json_dumps(tasks), result_id),
        )
    return {"status": "created", "task": task}


def recompute_training_result(settings: Settings, result_id: str) -> dict[str, object]:
    with connection(settings) as conn:
        result = conn.execute("SELECT * FROM training_results WHERE id = ?", (result_id,)).fetchone()
        if result is None:
            raise LookupError("training result not found")
        turns = conn.execute(
            "SELECT * FROM training_turns WHERE session_id = ? AND answered_at IS NOT NULL ORDER BY sequence",
            (result["session_id"],),
        ).fetchall()
        computed = _aggregate_result(turns)
        replay = _json_object(result["replay_json"])
        expected_hash = _stable_hash(
            {
                "scoring_version": str(result["scoring_version"]),
                "scores": computed["scores"],
                "turns": replay.get("turns", []),
            }
        )
    return {
        "result_id": result_id,
        "identical": expected_hash == str(result["score_hash"]),
        "stored_hash": str(result["score_hash"]),
        "recomputed_hash": expected_hash,
        "dimension_scores": computed["scores"],
        "total_score": computed["total"],
        "scoring_version": str(result["scoring_version"]),
    }


def _select_case_notices(conn) -> list[Any]:
    preferred = (
        "pbc_procurement:04b40d52-b636-11f1-88d4-b4055dfb2cc6",
        "pbc_procurement:5e3fd78f-b64c-11f1-88d4-b4055dfb2cc6",
        "pbc_procurement:d6378ae8-b730-11f1-88d4-b4055dfb2cc6",
        "ggzy:0051eddfc588cedd4da698903cec566821e7",
        "ungm:ungm-314912",
    )
    rows = []
    seen = set()
    for notice_id in preferred:
        row = conn.execute(
            "SELECT * FROM notices WHERE id = ? AND source_site != 'demo'", (notice_id,)
        ).fetchone()
        if row is not None:
            rows.append(row)
            seen.add(str(row["id"]))
    fallback = conn.execute(
        """
        SELECT * FROM notices
        WHERE source_site != 'demo' AND length(coalesce(content_text, '')) > 0
        ORDER BY CASE WHEN title LIKE '%更正%' THEN 0 ELSE 1 END,
                 length(content_text) DESC, datetime(publish_time) DESC
        LIMIT 20
        """
    ).fetchall()
    for row in fallback:
        if str(row["id"]) not in seen:
            rows.append(row)
            seen.add(str(row["id"]))
    return rows[:5]


def _notice_snapshot(conn, notice) -> dict[str, object]:
    notice_id = str(notice["id"])
    requirements = conn.execute(
        """
        SELECT id, requirement_key, title, evidence_text, source_url, source_locator, status
        FROM opportunity_requirements
        WHERE notice_id = ? AND status != 'superseded'
        ORDER BY requirement_key LIMIT 12
        """,
        (notice_id,),
    ).fetchall()
    revision = conn.execute(
        "SELECT id, changed_fields_json, created_at FROM notice_revisions WHERE notice_id = ? ORDER BY created_at DESC LIMIT 1",
        (notice_id,),
    ).fetchone()
    evidence = [
        {
            "id": f"NOTICE:{notice_id}",
            "type": "notice",
            "label": "公告原文",
            "source_url": str(notice["source_url"] or ""),
            "locator": "公告正文",
        }
    ]
    evidence.extend(
        {
            "id": f"REQ:{row['id']}",
            "type": "requirement",
            "label": str(row["title"]),
            "source_url": str(row["source_url"] or notice["source_url"] or ""),
            "locator": str(row["source_locator"] or "要求拆解"),
        }
        for row in requirements
    )
    if revision is not None:
        evidence.append(
            {
                "id": f"REV:{revision['id']}",
                "type": "revision",
                "label": "最近公告版本变化",
                "source_url": str(notice["source_url"] or ""),
                "locator": str(revision["created_at"]),
            }
        )
    content = re.sub(r"\s+", " ", str(notice["content_text"] or notice["core_content"] or ""))
    return {
        "notice_id": notice_id,
        "source_site": str(notice["source_site"]),
        "source_url": str(notice["source_url"]),
        "title": str(notice["title"]),
        "region": str(notice["region"] or "未标明"),
        "purchaser": str(notice["purchaser"] or "采购人待核验"),
        "publish_time": str(notice["publish_time"] or ""),
        "content_excerpt": content[:1000],
        "requirements": [dict(row) for row in requirements],
        "revision": dict(revision) if revision is not None else None,
        "allowed_evidence": evidence,
        "captured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "real_notice": True,
        "anonymized_for_training": True,
    }


def _build_questions(scenario_type: str, snapshot: dict[str, object]) -> list[dict[str, object]]:
    title = str(snapshot["title"])
    region = str(snapshot["region"])
    purchaser = str(snapshot["purchaser"])
    evidence = list(snapshot["allowed_evidence"])
    notice_ref = str(evidence[0]["id"])
    common = {
        "allowed_evidence": evidence,
        "follow_up_conditions": {
            "absolute_claim_without_evidence": True,
            "prompt": f"你刚才给出了确定性结论。请引用允许范围内的证据编号（例如 {notice_ref}）；如果证据不足，请改成有边界的表述。",
        },
        "stop_conditions": {"max_follow_ups": 1, "advance_after_supported_or_bounded_answer": True},
    }
    prompts = _question_templates(scenario_type, title, region, purchaser, notice_ref)
    questions = []
    for index, item in enumerate(prompts):
        question = {
            "id": f"{scenario_type}:q{index + 1}",
            "phase": PHASES[index],
            "prompt": item["prompt"],
            "competency": item["competency"],
            "reference_facts": item["reference_facts"],
            "hints": item["hints"],
            "scoring_rules": {
                "fact_groups": item["fact_groups"],
                "required_evidence_count": item.get("required_evidence_count", 1),
                "risk_keywords": item.get("risk_keywords", list(RISK_WORDS)),
                "action_groups": item.get("action_groups", [[word] for word in ACTION_WORDS[:3]]),
                "five_dimensions": list(DIMENSIONS),
                "deterministic": True,
            },
            **common,
        }
        questions.append(question)
    return questions


def _question_templates(
    scenario_type: str, title: str, region: str, purchaser: str, notice_ref: str
) -> list[dict[str, object]]:
    base = [
        {
            "prompt": f"请用三十秒说明“{_short(title, 38)}”为什么值得团队关注。",
            "competency": "项目价值表达",
            "reference_facts": [f"项目地区为{region}", f"采购人为{purchaser}", f"项目标题为{title}"],
            "fact_groups": [[region], [purchaser], _category_keywords(title)],
            "hints": ["先说采购对象、地区和采购人。", "再说明当前机会与证据边界。", f"可查看 {notice_ref} 的公告原文。"],
        },
        {
            "prompt": "请列出三个必须核验的项目事实，并说明哪些仍不能下确定结论。",
            "competency": "事实与边界识别",
            "reference_facts": ["采购对象、地区、采购人来自公告", "未核验字段不能说成已确认"],
            "fact_groups": [[region], [purchaser], ["采购", "项目", "标的"]],
            "hints": ["区分公告事实和团队判断。", "注意采购对象、时间和资格条件。", "使用“当前证据”“待核验”等边界词。"],
        },
        {
            "prompt": "请选择一条关键结论，给出对应证据编号、来源位置和仍需补证的内容。",
            "competency": "证据引用",
            "reference_facts": [f"允许证据包含 {notice_ref}", "证据编号必须可回到原文"],
            "fact_groups": [["证据", "原文", "公告"]],
            "required_evidence_count": 1,
            "hints": ["证据编号在允许资料范围中。", "说明原文位置和支持的结论。", f"可以从 {notice_ref} 开始。"],
        },
        {
            "prompt": "现在注入变化：截止时间提前五天。哪些判断会变化，哪些正式事实仍保持不变？",
            "competency": "变化应对",
            "reference_facts": ["截止时间变化需要重排任务", "模拟变化不能写回正式项目"],
            "fact_groups": [["五天", "提前"], ["正式", "不变", "原项目"]],
            "action_groups": [["重排", "调整"], ["负责人", "责任人"], ["截止", "时间"]],
            "hints": ["先分事实、影响和动作。", "检查资格、材料、评审和审批链。", "明确模拟不改变正式项目。"],
        },
        {
            "prompt": "请给出接下来三项行动，分别写明负责人、截止时间和验收证据。",
            "competency": "行动完整性",
            "reference_facts": ["行动需要负责人、截止时间和证据"],
            "fact_groups": [["三", "3"], ["负责人"], ["截止"]],
            "action_groups": [["负责人"], ["截止", "时间"], ["证据", "验收"]],
            "hints": ["每项行动用同一格式。", "写清谁、何时、交付什么。", "最后补充验收证据。"],
        },
        {
            "prompt": "请用一句结论、两条证据和一个风险边界完成最终总结。",
            "competency": "结构化总结",
            "reference_facts": ["结论、证据和风险边界必须同时出现"],
            "fact_groups": [["结论"], ["证据"], ["风险", "边界", "待核验"]],
            "action_groups": [["下一步", "行动", "核验"]],
            "hints": ["结论先行。", "引用两条允许证据。", "用一句话说明不能过度推断的边界。"],
        },
    ]
    if scenario_type == "technical_clarification":
        base[0]["prompt"] = "请以技术负责人身份说明本项目的采购对象、技术边界和首要澄清点。"
        base[3]["prompt"] = "客户临时要求扩容并保持业务不中断，你会追问哪三个技术条件？"
        base[4]["action_groups"] = [["容量", "规格"], ["兼容", "迁移"], ["验收", "测试"]]
    elif scenario_type == "correction_response":
        base[0]["prompt"] = "请以投标经理身份说明这次更正公告可能影响哪些工作，并先区分已知与未知。"
        base[1]["prompt"] = "更正前后至少需要核对哪三类字段？哪些变化必须触发人工确认？"
        base[3]["prompt"] = "现在确认截止时间提前五天，请指出必须立即重排的三项工作及依赖。"
        base[4]["action_groups"] = [["重排"], ["复核", "确认"], ["负责人", "截止"]]
    elif scenario_type == "partner_negotiation":
        base[0]["prompt"] = "请以合作谈判负责人身份说明为什么考虑该合作方，以及当前证据不能证明什么。"
        base[1]["prompt"] = "请列出签约前最需要核验的三类合作风险，并区分缺失信息与负面事实。"
        base[3]["prompt"] = "现在出现一条待复核的合作方风险信号，你会如何验证并控制谈判表述？"
        base[4]["action_groups"] = [["尽调", "核验"], ["合同", "条件"], ["负责人", "截止"]]
    return base


def _score_answer(answer: str, question: dict[str, object], valid_refs: list[str]) -> dict[str, object]:
    text = _normalize(answer)
    rules = dict(question.get("scoring_rules") or {})
    fact_groups = [list(group) for group in rules.get("fact_groups", [])]
    action_groups = [list(group) for group in rules.get("action_groups", [])]
    risk_keywords = [str(item) for item in rules.get("risk_keywords", [])]
    fact_hits = [_group_hit(text, group) for group in fact_groups]
    action_hits = [_group_hit(text, group) for group in action_groups]
    risk_hits = [item for item in risk_keywords if _normalize(item) in text]
    fact_score = round(100 * sum(fact_hits) / max(1, len(fact_hits)))
    required_refs = int(rules.get("required_evidence_count") or 0)
    evidence_score = 100 if len(valid_refs) >= max(1, required_refs) else (70 if required_refs == 0 else 0)
    risk_score = min(100, 30 + len(set(risk_hits)) * 18 + (20 if any(word in answer for word in UNCERTAINTY_WORDS) else 0))
    action_score = round(100 * sum(action_hits) / max(1, len(action_hits)))
    length_score = 100 if 60 <= len(answer) <= 800 else 75 if 30 <= len(answer) <= 1200 else 45
    structure_bonus = 0
    if any(marker in answer for marker in ("1.", "1、", "首先", "其次", "结论")):
        structure_bonus += 10
    if "。" in answer or ";" in answer or "；" in answer:
        structure_bonus += 10
    expression_score = min(100, length_score + structure_bonus)
    dimensions = {
        "fact_accuracy": fact_score,
        "evidence_citation": evidence_score,
        "risk_awareness": risk_score,
        "action_completeness": action_score,
        "expression_clarity": expression_score,
    }
    total = round(sum(dimensions.values()) / len(dimensions))
    return {
        "version": SCORING_VERSION,
        "dimensions": dimensions,
        "total": total,
        "basis": {
            "fact_groups_matched": sum(fact_hits),
            "fact_groups_total": len(fact_hits),
            "valid_evidence_refs": valid_refs,
            "risk_keywords_matched": sorted(set(risk_hits)),
            "action_groups_matched": sum(action_hits),
            "action_groups_total": len(action_hits),
            "answer_length": len(answer),
        },
        "deterministic": True,
    }


def _feedback_payload(
    answer: str,
    question: dict[str, object],
    score: dict[str, object],
    valid_refs: list[str],
    *,
    mode: str,
) -> dict[str, object]:
    absolute = any(item in answer for item in ABSOLUTE_CLAIMS)
    unsupported = absolute and not valid_refs
    evidence_required = int((question.get("scoring_rules") or {}).get("required_evidence_count") or 0) > 0
    missing_required_evidence = evidence_required and not valid_refs
    follow_up_required = unsupported or missing_required_evidence
    dimensions = dict(score["dimensions"])
    weak = [DIMENSIONS[key] for key, value in dimensions.items() if int(value) < 60]
    payload = {
        "follow_up_required": follow_up_required,
        "follow_up_reason": "确定性结论缺少允许证据" if unsupported else "本题要求引用证据" if missing_required_evidence else "",
        "correct_parts": [DIMENSIONS[key] for key, value in dimensions.items() if int(value) >= 80],
        "weak_dimensions": weak,
        "valid_evidence_refs": valid_refs,
        "scoring_basis_visible": True,
        "standard_answer_hidden": mode == "preparation",
    }
    if mode == "learning":
        payload["reference_facts"] = question.get("reference_facts", [])
        payload["allowed_evidence"] = question.get("allowed_evidence", [])
    return payload


def _model_evaluation_payload(
    candidate: dict[str, object] | None, rule_score: dict[str, object]
) -> dict[str, object]:
    if not candidate:
        return {"status": "not_used", "score_affects_result": False}
    rationale = _required(candidate.get("rationale"), "model rationale", 1200)
    confidence = max(0, min(int(candidate.get("confidence") or 0), 100))
    score = max(0, min(int(candidate.get("score") or 0), 100))
    conflict = abs(score - int(rule_score["total"])) > 25
    status = "pending_review" if confidence < 80 or conflict else "candidate"
    return {
        "status": status,
        "score": score,
        "confidence": confidence,
        "rationale": rationale,
        "conflict_with_rules": conflict,
        "score_affects_result": False,
    }


def _finalize_result(conn, session_id: str) -> None:
    session = conn.execute("SELECT * FROM training_sessions WHERE id = ?", (session_id,)).fetchone()
    turns = conn.execute(
        "SELECT * FROM training_turns WHERE session_id = ? AND answered_at IS NOT NULL ORDER BY sequence",
        (session_id,),
    ).fetchall()
    aggregated = _aggregate_result(turns)
    scores = aggregated["scores"]
    weaknesses = [
        {"key": key, "label": DIMENSIONS[key], "score": value}
        for key, value in scores.items()
        if int(value) < 70
    ]
    strengths = [
        {"key": key, "label": DIMENSIONS[key], "score": value}
        for key, value in scores.items()
        if int(value) >= 80
    ]
    tasks = [
        {
            "id": hashlib.sha256(f"{session_id}|{item['key']}".encode()).hexdigest()[:20],
            "dimension": item["key"],
            "title": f"补强{item['label']}",
            "basis": f"该维度当前得分 {item['score']}，建议复练相同场景并引用原证据。",
            "status": "open",
            "feishu_status": "not_requested",
        }
        for item in weaknesses
    ]
    replay_turns = [
        {
            "sequence": int(row["sequence"]),
            "phase": str(row["phase"]),
            "question_id": str(row["question_id"]),
            "prompt": str(row["prompt"]),
            "first_answer": str(row["first_answer"]),
            "evidence_refs": _json_list(row["evidence_refs_json"]),
            "score": _json_object(row["rule_score_json"]),
            "model_evaluation": _json_object(row["model_evaluation_json"]),
            "answered_at": str(row["answered_at"] or ""),
        }
        for row in turns
    ]
    replay = {
        "session_id": session_id,
        "scenario_id": str(session["scenario_id"]),
        "mode": str(session["mode"]),
        "role": str(session["role"]),
        "source_hash": str(session["source_hash"]),
        "turns": replay_turns,
        "formal_project_write_count": 0,
    }
    score_hash = _stable_hash(
        {"scoring_version": SCORING_VERSION, "scores": scores, "turns": replay_turns}
    )
    duration = 0
    if session["started_at"] and session["finished_at"]:
        try:
            duration = max(
                0,
                round(
                    (
                        datetime.fromisoformat(str(session["finished_at"]))
                        - datetime.fromisoformat(str(session["started_at"]))
                    ).total_seconds()
                ),
            )
        except ValueError:
            duration = 0
    result_id = hashlib.sha256(f"training-result|{session_id}".encode()).hexdigest()[:24]
    conn.execute(
        """
        INSERT INTO training_results(
            id, session_id, scoring_version, dimension_scores_json, total_score,
            readiness_level, strengths_json, weaknesses_json, remediation_tasks_json,
            replay_json, score_hash, model_review_status, duration_seconds
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            dimension_scores_json = excluded.dimension_scores_json,
            total_score = excluded.total_score,
            readiness_level = excluded.readiness_level,
            strengths_json = excluded.strengths_json,
            weaknesses_json = excluded.weaknesses_json,
            remediation_tasks_json = excluded.remediation_tasks_json,
            replay_json = excluded.replay_json,
            score_hash = excluded.score_hash,
            model_review_status = excluded.model_review_status,
            duration_seconds = excluded.duration_seconds,
            updated_at = datetime('now')
        """,
        (
            result_id,
            session_id,
            SCORING_VERSION,
            json_dumps(scores),
            aggregated["total"],
            _readiness_level(aggregated["total"]),
            json_dumps(strengths),
            json_dumps(weaknesses),
            json_dumps(tasks),
            json_dumps(replay),
            score_hash,
            "pending_review" if aggregated["model_pending"] else "not_used",
            duration,
        ),
    )


def _aggregate_result(turns) -> dict[str, object]:
    values = {key: [] for key in DIMENSIONS}
    model_pending = False
    for row in turns:
        rule = _json_object(row["rule_score_json"])
        dimensions = dict(rule.get("dimensions") or {})
        for key in DIMENSIONS:
            values[key].append(int(dimensions.get(key) or 0))
        model_pending = model_pending or _json_object(row["model_evaluation_json"]).get("status") == "pending_review"
    scores = {key: round(sum(items) / len(items)) if items else 0 for key, items in values.items()}
    return {"scores": scores, "total": round(sum(scores.values()) / len(scores)), "model_pending": model_pending}


def _scenario_payload(row, *, include_questions: bool) -> dict[str, object]:
    payload = {
        "id": str(row["id"]),
        "notice_id": str(row["notice_id"]),
        "title": str(row["title"]),
        "project_alias": str(row["project_alias"]),
        "scenario_type": str(row["scenario_type"]),
        "scenario_type_label": SCENARIO_TYPES.get(str(row["scenario_type"]), str(row["scenario_type"])),
        "target_roles": _json_list(row["target_roles_json"]),
        "allowed_modes": _json_list(row["allowed_modes_json"]),
        "difficulty": str(row["difficulty"]),
        "estimated_minutes": int(row["estimated_minutes"]),
        "state_machine": _json_list(row["state_machine_json"]),
        "source_snapshot": _json_object(row["source_snapshot_json"]),
        "approval_status": str(row["approval_status"]),
        "approved_by": str(row["approved_by"]),
        "source_url": str(row["source_url"] if "source_url" in row.keys() else ""),
        "question_count": len(_json_list(row["questions_json"])),
    }
    if include_questions:
        payload["questions"] = _json_list(row["questions_json"])
    return payload


def _turn_payload(row, *, mode: str) -> dict[str, object]:
    if row is None:
        return {}
    answered = bool(row["answered_at"])
    feedback = _json_object(row["feedback_json"])
    if mode == "preparation" and not answered:
        feedback = {}
    return {
        "id": str(row["id"]),
        "sequence": int(row["sequence"]),
        "phase": str(row["phase"]),
        "question_id": str(row["question_id"]),
        "prompt": str(row["prompt"]),
        "answer": str(row["answer"]),
        "first_answer": str(row["first_answer"]),
        "hint_level": int(row["hint_level"]),
        "evidence_refs": _json_list(row["evidence_refs_json"]),
        "rule_score": _json_object(row["rule_score_json"]),
        "model_evaluation": _json_object(row["model_evaluation_json"]),
        "feedback": feedback,
        "answered_at": str(row["answered_at"] or ""),
    }


def _result_payload(row) -> dict[str, object]:
    return {
        "id": str(row["id"]),
        "session_id": str(row["session_id"]),
        "scoring_version": str(row["scoring_version"]),
        "dimension_scores": _json_object(row["dimension_scores_json"]),
        "dimension_labels": DIMENSIONS,
        "total_score": int(row["total_score"]),
        "readiness_level": str(row["readiness_level"]),
        "strengths": _json_list(row["strengths_json"]),
        "weaknesses": _json_list(row["weaknesses_json"]),
        "remediation_tasks": _json_list(row["remediation_tasks_json"]),
        "replay": _json_object(row["replay_json"]),
        "score_hash": str(row["score_hash"]),
        "model_review_status": str(row["model_review_status"]),
        "duration_seconds": int(row["duration_seconds"]),
        "anonymized": bool(row["anonymized"]),
        "created_at": str(row["created_at"]),
    }


def _owned_session(conn, session_id: str, participant_key: str):
    row = conn.execute(
        "SELECT * FROM training_sessions WHERE id = ? AND participant_key = ?",
        (str(session_id), str(participant_key)),
    ).fetchone()
    if row is None:
        raise LookupError("training session not found")
    return row


def _open_turn(conn, session_id: str):
    return conn.execute(
        "SELECT * FROM training_turns WHERE session_id = ? AND answered_at IS NULL ORDER BY sequence DESC LIMIT 1",
        (session_id,),
    ).fetchone()


def _scenario_questions(conn, scenario_id: str) -> list[dict[str, object]]:
    row = conn.execute("SELECT questions_json FROM training_scenarios WHERE id = ?", (scenario_id,)).fetchone()
    if row is None:
        raise LookupError("training scenario not found")
    return [dict(item) for item in _json_list(row["questions_json"])]


def _question_by_id(conn, scenario_id: str, question_id: str) -> dict[str, object]:
    base_id = question_id.removesuffix(":followup")
    question = next((item for item in _scenario_questions(conn, scenario_id) if str(item["id"]) == base_id), None)
    if question is None:
        raise LookupError("training question not found")
    return question


def _insert_turn(conn, session_id: str, sequence: int, question: dict[str, object]) -> None:
    turn_id = hashlib.sha256(f"{session_id}|{sequence}|{question['id']}".encode()).hexdigest()[:24]
    conn.execute(
        """
        INSERT INTO training_turns(id, session_id, sequence, phase, question_id, prompt)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (turn_id, session_id, sequence, question["phase"], question["id"], question["prompt"]),
    )


def _rules_payload() -> dict[str, object]:
    return {
        "scoring_version": SCORING_VERSION,
        "state_machine": list(PHASES),
        "dimensions": DIMENSIONS,
        "formal_project_read_only": True,
        "model_score_affects_result": False,
        "low_confidence_requires_human_review": True,
        "preparation_hides_reference_answer": True,
        "voice_mode": "planned_after_hardware_validation",
    }


def _project_alias(notice, scenario_type: str) -> str:
    category = "服务器" if any(word in str(notice["title"]).lower() for word in ("服务器", "server")) else "采购"
    return f"{str(notice['region'] or '全国')}·{category}项目（脱敏）·{SCENARIO_TYPES[scenario_type]}"


def _target_roles(scenario_type: str) -> list[str]:
    return {
        "roadshow_pitch": ["主讲人", "项目负责人", "管理者"],
        "technical_clarification": ["技术负责人", "投标经理", "交付负责人"],
        "correction_response": ["投标经理", "法务", "项目负责人"],
        "partner_negotiation": ["销售", "法务", "合作负责人"],
    }[scenario_type]


def _category_keywords(title: str) -> list[str]:
    lower = title.lower()
    for words in (("服务器", "server"), ("物业", "保安"), ("软件", "许可"), ("设备", "采购")):
        if any(word in lower for word in words):
            return list(words)
    return ["项目", "采购"]


def _readiness_level(score: int) -> str:
    if score >= 85:
        return "ready"
    if score >= 70:
        return "nearly_ready"
    return "needs_practice"


def _group_hit(text: str, group: list[object]) -> int:
    return int(any(_normalize(str(item)) in text for item in group if str(item).strip()))


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _required(value: object, field: str, max_length: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        raise ValueError(f"{field} is required")
    if len(text) > max_length:
        raise ValueError(f"{field} is too long")
    return text


def _short(value: str, limit: int) -> str:
    return value if len(value) <= limit else f"{value[: limit - 1]}…"


def _stable_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _json_list(value: object) -> list[Any]:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _json_object(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _nested_string(payload: dict[str, Any], *path: str) -> str:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return ""
        value = value.get(key)
    return str(value or "")
