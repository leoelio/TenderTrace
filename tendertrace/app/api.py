from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import json
from pathlib import Path
import secrets
from threading import Thread
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx

from tendertrace.config import Settings
from tendertrace.db import connection, database_health, init_db
from tendertrace.digital_twin import build_digital_twin
from tendertrace.decision_sandbox import (
    compare_scenarios,
    decide_scenario_suggestion,
    get_decision_sandbox,
    promote_scenario,
    recompute_scenario,
    simulate_scenario,
)
from tendertrace.evidence_microscope import build_evidence_microscope, review_evidence
from tendertrace.change_impact_engine import (
    confirm_change_impact_action,
    dispatch_change_impact,
    get_change_impact,
)
from tendertrace.bid_workplan import (
    build_bid_workplan,
    complete_bid_task,
    confirm_requirement,
    export_bid_workplan,
    get_bid_workplan,
    merge_requirements,
    split_requirement,
    upsert_pricing_item,
)
from tendertrace.bid_memory import (
    archive_project_memory,
    decide_bid_memory_asset,
    get_bid_memory_dashboard,
)
from tendertrace.delivery.feishu_bitable import (
    check_feishu_bitable,
    update_opportunity_facts_in_bitable,
    update_opportunity_relationship_actions_in_bitable,
    update_opportunity_team_in_bitable,
    update_opportunity_stakeholders_in_bitable,
    update_opportunity_workflow_in_bitable,
)
from tendertrace.delivery.feishu_report import deliver_report_to_feishu
from tendertrace.delivery.ledger import list_delivery_attempts, record_delivery_attempt
from tendertrace.delivery.preferences import (
    load_feishu_receiver,
    resolve_feishu_receiver,
    save_feishu_receiver,
)
from tendertrace.evaluation import build_agent_evaluation_report
from tendertrace.gold import append_gold_notice, build_gold_coverage
from tendertrace.business_measurements import (
    business_measurement_summary,
    upsert_business_measurement,
)
from tendertrace.live_challenge import (
    begin_live_challenge_supplement,
    cancel_live_challenge_supplement,
    create_live_challenge,
    get_live_challenge,
    list_live_challenges,
    run_live_challenge_supplement,
)
from tendertrace.demo_reliability import (
    demo_reliability_overview,
    freeze_demo_case,
    get_demo_rehearsal,
    prepare_default_demo_cases,
    record_demo_layout_audit,
    run_demo_rehearsal,
)
from tendertrace.visual_system import record_visual_system_audit, visual_system_overview
from tendertrace.company_due_diligence import (
    add_authorized_external_evidence,
    add_company_evidence,
    add_company_relationship,
    aggregate_existing_company_data,
    ask_company_due_diligence,
    confirm_company_identity,
    create_company_due_diligence_task,
    create_company_entity,
    evaluate_company_risks,
    get_company_due_diligence_profile,
    latest_verified_company_snapshot,
    list_company_due_diligence_tasks,
    list_company_entities,
    resolve_company_candidates,
    review_company_evidence,
    save_company_due_diligence_snapshot,
    submit_due_diligence_review,
    subscribe_company_changes,
)
from tendertrace.integrations.feishu import (
    FeishuClient,
    FeishuError,
    feishu_chat_applink,
    feishu_agent_status,
    feishu_status,
)
from tendertrace.integrations.feishu_card_actions import (
    OpportunityNotFoundError,
    process_feishu_card_action,
)
from tendertrace.integrations.feishu_memory import build_memory_weekly_card
from tendertrace.integrations.feishu_notice_changes import send_opportunity_change_alerts
from tendertrace.integrations.feishu_opportunity import start_opportunity_collaboration
from tendertrace.integrations.feishu_war_room import (
    archive_war_room,
    build_war_room_plan,
    dispatch_war_room_changes,
    launch_war_room,
    retry_war_room_step,
    sync_war_room_back,
)
from tendertrace.integrations.feishu_relationship_actions import (
    create_relationship_action_task,
    sync_relationship_action_tasks,
)
from tendertrace.integrations.feishu_company_due_diligence import (
    sync_company_due_diligence_task,
)
from tendertrace.integrations.feishu_team import sync_opportunity_team
from tendertrace.integrations.feishu_source_alerts import (
    build_source_alert_snapshot,
    create_source_incident_task,
    send_source_health_alert,
)
from tendertrace.integrations.feishu_source_incidents import (
    ACTIVE_SOURCE_INCIDENT_STATUSES,
    list_source_incidents,
    sync_source_incidents,
)
from tendertrace.integrations.feishu_tasks import sync_feishu_tasks
from tendertrace.integrations.feishu_requirement_sync import (
    sync_bid_workplan_task_status,
    sync_bid_workplan_to_feishu,
    sync_requirement_completion_to_feishu,
    sync_requirement_task_status,
    sync_requirements_to_bitable,
    sync_requirements_to_feishu,
)
from tendertrace.integrations.feishu_leads import (
    import_partner_leads,
    list_feishu_lead_import_runs,
)
from tendertrace.integrations.feishu_briefing import send_opportunity_briefing
from tendertrace.integrations.feishu_escalation import (
    send_opportunity_escalation_summary,
)
from tendertrace.integrations.feishu_review_board import send_requirement_review_digest
from tendertrace.integrations.feishu_bot import (
    accept_feishu_message_event,
    feishu_long_connection_available,
    feishu_listener_status,
    list_feishu_message_events,
    pending_feishu_message_event_ids,
    process_feishu_message_event,
)
from tendertrace.intent import compile_intent
from tendertrace.llm.doctor import model_doctor
from tendertrace.llm.gateway import model_status
from tendertrace.memory import (
    build_weekly_report,
    load_memory_profile,
    persist_weekly_report,
    record_activity,
)
from tendertrace.memory_actions import apply_memory_advice_feedback
from tendertrace.notice_changes import list_notice_revisions
from tendertrace.notice_change_reviews import reviews_by_revision
from tendertrace.opportunity import (
    analyze_opportunity_with_market_context,
    get_opportunity,
    list_opportunities,
)
from tendertrace.opportunity_radar import build_opportunity_radar
from tendertrace.battle_map import (
    battle_map_event_detail,
    battle_map_revision,
    build_battle_map,
    evaluate_external_event_impacts,
    fetch_usgs_external_events,
    review_impact_link,
    save_battle_map_replay,
    sync_business_events,
)
from tendertrace.source_relation_graph import (
    build_source_relation_graph,
    decide_source_relation,
)
from tendertrace.scenario_training import (
    begin_training_session,
    create_training_session,
    get_training_hint,
    get_training_scenario,
    get_training_session,
    list_training_scenarios,
    list_training_sessions,
    recompute_training_result,
    seed_default_training_scenarios,
    submit_training_answer,
    sync_training_remediation_task,
    team_training_readiness,
)
from tendertrace.opportunity_facts import load_fact_audit, upsert_verified_facts
from tendertrace.opportunity_outcomes import record_outcome
from tendertrace.opportunity_collaboration import (
    list_collaboration_notes,
    record_collaboration_note,
)
from tendertrace.opportunity_requirements import (
    list_requirements,
    requirement_summary,
    upsert_requirement,
)
from tendertrace.capability_matching import (
    analyze_capability_matches,
    capability_match_summary,
    decide_capability_match,
    list_capabilities,
    list_requirement_capability_matches,
    upsert_capability,
)
from tendertrace.capability_passport import (
    build_capability_passport,
    complete_gap_action,
    create_gap_action,
    sync_project_results_to_passport,
)
from tendertrace.requirement_extraction import extract_and_save_requirements
from tendertrace.requirement_change_impact import requirement_change_impact
from tendertrace.requirement_review_board import (
    list_requirement_review_cases,
    requirement_review_summary,
    resolve_requirement_review_case,
    sync_requirement_review_cases,
)
from tendertrace.requirement_review_agents import (
    list_review_agent_runs,
    list_review_opinions,
    retry_review_agent,
    review_agent_runtime_summary,
    review_agent_suggestions,
    run_review_agents,
)
from tendertrace.requirement_review_human_opinions import (
    list_human_review_opinions,
    record_human_review_opinion,
)
from tendertrace.requirement_review_actions import (
    bind_review_action_to_requirement,
    complete_review_action,
    create_review_action,
    list_review_actions,
    review_action_summary,
)
from tendertrace.organization_memory import (
    OrganizationWorkspace,
    add_members as add_organization_members,
    create_workspace as create_organization_workspace,
    get_memory as get_organization_memory,
    get_workspace as get_organization_workspace,
    list_workspaces as list_organization_workspaces,
    record_memory as record_organization_memory,
    record_conversion as record_organization_memory_conversion,
    search_memories as search_organization_memories,
)
from tendertrace.vault.qianlima import QianlimaSessionVault
from tendertrace.opportunity_relationship_actions import (
    create_relationship_action,
    relationship_action as get_relationship_action,
    update_relationship_action,
)
from tendertrace.opportunity_team import remove_team_member, upsert_team_member
from tendertrace.opportunity_stakeholders import (
    remove_stakeholder,
    upsert_stakeholder,
)
from tendertrace.runlog import get_run, list_outbox_messages
from tendertrace.runner import run_once
from tendertrace.sanitize import sanitize_for_output, sanitize_stats
from tendertrace.runtime.checkpoint import SqliteCheckpointer
from tendertrace.runtime.trace import SqliteTraceStore
from tendertrace.scheduling.scheduler import (
    schedule_ingest_subscription,
    schedule_subscription,
    start_subscription_scheduler,
)
from tendertrace.scheduling.ingest_subscriptions import (
    create_ingest_subscription,
    delete_ingest_subscription,
    list_ingest_subscriptions,
    run_ingest_subscription,
)
from tendertrace.scheduling.subscriptions import (
    Subscription,
    create_subscription,
    list_subscriptions,
    run_subscription,
)
from tendertrace.source_map import build_source_map
from tendertrace.workflow import (
    WorkflowGateError,
    apply_action,
    get_workflow,
    update_workflow,
)


