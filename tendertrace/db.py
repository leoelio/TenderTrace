from __future__ import annotations

from contextlib import contextmanager
import json
import sqlite3
from pathlib import Path
from typing import Iterator

from tendertrace.config import Settings


SCHEMA_VERSION = 34


DDL = (
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS subscriptions (
        id TEXT PRIMARY KEY,
        original_query TEXT NOT NULL,
        bidql_json TEXT NOT NULL,
        schedule_kind TEXT NOT NULL,
        cron TEXT,
        timezone TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        last_run_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ingest_subscriptions (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        topics_json TEXT NOT NULL DEFAULT '[]',
        regions_json TEXT NOT NULL DEFAULT '[]',
        cron TEXT NOT NULL,
        timezone TEXT NOT NULL,
        window_days INTEGER NOT NULL DEFAULT 30,
        max_pages INTEGER NOT NULL DEFAULT 1,
        max_results INTEGER NOT NULL DEFAULT 20,
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        last_run_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runs (
        id TEXT PRIMARY KEY,
        subscription_id TEXT,
        original_query TEXT NOT NULL,
        mode TEXT NOT NULL,
        status TEXT NOT NULL,
        window_start TEXT,
        window_end TEXT,
        started_at TEXT NOT NULL DEFAULT (datetime('now')),
        finished_at TEXT,
        output_docx_path TEXT,
        stats_json TEXT NOT NULL DEFAULT '{}',
        error TEXT,
        FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS notices (
        id TEXT PRIMARY KEY,
        source_site TEXT NOT NULL,
        source_url TEXT NOT NULL,
        canonical_url TEXT NOT NULL,
        title TEXT NOT NULL,
        publish_time TEXT,
        region TEXT,
        purchaser TEXT,
        content_text TEXT,
        core_content TEXT,
        attachments_json TEXT NOT NULL DEFAULT '[]',
        fields_json TEXT NOT NULL DEFAULT '{}',
        snapshot_sha256 TEXT,
        simhash64 TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        last_seen_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS notice_revisions (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        change_hash TEXT NOT NULL,
        changed_fields_json TEXT NOT NULL DEFAULT '[]',
        before_json TEXT NOT NULL DEFAULT '{}',
        after_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS notice_change_reviews (
        revision_id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        severity TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        required_by TEXT NOT NULL,
        previous_decision TEXT NOT NULL DEFAULT 'pending',
        previous_decision_at TEXT,
        acknowledged_by TEXT,
        acknowledgment_note TEXT,
        acknowledged_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (revision_id) REFERENCES notice_revisions(id),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS clusters (
        cluster_key TEXT PRIMARY KEY,
        primary_notice_id TEXT,
        project_no TEXT,
        title_norm TEXT,
        publish_time TEXT,
        related_sources_json TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (primary_notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS evidence_items (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        cluster_key TEXT NOT NULL,
        source_site TEXT NOT NULL,
        source_url TEXT NOT NULL,
        snapshot_sha256 TEXT NOT NULL,
        excerpt TEXT NOT NULL,
        attachments_json TEXT NOT NULL DEFAULT '[]',
        fact_checks_json TEXT NOT NULL DEFAULT '[]',
        quality_score REAL NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS attachment_snapshots (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        cluster_key TEXT NOT NULL,
        name TEXT NOT NULL,
        url TEXT NOT NULL,
        type TEXT,
        status TEXT NOT NULL,
        local_path TEXT,
        sha256 TEXT,
        bytes INTEGER NOT NULL DEFAULT 0,
        text_excerpt TEXT,
        text_length INTEGER NOT NULL DEFAULT 0,
        error TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS page_artifacts (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        cluster_key TEXT NOT NULL,
        source_site TEXT NOT NULL,
        source_url TEXT NOT NULL,
        final_url TEXT,
        status_code INTEGER NOT NULL DEFAULT 0,
        fetcher TEXT NOT NULL,
        content_sha256 TEXT,
        content_length INTEGER NOT NULL DEFAULT 0,
        text_excerpt TEXT,
        blocked INTEGER NOT NULL DEFAULT 0,
        error TEXT,
        fetched_at TEXT,
        elapsed_ms INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sent_history (
        subscription_id TEXT NOT NULL,
        cluster_key TEXT NOT NULL,
        first_sent_at TEXT NOT NULL DEFAULT (datetime('now')),
        run_id TEXT NOT NULL,
        docx_path TEXT,
        PRIMARY KEY (subscription_id, cluster_key),
        FOREIGN KEY (subscription_id) REFERENCES subscriptions(id),
        FOREIGN KEY (run_id) REFERENCES runs(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS adapter_registry (
        site TEXT NOT NULL,
        version TEXT NOT NULL,
        contract_json TEXT NOT NULL,
        fixture_hash TEXT,
        drift_score REAL NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (site, version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS run_checkpoints (
        run_id TEXT NOT NULL,
        seq INTEGER NOT NULL,
        node TEXT NOT NULL,
        state_json TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (run_id, seq)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trace_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        seq INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        node TEXT,
        payload_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (run_id, seq)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS outbox_messages (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        subscription_id TEXT,
        docx_path TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'ready',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (run_id) REFERENCES runs(id),
        FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS model_audits (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        mode TEXT NOT NULL,
        provider TEXT NOT NULL,
        model TEXT,
        status TEXT NOT NULL,
        latency_ms INTEGER NOT NULL DEFAULT 0,
        error TEXT,
        prompt_sha256 TEXT,
        response_sha256 TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (run_id) REFERENCES runs(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS notice_embeddings (
        notice_id TEXT PRIMARY KEY,
        model TEXT NOT NULL,
        dim INTEGER NOT NULL,
        text_sha256 TEXT NOT NULL,
        vector_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_activity_events (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL DEFAULT 'admin',
        event_type TEXT NOT NULL,
        target TEXT,
        label TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        created_date TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS weekly_reports (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL DEFAULT 'admin',
        week_start TEXT NOT NULL,
        week_end TEXT NOT NULL,
        report_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (user_id, week_start, week_end)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_memory_profiles (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL DEFAULT 'admin',
        profile_json TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS memory_advice_feedback (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL DEFAULT 'admin',
        advice_id TEXT NOT NULL,
        status TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'web',
        actor TEXT,
        note TEXT,
        context_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (user_id, advice_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS delivery_attempts (
        id TEXT PRIMARY KEY,
        channel TEXT NOT NULL,
        artifact_type TEXT NOT NULL,
        artifact_key TEXT NOT NULL,
        run_id TEXT,
        subscription_id TEXT,
        status TEXT NOT NULL,
        external_id TEXT,
        error TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS integration_preferences (
        provider TEXT PRIMARY KEY,
        receive_id TEXT NOT NULL,
        receive_id_type TEXT NOT NULL,
        label TEXT,
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS opportunity_workflows (
        notice_id TEXT PRIMARY KEY,
        stage TEXT NOT NULL DEFAULT 'identified',
        owner_open_id TEXT,
        owner_name TEXT,
        next_action TEXT,
        due_at TEXT,
        feishu_task_guid TEXT,
        feishu_task_status TEXT NOT NULL DEFAULT 'not_created',
        feishu_task_completed_at TEXT,
        feishu_task_synced_at TEXT,
        feishu_event_id TEXT,
        feishu_message_id TEXT,
        qualification_score INTEGER NOT NULL DEFAULT 0,
        qualification_status TEXT NOT NULL DEFAULT 'pending',
        decision TEXT NOT NULL DEFAULT 'pending',
        decision_reason TEXT,
        decision_by TEXT,
        decision_at TEXT,
        decision_requested_at TEXT,
        stage_changed_at TEXT NOT NULL DEFAULT '',
        updated_by TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS opportunity_events (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        action TEXT NOT NULL,
        from_stage TEXT,
        to_stage TEXT,
        actor_open_id TEXT,
        payload_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS opportunity_collaboration_notes (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        content TEXT NOT NULL,
        actor TEXT NOT NULL,
        channel TEXT NOT NULL,
        source_message_id TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (notice_id) REFERENCES notices(id),
        UNIQUE (source_message_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS opportunity_outcomes (
        notice_id TEXT PRIMARY KEY,
        result TEXT NOT NULL,
        reason_code TEXT NOT NULL,
        winner_name TEXT,
        award_amount REAL,
        currency TEXT,
        summary TEXT NOT NULL,
        lessons TEXT NOT NULL,
        customer_feedback TEXT,
        follow_up_action TEXT,
        evidence_url TEXT,
        evidence_text TEXT,
        recorded_by TEXT,
        finalized_at TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS opportunity_team_members (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        member_key TEXT NOT NULL,
        member_open_id TEXT,
        member_name TEXT NOT NULL,
        role TEXT NOT NULL,
        organization_type TEXT NOT NULL DEFAULT 'internal',
        organization_name TEXT,
        responsibility TEXT,
        status TEXT NOT NULL DEFAULT 'active',
        feishu_task_guid TEXT,
        feishu_task_role TEXT NOT NULL DEFAULT 'follower',
        feishu_sync_status TEXT NOT NULL DEFAULT 'pending',
        feishu_sync_error TEXT,
        feishu_synced_at TEXT,
        added_by TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (notice_id, member_key, role),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS opportunity_stakeholders (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        stakeholder_key TEXT NOT NULL,
        stakeholder_name TEXT NOT NULL,
        organization_name TEXT,
        job_title TEXT,
        role TEXT NOT NULL,
        influence TEXT NOT NULL DEFAULT 'medium',
        stance TEXT NOT NULL DEFAULT 'unknown',
        relationship_strength TEXT NOT NULL DEFAULT 'unknown',
        owner_member_id TEXT,
        next_action TEXT,
        evidence_source TEXT,
        evidence_url TEXT,
        evidence_text TEXT,
        status TEXT NOT NULL DEFAULT 'active',
        added_by TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (notice_id, stakeholder_key, role),
        FOREIGN KEY (notice_id) REFERENCES notices(id),
        FOREIGN KEY (owner_member_id) REFERENCES opportunity_team_members(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS opportunity_relationship_actions (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        stakeholder_id TEXT,
        action_key TEXT NOT NULL,
        title TEXT NOT NULL,
        action_type TEXT NOT NULL DEFAULT 'engagement',
        priority TEXT NOT NULL DEFAULT 'normal',
        assignee_member_id TEXT,
        due_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        outcome_note TEXT,
        source_type TEXT NOT NULL DEFAULT 'manual',
        source_ref TEXT,
        feishu_task_guid TEXT,
        feishu_task_status TEXT NOT NULL DEFAULT 'not_created',
        feishu_task_synced_at TEXT,
        feishu_sync_error TEXT,
        completed_at TEXT,
        created_by TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (notice_id, action_key),
        FOREIGN KEY (notice_id) REFERENCES notices(id),
        FOREIGN KEY (stakeholder_id) REFERENCES opportunity_stakeholders(id),
        FOREIGN KEY (assignee_member_id) REFERENCES opportunity_team_members(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS opportunity_fact_overrides (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        field_name TEXT NOT NULL,
        field_value TEXT NOT NULL,
        source_url TEXT NOT NULL,
        evidence_text TEXT,
        note TEXT,
        actor TEXT,
        channel TEXT NOT NULL DEFAULT 'web',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (notice_id, field_name),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS opportunity_requirements (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        requirement_key TEXT NOT NULL,
        requirement_type TEXT NOT NULL,
        title TEXT NOT NULL,
        evidence_text TEXT NOT NULL,
        source_url TEXT NOT NULL,
        source_locator TEXT NOT NULL,
        mandatory INTEGER NOT NULL DEFAULT 0,
        confidence INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'pending',
        assignee_member_id TEXT,
        due_at TEXT,
        note TEXT,
        created_by TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (notice_id, requirement_key),
        FOREIGN KEY (notice_id) REFERENCES notices(id),
        FOREIGN KEY (assignee_member_id) REFERENCES opportunity_team_members(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS requirement_review_cases (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        requirement_id TEXT NOT NULL,
        reviewer_role TEXT NOT NULL,
        reason TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        decision TEXT,
        decision_note TEXT,
        decided_by TEXT,
        decided_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (requirement_id, reviewer_role, reason),
        FOREIGN KEY (notice_id) REFERENCES notices(id),
        FOREIGN KEY (requirement_id) REFERENCES opportunity_requirements(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS requirement_review_opinions (
        id TEXT PRIMARY KEY,
        review_id TEXT NOT NULL,
        notice_id TEXT NOT NULL,
        requirement_id TEXT NOT NULL,
        agent_role TEXT NOT NULL,
        decision TEXT NOT NULL,
        confidence INTEGER NOT NULL DEFAULT 0,
        rationale TEXT NOT NULL DEFAULT '',
        concerns_json TEXT NOT NULL DEFAULT '[]',
        model_status TEXT NOT NULL DEFAULT '',
        model_provider TEXT NOT NULL DEFAULT '',
        model_name TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (review_id, agent_role),
        FOREIGN KEY (notice_id) REFERENCES notices(id),
        FOREIGN KEY (requirement_id) REFERENCES opportunity_requirements(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS feishu_lead_import_runs (
        id TEXT PRIMARY KEY,
        mode TEXT NOT NULL,
        status TEXT NOT NULL,
        scanned_count INTEGER NOT NULL DEFAULT 0,
        candidate_count INTEGER NOT NULL DEFAULT 0,
        imported_count INTEGER NOT NULL DEFAULT 0,
        existing_count INTEGER NOT NULL DEFAULT 0,
        skipped_count INTEGER NOT NULL DEFAULT 0,
        updated_count INTEGER NOT NULL DEFAULT 0,
        invalid_count INTEGER NOT NULL DEFAULT 0,
        verified_count INTEGER NOT NULL DEFAULT 0,
        verification_failed_count INTEGER NOT NULL DEFAULT 0,
        unsafe_count INTEGER NOT NULL DEFAULT 0,
        message TEXT NOT NULL DEFAULT '',
        started_at TEXT NOT NULL,
        finished_at TEXT NOT NULL,
        duration_ms INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS feishu_message_events (
        event_id TEXT PRIMARY KEY,
        message_id TEXT NOT NULL UNIQUE,
        chat_id TEXT NOT NULL,
        chat_type TEXT NOT NULL DEFAULT '',
        sender_open_id TEXT NOT NULL DEFAULT '',
        query TEXT NOT NULL DEFAULT '',
        command_kind TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL,
        run_id TEXT,
        subscription_id TEXT,
        error TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS organization_workspaces (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        feishu_chat_id TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'active',
        created_by TEXT NOT NULL DEFAULT 'admin',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS organization_members (
        workspace_id TEXT NOT NULL,
        member_open_id TEXT NOT NULL,
        member_name TEXT NOT NULL DEFAULT '',
        role TEXT NOT NULL DEFAULT 'member',
        status TEXT NOT NULL DEFAULT 'active',
        added_by TEXT NOT NULL DEFAULT 'admin',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (workspace_id, member_open_id),
        FOREIGN KEY (workspace_id) REFERENCES organization_workspaces(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS organization_memories (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        memory_type TEXT NOT NULL DEFAULT 'note',
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        source_type TEXT NOT NULL,
        source_message_id TEXT,
        sender_open_id TEXT,
        related_notice_id TEXT,
        evidence_url TEXT,
        content_hash TEXT NOT NULL,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (workspace_id, source_message_id),
        UNIQUE (workspace_id, content_hash),
        FOREIGN KEY (workspace_id) REFERENCES organization_workspaces(id),
        FOREIGN KEY (related_notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS organization_memory_events (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        memory_id TEXT,
        action TEXT NOT NULL,
        actor_open_id TEXT,
        payload_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (workspace_id) REFERENCES organization_workspaces(id),
        FOREIGN KEY (memory_id) REFERENCES organization_memories(id)
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS organization_memories_fts USING fts5(
        memory_id UNINDEXED,
        workspace_id UNINDEXED,
        title,
        content
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS source_incidents (
        artifact_key TEXT PRIMARY KEY,
        status TEXT NOT NULL DEFAULT 'open',
        severity TEXT NOT NULL DEFAULT 'warning',
        issue_count INTEGER NOT NULL DEFAULT 0,
        source_sites_json TEXT NOT NULL DEFAULT '[]',
        snapshot_json TEXT NOT NULL DEFAULT '{}',
        feishu_task_guid TEXT NOT NULL,
        assigned INTEGER NOT NULL DEFAULT 0,
        due_at TEXT NOT NULL,
        task_completed_at TEXT,
        synced_at TEXT,
        resolved_at TEXT,
        last_error TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS source_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_site TEXT NOT NULL,
        status TEXT NOT NULL,
        notice_count INTEGER NOT NULL DEFAULT 0,
        error TEXT,
        fetch_stats_json TEXT NOT NULL DEFAULT '{}',
        observed_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
)


FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS notices_fts USING fts5(
    notice_id UNINDEXED,
    title,
    content_text
)
"""


INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_runs_subscription ON runs(subscription_id)",
    "CREATE INDEX IF NOT EXISTS idx_notices_publish_time ON notices(publish_time)",
    "CREATE INDEX IF NOT EXISTS idx_notices_source_site ON notices(source_site)",
    "CREATE INDEX IF NOT EXISTS idx_notice_revisions_notice ON notice_revisions(notice_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_notice_revisions_time ON notice_revisions(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_notice_change_reviews_notice ON notice_change_reviews(notice_id, status, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_notice_change_reviews_due ON notice_change_reviews(status, required_by)",
    "CREATE INDEX IF NOT EXISTS idx_clusters_project_no ON clusters(project_no)",
    "CREATE INDEX IF NOT EXISTS idx_evidence_items_cluster ON evidence_items(cluster_key)",
    "CREATE INDEX IF NOT EXISTS idx_evidence_items_notice ON evidence_items(notice_id)",
    "CREATE INDEX IF NOT EXISTS idx_attachment_snapshots_notice ON attachment_snapshots(notice_id)",
    "CREATE INDEX IF NOT EXISTS idx_attachment_snapshots_cluster ON attachment_snapshots(cluster_key)",
    "CREATE INDEX IF NOT EXISTS idx_page_artifacts_notice ON page_artifacts(notice_id)",
    "CREATE INDEX IF NOT EXISTS idx_page_artifacts_cluster ON page_artifacts(cluster_key)",
    "CREATE INDEX IF NOT EXISTS idx_page_artifacts_source ON page_artifacts(source_site, fetched_at)",
    "CREATE INDEX IF NOT EXISTS idx_run_checkpoints_run ON run_checkpoints(run_id, seq)",
    "CREATE INDEX IF NOT EXISTS idx_trace_events_run ON trace_events(run_id, seq)",
    "CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox_messages(status, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_model_audits_run ON model_audits(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_model_audits_status ON model_audits(status)",
    "CREATE INDEX IF NOT EXISTS idx_ingest_subscriptions_status ON ingest_subscriptions(status)",
    "CREATE INDEX IF NOT EXISTS idx_notice_embeddings_model ON notice_embeddings(model)",
    "CREATE INDEX IF NOT EXISTS idx_user_activity_user_date ON user_activity_events(user_id, created_date)",
    "CREATE INDEX IF NOT EXISTS idx_user_activity_type_time ON user_activity_events(event_type, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_weekly_reports_user_period ON weekly_reports(user_id, week_start, week_end)",
    "CREATE INDEX IF NOT EXISTS idx_user_memory_profiles_user ON user_memory_profiles(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_memory_advice_feedback_user ON memory_advice_feedback(user_id, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_delivery_attempts_artifact ON delivery_attempts(artifact_key, channel, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_delivery_attempts_status ON delivery_attempts(status, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_opportunity_workflows_stage ON opportunity_workflows(stage, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_opportunity_events_notice ON opportunity_events(notice_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_opportunity_collaboration_notes_notice ON opportunity_collaboration_notes(notice_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_opportunity_outcomes_result ON opportunity_outcomes(result, finalized_at)",
    "CREATE INDEX IF NOT EXISTS idx_opportunity_team_notice ON opportunity_team_members(notice_id, status, role)",
    "CREATE INDEX IF NOT EXISTS idx_opportunity_team_sync ON opportunity_team_members(feishu_sync_status, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_opportunity_stakeholders_notice ON opportunity_stakeholders(notice_id, status, role)",
    "CREATE INDEX IF NOT EXISTS idx_opportunity_stakeholders_risk ON opportunity_stakeholders(status, influence, stance)",
    "CREATE INDEX IF NOT EXISTS idx_relationship_actions_notice ON opportunity_relationship_actions(notice_id, status, due_at)",
    "CREATE INDEX IF NOT EXISTS idx_relationship_actions_sync ON opportunity_relationship_actions(feishu_task_status, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_opportunity_fact_overrides_notice ON opportunity_fact_overrides(notice_id, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_opportunity_requirements_notice ON opportunity_requirements(notice_id, status, requirement_type)",
    "CREATE INDEX IF NOT EXISTS idx_opportunity_requirements_assignee ON opportunity_requirements(assignee_member_id, status, due_at)",
    "CREATE INDEX IF NOT EXISTS idx_requirement_review_cases_notice ON requirement_review_cases(notice_id, status, reviewer_role)",
    "CREATE INDEX IF NOT EXISTS idx_requirement_review_opinions_review ON requirement_review_opinions(review_id, agent_role)",
    "CREATE INDEX IF NOT EXISTS idx_requirement_review_opinions_notice ON requirement_review_opinions(notice_id, agent_role)",
    "CREATE INDEX IF NOT EXISTS idx_feishu_lead_import_runs_time ON feishu_lead_import_runs(started_at)",
    "CREATE INDEX IF NOT EXISTS idx_feishu_message_events_status ON feishu_message_events(status, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_organization_workspaces_status ON organization_workspaces(status, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_organization_members_workspace ON organization_members(workspace_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_organization_memories_workspace ON organization_memories(workspace_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_organization_memories_notice ON organization_memories(related_notice_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_organization_memory_events_workspace ON organization_memory_events(workspace_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_source_incidents_status ON source_incidents(status, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_source_observations_site_time ON source_observations(source_site, observed_at)",
)

REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "notices": (
        "purchaser TEXT",
        "core_content TEXT",
        "attachments_json TEXT NOT NULL DEFAULT '[]'",
        "updated_at TEXT NOT NULL DEFAULT ''",
        "last_seen_at TEXT NOT NULL DEFAULT ''",
        "notice_type TEXT NOT NULL DEFAULT 'other'",
        "notice_type_label TEXT NOT NULL DEFAULT '其他'",
    ),
    "feishu_lead_import_runs": (
        "verified_count INTEGER NOT NULL DEFAULT 0",
        "verification_failed_count INTEGER NOT NULL DEFAULT 0",
        "unsafe_count INTEGER NOT NULL DEFAULT 0",
    ),
    "opportunity_workflows": (
        "qualification_score INTEGER NOT NULL DEFAULT 0",
        "qualification_status TEXT NOT NULL DEFAULT 'pending'",
        "decision TEXT NOT NULL DEFAULT 'pending'",
        "decision_reason TEXT",
        "decision_by TEXT",
        "decision_at TEXT",
        "decision_requested_at TEXT",
        "stage_changed_at TEXT NOT NULL DEFAULT ''",
        "feishu_task_status TEXT NOT NULL DEFAULT 'not_created'",
        "feishu_task_completed_at TEXT",
        "feishu_task_synced_at TEXT",
    ),
    "opportunity_requirements": (
        "feishu_task_guid TEXT",
        "feishu_task_status TEXT NOT NULL DEFAULT 'not_created'",
    ),
}


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def connection(settings: Settings) -> Iterator[sqlite3.Connection]:
    settings.ensure_directories()
    conn = connect(settings.db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(settings: Settings) -> None:
    settings.ensure_directories()
    with connection(settings) as conn:
        for statement in DDL:
            conn.execute(statement)
        _ensure_required_columns(conn)
        conn.execute(
            """
            UPDATE notices
            SET updated_at = CASE WHEN updated_at = '' THEN created_at ELSE updated_at END,
                last_seen_at = CASE WHEN last_seen_at = '' THEN created_at ELSE last_seen_at END
            WHERE updated_at = '' OR last_seen_at = ''
            """
        )
        _ensure_fts(conn)
        for statement in INDEXES:
            conn.execute(statement)
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)",
            (SCHEMA_VERSION,),
        )


def database_health(settings: Settings) -> dict[str, object]:
    if not settings.db_path.exists():
        return {"initialized": False, "path": str(settings.db_path)}
    with connection(settings) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()
        migrations = conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
    return {
        "initialized": True,
        "path": str(settings.db_path),
        "sqlite_user_version": version,
        "schema_versions": [row["version"] for row in migrations],
        "tables": [row["name"] for row in tables],
    }


def json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _ensure_required_columns(conn: sqlite3.Connection) -> None:
    for table, columns in REQUIRED_COLUMNS.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for column in columns:
            name = column.split(" ", 1)[0]
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column}")


def _ensure_fts(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute(FTS_DDL)
        return True
    except sqlite3.OperationalError:
        return False