def create_app():
    try:
        from fastapi import Body, FastAPI, HTTPException, Request
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
    except ImportError as exc:
        raise RuntimeError(
            "FastAPI is not installed. Run: python -m pip install -e .[dev]"
        ) from exc

    settings = Settings.load()
    init_db(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.scheduler = None
        app.state.feishu_executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="feishu-bot",
        )
        if settings.scheduler_enabled:
            app.state.scheduler = start_subscription_scheduler(settings)
        for event_id in pending_feishu_message_event_ids(settings):
            app.state.feishu_executor.submit(
                process_feishu_message_event,
                settings,
                event_id,
                scheduler=app.state.scheduler,
            )
        try:
            yield
        finally:
            scheduler = app.state.scheduler
            if scheduler is not None:
                scheduler.shutdown(wait=False)
            app.state.feishu_executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="TenderTrace", version="0.1.0", lifespan=lifespan)
    app.state.scheduler = None
    app.state.feishu_executor = None

    def schedule_adaptive_ingest(subscription) -> None:
        schedule_ingest_subscription(app.state.scheduler, settings, subscription)

    def schedule_adaptive_subscription(subscription) -> None:
        schedule_subscription(app.state.scheduler, settings, subscription)

    def send_adaptive_opportunity_briefing(
        receive_id: str | None,
        receive_id_type: str | None,
    ):
        return send_opportunity_briefing(
            settings,
            receive_id=receive_id,
            receive_id_type=receive_id_type,
        )

    def start_adaptive_opportunity_collaboration(
        opportunity: dict[str, object],
        owner_open_id: str,
        owner_name: str,
    ):
        return start_opportunity_collaboration(
            settings,
            opportunity,
            owner_open_id=owner_open_id,
            owner_name=owner_name,
            create_task=True,
            create_calendar_event=True,
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=(
            r"https?://(?:localhost|127\.0\.0\.1)(?::\d+)?|"
            r"https://(?:[A-Za-z0-9-]+\.)*(?:feishu\.cn|larksuite\.com)"
        ),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-TenderTrace-Token"],
    )

    @app.middleware("http")
    async def api_token_middleware(request: Request, call_next):
        if _requires_api_token(settings, request):
            expected = settings.api_token()
            provided = _api_token_from_headers(request.headers)
            if not expected or not secrets.compare_digest(provided, expected):
                return JSONResponse({"detail": "invalid API token"}, status_code=401)
        return await call_next(request)

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "config": settings.safe_summary(),
            "database": database_health(settings),
        }

    @app.get("/api/sources")
    def sources() -> dict[str, object]:
        source_map = build_source_map(settings)
        items = list(source_map["items"])
        for item in items:
            if isinstance(item, dict) and item.get("site") == "qianlima":
                item.update(source_map["qianlima"])
        return {"items": items}

    @app.get("/api/source-map")
    def source_map() -> dict[str, object]:
        return build_source_map(settings)

    @app.get("/api/opportunity-radar")
    def opportunity_radar(
        scope: str = "all",
        window_days: int = 365,
        category: str = "",
    ) -> dict[str, object]:
        try:
            return build_opportunity_radar(
                settings,
                scope=scope,
                window_days=window_days,
                category=category,
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/opportunity-radar/refresh")
    def refresh_opportunity_radar(
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            return build_opportunity_radar(
                settings,
                scope=str(request.get("scope") or "all"),
                window_days=int(request.get("window_days") or 365),
                category=str(request.get("category") or ""),
                persist=True,
                actor=str(request.get("actor") or "admin"),
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/battle-map")
    def battle_map(
        scope: str = "global",
        window_hours: int = 2160,
        category: str = "",
        layers: str = "opportunity,award,flow,external",
        mode: str = "live",
    ) -> dict[str, object]:
        try:
            return build_battle_map(
                settings,
                scope=scope,
                window_hours=window_hours,
                category=category,
                layers=[item.strip() for item in layers.split(",") if item.strip()],
                mode=mode,
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/battle-map/sync")
    def sync_battle_map(request: dict[str, object] = Body(default={})) -> dict[str, object]:
        try:
            business = sync_business_events(settings)
            external: dict[str, object] = {"status": "not_requested", "event_ids": []}
            evaluations = []
            if bool(request.get("fetch_external")):
                external = fetch_usgs_external_events(
                    settings,
                    limit=int(request.get("external_limit") or 60),
                )
                for event_id in external.get("event_ids", []):
                    evaluations.append(
                        evaluate_external_event_impacts(
                            settings,
                            str(event_id),
                            actor=str(request.get("actor") or "admin"),
                        )
                    )
            return {
                "status": "synced",
                "business": business,
                "external": external,
                "evaluated_event_count": len(evaluations),
                "candidate_impact_count": sum(
                    int(item.get("candidate_impact_count") or 0) for item in evaluations
                ),
                "revision": battle_map_revision(settings),
            }
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/battle-map/events/{event_id}")
    def battle_map_event(event_id: str) -> dict[str, object]:
        try:
            return battle_map_event_detail(settings, event_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/battle-map/external-events/{event_id}/evaluate")
    def evaluate_battle_map_external_event(
        event_id: str,
        request: dict[str, object] = Body(default={}),
    ) -> dict[str, object]:
        try:
            return evaluate_external_event_impacts(
                settings,
                event_id,
                actor=str(request.get("actor") or "admin"),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/battle-map/impacts/{impact_id}/review")
    def review_battle_map_impact(
        impact_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            return review_impact_link(
                settings,
                impact_id,
                status=str(request.get("status") or ""),
                actor=str(request.get("actor") or "admin"),
                note=str(request.get("note") or ""),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/battle-map/replays")
    def save_battle_map_replay_api(
        request: dict[str, object] = Body(default={}),
    ) -> dict[str, object]:
        try:
            return save_battle_map_replay(
                settings,
                scope=str(request.get("scope") or "global"),
                window_hours=int(request.get("window_hours") or 2160),
                category=str(request.get("category") or ""),
                actor=str(request.get("actor") or "admin"),
                verified=bool(request.get("verified", True)),
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/battle-map/stream")
    async def battle_map_stream():
        async def stream():
            previous = ""
            for _ in range(6):
                revision = battle_map_revision(settings)
                current = str(revision["revision"])
                if current != previous:
                    yield f"event: revision\ndata: {json.dumps(revision, ensure_ascii=False)}\n\n"
                    previous = current
                else:
                    yield ": heartbeat\n\n"
                await asyncio.sleep(10)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/training/scenarios/seed")
    def seed_training_scenarios_api(
        request: dict[str, object] = Body(default={}),
    ) -> dict[str, object]:
        try:
            return seed_default_training_scenarios(
                settings, actor=str(request.get("actor") or "training-curator")
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/training/scenarios")
    def training_scenarios_api() -> dict[str, object]:
        return list_training_scenarios(settings)

    @app.get("/api/training/scenarios/{scenario_id}")
    def training_scenario_api(scenario_id: str) -> dict[str, object]:
        try:
            return get_training_scenario(settings, scenario_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/training/sessions")
    def create_training_session_api(
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            return create_training_session(
                settings,
                str(request.get("scenario_id") or ""),
                mode=str(request.get("mode") or "preparation"),
                role=str(request.get("role") or ""),
                difficulty=str(request.get("difficulty") or "standard"),
                participant_key=str(request.get("participant_key") or "local-user"),
                participant_display=str(request.get("participant_display") or "本地学员"),
                sample_kind=str(request.get("sample_kind") or "live"),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/training/sessions/{session_id}/begin")
    def begin_training_session_api(
        session_id: str,
        request: dict[str, object] = Body(default={}),
    ) -> dict[str, object]:
        try:
            return begin_training_session(
                settings,
                session_id,
                participant_key=str(request.get("participant_key") or "local-user"),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/training/sessions/{session_id}/hint")
    def training_hint_api(
        session_id: str,
        request: dict[str, object] = Body(default={}),
    ) -> dict[str, object]:
        try:
            return get_training_hint(
                settings,
                session_id,
                participant_key=str(request.get("participant_key") or "local-user"),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/training/sessions/{session_id}/answer")
    def submit_training_answer_api(
        session_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            refs = request.get("evidence_refs")
            return submit_training_answer(
                settings,
                session_id,
                participant_key=str(request.get("participant_key") or "local-user"),
                answer=str(request.get("answer") or ""),
                evidence_refs=[str(item) for item in refs] if isinstance(refs, list) else [],
                model_evaluation=(
                    dict(request["model_evaluation"])
                    if isinstance(request.get("model_evaluation"), dict)
                    else None
                ),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/training/sessions/{session_id}")
    def training_session_api(
        session_id: str,
        participant_key: str = "local-user",
        manager: bool = False,
    ) -> dict[str, object]:
        try:
            return get_training_session(
                settings,
                session_id,
                participant_key=participant_key,
                manager=manager,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/training/sessions")
    def training_session_history_api(
        participant_key: str = "local-user",
        manager: bool = False,
        limit: int = 50,
    ) -> dict[str, object]:
        return list_training_sessions(
            settings,
            participant_key=participant_key,
            manager=manager,
            limit=limit,
        )

    @app.get("/api/training/team-readiness")
    def team_training_readiness_api() -> dict[str, object]:
        return team_training_readiness(settings)

    @app.post("/api/training/results/{result_id}/recompute")
    def recompute_training_result_api(result_id: str) -> dict[str, object]:
        try:
            return recompute_training_result(settings, result_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/training/results/{result_id}/tasks/{task_id}/sync-feishu")
    def sync_training_task_api(
        result_id: str,
        task_id: str,
        request: dict[str, object] = Body(default={}),
    ) -> dict[str, object]:
        try:
            return sync_training_remediation_task(
                settings,
                result_id,
                task_id,
                assignee_open_id=str(request.get("assignee_open_id") or ""),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (FeishuError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/sources/qianlima/verify")
    def verify_qianlima_login() -> dict[str, object]:
        vault = QianlimaSessionVault(settings)
        storage_state = vault.status().to_dict()
        probe = vault.live_probe()
        record_activity(
            settings,
            event_type="source_login_verify",
            target="qianlima",
            label=str(probe.get("status") or "unknown"),
            metadata={"status": probe.get("status"), "validation": storage_state.get("validation")},
        )
        return {
            "site": "qianlima",
            "storage_state": storage_state,
            "live_probe": probe,
        }

    @app.get("/api/sources/alerts")
    def source_alerts() -> dict[str, object]:
        snapshot = build_source_alert_snapshot(settings)
        message = feishu_status(settings)
        receiver = load_feishu_receiver(settings)
        receiver_configured = bool(receiver is not None or message.default_receive_id_configured)
        receiver_type = (
            receiver.receive_id_type if receiver is not None else message.default_receive_id_type
        )
        snapshot["delivery_ready"] = bool(message.configured and receiver_configured)
        snapshot["task_ready"] = bool(message.configured)
        snapshot["task_assignee_ready"] = bool(
            receiver_configured and receiver_type == "open_id"
        )
        snapshot["incident_sla_hours"] = settings.source_incident_sla_hours
        active_incidents = list_source_incidents(
            settings,
            statuses=ACTIVE_SOURCE_INCIDENT_STATUSES,
            limit=200,
        )
        latest_incidents = list_source_incidents(settings, limit=1)
        snapshot["incident_summary"] = {
            "active_count": len(active_incidents),
            "latest": (
                active_incidents[0].safe_dict()
                if active_incidents
                else latest_incidents[0].safe_dict()
                if latest_incidents
                else None
            ),
        }
        return snapshot

    @app.get("/api/sources/incidents")
    def source_incidents(limit: int = 20) -> dict[str, object]:
        incidents = list_source_incidents(settings, limit=limit)
        return {
            "items": [incident.safe_dict() for incident in incidents],
            "active_count": sum(
                incident.status in ACTIVE_SOURCE_INCIDENT_STATUSES for incident in incidents
            ),
        }

    @app.post("/api/sources/alerts/send-feishu")
    def send_source_alerts(request: dict[str, object] = Body(default={})) -> dict[str, object]:
        try:
            result = send_source_health_alert(
                settings,
                force=bool(request.get("force", False)),
                receive_id=str(request.get("receive_id") or "").strip(),
                receive_id_type=str(request.get("receive_id_type") or "").strip(),
            )
        except (FeishuError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        record_activity(
            settings,
            event_type="source_health_alert_send",
            target="sources",
            label=f"{result.issue_count} 个来源异常",
            metadata={"status": result.status},
        )
        return result.to_dict()

    @app.post("/api/sources/alerts/create-feishu-task")
    def create_source_incident(
        request: dict[str, object] = Body(default={}),
    ) -> dict[str, object]:
        try:
            result = create_source_incident_task(
                settings,
                force=bool(request.get("force", False)),
            )
        except (FeishuError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        record_activity(
            settings,
            event_type="source_health_task_create",
            target="sources",
            label=f"{result.issue_count} 个来源异常处置",
            metadata={"status": result.status, "assigned": result.assigned},
        )
        return result.to_dict()

    @app.post("/api/sources/incidents/sync")
    def sync_source_incident_tasks(
        request: dict[str, object] = Body(default={}),
    ) -> dict[str, object]:
        try:
            result = sync_source_incidents(
                settings,
                limit=int(request.get("limit") or 100),
            )
        except (FeishuError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        record_activity(
            settings,
            event_type="source_incident_sync",
            target="source_incidents",
            label=f"同步 {result.scanned_count} 个来源处置任务",
            metadata=result.to_dict(),
        )
        return result.to_dict()

    @app.get("/api/model")
    def model() -> dict[str, object]:
        return model_status(settings).to_dict()

    @app.get("/api/model/doctor")
    def model_doctor_api(live: bool = False) -> dict[str, object]:
        return model_doctor(settings, live=live).to_dict()

    @app.get("/api/integrations/feishu/status")
    def feishu_integration_status() -> dict[str, object]:
        return feishu_status(settings).to_dict()

    @app.get("/api/integrations/feishu/agent/status")
    def feishu_agent_integration_status() -> dict[str, object]:
        return feishu_agent_status(settings).to_dict()

    @app.get("/api/integrations/feishu/overview")
    def feishu_overview() -> dict[str, object]:
        message = feishu_status(settings).to_dict()
        agent = feishu_agent_status(settings).to_dict()
        receiver = load_feishu_receiver(settings)
        lead_import_runs = list_feishu_lead_import_runs(settings, limit=1)
        latest_lead_import = lead_import_runs[0].to_dict() if lead_import_runs else None
        message_events = list_feishu_message_events(settings, limit=1)
        latest_message_event = message_events[0].to_dict() if message_events else None
        long_connection_available = feishu_long_connection_available()
        listener = feishu_listener_status(settings)
        webhook_ready = bool(
            message["configured"] and settings.feishu_callback_verification_token_present
        )
        event_callback_ready = bool(
            message["configured"] and (bool(listener["running"]) or webhook_ready)
        )
        bitable_ready = bool(
            settings.feishu_app_id
            and settings.feishu_app_secret_present
            and settings.feishu_bitable_app_token
            and settings.feishu_bitable_table_id
        )
        receiver_configured = bool(receiver or message["default_receive_id_configured"])
        receiver_type = (
            receiver.receive_id_type
            if receiver is not None
            else str(message["default_receive_id_type"] or "")
        )
        report_ready = bool(message["configured"] and receiver_configured)
        active_source_incidents = list_source_incidents(
            settings,
            statuses=ACTIVE_SOURCE_INCIDENT_STATUSES,
            limit=200,
        )
        organization_spaces = list_organization_workspaces(settings, limit=200)
        issues: list[dict[str, str]] = []
        if not message["configured"]:
            issues.append({"code": "message_app", "message": "消息应用尚未启用或凭据不完整"})
        elif not receiver_configured:
            issues.append({"code": "receiver", "message": "尚未设置默认飞书会话或用户"})
        if not bitable_ready:
            issues.append({"code": "bitable", "message": "多维表格凭据或数据表标识不完整"})
        if agent["enabled"] and not agent["configured"]:
            issues.append({"code": "agent", "message": "智能体应用尚未启用或凭据不完整"})
        return {
            "status": "ready" if report_ready else "attention",
            "message": message,
            "receiver": (
                receiver.safe_dict()
                if receiver is not None
                else {
                    "configured": bool(message["default_receive_id_configured"]),
                    "label": "环境配置" if message["default_receive_id_configured"] else None,
                    "receive_id_type": message["default_receive_id_type"],
                }
            ),
            "agent": agent,
            "features": {
                "report_delivery": {"ready": report_ready},
                "weekly_digest": {"ready": report_ready},
                "bitable_sync": {
                    "ready": bitable_ready,
                    "url": settings.feishu_bitable_base_url,
                },
                "partner_lead_ingest": {
                    "ready": bitable_ready,
                    "url": settings.feishu_bitable_base_url,
                    "automation_enabled": settings.feishu_lead_import_enabled,
                    "cron": settings.feishu_lead_import_cron,
                    "last_run": latest_lead_import,
                },
                "fact_verification": {
                    "ready": bitable_ready,
                    "url": settings.feishu_bitable_base_url,
                },
                "conversation_commands": {
                    "ready": bool(
                        message["configured"]
                        and (bool(listener["running"]) or webhook_ready)
                    ),
                    "long_connection_available": long_connection_available,
                    "listener": listener,
                    "webhook_ready": webhook_ready,
                    "last_event": latest_message_event,
                },
                "organization_collaboration": {
                    "ready": bool(
                        message["configured"]
                        and (bool(listener["running"]) or webhook_ready)
                    ),
                    "workspace_count": len(organization_spaces),
                    "memory_count": sum(item.memory_count for item in organization_spaces),
                },
                "agent_service": {
                    "ready": bool(agent["configured"]) or not bool(agent["enabled"]),
                    "configured": bool(agent["configured"]),
                    "enabled": bool(agent["enabled"]),
                    "optional": True,
                    "detail": (
                        "独立智能体应用已配置"
                        if agent["configured"]
                        else "未启用；现有机器人、表格、任务与日历继续使用消息应用"
                    ),
                },
                "opportunity_cards": {"ready": bool(message["configured"])},
                "decision_escalation": {
                    "ready": report_ready,
                    "automation_enabled": settings.opportunity_escalation_enabled,
                    "cron": settings.opportunity_escalation_cron,
                },
                "opportunity_briefing": {
                    "ready": report_ready,
                    "automation_enabled": settings.opportunity_briefing_enabled,
                    "cron": settings.opportunity_briefing_cron,
                },
                "task_sync": {
                    "ready": bool(message["configured"]),
                    "automation_enabled": settings.feishu_task_sync_enabled,
                    "cron": settings.feishu_task_sync_cron,
                },
                "relationship_actions": {
                    "ready": bool(message["configured"]),
                    "automation_enabled": settings.feishu_task_sync_enabled,
                    "cron": settings.feishu_task_sync_cron,
                },
                "source_health_alert": {
                    "ready": report_ready,
                    "automation_enabled": settings.source_alert_enabled,
                    "cron": settings.source_alert_cron,
                    "minimum_reliability": settings.source_alert_min_reliability,
                    "stale_hours": settings.source_alert_stale_hours,
                },
                "source_incident_task": {
                    "ready": bool(message["configured"]),
                    "assigned": bool(receiver_configured and receiver_type == "open_id"),
                    "sla_hours": settings.source_incident_sla_hours,
                    "active_count": len(active_source_incidents),
                    "sync_enabled": settings.feishu_task_sync_enabled,
                },
                "deadline_calendar": {
                    "ready": bool(message["configured"] and settings.feishu_calendar_id),
                },
                "card_callback": {
                    "ready": event_callback_ready,
                },
            },
            "issues": issues,
            "recent_attempts": [
                attempt.to_dict()
                for attempt in list_delivery_attempts(settings, channel="feishu", limit=8)
            ],
        }

    @app.get("/api/integrations/feishu/bitable/check")
    def feishu_bitable_check() -> dict[str, object]:
        return check_feishu_bitable(settings).to_dict()

    @app.post("/api/integrations/feishu/bitable/ensure-fields")
    def feishu_bitable_ensure_fields() -> dict[str, object]:
        return check_feishu_bitable(settings, ensure_fields=True).to_dict()

    @app.post("/api/integrations/feishu/bitable/import-leads")
    def feishu_bitable_import_leads(
        request: dict[str, object] = Body(default={}),
    ) -> dict[str, object]:
        return import_partner_leads(
            settings,
            dry_run=bool(request.get("dry_run", False)),
        ).to_dict()

    @app.get("/api/integrations/feishu/bitable/import-runs")
    def feishu_bitable_import_runs(limit: int = 20) -> dict[str, object]:
        return {
            "items": [
                item.to_dict()
                for item in list_feishu_lead_import_runs(settings, limit=limit)
            ]
        }

    @app.get("/api/integrations/feishu/chats")
    def feishu_chats(page_size: int = 20, page_token: str | None = None) -> dict[str, object]:
        try:
            return FeishuClient(settings).list_chats(page_size=page_size, page_token=page_token)
        except FeishuError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/integrations/feishu/users")
    def feishu_users(limit: int = 100) -> dict[str, object]:
        try:
            return FeishuClient(settings).list_authorized_users(limit=limit)
        except (FeishuError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/integrations/feishu/receiver")
    def save_feishu_receiver_api(request: dict[str, object] = Body(...)) -> dict[str, object]:
        try:
            preference = save_feishu_receiver(
                settings,
                receive_id=str(request.get("receive_id") or ""),
                receive_id_type=str(request.get("receive_id_type") or "chat_id"),
                label=_optional_string(request.get("label")),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return preference.safe_dict()

    @app.get("/api/live-challenges")
    def live_challenges(limit: int = 20) -> dict[str, object]:
        return list_live_challenges(settings, limit=limit)

    @app.post("/api/live-challenges")
    def create_live_challenge_session(
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            return create_live_challenge(
                settings,
                category=request.get("category"),
                region=request.get("region"),
                time_window=request.get("time_window") or "90d",
                keyword=request.get("keyword") or "",
                actor=request.get("actor") or "judge",
                max_results=int(request.get("max_results") or 12),
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/live-challenges/{session_id}")
    def live_challenge_detail(session_id: str) -> dict[str, object]:
        try:
            return get_live_challenge(settings, session_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/live-challenges/{session_id}/supplement")
    def supplement_live_challenge(session_id: str) -> dict[str, object]:
        try:
            payload = begin_live_challenge_supplement(settings, session_id)
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if "not found" in message else 409
            raise HTTPException(status_code=status_code, detail=message) from exc
        Thread(
            target=run_live_challenge_supplement,
            kwargs={"settings": settings, "session_id": session_id},
            daemon=True,
            name=f"live-challenge-{session_id[:8]}",
        ).start()
        return payload

    @app.post("/api/live-challenges/{session_id}/cancel")
    def cancel_live_challenge(session_id: str) -> dict[str, object]:
        try:
            return cancel_live_challenge_supplement(settings, session_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/demo-reliability")
    def demo_reliability(compact: bool = False) -> dict[str, object]:
        overview = demo_reliability_overview(settings)
        if not compact:
            return overview
        cases = []
        for item in overview.get("cases", []):
            if not isinstance(item, dict):
                continue
            snapshot = item.get("snapshot") if isinstance(item.get("snapshot"), dict) else {}
            result = snapshot.get("result") if isinstance(snapshot.get("result"), dict) else {}
            twin = result.get("digital_twin") if isinstance(result.get("digital_twin"), dict) else {}
            cases.append(
                {
                    key: item.get(key)
                    for key in (
                        "id",
                        "role",
                        "label",
                        "source_id",
                        "verification_status",
                        "snapshot_verified",
                        "replay_verified",
                        "display",
                    )
                }
                | {
                    "snapshot": {
                        "result": {
                            "digital_twin": {
                                key: twin.get(key)
                                for key in ("project", "scores", "next_actions")
                            }
                        }
                    }
                }
            )
        return {
            "status": overview.get("status"),
            "environment": overview.get("environment", {}),
            "cases": cases,
        }

    @app.post("/api/demo-reliability/prepare")
    def prepare_demo_reliability(
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            result = prepare_default_demo_cases(
                settings,
                actor=str(request.get("actor") or "admin"),
            )
        except (LookupError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {**result, "overview": demo_reliability_overview(settings)}

    @app.post("/api/demo-reliability/cases/freeze")
    def freeze_demo_reliability_case(
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            return freeze_demo_case(
                settings,
                role=request.get("role"),
                label=request.get("label"),
                source_type=request.get("source_type"),
                source_id=request.get("source_id"),
                actor=request.get("actor") or "admin",
            )
        except (LookupError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/demo-reliability/rehearsals")
    def run_demo_reliability_rehearsal(
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            return run_demo_rehearsal(
                settings,
                case_id=request.get("case_id"),
                requested_mode=request.get("requested_mode") or "live",
                browser_online=request.get("browser_online", True),
                viewport_width=request.get("viewport_width") or 1440,
                viewport_height=request.get("viewport_height") or 900,
                scenario=request.get("scenario") or "standard",
                actor=request.get("actor") or "judge",
            )
        except (LookupError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/demo-reliability/rehearsals/{rehearsal_id}")
    def demo_reliability_rehearsal(rehearsal_id: str) -> dict[str, object]:
        try:
            return get_demo_rehearsal(settings, rehearsal_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/demo-reliability/layout-audits")
    def save_demo_layout_audit(
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            return record_demo_layout_audit(
                settings,
                profile=request.get("profile"),
                viewport_width=request.get("viewport_width"),
                viewport_height=request.get("viewport_height"),
                scroll_width=request.get("scroll_width"),
                critical_overflows=request.get("critical_overflows") or [],
                user_agent=request.get("user_agent") or "",
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/visual-system")
    def visual_system() -> dict[str, object]:
        return visual_system_overview(settings)

    @app.post("/api/visual-system/audits")
    def save_visual_system_audit(
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            return record_visual_system_audit(
                settings,
                profile=request.get("profile"),
                viewport_width=request.get("viewport_width"),
                viewport_height=request.get("viewport_height"),
                notice_id=request.get("notice_id"),
                scroll_width=request.get("scroll_width"),
                critical_overflows=request.get("critical_overflows") or [],
                checks=request.get("checks") or {},
                user_agent=request.get("user_agent") or "",
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/integrations/feishu/test-message")
    def feishu_test_message(request: dict[str, object] = Body(...)) -> dict[str, object]:
        text = str(request.get("text") or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="text is required")
        receive_id = _optional_string(request.get("receive_id"))
        receive_id_type = _optional_string(request.get("receive_id_type"))
        if not receive_id:
            preference = load_feishu_receiver(settings)
            if preference is not None:
                receive_id = preference.receive_id
                receive_id_type = receive_id_type or preference.receive_id_type
            else:
                receive_id = settings.feishu_default_receive_id or None
        receive_id_type = receive_id_type or settings.feishu_default_receive_id_type
        try:
            result = FeishuClient(settings).send_text(
                text,
                receive_id=receive_id,
                receive_id_type=receive_id_type,
            )
        except FeishuError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"status": "sent", "response": result}

    @app.get("/api/organization/workspaces")
    def organization_workspaces(limit: int = 100) -> dict[str, object]:
        return {
            "items": [
                _organization_workspace_payload(item)
                for item in list_organization_workspaces(settings, limit=limit)
            ]
        }

    @app.post("/api/organization/workspaces")
    def create_organization_workspace_api(
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        name = str(request.get("name") or "").strip()
        members = request.get("members") if isinstance(request.get("members"), list) else []
        normalized_members = [
            {
                "open_id": str(item.get("open_id") or ""),
                "name": str(item.get("name") or ""),
                "role": str(item.get("role") or "member"),
            }
            for item in members
            if isinstance(item, dict) and str(item.get("open_id") or "").strip()
        ]
        try:
            feishu = FeishuClient(settings)
            chat = feishu.create_chat(
                name=name,
                member_open_ids=[item["open_id"] for item in normalized_members],
                description="TenderTrace 机会协作与组织记忆工作区",
                client_uuid=str(uuid4()),
            )
            chat_id = str(chat.get("chat_id") or "").strip()
            if not chat_id:
                raise FeishuError("Feishu create chat response is missing chat_id")
            workspace = create_organization_workspace(
                settings,
                name=name,
                feishu_chat_id=chat_id,
                members=normalized_members,
                actor=str(request.get("actor") or "admin"),
            )
        except (FeishuError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            feishu.send_text(
                _organization_workspace_welcome_message(
                    settings,
                    workspace,
                    member_count=len(normalized_members),
                ),
                receive_id=chat_id,
                receive_id_type="chat_id",
            )
            notification = {
                "status": "sent",
                "message": "项目群通知已发送",
            }
        except FeishuError:
            notification = {
                "status": "failed",
                "message": "项目群已创建，但群内通知发送失败，请确认机器人发言权限",
            }
        return {
            "status": "created",
            "workspace": _organization_workspace_payload(workspace),
            "notification": notification,
        }

    @app.post("/api/organization/workspaces/{workspace_id}/members")
    def add_organization_members_api(
        workspace_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        workspace = get_organization_workspace(settings, workspace_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail="organization workspace not found")
        members = request.get("members") if isinstance(request.get("members"), list) else []
        normalized_members = [
            {
                "open_id": str(item.get("open_id") or ""),
                "name": str(item.get("name") or ""),
                "role": str(item.get("role") or "member"),
            }
            for item in members
            if isinstance(item, dict) and str(item.get("open_id") or "").strip()
        ]
        try:
            FeishuClient(settings).add_chat_members(
                workspace.feishu_chat_id,
                [item["open_id"] for item in normalized_members],
            )
            stored = add_organization_members(
                settings,
                workspace_id,
                normalized_members,
                actor=str(request.get("actor") or "admin"),
            )
        except (FeishuError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"status": "invited", "members": stored}

    @app.post("/api/organization/workspaces/{workspace_id}/outbox/{filename}/send-feishu")
    def send_workspace_outbox_to_feishu(
        workspace_id: str,
        filename: str,
        request: dict[str, object] | None = Body(default=None),
    ) -> dict[str, object]:
        workspace = get_organization_workspace(settings, workspace_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail="organization workspace not found")
        path = _resolve_outbox_path(settings, filename)
        if not path.exists():
            raise HTTPException(status_code=404, detail="file not found")
        request = request or {}
        run_id = _optional_string(request.get("run_id"))
        result = deliver_report_to_feishu(
            settings,
            docx_path=path,
            run_id=run_id,
            subscription_id=_optional_string(request.get("subscription_id")),
            receive_id=workspace.feishu_chat_id,
            receive_id_type="chat_id",
            report_summary=_report_delivery_summary(settings, run_id),
        )
        record_activity(
            settings,
            event_type="organization_report_send",
            target=workspace_id,
            label=path.name,
            metadata={
                "status": result.status,
                "digest_status": result.digest_status,
                "workspace": workspace.name,
            },
        )
        if result.status != "sent":
            raise HTTPException(status_code=400, detail=result.to_dict())
        return {
            "status": "sent",
            "workspace": _organization_workspace_payload(workspace),
            "delivery": result.to_dict(),
        }

    @app.get("/api/organization/workspaces/{workspace_id}/memories")
    def organization_memories(
        workspace_id: str,
        query: str = "",
        memory_type: str = "",
        limit: int = 50,
    ) -> dict[str, object]:
        try:
            items = search_organization_memories(
                settings,
                workspace_id=workspace_id,
                query=query,
                memory_type=memory_type,
                limit=limit,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"items": [item.to_dict() for item in items]}

    @app.post("/api/organization/workspaces/{workspace_id}/memories")
    def record_organization_memory_api(
        workspace_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            memory = record_organization_memory(
                settings,
                workspace_id=workspace_id,
                content=str(request.get("content") or ""),
                title=str(request.get("title") or ""),
                memory_type=str(request.get("memory_type") or "note"),
                source_type="web",
                related_notice_id=str(request.get("related_notice_id") or ""),
                evidence_url=str(request.get("evidence_url") or ""),
                actor=str(request.get("actor") or "admin"),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"status": "recorded", "memory": memory.to_dict()}

    @app.post("/api/organization/workspaces/{workspace_id}/memories/{memory_id}/convert")
    def convert_organization_memory_api(
        workspace_id: str,
        memory_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        memory = get_organization_memory(
            settings,
            workspace_id=workspace_id,
            memory_id=memory_id,
        )
        if memory is None:
            raise HTTPException(status_code=404, detail="organization memory not found")
        target_type = str(request.get("target_type") or "").strip()
        notice_id = str(request.get("notice_id") or memory.related_notice_id).strip()
        actor = str(request.get("actor") or "admin")
        try:
            if target_type == "opportunity_fact":
                facts = request.get("facts") if isinstance(request.get("facts"), dict) else {}
                source_url = str(request.get("evidence_url") or memory.evidence_url)
                result: object = upsert_verified_facts(
                    settings,
                    notice_id=notice_id,
                    facts=facts,
                    source_url=source_url,
                    evidence_text=memory.content,
                    note=f"来自组织记忆：{memory.title}",
                    actor=actor,
                    channel="organization_memory",
                )
                target_id = notice_id
            elif target_type == "relationship_action":
                action = create_relationship_action(
                    settings,
                    notice_id=notice_id,
                    title=str(request.get("title") or memory.title),
                    due_at=str(request.get("due_at") or ""),
                    stakeholder_id=str(request.get("stakeholder_id") or ""),
                    action_type=str(request.get("action_type") or "internal_alignment"),
                    priority=str(request.get("priority") or "normal"),
                    assignee_member_id=str(request.get("assignee_member_id") or ""),
                    source_type="organization_memory",
                    source_ref=memory.id,
                    actor=actor,
                )
                result = action.to_dict()
                target_id = action.id
            else:
                raise ValueError("target_type must be opportunity_fact or relationship_action")
            record_organization_memory_conversion(
                settings,
                workspace_id=workspace_id,
                memory_id=memory_id,
                target_type=target_type,
                target_id=target_id,
                actor=actor,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"status": "converted", "target_type": target_type, "result": result}

    @app.get("/api/organization/workspaces/{workspace_id}/bid-memory")
    def organization_bid_memory_dashboard(
        workspace_id: str,
        notice_id: str = "",
        actor: str = "admin",
    ) -> dict[str, object]:
        try:
            return get_bid_memory_dashboard(
                settings,
                workspace_id=workspace_id,
                notice_id=notice_id.strip(),
                actor=actor.strip() or "admin",
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/organization/workspaces/{workspace_id}/companies")
    def company_due_diligence_entities(
        workspace_id: str,
        query: str = "",
        actor: str = "admin",
        limit: int = 100,
    ) -> dict[str, object]:
        try:
            return {
                "items": list_company_entities(
                    settings,
                    workspace_id=workspace_id,
                    actor=actor,
                    query=query,
                    limit=limit,
                )
            }
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/organization/workspaces/{workspace_id}/companies")
    def create_company_due_diligence_entity_api(
        workspace_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            entity = create_company_entity(
                settings,
                workspace_id=workspace_id,
                legal_name=request.get("legal_name"),
                unified_credit_code=request.get("unified_credit_code") or "",
                region=request.get("region") or "",
                legal_representative=request.get("legal_representative") or "",
                entity_type=request.get("entity_type") or "company",
                aliases=request.get("aliases") if isinstance(request.get("aliases"), list) else [],
                actor=str(request.get("actor") or "admin"),
            )
            return {"status": "created", "entity": entity}
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/organization/workspaces/{workspace_id}/companies/resolve")
    def resolve_company_due_diligence_entity_api(
        workspace_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            return resolve_company_candidates(
                settings,
                workspace_id=workspace_id,
                query=request.get("query") or "",
                unified_credit_code=request.get("unified_credit_code") or "",
                region=request.get("region") or "",
                legal_representative=request.get("legal_representative") or "",
                actor=str(request.get("actor") or "admin"),
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/organization/workspaces/{workspace_id}/companies/{entity_id}/confirm")
    def confirm_company_due_diligence_entity_api(
        workspace_id: str,
        entity_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            return {
                "status": "confirmed",
                "entity": confirm_company_identity(
                    settings,
                    entity_id,
                    workspace_id=workspace_id,
                    actor=str(request.get("actor") or "admin"),
                    unified_credit_code=request.get("unified_credit_code"),
                    reason=request.get("reason"),
                ),
            }
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/organization/workspaces/{workspace_id}/companies/{entity_id}")
    def company_due_diligence_profile_api(
        workspace_id: str,
        entity_id: str,
        actor: str = "admin",
    ) -> dict[str, object]:
        try:
            return get_company_due_diligence_profile(
                settings,
                entity_id,
                workspace_id=workspace_id,
                actor=actor,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/organization/workspaces/{workspace_id}/companies/{entity_id}/aggregate")
    def aggregate_company_due_diligence_api(
        workspace_id: str,
        entity_id: str,
        request: dict[str, object] = Body(default={}),
    ) -> dict[str, object]:
        try:
            return aggregate_existing_company_data(
                settings,
                entity_id,
                workspace_id=workspace_id,
                actor=str(request.get("actor") or "admin"),
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/organization/workspaces/{workspace_id}/companies/{entity_id}/evaluate")
    def evaluate_company_due_diligence_api(
        workspace_id: str,
        entity_id: str,
        request: dict[str, object] = Body(default={}),
    ) -> dict[str, object]:
        try:
            return evaluate_company_risks(
                settings,
                entity_id,
                workspace_id=workspace_id,
                actor=str(request.get("actor") or "admin"),
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/organization/workspaces/{workspace_id}/companies/{entity_id}/evidence")
    def add_company_due_diligence_evidence_api(
        workspace_id: str,
        entity_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            external = bool(request.get("external"))
            if external:
                evidence = add_authorized_external_evidence(
                    settings,
                    entity_id,
                    workspace_id=workspace_id,
                    actor=str(request.get("actor") or "admin"),
                    evidence_type=request.get("evidence_type"),
                    title=request.get("title"),
                    content_text=request.get("content_text"),
                    source_type=request.get("source_type"),
                    source_name=request.get("source_name"),
                    source_url=request.get("source_url"),
                    source_license=request.get("source_license"),
                    access_frequency=request.get("access_frequency"),
                    occurred_at=request.get("occurred_at") or "",
                    valid_until=request.get("valid_until") or "",
                    confidence=int(request.get("confidence") or 80),
                )
            else:
                evidence = add_company_evidence(
                    settings,
                    entity_id,
                    workspace_id=workspace_id,
                    actor=str(request.get("actor") or "admin"),
                    evidence_type=request.get("evidence_type"),
                    title=request.get("title"),
                    content_text=request.get("content_text"),
                    source_type=request.get("source_type") or "manual_upload",
                    source_name=request.get("source_name") or "人工提交材料",
                    source_url=request.get("source_url") or "",
                    source_license=request.get("source_license") or "authorized_manual",
                    access_policy=request.get("access_policy") or "workspace",
                    access_frequency=request.get("access_frequency") or "manual",
                    occurred_at=request.get("occurred_at") or "",
                    valid_until=request.get("valid_until") or "",
                    confidence=int(request.get("confidence") or 70),
                    redacted_content=request.get("redacted_content") or "",
                    sensitive=bool(request.get("sensitive")),
                    notice_id=str(request.get("notice_id") or ""),
                )
            return {"status": "recorded", "evidence": evidence}
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/organization/workspaces/{workspace_id}/companies/{entity_id}/evidence/{evidence_id}/review")
    def review_company_due_diligence_evidence_api(
        workspace_id: str,
        entity_id: str,
        evidence_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        del entity_id
        try:
            return review_company_evidence(
                settings,
                evidence_id,
                workspace_id=workspace_id,
                actor=str(request.get("actor") or "admin"),
                status=request.get("status"),
                reason=request.get("reason"),
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/organization/workspaces/{workspace_id}/companies/{entity_id}/ask")
    def ask_company_due_diligence_api(
        workspace_id: str,
        entity_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            return ask_company_due_diligence(
                settings,
                entity_id,
                workspace_id=workspace_id,
                actor=str(request.get("actor") or "admin"),
                question=request.get("question"),
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/organization/workspaces/{workspace_id}/companies/{entity_id}/relationships")
    def add_company_due_diligence_relationship_api(
        workspace_id: str,
        entity_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            return add_company_relationship(
                settings,
                entity_id,
                workspace_id=workspace_id,
                actor=str(request.get("actor") or "admin"),
                related_label=request.get("related_label"),
                relationship_type=request.get("relationship_type"),
                basis_type=request.get("basis_type"),
                confidence=int(request.get("confidence") or 0),
                evidence_id=str(request.get("evidence_id") or ""),
                to_entity_id=str(request.get("to_entity_id") or ""),
                related_object_type=request.get("related_object_type") or "company",
                related_object_id=request.get("related_object_id") or "",
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/organization/workspaces/{workspace_id}/companies/{entity_id}/reviews")
    def submit_company_due_diligence_review_api(
        workspace_id: str,
        entity_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            return submit_due_diligence_review(
                settings,
                entity_id,
                workspace_id=workspace_id,
                actor=str(request.get("actor") or "admin"),
                recommendation=request.get("recommendation"),
                reason=request.get("reason"),
                valid_until=request.get("valid_until"),
                conditions=request.get("conditions") if isinstance(request.get("conditions"), list) else [],
                notice_id=str(request.get("notice_id") or ""),
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/organization/workspaces/{workspace_id}/companies/{entity_id}/subscribe")
    def subscribe_company_due_diligence_changes_api(
        workspace_id: str,
        entity_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            return subscribe_company_changes(
                settings,
                entity_id,
                workspace_id=workspace_id,
                actor=str(request.get("actor") or "admin"),
                event_types=request.get("event_types") if isinstance(request.get("event_types"), list) else [],
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/organization/workspaces/{workspace_id}/companies/{entity_id}/tasks")
    def create_company_due_diligence_task_api(
        workspace_id: str,
        entity_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            return create_company_due_diligence_task(
                settings,
                entity_id,
                workspace_id=workspace_id,
                actor=str(request.get("actor") or "admin"),
                title=request.get("title"),
                question=request.get("question"),
                task_type=request.get("task_type"),
                assignee_open_id=request.get("assignee_open_id") or "",
                due_at=request.get("due_at"),
                risk_signal_id=str(request.get("risk_signal_id") or ""),
                notice_id=str(request.get("notice_id") or ""),
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/organization/workspaces/{workspace_id}/companies/{entity_id}/tasks/{task_id}/sync-feishu")
    def sync_company_due_diligence_task_api(
        workspace_id: str,
        entity_id: str,
        task_id: str,
        actor: str = "admin",
    ) -> dict[str, object]:
        try:
            task_ids = {
                str(item["id"])
                for item in list_company_due_diligence_tasks(
                    settings,
                    entity_id,
                    workspace_id=workspace_id,
                    actor=actor,
                )
            }
            if task_id not in task_ids:
                raise LookupError("company due diligence task not found")
            return sync_company_due_diligence_task(settings, task_id)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (FeishuError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/organization/workspaces/{workspace_id}/companies/{entity_id}/snapshots")
    def save_company_due_diligence_snapshot_api(
        workspace_id: str,
        entity_id: str,
        request: dict[str, object] = Body(default={}),
    ) -> dict[str, object]:
        try:
            return save_company_due_diligence_snapshot(
                settings,
                entity_id,
                workspace_id=workspace_id,
                actor=str(request.get("actor") or "admin"),
                verified=bool(request.get("verified")),
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/organization/workspaces/{workspace_id}/companies/{entity_id}/snapshots/latest")
    def latest_company_due_diligence_snapshot_api(
        workspace_id: str,
        entity_id: str,
        actor: str = "admin",
    ) -> dict[str, object]:
        try:
            return latest_verified_company_snapshot(
                settings,
                entity_id,
                workspace_id=workspace_id,
                actor=actor,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/opportunities/{notice_id}/bid-memory/archive")
    def archive_opportunity_to_bid_memory(
        notice_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        raw_tags = request.get("tags")
        raw_materials = request.get("materials")
        tags = [str(value) for value in raw_tags] if isinstance(raw_tags, list) else []
        materials = [dict(value) for value in raw_materials if isinstance(value, dict)] if isinstance(raw_materials, list) else []
        try:
            return archive_project_memory(
                settings,
                notice_id,
                workspace_id=str(request.get("workspace_id") or ""),
                actor=str(request.get("actor") or "admin"),
                tags=tags,
                materials=materials,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/organization/workspaces/{workspace_id}/bid-memory/assets/{asset_id}/decision")
    def decide_organization_bid_memory_asset(
        workspace_id: str,
        asset_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            return {
                "status": "updated",
                "asset": decide_bid_memory_asset(
                    settings,
                    asset_id,
                    workspace_id=workspace_id,
                    action=str(request.get("action") or ""),
                    actor=str(request.get("actor") or "admin"),
                    note=str(request.get("note") or ""),
                    corrections=_mapping_value(request.get("corrections")),
                ),
            }
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/intent/parse")
    def parse_intent(request: dict[str, object] = Body(...)) -> dict[str, object]:
        query = str(request.get("query") or "")
        now_raw = request.get("now")
        now = datetime.fromisoformat(str(now_raw)) if now_raw else None
        return compile_intent(query, now=now)

    @app.get("/api/opportunities")
    def opportunities(
        limit: int = 50,
        level: str | None = None,
        topic: str | None = None,
        sort: str = "priority",
    ) -> dict[str, object]:
        normalized_level = level.upper() if level else None
        if normalized_level and normalized_level not in {"A", "B", "C", "D"}:
            raise HTTPException(status_code=400, detail="level must be one of: A, B, C, D")
        normalized_topic = str(topic or "").strip()[:40] or None
        normalized_sort = str(sort or "priority").strip().lower()
        if normalized_sort not in {"priority", "recent", "deadline"}:
            raise HTTPException(
                status_code=400,
                detail="sort must be one of: priority, recent, deadline",
            )
        return list_opportunities(
            settings,
            limit=limit,
            level=normalized_level,
            topic=normalized_topic,
            sort=normalized_sort,
        )

    @app.get("/api/opportunities/changes")
    def opportunity_changes(
        limit: int = 100,
        notice_id: str = "",
    ) -> dict[str, object]:
        items = list_notice_revisions(
            settings,
            notice_id=notice_id.strip(),
            limit=limit,
        )
        reviews = reviews_by_revision(settings, [item.id for item in items])
        return {
            "items": [
                {**item.to_dict(), "review": reviews.get(item.id, {})}
                for item in items
            ],
            "returned": len(items),
        }

    @app.get("/api/opportunities/{notice_id}")
    def opportunity_detail(notice_id: str) -> dict[str, object]:
        item = get_opportunity(settings, notice_id)
        if item is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        return item

    @app.get("/api/opportunities/{notice_id}/digital-twin")
    def opportunity_digital_twin(notice_id: str) -> dict[str, object]:
        item = build_digital_twin(settings, notice_id)
        if item is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        return item

    @app.get("/api/opportunities/{notice_id}/source-relations")
    def opportunity_source_relations(notice_id: str) -> dict[str, object]:
        item = build_source_relation_graph(settings, notice_id)
        if item is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        return item

    @app.post("/api/opportunities/{notice_id}/source-relations/{related_notice_id}/decision")
    def decide_opportunity_source_relation(
        notice_id: str,
        related_notice_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            return decide_source_relation(
                settings,
                notice_id,
                related_notice_id,
                action=str(request.get("action") or ""),
                actor=str(request.get("actor") or ""),
                reason=str(request.get("reason") or ""),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/opportunities/{notice_id}/decision-sandbox")
    def opportunity_decision_sandbox(notice_id: str) -> dict[str, object]:
        try:
            return get_decision_sandbox(settings, notice_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/opportunities/{notice_id}/decision-sandbox/scenarios")
    def create_decision_sandbox_scenario(
        notice_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            return simulate_scenario(
                settings,
                notice_id,
                name=str(request.get("name") or ""),
                params=dict(request.get("params") or {}),
                actor=str(request.get("actor") or ""),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/opportunities/{notice_id}/decision-sandbox/scenarios/{scenario_id}/recompute")
    def recompute_decision_sandbox_scenario(notice_id: str, scenario_id: str) -> dict[str, object]:
        try:
            return recompute_scenario(settings, notice_id, scenario_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/opportunities/{notice_id}/decision-sandbox/compare")
    def compare_decision_sandbox_scenarios(
        notice_id: str,
        left_id: str,
        right_id: str,
    ) -> dict[str, object]:
        try:
            return compare_scenarios(settings, notice_id, left_id, right_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/opportunities/{notice_id}/decision-sandbox/scenarios/{scenario_id}/promote")
    def promote_decision_sandbox_scenario(
        notice_id: str,
        scenario_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            return promote_scenario(
                settings,
                notice_id,
                scenario_id,
                actor=str(request.get("actor") or ""),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/opportunities/{notice_id}/decision-sandbox/suggestions/{suggestion_id}/decision")
    def decide_decision_sandbox_suggestion(
        notice_id: str,
        suggestion_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            return decide_scenario_suggestion(
                settings,
                notice_id,
                suggestion_id,
                accept=bool(request.get("accept")),
                actor=str(request.get("actor") or ""),
                note=str(request.get("note") or ""),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/opportunities/{notice_id}/evidence-microscope")
    def opportunity_evidence_microscope(
        notice_id: str,
        claim_type: str = "",
        claim_key: str = "",
    ) -> dict[str, object]:
        payload = build_evidence_microscope(
            settings,
            notice_id,
            claim_type=claim_type.strip(),
            claim_key=claim_key.strip(),
        )
        if payload is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        return payload

    @app.get("/api/opportunities/{notice_id}/change-impact")
    def opportunity_change_impact(
        notice_id: str,
        revision_id: str = "",
        affected_only: bool = False,
    ) -> dict[str, object]:
        payload = get_change_impact(
            settings,
            notice_id,
            revision_id=revision_id.strip(),
            affected_only=affected_only,
        )
        if payload is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        return payload

    @app.post("/api/opportunities/{notice_id}/change-impact/actions/{action_id}/confirm")
    def confirm_opportunity_change_impact_action(
        notice_id: str,
        action_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            return confirm_change_impact_action(
                settings,
                notice_id,
                action_id,
                actor=str(request.get("actor") or ""),
                note=str(request.get("note") or ""),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/opportunities/{notice_id}/change-impact/{round_id}/dispatch")
    def dispatch_opportunity_change_impact(
        notice_id: str,
        round_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            return dispatch_change_impact(
                settings,
                notice_id,
                round_id,
                actor=str(request.get("actor") or ""),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (FeishuError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/opportunities/{notice_id}/evidence-microscope/{evidence_id}/review")
    def review_opportunity_evidence(
        notice_id: str,
        evidence_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            return review_evidence(
                settings,
                notice_id,
                evidence_id,
                action=str(request.get("action") or ""),
                actor=str(request.get("actor") or ""),
                reason=str(request.get("reason") or ""),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/opportunities/changes/send-feishu")
    def send_opportunity_changes(
        request: dict[str, object] = Body(default={}),
    ) -> dict[str, object]:
        try:
            result = send_opportunity_change_alerts(
                settings,
                limit=int(request.get("limit") or 100),
            )
        except (FeishuError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        record_activity(
            settings,
            event_type="opportunity_change_alert",
            target="notice_revisions",
            label=f"推送 {result.sent_count} 条机会变更",
            metadata=result.to_dict(),
        )
        return result.to_dict()

    @app.post("/api/opportunities/analyze")
    def analyze_opportunity(request: dict[str, object] = Body(...)) -> dict[str, object]:
        return analyze_opportunity_with_market_context(settings, request)

    @app.post("/api/opportunities/escalations/send-feishu")
    def send_opportunity_escalations(
        request: dict[str, object] = Body(default={}),
    ) -> dict[str, object]:
        try:
            result = send_opportunity_escalation_summary(
                settings,
                force=bool(request.get("force", False)),
            )
        except (FeishuError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        record_activity(
            settings,
            event_type="opportunity_escalation_send",
            target=result.artifact_key,
            label=f"{result.escalation_count} 条决策升级",
            metadata={"status": result.status},
        )
        return result.to_dict()

    @app.post("/api/opportunities/briefing/send-feishu")
    def send_opportunity_management_briefing(
        request: dict[str, object] = Body(default={}),
    ) -> dict[str, object]:
        try:
            result = send_opportunity_briefing(
                settings,
                force=bool(request.get("force", False)),
            )
        except (FeishuError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        record_activity(
            settings,
            event_type="opportunity_briefing_send",
            target=result.artifact_key,
            label=f"{result.opportunity_count} 条机会经营晨报",
            metadata={"status": result.status},
        )
        return result.to_dict()

    @app.post("/api/opportunities/tasks/sync")
    def sync_opportunity_tasks(
        request: dict[str, object] = Body(default={}),
    ) -> dict[str, object]:
        try:
            result = sync_feishu_tasks(
                settings,
                limit=int(request.get("limit") or 200),
            )
            relationship_result = sync_relationship_action_tasks(
                settings,
                limit=int(request.get("limit") or 200),
            )
        except (FeishuError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        record_activity(
            settings,
            event_type="feishu_task_sync",
            target="opportunity_tasks",
            label=f"同步 {result.scanned_count} 个飞书任务",
            metadata=result.to_dict(),
        )
        payload = result.to_dict()
        payload["relationship_actions"] = relationship_result.to_dict()
        return payload

    @app.get("/api/opportunities/{notice_id}/war-room")
    def opportunity_war_room_plan(
        notice_id: str,
        workspace_id: str = "",
    ) -> dict[str, object]:
        try:
            workspace = get_organization_workspace(settings, workspace_id) if workspace_id else None
            if workspace_id and workspace is None:
                raise HTTPException(status_code=404, detail="organization workspace not found")
            return build_war_room_plan(
                settings,
                notice_id,
                receive_id=workspace.feishu_chat_id if workspace is not None else "",
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/opportunities/{notice_id}/war-room/launch")
    def launch_opportunity_war_room(
        notice_id: str,
        request: dict[str, object] = Body(default={}),
    ) -> dict[str, object]:
        if get_opportunity(settings, notice_id) is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        workspace_id = _optional_string(request.get("workspace_id"))
        workspace = get_organization_workspace(settings, workspace_id) if workspace_id else None
        if workspace_id and workspace is None:
            raise HTTPException(status_code=404, detail="organization workspace not found")
        if workspace is not None:
            receive_id, receive_id_type = workspace.feishu_chat_id, "chat_id"
        else:
            receive_id, receive_id_type = resolve_feishu_receiver(
                settings,
                receive_id=_optional_string(request.get("receive_id")),
                receive_id_type=_optional_string(request.get("receive_id_type")),
            )
        try:
            result = launch_war_room(
                settings,
                notice_id,
                receive_id=receive_id,
                receive_id_type=receive_id_type,
                actor=_optional_string(request.get("actor")) or "admin",
                workspace_id=workspace_id,
            )
        except (FeishuError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        record_activity(
            settings,
            event_type="war_room_launch",
            target=notice_id,
            label=str(result.get("message") or "飞书战情室启动"),
            metadata={"status": result.get("status"), "failed_count": result.get("failed_count", 0)},
        )
        return result

    @app.post("/api/opportunities/{notice_id}/war-room/steps/{step_key}/retry")
    def retry_opportunity_war_room_step(
        notice_id: str,
        step_key: str,
        request: dict[str, object] = Body(default={}),
    ) -> dict[str, object]:
        try:
            return retry_war_room_step(
                settings,
                notice_id,
                step_key,
                actor=_optional_string(request.get("actor")) or "admin",
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (FeishuError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/opportunities/{notice_id}/war-room/sync-back")
    def sync_opportunity_war_room_back(
        notice_id: str,
        request: dict[str, object] = Body(default={}),
    ) -> dict[str, object]:
        try:
            return sync_war_room_back(
                settings,
                notice_id,
                actor=_optional_string(request.get("actor")) or "admin",
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (FeishuError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/opportunities/{notice_id}/war-room/dispatch-changes")
    def dispatch_opportunity_war_room_changes(
        notice_id: str,
        request: dict[str, object] = Body(default={}),
    ) -> dict[str, object]:
        try:
            return dispatch_war_room_changes(
                settings,
                notice_id,
                actor=_optional_string(request.get("actor")) or "admin",
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (FeishuError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/opportunities/{notice_id}/war-room/archive")
    def archive_opportunity_war_room(
        notice_id: str,
        request: dict[str, object] = Body(default={}),
    ) -> dict[str, object]:
        try:
            return archive_war_room(
                settings,
                notice_id,
                actor=_optional_string(request.get("actor")) or "admin",
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/opportunities/{notice_id}/collaboration-notes")
    def opportunity_collaboration_notes(notice_id: str, limit: int = 50) -> dict[str, object]:
        if get_opportunity(settings, notice_id) is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        items = list_collaboration_notes(settings, notice_id, limit=limit)
        return {"items": [item.to_dict() for item in items], "returned": len(items)}

    @app.post("/api/opportunities/{notice_id}/collaboration-notes")
    def save_opportunity_collaboration_note(
        notice_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        if get_opportunity(settings, notice_id) is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        try:
            note = record_collaboration_note(
                settings,
                notice_id=notice_id,
                content=str(request.get("content") or ""),
                actor=str(request.get("actor") or "admin"),
                channel=str(request.get("channel") or "web"),
                source_message_id=str(request.get("source_message_id") or ""),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"status": "saved", "note": note.to_dict()}

    @app.post("/api/opportunities/send-feishu")
    def send_opportunity_feishu(request: dict[str, object] = Body(...)) -> dict[str, object]:
        notice_id = str(request.get("notice_id") or "").strip()
        if not notice_id:
            raise HTTPException(status_code=400, detail="notice_id is required")
        opportunity = get_opportunity(settings, notice_id)
        if opportunity is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        receive_id, receive_id_type = resolve_feishu_receiver(
            settings,
            receive_id=_optional_string(request.get("receive_id")),
            receive_id_type=_optional_string(request.get("receive_id_type")),
        )
        try:
            result = start_opportunity_collaboration(
                settings,
                opportunity,
                receive_id=receive_id,
                receive_id_type=receive_id_type,
                owner_open_id=str(request.get("owner_open_id") or "").strip(),
                owner_name=str(request.get("owner_name") or "").strip(),
                create_task=bool(request.get("create_task", True)),
                create_calendar_event=bool(request.get("create_calendar_event", True)),
            )
            attempt = record_delivery_attempt(
                settings,
                channel="feishu",
                artifact_type="opportunity",
                artifact_key=notice_id,
                status="sent",
                external_id=result.message_id or result.task_guid or None,
            )
        except (FeishuError, ValueError) as exc:
            attempt = record_delivery_attempt(
                settings,
                channel="feishu",
                artifact_type="opportunity",
                artifact_key=notice_id,
                status="failed",
                error=str(exc),
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        record_activity(
            settings,
            event_type="feishu_opportunity_send",
            target=notice_id,
            label=str(opportunity.get("title") or ""),
        )
        return {
            "status": "sent" if result.message_id else "started",
            "attempt_id": attempt.id,
            **result.to_dict(),
        }

    @app.get("/api/opportunities/{notice_id}/workflow")
    def opportunity_workflow(notice_id: str) -> dict[str, object]:
        if get_opportunity(settings, notice_id) is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        return get_workflow(settings, notice_id).to_dict()

    @app.get("/api/opportunities/{notice_id}/team")
    def opportunity_team(notice_id: str) -> dict[str, object]:
        opportunity = get_opportunity(settings, notice_id)
        if opportunity is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        return _mapping_value(opportunity.get("team"))

    @app.get("/api/opportunities/{notice_id}/requirements")
    def opportunity_requirements(notice_id: str) -> dict[str, object]:
        if get_opportunity(settings, notice_id) is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        return {
            "items": [item.to_dict() for item in list_requirements(settings, notice_id)],
            "summary": requirement_summary(settings, notice_id),
            "impact": requirement_change_impact(settings, notice_id),
        }

    @app.get("/api/capabilities")
    def enterprise_capabilities(workspace_id: str = "default") -> dict[str, object]:
        return {"items": [item.to_dict() for item in list_capabilities(settings, workspace_id=workspace_id)]}

    @app.post("/api/capabilities")
    def save_enterprise_capability(request: dict[str, object] = Body(...)) -> dict[str, object]:
        try:
            capability = upsert_capability(
                settings,
                capability_key=str(request.get("capability_key") or ""),
                title=str(request.get("title") or ""),
                capability_type=str(request.get("capability_type") or ""),
                evidence_text=str(request.get("evidence_text") or ""),
                source_url=str(request.get("source_url") or ""),
                source_locator=str(request.get("source_locator") or ""),
                verification_status=str(request.get("verification_status") or "draft"),
                owner=str(request.get("owner") or ""),
                valid_until=str(request.get("valid_until") or ""),
                workspace_id=str(request.get("workspace_id") or "default"),
                applicable_entity=str(request.get("applicable_entity") or ""),
                product_model=str(request.get("product_model") or ""),
                regions=request.get("regions") if isinstance(request.get("regions"), list) else [],
                authorization_scope=str(request.get("authorization_scope") or ""),
                source_file_name=str(request.get("source_file_name") or ""),
                valid_from=str(request.get("valid_from") or ""),
                industry=str(request.get("industry") or ""),
                sample_redacted=bool(request.get("sample_redacted")),
                actor=str(request.get("actor") or "admin"),
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"status": "saved", "capability": capability.to_dict()}

    @app.get("/api/opportunities/{notice_id}/capability-matches")
    def opportunity_capability_matches(notice_id: str) -> dict[str, object]:
        if get_opportunity(settings, notice_id) is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        return {
            "items": [item.to_dict() for item in list_requirement_capability_matches(settings, notice_id)],
            "summary": capability_match_summary(settings, notice_id),
        }

    @app.post("/api/opportunities/{notice_id}/capability-matches/analyze")
    def analyze_opportunity_capability_matches(
        notice_id: str,
        request: dict[str, object] = Body(default={}),
    ) -> dict[str, object]:
        if get_opportunity(settings, notice_id) is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        try:
            return analyze_capability_matches(
                settings,
                notice_id,
                workspace_id=str(request.get("workspace_id") or ""),
            )
        except LookupError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/opportunities/{notice_id}/capability-matches/{match_id}/decision")
    def decide_opportunity_capability_match(
        notice_id: str,
        match_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            item = decide_capability_match(
                settings,
                notice_id,
                match_id,
                verdict=str(request.get("verdict") or ""),
                actor=str(request.get("actor") or "admin"),
                note=str(request.get("note") or ""),
                accept=bool(request.get("accept")),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "status": "saved",
            "item": item.to_dict(),
            "summary": capability_match_summary(settings, notice_id),
        }

    @app.get("/api/opportunities/{notice_id}/capability-passport")
    def opportunity_capability_passport(notice_id: str, workspace_id: str = "") -> dict[str, object]:
        if get_opportunity(settings, notice_id) is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        return build_capability_passport(settings, notice_id, workspace_id=workspace_id)

    @app.post("/api/opportunities/{notice_id}/capability-gap-actions")
    def create_opportunity_capability_gap_action(
        notice_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            item = create_gap_action(
                settings,
                notice_id,
                str(request.get("match_id") or ""),
                action_type=str(request.get("action_type") or ""),
                actor=str(request.get("actor") or "admin"),
                assignee_member_id=str(request.get("assignee_member_id") or ""),
                due_at=str(request.get("due_at") or ""),
                title=str(request.get("title") or ""),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"status": "created", "item": item, "passport": build_capability_passport(settings, notice_id)}

    @app.post("/api/opportunities/{notice_id}/capability-gap-actions/{action_id}/complete")
    def complete_opportunity_capability_gap_action(
        notice_id: str,
        action_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            item = complete_gap_action(
                settings,
                notice_id,
                action_id,
                actor=str(request.get("actor") or "admin"),
                note=str(request.get("note") or ""),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"status": "completed", "item": item, "passport": build_capability_passport(settings, notice_id)}

    @app.post("/api/opportunities/{notice_id}/capability-passport/sync-result")
    def sync_opportunity_result_to_capability_passport(notice_id: str) -> dict[str, object]:
        try:
            result = sync_project_results_to_passport(settings, notice_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"status": "synced", **result, "passport": build_capability_passport(settings, notice_id)}

    @app.post("/api/opportunities/{notice_id}/requirements/extract")
    def extract_opportunity_requirements(notice_id: str) -> dict[str, object]:
        try:
            result = extract_and_save_requirements(settings, notice_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            **result,
            "summary": requirement_summary(settings, notice_id),
            "impact": requirement_change_impact(settings, notice_id),
        }

    @app.post("/api/opportunities/{notice_id}/requirements/sync-feishu")
    def sync_opportunity_requirements_to_feishu(notice_id: str) -> dict[str, object]:
        if get_opportunity(settings, notice_id) is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        return sync_requirements_to_feishu(settings, notice_id).to_dict()

    @app.post("/api/opportunities/{notice_id}/requirements/sync-bitable")
    def sync_opportunity_requirements_to_bitable(notice_id: str) -> dict[str, object]:
        if get_opportunity(settings, notice_id) is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        return sync_requirements_to_bitable(settings, notice_id)

    @app.post("/api/opportunities/{notice_id}/requirements/sync-task-status")
    def sync_opportunity_requirement_task_status(notice_id: str) -> dict[str, object]:
        if get_opportunity(settings, notice_id) is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        return sync_requirement_task_status(settings, notice_id).to_dict()

    @app.post("/api/opportunities/{notice_id}/requirements/sync-completion")
    def sync_opportunity_requirement_completion(notice_id: str) -> dict[str, object]:
        if get_opportunity(settings, notice_id) is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        return sync_requirement_completion_to_feishu(settings, notice_id).to_dict()

    @app.post("/api/opportunities/{notice_id}/requirements")
    def save_opportunity_requirement(
        notice_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            requirement = upsert_requirement(
                settings,
                notice_id=notice_id,
                requirement_key=str(request.get("requirement_key") or ""),
                requirement_type=str(request.get("requirement_type") or ""),
                title=str(request.get("title") or ""),
                evidence_text=str(request.get("evidence_text") or ""),
                source_url=str(request.get("source_url") or ""),
                source_locator=str(request.get("source_locator") or ""),
                mandatory=bool(request.get("mandatory")),
                confidence=int(request.get("confidence") or 0),
                weight=float(request.get("weight") or 0),
                status=str(request.get("status") or "pending"),
                assignee_member_id=str(request.get("assignee_member_id") or ""),
                due_at=str(request.get("due_at") or ""),
                note=str(request.get("note") or ""),
                source_revision_id=str(request.get("source_revision_id") or ""),
                parent_requirement_id=str(request.get("parent_requirement_id") or ""),
                extraction_mode=str(request.get("extraction_mode") or "manual"),
                actor=str(request.get("actor") or "admin"),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "status": "saved",
            "requirement": requirement.to_dict(),
            "summary": requirement_summary(settings, notice_id),
            "impact": requirement_change_impact(settings, notice_id),
        }

    @app.get("/api/opportunities/{notice_id}/bid-workplan")
    def opportunity_bid_workplan(notice_id: str) -> dict[str, object]:
        try:
            return get_bid_workplan(settings, notice_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/opportunities/{notice_id}/requirements/{requirement_id}/confirm")
    def confirm_opportunity_requirement(
        notice_id: str,
        requirement_id: str,
        request: dict[str, object] = Body(default={}),
    ) -> dict[str, object]:
        try:
            item = confirm_requirement(
                settings,
                notice_id,
                requirement_id,
                actor=str(request.get("actor") or "web:admin"),
                assignee_member_id=str(request.get("assignee_member_id") or ""),
                due_at=str(request.get("due_at") or ""),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"status": "confirmed", "requirement": item, "workplan": get_bid_workplan(settings, notice_id)}

    @app.post("/api/opportunities/{notice_id}/requirements/{requirement_id}/split")
    def split_opportunity_requirement(
        notice_id: str,
        requirement_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        raw_parts = request.get("parts")
        parts = [item for item in raw_parts if isinstance(item, dict)] if isinstance(raw_parts, list) else []
        try:
            children = split_requirement(
                settings,
                notice_id,
                requirement_id,
                parts,
                actor=str(request.get("actor") or "web:admin"),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"status": "split", "items": children, "workplan": get_bid_workplan(settings, notice_id)}

    @app.post("/api/opportunities/{notice_id}/requirements/merge")
    def merge_opportunity_requirements(
        notice_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        raw_ids = request.get("requirement_ids")
        requirement_ids = [str(value) for value in raw_ids] if isinstance(raw_ids, list) else []
        try:
            item = merge_requirements(
                settings,
                notice_id,
                requirement_ids,
                requirement_key=str(request.get("requirement_key") or ""),
                title=str(request.get("title") or ""),
                actor=str(request.get("actor") or "web:admin"),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"status": "merged", "requirement": item, "workplan": get_bid_workplan(settings, notice_id)}

    @app.post("/api/opportunities/{notice_id}/bid-workplan/build")
    def build_opportunity_bid_workplan(
        notice_id: str,
        request: dict[str, object] = Body(default={}),
    ) -> dict[str, object]:
        try:
            return build_bid_workplan(settings, notice_id, actor=str(request.get("actor") or "web:admin"))
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/opportunities/{notice_id}/bid-workplan/tasks/{task_id}/complete")
    def complete_opportunity_bid_workplan_task(
        notice_id: str,
        task_id: str,
        request: dict[str, object] = Body(default={}),
    ) -> dict[str, object]:
        try:
            return complete_bid_task(settings, notice_id, task_id, actor=str(request.get("actor") or "web:admin"))
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/opportunities/{notice_id}/bid-workplan/pricing")
    def save_opportunity_bid_pricing(
        notice_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            item = upsert_pricing_item(
                settings,
                notice_id,
                item_key=str(request.get("item_key") or ""),
                title=str(request.get("title") or ""),
                requirement_id=str(request.get("requirement_id") or ""),
                quantity=float(request.get("quantity") or 0),
                unit=str(request.get("unit") or "项"),
                unit_price=float(request.get("unit_price") or 0),
                cost=float(request.get("cost") or 0),
                tax_rate=float(request.get("tax_rate") or 0),
                owner_member_id=str(request.get("owner_member_id") or ""),
                status=str(request.get("status") or "draft"),
                note=str(request.get("note") or ""),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"status": "saved", "item": item, "workplan": get_bid_workplan(settings, notice_id)}

    @app.post("/api/opportunities/{notice_id}/bid-workplan/sync-feishu")
    def sync_opportunity_bid_workplan_feishu(notice_id: str) -> dict[str, object]:
        try:
            result = sync_bid_workplan_to_feishu(settings, notice_id)
        except (FeishuError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {**result, "workplan": get_bid_workplan(settings, notice_id)}

    @app.post("/api/opportunities/{notice_id}/bid-workplan/sync-task-status")
    def sync_opportunity_bid_workplan_status(notice_id: str) -> dict[str, object]:
        try:
            result = sync_bid_workplan_task_status(settings, notice_id)
        except (FeishuError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {**result, "workplan": get_bid_workplan(settings, notice_id)}

    @app.get("/api/opportunities/{notice_id}/bid-workplan/export")
    def export_opportunity_bid_workplan(notice_id: str):
        try:
            path = export_bid_workplan(settings, notice_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return FileResponse(path, filename=path.name, media_type="application/zip")

    @app.get("/api/opportunities/{notice_id}/review-board")
    def opportunity_review_board(notice_id: str) -> dict[str, object]:
        if get_opportunity(settings, notice_id) is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        return {
            "items": [item.to_dict() for item in list_requirement_review_cases(settings, notice_id)],
            "summary": requirement_review_summary(settings, notice_id),
            "opinions": [item.to_dict() for item in list_review_opinions(settings, notice_id)],
            "human_opinions": [
                item.to_dict() for item in list_human_review_opinions(settings, notice_id)
            ],
            "actions": [item.to_dict() for item in list_review_actions(settings, notice_id)],
            "action_summary": review_action_summary(settings, notice_id),
            "suggestions": review_agent_suggestions(settings, notice_id),
            "agent_runs": list_review_agent_runs(settings, notice_id),
            "agent_runtime": review_agent_runtime_summary(settings, notice_id),
        }

    @app.post("/api/opportunities/{notice_id}/review-board/sync")
    def sync_opportunity_review_board(notice_id: str) -> dict[str, object]:
        if get_opportunity(settings, notice_id) is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        return sync_requirement_review_cases(settings, notice_id)

    @app.post("/api/opportunities/{notice_id}/review-board/agents")
    def run_opportunity_review_agents(
        notice_id: str,
        request: dict[str, object] = Body(default={}),
    ) -> dict[str, object]:
        if get_opportunity(settings, notice_id) is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        roles = request.get("roles") if isinstance(request.get("roles"), list) else None
        review_ids = request.get("review_ids") if isinstance(request.get("review_ids"), list) else None
        try:
            return run_review_agents(
                settings,
                notice_id,
                roles=[str(item) for item in roles] if roles is not None else None,
                review_ids=[str(item) for item in review_ids] if review_ids is not None else None,
                actor=str(request.get("actor") or "web:admin"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/opportunities/{notice_id}/review-board/{review_id}/agents/{agent_role}/retry")
    def retry_opportunity_review_agent(notice_id: str, review_id: str, agent_role: str) -> dict[str, object]:
        try:
            return retry_review_agent(settings, notice_id, review_id, agent_role, actor="web:admin")
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/opportunities/{notice_id}/review-board/send-feishu")
    def send_opportunity_review_board_to_feishu(
        notice_id: str,
        request: dict[str, object] = Body(default={}),
    ) -> dict[str, object]:
        if get_opportunity(settings, notice_id) is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        workspace_id = _optional_string(request.get("workspace_id"))
        workspace = get_organization_workspace(settings, workspace_id) if workspace_id else None
        if workspace_id and workspace is None:
            raise HTTPException(status_code=404, detail="organization workspace not found")
        try:
            result = send_requirement_review_digest(
                settings,
                notice_id,
                receive_id=workspace.feishu_chat_id if workspace is not None else None,
                receive_id_type="chat_id" if workspace is not None else None,
                force=bool(request.get("force", False)),
            )
        except (FeishuError, LookupError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        record_activity(
            settings,
            event_type="feishu_review_board_send",
            target=notice_id,
            label=f"会审摘要{result.status}",
            metadata=result.to_dict(),
        )
        return result.to_dict()

    @app.post("/api/opportunities/{notice_id}/review-board/opinions")
    def save_opportunity_review_opinion(
        notice_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            opinion = record_human_review_opinion(
                settings,
                notice_id=notice_id,
                requirement_id=str(request.get("requirement_id") or ""),
                content=str(request.get("content") or ""),
                actor=str(request.get("actor") or ""),
                channel="web",
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "status": "saved",
            "opinion": opinion.to_dict(),
            "human_opinions": [
                item.to_dict() for item in list_human_review_opinions(settings, notice_id)
            ],
        }

    @app.post("/api/opportunities/{notice_id}/review-board/opinions/{opinion_id}/actions")
    def create_opportunity_review_action(
        notice_id: str,
        opinion_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            action = create_review_action(
                settings,
                notice_id=notice_id,
                opinion_id=opinion_id,
                assignee_member_id=str(request.get("assignee_member_id") or ""),
                due_at=str(request.get("due_at") or ""),
                action_note=str(request.get("action_note") or ""),
                actor=str(request.get("actor") or ""),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "status": "saved",
            "action": action.to_dict(),
            "summary": review_action_summary(settings, notice_id),
        }

    @app.post("/api/opportunities/{notice_id}/review-board/actions/{action_id}/complete")
    def complete_opportunity_review_action(
        notice_id: str,
        action_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            action = complete_review_action(
                settings,
                notice_id=notice_id,
                action_id=action_id,
                actor=str(request.get("actor") or ""),
                completion_note=str(request.get("completion_note") or ""),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "status": "completed",
            "action": action.to_dict(),
            "summary": review_action_summary(settings, notice_id),
        }

    @app.post("/api/opportunities/{notice_id}/review-board/actions/{action_id}/sync-feishu")
    def sync_opportunity_review_action_to_feishu(
        notice_id: str,
        action_id: str,
    ) -> dict[str, object]:
        try:
            action = bind_review_action_to_requirement(
                settings,
                notice_id=notice_id,
                action_id=action_id,
            )
            result = sync_requirements_to_feishu(
                settings,
                notice_id,
                requirement_ids={action.requirement_id},
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (FeishuError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "status": result.status,
            "action": action.to_dict(),
            "sync": result.to_dict(),
            "summary": review_action_summary(settings, notice_id),
        }

    @app.post("/api/opportunities/{notice_id}/review-board/{review_id}/resolve")
    def resolve_opportunity_review_board_item(
        notice_id: str,
        review_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            item = resolve_requirement_review_case(
                settings,
                notice_id,
                review_id,
                decision=str(request.get("decision") or ""),
                actor=str(request.get("actor") or ""),
                note=str(request.get("note") or ""),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "status": "resolved",
            "item": item.to_dict(),
            "summary": requirement_review_summary(settings, notice_id),
        }

    @app.post("/api/opportunities/{notice_id}/team")
    def add_opportunity_team_member(
        notice_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        if get_opportunity(settings, notice_id) is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        try:
            member = upsert_team_member(
                settings,
                notice_id=notice_id,
                member_name=str(request.get("member_name") or ""),
                member_open_id=str(request.get("member_open_id") or ""),
                role=str(request.get("role") or ""),
                organization_type=str(request.get("organization_type") or "internal"),
                organization_name=str(request.get("organization_name") or ""),
                responsibility=str(request.get("responsibility") or ""),
                actor=str(request.get("actor") or "admin"),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _team_mutation_response(settings, notice_id, member.to_dict(), "added")

    @app.delete("/api/opportunities/{notice_id}/team/{member_id}")
    def delete_opportunity_team_member(
        notice_id: str,
        member_id: str,
        actor: str = "admin",
    ) -> dict[str, object]:
        try:
            member = remove_team_member(
                settings,
                notice_id=notice_id,
                member_id=member_id,
                actor=actor,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _team_mutation_response(settings, notice_id, member.to_dict(), "removed")

    @app.get("/api/opportunities/{notice_id}/stakeholders")
    def opportunity_stakeholders(notice_id: str) -> dict[str, object]:
        opportunity = get_opportunity(settings, notice_id)
        if opportunity is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        return _mapping_value(opportunity.get("stakeholder_map"))

    @app.post("/api/opportunities/{notice_id}/stakeholders")
    def add_opportunity_stakeholder(
        notice_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        if get_opportunity(settings, notice_id) is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        try:
            stakeholder = upsert_stakeholder(
                settings,
                notice_id=notice_id,
                stakeholder_name=str(request.get("stakeholder_name") or ""),
                organization_name=str(request.get("organization_name") or ""),
                job_title=str(request.get("job_title") or ""),
                role=str(request.get("role") or ""),
                influence=str(request.get("influence") or "medium"),
                stance=str(request.get("stance") or "unknown"),
                relationship_strength=str(
                    request.get("relationship_strength") or "unknown"
                ),
                owner_member_id=str(request.get("owner_member_id") or ""),
                next_action=str(request.get("next_action") or ""),
                evidence_source=str(request.get("evidence_source") or ""),
                evidence_url=str(request.get("evidence_url") or ""),
                evidence_text=str(request.get("evidence_text") or ""),
                actor=str(request.get("actor") or "admin"),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _stakeholder_mutation_response(
            settings,
            notice_id,
            stakeholder.to_dict(),
            "updated",
        )

    @app.delete("/api/opportunities/{notice_id}/stakeholders/{stakeholder_id}")
    def delete_opportunity_stakeholder(
        notice_id: str,
        stakeholder_id: str,
        actor: str = "admin",
    ) -> dict[str, object]:
        try:
            stakeholder = remove_stakeholder(
                settings,
                notice_id=notice_id,
                stakeholder_id=stakeholder_id,
                actor=actor,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _stakeholder_mutation_response(
            settings,
            notice_id,
            stakeholder.to_dict(),
            "removed",
        )

    @app.get("/api/opportunities/{notice_id}/relationship-actions")
    def opportunity_relationship_actions(notice_id: str) -> dict[str, object]:
        opportunity = get_opportunity(settings, notice_id)
        if opportunity is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        return _mapping_value(opportunity.get("relationship_actions"))

    @app.post("/api/opportunities/{notice_id}/relationship-actions")
    def add_opportunity_relationship_action(
        notice_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        if get_opportunity(settings, notice_id) is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        try:
            action = create_relationship_action(
                settings,
                notice_id=notice_id,
                stakeholder_id=str(request.get("stakeholder_id") or ""),
                title=str(request.get("title") or ""),
                action_type=str(request.get("action_type") or "engagement"),
                priority=str(request.get("priority") or "normal"),
                assignee_member_id=str(request.get("assignee_member_id") or ""),
                due_at=str(request.get("due_at") or ""),
                source_type=str(request.get("source_type") or "manual"),
                source_ref=str(request.get("source_ref") or ""),
                actor=str(request.get("actor") or "admin"),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        task_result = None
        task_error = ""
        if bool(request.get("create_feishu_task", False)):
            try:
                task_result = create_relationship_action_task(settings, action.id)
                action = task_result.action
            except (FeishuError, ValueError, TypeError) as exc:
                task_error = f"{type(exc).__name__}: {exc}"
        return _relationship_action_mutation_response(
            settings,
            notice_id,
            action.to_dict(),
            "created",
            task_result=task_result.to_dict() if task_result else None,
            task_error=task_error,
        )

    @app.patch(
        "/api/opportunities/{notice_id}/relationship-actions/{relationship_action_id}"
    )
    def update_opportunity_relationship_action(
        notice_id: str,
        relationship_action_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        try:
            current = get_relationship_action(settings, relationship_action_id)
            if current.notice_id != notice_id:
                raise LookupError("relationship action not found")
            target_status = str(request.get("status") or "")
            if (
                current.feishu_task_guid
                and current.status == "open"
                and target_status in {"completed", "cancelled"}
            ):
                raise HTTPException(
                    status_code=409,
                    detail="请先在飞书任务中完成或关闭，系统同步后再补充结果",
                )
            action = update_relationship_action(
                settings,
                notice_id=notice_id,
                action_id=relationship_action_id,
                status=target_status,
                outcome_note=str(request.get("outcome_note") or ""),
                actor=str(request.get("actor") or "admin"),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _relationship_action_mutation_response(
            settings,
            notice_id,
            action.to_dict(),
            "updated",
        )

    @app.post(
        "/api/opportunities/{notice_id}/relationship-actions/{relationship_action_id}/feishu-task"
    )
    def create_opportunity_relationship_action_feishu_task(
        notice_id: str,
        relationship_action_id: str,
    ) -> dict[str, object]:
        try:
            current = get_relationship_action(settings, relationship_action_id)
            if current.notice_id != notice_id:
                raise LookupError("relationship action not found")
            result = create_relationship_action_task(settings, relationship_action_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (FeishuError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _relationship_action_mutation_response(
            settings,
            notice_id,
            result.action.to_dict(),
            result.status,
            task_result=result.to_dict(),
        )

    @app.get("/api/opportunities/{notice_id}/facts")
    def opportunity_facts(notice_id: str) -> dict[str, object]:
        opportunity = get_opportunity(settings, notice_id)
        if opportunity is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        return {
            "opportunity": opportunity,
            "overrides": opportunity.get("fact_overrides") or [],
            "audit": load_fact_audit(settings, notice_id),
        }

    @app.patch("/api/opportunities/{notice_id}/facts")
    def update_opportunity_facts(
        notice_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        opportunity = get_opportunity(settings, notice_id)
        if opportunity is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        facts = request.get("facts")
        if not isinstance(facts, dict):
            raise HTTPException(status_code=400, detail="facts must be an object")
        audit_before = load_fact_audit(settings, notice_id, limit=1)
        try:
            overrides = upsert_verified_facts(
                settings,
                notice_id=notice_id,
                facts=facts,
                source_url=str(request.get("source_url") or opportunity.get("source_url") or ""),
                evidence_text=str(request.get("evidence_text") or ""),
                note=str(request.get("note") or ""),
                actor=str(request.get("actor") or "admin"),
                channel=str(request.get("channel") or "web"),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        refreshed = get_opportunity(settings, notice_id)
        if refreshed is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        audit = load_fact_audit(settings, notice_id)
        before_id = str(audit_before[0].get("id") or "") if audit_before else ""
        after_id = str(audit[0].get("id") or "") if audit else ""
        changed = bool(after_id and after_id != before_id)
        if changed:
            qualification = _mapping_value(refreshed.get("qualification"))
            workflow = update_workflow(
                settings,
                notice_id,
                qualification_score=int(qualification.get("score") or 0),
                qualification_status=str(qualification.get("status") or "blocked"),
                updated_by=str(request.get("actor") or "admin"),
            )
            refreshed = get_opportunity(settings, notice_id) or refreshed
            bitable = update_opportunity_facts_in_bitable(
                settings,
                notice_id=notice_id,
                opportunity=refreshed,
            )
            bitable_status = bitable.status
            bitable_message = bitable.message
            record_activity(
                settings,
                event_type="opportunity_facts_verified",
                target=notice_id,
                label=f"核验 {len(overrides)} 项事实",
                metadata={"fields": sorted(facts), "bitable_status": bitable.status},
            )
        else:
            workflow = get_workflow(settings, notice_id)
            bitable_status = "skipped"
            bitable_message = "verified facts are unchanged"
        return {
            "status": "updated" if changed else "unchanged",
            "opportunity": refreshed,
            "workflow": workflow.to_dict(),
            "overrides": overrides,
            "audit": audit,
            "bitable_status": bitable_status,
            "bitable_message": bitable_message,
        }

    @app.post("/api/opportunities/{notice_id}/actions")
    def opportunity_action(
        notice_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        opportunity = get_opportunity(settings, notice_id)
        if opportunity is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        action = str(request.get("action") or "").strip()
        if not action:
            raise HTTPException(status_code=400, detail="action is required")
        channel = str(request.get("channel") or "web").strip()
        if channel not in {"web", "feishu_record_view", "api"}:
            raise HTTPException(status_code=400, detail="unsupported opportunity action channel")
        actor_open_id = str(request.get("actor_open_id") or "").strip()
        actor_name = str(request.get("actor_name") or "").strip()
        if action == "claim" and actor_open_id.startswith("base:"):
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Base 用户不能直接认领，请发送飞书机会卡后由成员点击认领",
                    "action": action,
                    "reasons": ["Base 用户标识不能替代 Task v2 所需的飞书 open_id"],
                },
            )
        if channel == "feishu_record_view":
            if action == "claim":
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "记录视图不能直接认领，请发送飞书机会卡后由成员点击认领",
                        "action": action,
                        "reasons": ["Base 用户标识不能替代 Task v2 所需的飞书 open_id"],
                    },
                )
            if not actor_open_id.startswith("base:"):
                raise HTTPException(
                    status_code=400,
                    detail="feishu_record_view requires a base-scoped actor id",
                )
        actor_open_id = actor_open_id or ("web:admin" if channel == "web" else "api")
        actor_name = actor_name or ("admin" if channel == "web" else channel)
        try:
            workflow = apply_action(
                settings,
                notice_id,
                action,
                actor_open_id=actor_open_id,
                actor_name=actor_name,
                qualification=_mapping_value(opportunity.get("qualification")),
                decision_reason=str(request.get("reason") or "").strip(),
                payload={
                    "channel": channel,
                    "outcome": request.get("outcome"),
                },
            )
        except WorkflowGateError as exc:
            raise HTTPException(
                status_code=409,
                detail={"message": str(exc), "action": exc.action, "reasons": exc.reasons},
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        workflow, refreshed, refreshed_opportunity = _refresh_qualification(
            settings,
            notice_id,
            workflow,
        )
        bitable = update_opportunity_workflow_in_bitable(
            settings,
            notice_id=notice_id,
            workflow=_workflow_sync_payload(workflow, refreshed_opportunity),
        )
        record_activity(
            settings,
            event_type="opportunity_action",
            target=notice_id,
            label=workflow.stage_label,
            metadata={"action": action, "channel": channel},
        )
        return {
            "status": "updated",
            "workflow": workflow.to_dict(),
            "qualification": refreshed,
            "bitable_status": bitable.status,
        }

    @app.put("/api/opportunities/{notice_id}/outcome")
    def opportunity_outcome(
        notice_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        opportunity = get_opportunity(settings, notice_id)
        if opportunity is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        workflow = get_workflow(settings, notice_id)
        if workflow.stage not in {"won", "lost"}:
            raise HTTPException(
                status_code=409,
                detail="submit the outcome together with mark_won or mark_lost",
            )
        try:
            outcome = record_outcome(
                settings,
                notice_id,
                _mapping_value(request.get("outcome")),
                expected_result=workflow.stage,
                actor=str(request.get("actor_name") or "admin").strip(),
            )
        except (LookupError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        refreshed = get_opportunity(settings, notice_id)
        assert refreshed is not None
        bitable = update_opportunity_workflow_in_bitable(
            settings,
            notice_id=notice_id,
            workflow=_workflow_sync_payload(workflow, refreshed),
        )
        record_activity(
            settings,
            event_type="opportunity_outcome_updated",
            target=notice_id,
            label="投标结果复盘已更新",
            metadata={"result": outcome.result, "bitable_status": bitable.status},
        )
        return {
            "status": "updated",
            "outcome": outcome.to_dict(),
            "bitable_status": bitable.status,
            "bitable_message": bitable.message,
        }

    @app.post("/api/integrations/feishu/callback")
    def feishu_card_callback(request: dict[str, object] = Body(...)) -> dict[str, object]:
        expected = settings.feishu_callback_verification_token()
        if not expected:
            raise HTTPException(
                status_code=503,
                detail="FEISHU_CALLBACK_VERIFICATION_TOKEN is not configured",
            )
        supplied = _feishu_callback_token(request)
        if not supplied or not secrets.compare_digest(supplied, expected):
            raise HTTPException(status_code=401, detail="invalid Feishu callback token")
        challenge = str(request.get("challenge") or "")
        if challenge:
            return {"challenge": challenge}
        schedule_ingest_callback = (
            schedule_adaptive_ingest if app.state.scheduler is not None else None
        )
        schedule_user_callback = (
            schedule_adaptive_subscription if app.state.scheduler is not None else None
        )
        try:
            return process_feishu_card_action(
                settings,
                request,
                schedule_ingest=schedule_ingest_callback,
                schedule_subscription=schedule_user_callback,
                send_opportunity_briefing=send_adaptive_opportunity_briefing,
                start_collaboration=start_adaptive_opportunity_collaboration,
            )
        except OpportunityNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (FeishuError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/integrations/feishu/events")
    def feishu_message_event(request: dict[str, object] = Body(...)) -> dict[str, object]:
        expected = settings.feishu_callback_verification_token()
        if not expected:
            raise HTTPException(
                status_code=503,
                detail="FEISHU_CALLBACK_VERIFICATION_TOKEN is not configured",
            )
        supplied = _feishu_callback_token(request)
        if not supplied or not secrets.compare_digest(supplied, expected):
            raise HTTPException(status_code=401, detail="invalid Feishu callback token")
        challenge = str(request.get("challenge") or "")
        if challenge:
            return {"challenge": challenge}
        try:
            event = accept_feishu_message_event(settings, request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        executor = app.state.feishu_executor
        if event.status == "accepted" and executor is not None:
            executor.submit(
                process_feishu_message_event,
                settings,
                event.event_id,
                scheduler=app.state.scheduler,
            )
        return {"code": 0, "status": event.status, "event_id": event.event_id}

    @app.get("/api/integrations/feishu/message-events")
    def feishu_message_event_history(limit: int = 20) -> dict[str, object]:
        return {
            "items": [
                item.to_dict() for item in list_feishu_message_events(settings, limit=limit)
            ]
        }

    @app.post("/api/runs")
    def create_run(request: dict[str, object] = Body(...)) -> dict[str, object]:
        query = str(request.get("query") or "").strip()
        if not query:
            raise HTTPException(status_code=400, detail="query is required")
        now_raw = request.get("now")
        now = datetime.fromisoformat(str(now_raw)) if now_raw else None
        max_pages, max_results = _parse_limits(request)
        feishu_receive_id, feishu_receive_id_type = _feishu_delivery_target_from_request(
            settings,
            request,
        )
        result = run_once(
            settings=settings,
            query=query,
            now=now,
            max_pages=max_pages,
            max_results=max_results,
            model_strategy=_model_strategy_from_request(request),
            delivery_channels=_delivery_channels_from_request(request),
            feishu_receive_id=feishu_receive_id,
            feishu_receive_id_type=feishu_receive_id_type,
        ).to_dict()
        record_activity(
            settings,
            event_type="run_start",
            target="api",
            label=query,
            metadata={"query": query, "run_id": result.get("run_id"), "sync": True},
        )
        return result

    @app.post("/api/runs/start")
    def start_run_api(
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        query = str(request.get("query") or "").strip()
        if not query:
            raise HTTPException(status_code=400, detail="query is required")
        now_raw = request.get("now")
        now = datetime.fromisoformat(str(now_raw)) if now_raw else None
        max_pages, max_results = _parse_limits(request)
        feishu_receive_id, feishu_receive_id_type = _feishu_delivery_target_from_request(
            settings,
            request,
        )
        run_id = str(uuid4())
        thread = Thread(
            target=run_once,
            kwargs={
                "settings": settings,
                "query": query,
                "now": now,
                "max_pages": max_pages,
                "max_results": max_results,
                "model_strategy": _model_strategy_from_request(request),
                "delivery_channels": _delivery_channels_from_request(request),
                "feishu_receive_id": feishu_receive_id,
                "feishu_receive_id_type": feishu_receive_id_type,
                "run_id": run_id,
            },
            daemon=True,
        )
        thread.start()
        record_activity(
            settings,
            event_type="run_start",
            target="web",
            label=query,
            metadata={"query": query, "run_id": run_id, "async": True},
        )
        return {"run_id": run_id, "status": "queued"}

    @app.post("/api/subscriptions")
    def create_subscription_api(request: dict[str, object] = Body(...)) -> dict[str, object]:
        query = str(request.get("query") or "").strip()
        if not query:
            raise HTTPException(status_code=400, detail="query is required")
        now_raw = request.get("now")
        now = datetime.fromisoformat(str(now_raw)) if now_raw else None
        max_pages, max_results = _parse_limits(request)
        feishu_receive_id, feishu_receive_id_type = _feishu_delivery_target_from_request(
            settings,
            request,
        )
        try:
            subscription = create_subscription(
                settings,
                query=query,
                now=now,
                max_pages=max_pages,
                max_results=max_results,
                schedule_override=_schedule_override_from_request(request),
                model_strategy=_model_strategy_from_request(request),
                delivery_channels=_delivery_channels_from_request(request),
                feishu_receive_id=feishu_receive_id,
                feishu_receive_id_type=feishu_receive_id_type,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if app.state.scheduler is not None:
            schedule_subscription(app.state.scheduler, settings, subscription)
        record_activity(
            settings,
            event_type="subscription_create",
            target="web",
            label=query,
            metadata={"query": query, "subscription_id": subscription.id},
        )
        return subscription.to_dict()

    @app.get("/api/subscriptions")
    def subscriptions() -> dict[str, object]:
        return {
            "items": [
                _subscription_api_item(settings, item) for item in list_subscriptions(settings)
            ]
        }

    @app.post("/api/ingest-subscriptions")
    def create_ingest_subscription_api(request: dict[str, object] = Body(...)) -> dict[str, object]:
        topics = _string_list(request.get("topics"))
        regions = _string_list(request.get("regions"))
        if not topics or not regions:
            raise HTTPException(status_code=400, detail="topics and regions are required")
        try:
            subscription = create_ingest_subscription(
                settings,
                name=str(request.get("name") or "ingest"),
                topics=topics,
                regions=regions,
                cron=str(request.get("cron") or settings.ingest_cron),
                window_days=int(request.get("window_days") or 30),
                max_pages=int(request.get("max_pages") or 1),
                max_results=int(request.get("max_results") or 20),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if app.state.scheduler is not None:
            schedule_ingest_subscription(app.state.scheduler, settings, subscription)
        return subscription.to_dict()

    @app.get("/api/ingest-subscriptions")
    def ingest_subscriptions() -> dict[str, object]:
        return {"items": [item.to_dict() for item in list_ingest_subscriptions(settings)]}

    @app.post("/api/ingest-subscriptions/{subscription_id}/run")
    def run_ingest_subscription_api(subscription_id: str) -> dict[str, object]:
        try:
            return run_ingest_subscription(settings, subscription_id=subscription_id).to_dict()
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete("/api/ingest-subscriptions/{subscription_id}")
    def delete_ingest_subscription_api(subscription_id: str) -> dict[str, object]:
        if not delete_ingest_subscription(settings, subscription_id):
            raise HTTPException(status_code=404, detail="ingest subscription not found")
        scheduler = app.state.scheduler
        if scheduler is not None:
            try:
                scheduler.remove_job(f"ingest_subscription:{subscription_id}")
            except Exception:
                pass
        return {"status": "deleted", "id": subscription_id}

    @app.post("/api/subscriptions/{subscription_id}/run")
    def run_subscription_api(subscription_id: str) -> dict[str, object]:
        try:
            result = run_subscription(settings, subscription_id=subscription_id).to_dict()
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        record_activity(
            settings,
            event_type="subscription_run",
            target="subscription",
            label=subscription_id,
            metadata={"subscription_id": subscription_id, "run_id": result.get("run_id")},
        )
        return result

    @app.delete("/api/subscriptions/{subscription_id}")
    def delete_subscription_api(subscription_id: str) -> dict[str, object]:
        with connection(settings) as conn:
            row = conn.execute(
                "SELECT id FROM subscriptions WHERE id = ?",
                (subscription_id,),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="subscription not found")
            conn.execute(
                """
                UPDATE subscriptions
                SET status = 'deleted', updated_at = datetime('now')
                WHERE id = ?
                """,
                (subscription_id,),
            )
        scheduler = app.state.scheduler
        if scheduler is not None:
            try:
                scheduler.remove_job(f"subscription:{subscription_id}")
            except Exception:
                pass
        record_activity(
            settings,
            event_type="subscription_delete",
            target="subscription",
            label=subscription_id,
            metadata={"subscription_id": subscription_id},
        )
        return {"status": "deleted", "id": subscription_id}

    @app.get("/api/runs")
    def runs() -> dict[str, object]:
        with connection(settings) as conn:
            rows = conn.execute(
                """
                SELECT id, subscription_id, original_query, mode, status, window_start, window_end,
                       started_at, finished_at, output_docx_path, stats_json, error
                FROM runs
                WHERE status != 'deleted'
                ORDER BY started_at DESC
                LIMIT 100
                """
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["stats"] = sanitize_stats(json.loads(item.pop("stats_json") or "{}"))
            item["outbox_path"] = _outbox_path_for_run(item["id"], settings)
            items.append(item)
        return {"items": items}

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: str) -> dict[str, object]:
        run = get_run(settings, run_id)
        if run is None or run.get("status") == "deleted":
            raise HTTPException(status_code=404, detail="run not found")
        run["outbox_path"] = _outbox_path_for_run(run_id, settings)
        run["progress"] = _run_progress(settings, run_id, str(run.get("status") or ""))
        stats = run.get("stats")
        if isinstance(stats, dict):
            run["notice_count"] = stats.get("notice_count", 0)
            run["trace_events"] = stats.get("trace_events", 0)
        return run

    @app.get("/api/runs/{run_id}/status")
    def run_status(run_id: str) -> dict[str, object]:
        run = get_run(settings, run_id)
        if run is None or run.get("status") == "deleted":
            raise HTTPException(status_code=404, detail="run not found")
        return {
            "run_id": run_id,
            "status": run.get("status"),
            "progress": _run_progress(settings, run_id, str(run.get("status") or "")),
        }

    @app.delete("/api/runs/{run_id}")
    def delete_run_api(run_id: str) -> dict[str, object]:
        with connection(settings) as conn:
            row = conn.execute("SELECT id FROM runs WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="run not found")
            conn.execute("DELETE FROM outbox_messages WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM model_audits WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM trace_events WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM run_checkpoints WHERE run_id = ?", (run_id,))
            conn.execute(
                """
                UPDATE runs
                SET status = 'deleted',
                    finished_at = COALESCE(finished_at, datetime('now')),
                    error = COALESCE(error, 'deleted by user')
                WHERE id = ?
                """,
                (run_id,),
            )
        record_activity(
            settings,
            event_type="run_delete",
            target="run",
            label=run_id,
            metadata={"run_id": run_id},
        )
        return {"status": "deleted", "id": run_id}

    @app.get("/api/outbox")
    def outbox() -> dict[str, object]:
        tracked = list_outbox_messages(settings)
        latest_feishu: dict[str, dict[str, object]] = {}
        for attempt in list_delivery_attempts(settings, channel="feishu", limit=500):
            latest_feishu.setdefault(attempt.artifact_key, attempt.to_dict())
        tracked_paths = {str(Path(item.docx_path).resolve()) for item in tracked}
        files = sorted(
            settings.outbox_dir.glob("*.docx"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        untracked = [file for file in files if str(file.resolve()) not in tracked_paths]
        return {
            "items": [
                {
                    "id": item.id,
                    "run_id": item.run_id,
                    "subscription_id": item.subscription_id,
                    "name": Path(item.docx_path).name,
                    "path": item.docx_path,
                    "size": Path(item.docx_path).stat().st_size,
                    "status": item.status,
                    "created_at": item.created_at,
                    "download_url": f"/api/outbox/{Path(item.docx_path).name}",
                    "feishu_delivery": latest_feishu.get(Path(item.docx_path).name),
                }
                for item in tracked
                if Path(item.docx_path).exists()
            ]
            + [
                {
                    "id": None,
                    "run_id": None,
                    "subscription_id": None,
                    "name": file.name,
                    "path": str(file),
                    "size": file.stat().st_size,
                    "status": "ready",
                    "created_at": None,
                    "download_url": f"/api/outbox/{file.name}",
                    "feishu_delivery": latest_feishu.get(file.name),
                }
                for file in untracked
            ]
        }

    @app.post("/api/outbox/{filename}/send-feishu")
    def send_outbox_to_feishu(
        filename: str,
        request: dict[str, object] | None = Body(default=None),
    ) -> dict[str, object]:
        path = _resolve_outbox_path(settings, filename)
        if not path.exists():
            raise HTTPException(status_code=404, detail="file not found")
        request = request or {}
        run_id = _optional_string(request.get("run_id"))
        result = deliver_report_to_feishu(
            settings,
            docx_path=path,
            run_id=run_id,
            subscription_id=_optional_string(request.get("subscription_id")),
            receive_id=_optional_string(request.get("receive_id")),
            receive_id_type=_optional_string(request.get("receive_id_type")),
            report_summary=_report_delivery_summary(settings, run_id),
        )
        record_activity(
            settings,
            event_type="feishu_report_send",
            target="outbox",
            label=path.name,
            metadata={
                "filename": path.name,
                "status": result.status,
                "digest_status": result.digest_status,
            },
        )
        if result.status != "sent":
            raise HTTPException(status_code=400, detail=result.to_dict())
        return result.to_dict()

    @app.get("/api/outbox/{filename}")
    def download_outbox(filename: str):
        path = (settings.outbox_dir / filename).resolve()
        if settings.outbox_dir.resolve() not in path.parents or path.suffix.lower() != ".docx":
            raise HTTPException(status_code=400, detail="invalid outbox path")
        if not path.exists():
            raise HTTPException(status_code=404, detail="file not found")
        record_activity(
            settings,
            event_type="download",
            target="outbox",
            label=path.name,
            metadata={"filename": path.name},
        )
        return FileResponse(path, filename=path.name)

    @app.delete("/api/outbox/{filename}")
    def delete_outbox(filename: str) -> dict[str, object]:
        path = (settings.outbox_dir / filename).resolve()
        if settings.outbox_dir.resolve() not in path.parents or path.suffix.lower() != ".docx":
            raise HTTPException(status_code=400, detail="invalid outbox path")
        deleted_file = False
        if path.exists():
            path.unlink()
            deleted_file = True
        with connection(settings) as conn:
            rows = conn.execute(
                "SELECT id, docx_path FROM outbox_messages",
            ).fetchall()
            for row in rows:
                if Path(row["docx_path"]).name == filename:
                    conn.execute("DELETE FROM outbox_messages WHERE id = ?", (row["id"],))
        record_activity(
            settings,
            event_type="outbox_delete",
            target="outbox",
            label=filename,
            metadata={"filename": filename, "file_deleted": deleted_file},
        )
        return {"status": "deleted", "filename": filename, "file_deleted": deleted_file}

    @app.get("/api/evaluations/agent")
    def agent_evaluation() -> dict[str, object]:
        return build_agent_evaluation_report(settings)

    @app.get("/api/evaluations/gold/coverage")
    def gold_coverage() -> dict[str, object]:
        return build_gold_coverage(settings).to_dict()

    @app.post("/api/evaluations/gold/cases/{case_id}/notices")
    def record_gold_notice(case_id: str, request: dict[str, object] = Body(...)) -> dict[str, object]:
        raw_notice = request.get("notice")
        if not isinstance(raw_notice, dict):
            raise HTTPException(status_code=400, detail="notice object is required")
        try:
            result = append_gold_notice(
                settings,
                case_id=case_id,
                reviewer=str(request.get("reviewer") or ""),
                notice=raw_notice,
                note=str(request.get("note") or ""),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "annotation": result,
            "coverage": build_gold_coverage(settings).to_dict(),
            "evaluation": build_agent_evaluation_report(settings),
        }

    @app.post("/api/evaluations/business-measurements")
    def save_business_measurement(request: dict[str, object] = Body(...)) -> dict[str, object]:
        try:
            item = upsert_business_measurement(
                settings,
                task_type=str(request.get("task_type") or ""),
                sample_ref=str(request.get("sample_ref") or ""),
                baseline_minutes=float(request.get("baseline_minutes") or 0),
                assisted_minutes=float(request.get("assisted_minutes") or 0),
                quality_status=str(request.get("quality_status") or "not_reviewed"),
                reviewer=str(request.get("reviewer") or ""),
                note=str(request.get("note") or ""),
                recorded_by=str(request.get("recorded_by") or ""),
                experiment_id=str(request.get("experiment_id") or "tendertrace-value-lab-v1"),
                experiment_version=int(request.get("experiment_version") or 1),
                participant=str(request.get("participant") or ""),
                document_type=str(request.get("document_type") or ""),
                file_count=int(request.get("file_count") or 1),
                sequence_order=str(request.get("sequence_order") or "manual_first"),
                conditions=str(request.get("conditions") or ""),
                source_url=str(request.get("source_url") or ""),
                raw_record_url=str(request.get("raw_record_url") or ""),
                gold_standard_url=str(request.get("gold_standard_url") or ""),
                baseline_active_minutes=float(
                    request.get("baseline_active_minutes")
                    if request.get("baseline_active_minutes") is not None
                    else request.get("baseline_minutes") or 0
                ),
                assisted_active_minutes=float(
                    request.get("assisted_active_minutes")
                    if request.get("assisted_active_minutes") is not None
                    else request.get("assisted_minutes") or 0
                ),
                baseline_machine_wait_seconds=float(request.get("baseline_machine_wait_seconds") or 0),
                assisted_machine_wait_seconds=float(request.get("assisted_machine_wait_seconds") or 0),
                baseline_omissions=int(request.get("baseline_omissions") or 0),
                assisted_omissions=int(request.get("assisted_omissions") or 0),
                baseline_false_satisfied=int(request.get("baseline_false_satisfied") or 0),
                assisted_false_satisfied=int(request.get("assisted_false_satisfied") or 0),
                baseline_rework_count=int(request.get("baseline_rework_count") or 0),
                assisted_rework_count=int(request.get("assisted_rework_count") or 0),
                is_outlier=bool(request.get("is_outlier")),
                outlier_reason=str(request.get("outlier_reason") or ""),
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"status": "saved", "item": item.to_dict(), "summary": business_measurement_summary(settings)}

    @app.get("/api/evaluations/business-measurements")
    def read_business_measurements() -> dict[str, object]:
        return business_measurement_summary(settings)

    @app.post("/api/memory/events")
    def memory_event(request: dict[str, object] = Body(...)) -> dict[str, object]:
        event_type = str(request.get("event_type") or "").strip()
        if not event_type:
            raise HTTPException(status_code=400, detail="event_type is required")
        metadata = request.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise HTTPException(status_code=400, detail="metadata must be an object")
        try:
            return record_activity(
                settings,
                event_type=event_type,
                target=str(request.get("target") or ""),
                label=str(request.get("label") or ""),
                metadata=metadata,
                user_id=str(request.get("user_id") or "admin"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/memory/weekly")
    def weekly_memory(
        user_id: str = "admin", days: int = 7, save: bool = False
    ) -> dict[str, object]:
        if days < 1 or days > 31:
            raise HTTPException(status_code=400, detail="days must be between 1 and 31")
        report = build_weekly_report(settings, user_id=user_id, days=days)
        if save:
            return persist_weekly_report(settings, report)
        return report

    @app.post("/api/memory/weekly")
    def save_weekly_memory(
        request: dict[str, object] | None = Body(default=None),
    ) -> dict[str, object]:
        request = request or {}
        try:
            days = int(request.get("days") or 7)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="days must be an integer") from exc
        if days < 1 or days > 31:
            raise HTTPException(status_code=400, detail="days must be between 1 and 31")
        report = build_weekly_report(
            settings,
            user_id=str(request.get("user_id") or "admin"),
            days=days,
        )
        return persist_weekly_report(settings, report)

    @app.post("/api/memory/advice/{advice_id}/feedback")
    def memory_advice_feedback(
        advice_id: str,
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        user_id = str(request.get("user_id") or "admin")
        context = request.get("context")
        if context is not None and not isinstance(context, dict):
            raise HTTPException(status_code=400, detail="context must be an object")
        schedule_ingest_callback = (
            schedule_adaptive_ingest if app.state.scheduler is not None else None
        )
        schedule_user_callback = (
            schedule_adaptive_subscription if app.state.scheduler is not None else None
        )
        try:
            result = apply_memory_advice_feedback(
                settings,
                advice_id=advice_id,
                status=str(request.get("status") or ""),
                user_id=user_id,
                source=str(request.get("source") or "web"),
                actor=str(request.get("actor") or ""),
                note=str(request.get("note") or ""),
                context=context,
                schedule_ingest=schedule_ingest_callback,
                schedule_subscription=schedule_user_callback,
                send_opportunity_briefing=send_adaptive_opportunity_briefing,
            )
        except (FeishuError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        feedback = result.feedback
        record_activity(
            settings,
            event_type="advice_feedback",
            target=advice_id,
            label=str(feedback.get("status") or ""),
            metadata={
                "source": feedback.get("source") or "web",
                "automation_status": result.automation.get("status") or "not_applicable",
            },
            user_id=user_id,
        )
        return {
            "status": "updated",
            **result.to_dict(),
        }

    @app.post("/api/memory/weekly/send-feishu")
    def send_weekly_memory_to_feishu(
        request: dict[str, object] | None = Body(default=None),
    ) -> dict[str, object]:
        request = request or {}
        try:
            days = int(request.get("days") or 7)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="days must be an integer") from exc
        if days < 1 or days > 31:
            raise HTTPException(status_code=400, detail="days must be between 1 and 31")
        report = build_weekly_report(
            settings,
            user_id=str(request.get("user_id") or "admin"),
            days=days,
        )
        period = report.get("period") if isinstance(report.get("period"), dict) else {}
        artifact_key = f"weekly:{period.get('from', '')}:{period.get('to', '')}"
        receive_id, receive_id_type = resolve_feishu_receiver(
            settings,
            receive_id=_optional_string(request.get("receive_id")),
            receive_id_type=_optional_string(request.get("receive_id_type")),
        )
        try:
            response = FeishuClient(settings).send_card(
                build_memory_weekly_card(report),
                receive_id=receive_id,
                receive_id_type=receive_id_type,
            )
            data = response.get("data")
            message_id = str(data.get("message_id") or "") if isinstance(data, dict) else ""
            attempt = record_delivery_attempt(
                settings,
                channel="feishu",
                artifact_type="weekly_digest",
                artifact_key=artifact_key,
                status="sent",
                external_id=message_id or None,
            )
        except FeishuError as exc:
            attempt = record_delivery_attempt(
                settings,
                channel="feishu",
                artifact_type="weekly_digest",
                artifact_key=artifact_key,
                status="failed",
                error=str(exc),
            )
            raise HTTPException(status_code=400, detail=attempt.to_dict()) from exc
        record_activity(
            settings,
            event_type="feishu_weekly_send",
            target="memory",
            label=artifact_key,
            metadata={"status": "sent"},
        )
        return attempt.to_dict()

    @app.get("/api/memory/profile")
    def memory_profile(user_id: str = "admin") -> dict[str, object]:
        profile = load_memory_profile(settings, user_id=user_id)
        if profile is None:
            return {"user_id": user_id, "status": "empty"}
        return {"status": "ready", **profile}

    @app.get("/api/traces/{run_id}")
    def trace_events(run_id: str) -> dict[str, object]:
        store = SqliteTraceStore(settings)
        return {
            "run_id": run_id,
            "events": [
                {
                    "seq": event.seq,
                    "event_type": event.event_type,
                    "node": event.node,
                    "payload": sanitize_for_output(event.payload),
                    "created_at": event.created_at,
                }
                for event in store.list_events(run_id)
            ],
        }

    @app.get("/api/checkpoints/{run_id}")
    def checkpoints(run_id: str) -> dict[str, object]:
        checkpointer = SqliteCheckpointer(settings)
        return {
            "run_id": run_id,
            "checkpoints": [
                {
                    "seq": checkpoint.seq,
                    "node": checkpoint.node,
                    "status": checkpoint.status,
                    "state": sanitize_for_output(checkpoint.state.to_dict()),
                }
                for checkpoint in checkpointer.list(run_id)
            ],
        }

    web_dist = settings.workspace_root / "web" / "dist"
    if web_dist.exists():
        try:
            from fastapi.staticfiles import StaticFiles
        except ImportError:
            StaticFiles = None
        if StaticFiles is not None:
            app.mount("/", StaticFiles(directory=Path(web_dist), html=True), name="web")

    return app


def _organization_workspace_payload(workspace: OrganizationWorkspace) -> dict[str, object]:
    payload = workspace.to_dict()
    payload["feishu_chat_url"] = feishu_chat_applink(workspace.feishu_chat_id)
    return payload


def _organization_workspace_welcome_message(
    settings: Settings,
    workspace: OrganizationWorkspace,
    *,
    member_count: int,
) -> str:
    workspace_url = (
        f"{settings.public_base_url}/?view=organizationView&workspace={workspace.id}"
    )
    return "\n".join(
        [
            f"TenderTrace 项目群已创建｜{workspace.name}",
            f"已邀请 {member_count} 名协作成员，机器人已加入群聊。",
            "",
            "你可以在群内：",
            "1. 直接发送招投标问题，生成 Word 或创建增量订阅；",
            "2. 发送“记录组织记忆：内容”，沉淀团队事实；",
            "3. 发送“查询组织记忆：关键词”，检索共享知识。",
            "4. 发送“项目意见 机会编号：内容”，把协作判断写入机会审计链。",
            "5. 发送“会审意见 机会编号 要求编号：内容”，补充会审依据。",
            "",
            f"返回 TenderTrace 组织协作：{workspace_url}",
        ]
    )


def _parse_limits(request: dict[str, object]) -> tuple[int, int]:
    try:
        max_pages = int(request.get("max_pages") or 1)
        max_results = int(request.get("max_results") or 10)
    except (TypeError, ValueError) as exc:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail="max_pages and max_results must be integers",
        ) from exc
    if max_pages < 1 or max_results < 1:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="max_pages and max_results must be positive")
    return max_pages, max_results


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def _delivery_channels_from_request(request: dict[str, object]) -> tuple[str, ...] | None:
    if "delivery_channels" not in request:
        return None
    raw = request.get("delivery_channels")
    if not isinstance(raw, list):
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="delivery_channels must be an array")
    aliases = {"feishu_message": "feishu"}
    selected = {"web", "outbox"}
    for item in raw:
        channel = aliases.get(str(item).strip().lower(), str(item).strip().lower())
        if channel not in {"web", "outbox", "feishu"}:
            from fastapi import HTTPException

            raise HTTPException(status_code=400, detail=f"unsupported delivery channel: {channel}")
        selected.add(channel)
    return tuple(channel for channel in ("web", "outbox", "feishu") if channel in selected)


def _feishu_delivery_target_from_request(
    settings: Settings,
    request: dict[str, object],
) -> tuple[str | None, str | None]:
    workspace_id = _optional_string(request.get("feishu_workspace_id"))
    if workspace_id is None:
        return None, None
    workspace = get_organization_workspace(settings, workspace_id)
    if workspace is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="organization workspace not found")
    if workspace.status != "active" or not workspace.feishu_chat_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="organization workspace is not available")
    return workspace.feishu_chat_id, "chat_id"


def _optional_string(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value).strip() or None


def _feishu_callback_token(payload: dict[str, object]) -> str:
    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    return str(header.get("token") or payload.get("token") or "")


def _model_strategy_from_request(request: dict[str, object]) -> str | None:
    value = request.get("model_strategy")
    if value in (None, ""):
        return None
    strategy = str(value).strip().lower()
    allowed = {"config", "rules", "local", "cloud", "hybrid"}
    if strategy not in allowed:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail="model_strategy must be one of: config, rules, local, cloud, hybrid",
        )
    return strategy


def _schedule_override_from_request(request: dict[str, object]) -> dict[str, object] | None:
    value = request.get("schedule")
    if value is None:
        return None
    if not isinstance(value, dict):
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="schedule must be an object")
    return value


def _subscription_api_item(settings: Settings, subscription: Subscription) -> dict[str, object]:
    item = subscription.to_dict()
    runtime = subscription.bidql.get("_runtime")
    item["delivery_channels"] = (
        runtime.get("delivery_channels", ["web", "outbox"])
        if isinstance(runtime, dict)
        else ["web", "outbox"]
    )
    item["next_run_at"] = _next_run_at(subscription)
    item.update(_latest_subscription_run(settings, subscription.id))
    return item


def _latest_subscription_run(settings: Settings, subscription_id: str) -> dict[str, object]:
    with connection(settings) as conn:
        row = conn.execute(
            """
            SELECT id, status, finished_at, output_docx_path, stats_json
            FROM runs
            WHERE subscription_id = ? AND status != 'deleted'
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (subscription_id,),
        ).fetchone()
        outbox = conn.execute(
            """
            SELECT docx_path
            FROM outbox_messages
            WHERE subscription_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (subscription_id,),
        ).fetchone()
    if row is None:
        return {
            "last_run_id": None,
            "last_run_status": None,
            "last_run_finished_at": None,
            "last_notice_count": 0,
            "last_new_count": 0,
            "last_skipped_sent": 0,
            "last_outbox_path": None,
            "last_outbox_name": None,
            "last_download_url": None,
            "last_email_status": None,
            "last_feishu_status": None,
        }
    stats = sanitize_stats(_loads_json(row["stats_json"]))
    outbox_path = str(outbox["docx_path"]) if outbox else str(row["output_docx_path"] or "")
    outbox_name = Path(outbox_path).name if outbox_path else None
    email = stats.get("email_delivery")
    email_status = email.get("status") if isinstance(email, dict) else None
    feishu = stats.get("feishu_message_delivery")
    feishu_status_value = feishu.get("status") if isinstance(feishu, dict) else None
    return {
        "last_run_id": row["id"],
        "last_run_status": row["status"],
        "last_run_finished_at": row["finished_at"],
        "last_notice_count": _int_stat(stats, "notice_count"),
        "last_new_count": _int_stat(stats, "new"),
        "last_skipped_sent": _int_stat(stats, "skipped_sent"),
        "last_outbox_path": outbox_path or None,
        "last_outbox_name": outbox_name,
        "last_download_url": f"/api/outbox/{outbox_name}" if outbox_name else None,
        "last_email_status": email_status,
        "last_feishu_status": feishu_status_value,
    }


def _resolve_outbox_path(settings: Settings, filename: str) -> Path:
    path = (settings.outbox_dir / filename).resolve()
    if settings.outbox_dir.resolve() not in path.parents or path.suffix.lower() != ".docx":
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="invalid outbox path")
    return path


def _report_delivery_summary(settings: Settings, run_id: str | None) -> dict[str, object]:
    if not run_id:
        return {}
    run = get_run(settings, run_id)
    if run is None:
        return {}
    stats = run.get("stats") if isinstance(run.get("stats"), dict) else {}
    source_sites = stats.get("source_sites") if isinstance(stats.get("source_sites"), list) else []
    return {
        "query": str(run.get("original_query") or ""),
        "notice_count": _int_stat(stats, "notice_count"),
        "evidence_passed": _int_stat(stats, "evidence_passed"),
        "source_sites": source_sites,
        "incremental": str(run.get("mode") or "") == "incremental",
    }


def _opportunity_message(opportunity: dict[str, object]) -> str:
    intelligence = (
        opportunity.get("intelligence")
        if isinstance(opportunity.get("intelligence"), dict)
        else {}
    )
    scores = intelligence.get("scores") if isinstance(intelligence.get("scores"), dict) else {}
    market_context = (
        intelligence.get("market_context")
        if isinstance(intelligence.get("market_context"), dict)
        else {}
    )
    benchmark = (
        market_context.get("benchmark")
        if isinstance(market_context.get("benchmark"), dict)
        else {}
    )
    competition = (
        intelligence.get("competition")
        if isinstance(intelligence.get("competition"), dict)
        else {}
    )
    requirement_review = (
        intelligence.get("requirement_review")
        if isinstance(intelligence.get("requirement_review"), dict)
        else {}
    )
    actions = intelligence.get("recommended_actions")
    action_lines = []
    if isinstance(actions, list):
        for item in actions[:3]:
            if isinstance(item, dict) and item.get("action"):
                action_lines.append(f"• {item.get('role', '负责人')}：{item['action']}")
    lines = [
        f"TenderTrace 机会情报｜{intelligence.get('level', 'D')} 级 · {intelligence.get('score', 0)} 分",
        str(opportunity.get("title") or "未命名机会"),
        (
            f"地区：{opportunity.get('region') or '-'}｜客户：{opportunity.get('purchaser') or '-'}｜"
            f"预算：{opportunity.get('budget') or '-'}"
        ),
        (
            f"时效 {scores.get('freshness', 0)}｜完整 {scores.get('completeness', 0)}｜"
            f"可信 {scores.get('credibility', 0)}｜阶段 {intelligence.get('stage', '线索识别')}"
        ),
        f"目标：{intelligence.get('project_target') or '待确认'}",
        f"策略：{intelligence.get('strategy') or '待确认'}",
    ]
    if benchmark.get("message"):
        lines.append(f"市场：{benchmark['message']}")
    if competition.get("message"):
        lines.append(f"竞情：{competition['message']}")
    if requirement_review:
        lines.append(
            f"需求：当前文本覆盖 {requirement_review.get('covered_count', 0)}/"
            f"{requirement_review.get('total_count', 0)} 项；"
            f"待核对 {'、'.join(str(item) for item in requirement_review.get('missing', [])[:4]) or '无'}"
        )
    if action_lines:
        lines.extend(["", "下一步", *action_lines])
    source_url = str(opportunity.get("source_url") or "").strip()
    if source_url:
        lines.extend(["", f"原文：{source_url}"])
    return "\n".join(lines)


def _next_run_at(subscription: Subscription) -> str | None:
    if subscription.schedule_kind == "recurring" and subscription.cron:
        return _next_cron_at(subscription.cron, subscription.timezone)
    if subscription.schedule_kind == "once_at":
        schedule = subscription.bidql.get("schedule")
        if isinstance(schedule, dict):
            date_text = str(schedule.get("date") or "").strip()
            time_text = str(schedule.get("time") or "09:00").strip()
            if date_text:
                return f"{date_text}T{time_text}"
    return None


def _next_cron_at(cron: str, timezone: str) -> str | None:
    parts = cron.split()
    if len(parts) != 5:
        return None
    minute_text, hour_text, day_text, _month_text, weekday_text = parts
    if not minute_text.isdigit() or not hour_text.isdigit():
        return None
    minute = int(minute_text)
    hour = int(hour_text)
    if not 0 <= minute <= 59 or not 0 <= hour <= 23:
        return None
    now = datetime.now(ZoneInfo(timezone))
    if weekday_text != "*":
        return _next_weekly_at(now, hour, minute, weekday_text)
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if day_text != "*" and day_text.isdigit():
        day = int(day_text)
        if day < 1 or day > 31:
            return None
        candidate = _next_monthly_at(now, hour, minute, day)
    elif candidate <= now:
        candidate += timedelta(days=1)
    return candidate.isoformat(timespec="minutes")


def _next_weekly_at(now: datetime, hour: int, minute: int, weekday_text: str) -> str | None:
    if not weekday_text.isdigit():
        return None
    weekday = int(weekday_text)
    if weekday < 0 or weekday > 6:
        return None
    target_weekday = 6 if weekday == 0 else weekday - 1
    days_ahead = (target_weekday - now.weekday()) % 7
    candidate = (now + timedelta(days=days_ahead)).replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    )
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate.isoformat(timespec="minutes")


def _next_monthly_at(now: datetime, hour: int, minute: int, day: int) -> str | None:
    year = now.year
    month = now.month
    for _ in range(13):
        try:
            candidate = now.replace(
                year=year,
                month=month,
                day=day,
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )
        except ValueError:
            candidate = None
        if candidate and candidate > now:
            return candidate.isoformat(timespec="minutes")
        month += 1
        if month > 12:
            year += 1
            month = 1
    return None


def _loads_json(value: str) -> dict[str, object]:
    try:
        loaded = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _mapping_value(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _refresh_qualification(settings: Settings, notice_id: str, workflow):
    opportunity = get_opportunity(settings, notice_id)
    if opportunity is None:
        return workflow, {}, {}
    qualification = _mapping_value(opportunity.get("qualification"))
    workflow = update_workflow(
        settings,
        notice_id,
        qualification_score=int(qualification.get("score") or 0),
        qualification_status=str(qualification.get("status") or "pending"),
    )
    opportunity["workflow"] = workflow.to_dict()
    opportunity["qualification"] = qualification
    return workflow, qualification, opportunity


def _team_mutation_response(
    settings: Settings,
    notice_id: str,
    member: dict[str, object],
    action: str,
) -> dict[str, object]:
    team_sync = sync_opportunity_team(settings, notice_id)
    opportunity = get_opportunity(settings, notice_id)
    if opportunity is None:
        raise LookupError("opportunity not found after team update")
    team = _mapping_value(opportunity.get("team"))
    bitable = update_opportunity_team_in_bitable(
        settings,
        notice_id=notice_id,
        team=team,
    )
    record_activity(
        settings,
        event_type=f"opportunity_team_member_{action}",
        target=notice_id,
        label=str(member.get("member_name") or ""),
        metadata={
            "role": str(member.get("role") or ""),
            "team_sync_status": team_sync.status,
            "bitable_status": bitable.status,
        },
    )
    return {
        "status": action,
        "member": member,
        "team": team,
        "qualification": opportunity.get("qualification"),
        "team_sync": team_sync.to_dict(),
        "bitable_status": bitable.status,
        "bitable_message": bitable.message,
    }


def _stakeholder_mutation_response(
    settings: Settings,
    notice_id: str,
    stakeholder: dict[str, object],
    action: str,
) -> dict[str, object]:
    opportunity = get_opportunity(settings, notice_id)
    if opportunity is None:
        raise LookupError("opportunity not found after stakeholder update")
    stakeholder_map = _mapping_value(opportunity.get("stakeholder_map"))
    bitable = update_opportunity_stakeholders_in_bitable(
        settings,
        notice_id=notice_id,
        stakeholder_map=stakeholder_map,
    )
    record_activity(
        settings,
        event_type=f"opportunity_stakeholder_{action}",
        target=notice_id,
        label=str(stakeholder.get("stakeholder_name") or ""),
        metadata={
            "role": str(stakeholder.get("role") or ""),
            "risk_level": str(stakeholder_map.get("risk_level") or "normal"),
            "bitable_status": bitable.status,
        },
    )
    return {
        "status": action,
        "stakeholder": stakeholder,
        "stakeholder_map": stakeholder_map,
        "qualification": opportunity.get("qualification"),
        "bitable_status": bitable.status,
        "bitable_message": bitable.message,
    }


def _relationship_action_mutation_response(
    settings: Settings,
    notice_id: str,
    relationship_action: dict[str, object],
    action: str,
    *,
    task_result: dict[str, object] | None = None,
    task_error: str = "",
) -> dict[str, object]:
    opportunity = get_opportunity(settings, notice_id)
    if opportunity is None:
        raise LookupError("opportunity not found after relationship action update")
    action_plan = _mapping_value(opportunity.get("relationship_actions"))
    bitable = update_opportunity_relationship_actions_in_bitable(
        settings,
        notice_id=notice_id,
        action_plan=action_plan,
    )
    record_activity(
        settings,
        event_type=f"opportunity_relationship_action_{action}",
        target=notice_id,
        label=str(relationship_action.get("title") or ""),
        metadata={
            "relationship_action_id": str(relationship_action.get("id") or ""),
            "priority": str(relationship_action.get("priority") or "normal"),
            "task_status": str(
                relationship_action.get("feishu_task_status") or "not_created"
            ),
            "bitable_status": bitable.status,
        },
    )
    return {
        "status": "partial" if task_error else action,
        "action": relationship_action,
        "action_plan": action_plan,
        "qualification": opportunity.get("qualification"),
        "task": task_result or {},
        "task_error": task_error,
        "bitable_status": bitable.status,
        "bitable_message": bitable.message,
    }


def _workflow_sync_payload(workflow, opportunity: dict[str, object]) -> dict[str, object]:
    payload = workflow.to_dict()
    action_state = _mapping_value(opportunity.get("action_state"))
    payload.update(
        {
            "decision_sla_status": action_state.get("decision_sla_status") or "not_applicable",
            "decision_sla_hours": action_state.get("decision_sla_hours") or 0,
            "decision_wait_hours": action_state.get("decision_wait_hours") or 0,
            "decision_due_at": action_state.get("decision_due_at") or "",
        }
    )
    payload["outcome"] = _mapping_value(opportunity.get("outcome"))
    return payload


def _int_stat(stats: dict[str, object], key: str) -> int:
    try:
        return int(stats.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _requires_api_token(settings: Settings, request) -> bool:
    if not settings.api_token_present:
        return False
    path = request.url.path
    if not path.startswith("/api/") or path in {
        "/api/health",
        "/api/integrations/feishu/callback",
        "/api/integrations/feishu/events",
    }:
        return False
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        return True
    return path == "/api/memory/weekly" and str(request.query_params.get("save")).lower() in {
        "1",
        "true",
        "yes",
    }


def _api_token_from_headers(headers) -> str:
    token = headers.get("x-tendertrace-token")
    if token:
        return token
    authorization = headers.get("authorization") or ""
    prefix = "Bearer "
    if authorization.startswith(prefix):
        return authorization[len(prefix) :]
    return ""


def _outbox_path_for_run(run_id: str, settings: Settings) -> str | None:
    for item in list_outbox_messages(settings):
        if item.run_id == run_id:
            return item.docx_path
    return None


RUN_PROGRESS_NODES = ("intent", "collect", "evidence", "report")


def _run_progress(settings: Settings, run_id: str, status: str) -> dict[str, object]:
    checkpoints = SqliteCheckpointer(settings).list(run_id)
    events = SqliteTraceStore(settings).list_events(run_id)
    completed = [
        checkpoint.node
        for checkpoint in checkpoints
        if checkpoint.status == "completed" and checkpoint.node in RUN_PROGRESS_NODES
    ]
    completed_set = set(completed)
    if status == "finished":
        percent = 100
    elif status == "failed":
        percent = int(len(completed_set) / len(RUN_PROGRESS_NODES) * 100)
    else:
        percent = int(len(completed_set) / len(RUN_PROGRESS_NODES) * 100)
    latest_checkpoint = checkpoints[-1] if checkpoints else None
    latest_event = events[-1] if events else None
    return {
        "percent": percent,
        "nodes": [
            {
                "node": node,
                "status": "completed" if node in completed_set else "pending",
            }
            for node in RUN_PROGRESS_NODES
        ],
        "current_node": latest_checkpoint.node if latest_checkpoint else None,
        "latest_event": (
            {
                "seq": latest_event.seq,
                "event_type": latest_event.event_type,
                "node": latest_event.node,
                "payload": sanitize_for_output(latest_event.payload),
                "created_at": latest_event.created_at,
            }
            if latest_event
            else None
        ),
    }
