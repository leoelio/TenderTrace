from __future__ import annotations

from contextlib import contextmanager
import json
import sqlite3
from pathlib import Path
from typing import Iterator

from tendertrace.config import Settings


SCHEMA_VERSION = 58


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
    CREATE TABLE IF NOT EXISTS change_impact_rounds (
        id TEXT PRIMARY KEY,
        revision_id TEXT NOT NULL UNIQUE,
        notice_id TEXT NOT NULL,
        round_number INTEGER NOT NULL,
        severity TEXT NOT NULL,
        summary TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        generated_at TEXT NOT NULL DEFAULT (datetime('now')),
        confirmed_by TEXT,
        confirmation_note TEXT,
        confirmed_at TEXT,
        FOREIGN KEY (revision_id) REFERENCES notice_revisions(id),
        FOREIGN KEY (notice_id) REFERENCES notices(id),
        UNIQUE (notice_id, round_number)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS change_impact_events (
        id TEXT PRIMARY KEY,
        round_id TEXT NOT NULL,
        revision_id TEXT NOT NULL,
        notice_id TEXT NOT NULL,
        field_name TEXT NOT NULL,
        change_type TEXT NOT NULL,
        old_value_json TEXT NOT NULL DEFAULT 'null',
        new_value_json TEXT NOT NULL DEFAULT 'null',
        source_url TEXT NOT NULL DEFAULT '',
        source_locator TEXT NOT NULL DEFAULT '',
        detection_method TEXT NOT NULL DEFAULT 'rule',
        confidence INTEGER NOT NULL DEFAULT 100,
        discovered_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (revision_id, field_name, change_type),
        FOREIGN KEY (round_id) REFERENCES change_impact_rounds(id),
        FOREIGN KEY (revision_id) REFERENCES notice_revisions(id),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS change_impact_items (
        id TEXT PRIMARY KEY,
        round_id TEXT NOT NULL,
        event_id TEXT NOT NULL,
        revision_id TEXT NOT NULL,
        notice_id TEXT NOT NULL,
        target_type TEXT NOT NULL,
        target_id TEXT NOT NULL,
        target_title TEXT NOT NULL,
        impact_status TEXT NOT NULL,
        previous_status TEXT NOT NULL DEFAULT '',
        reason TEXT NOT NULL,
        owner_id TEXT NOT NULL DEFAULT '',
        owner_name TEXT NOT NULL DEFAULT '',
        due_at TEXT NOT NULL DEFAULT '',
        confirmed_by TEXT,
        confirmation_note TEXT,
        confirmed_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (round_id, event_id, target_type, target_id),
        FOREIGN KEY (round_id) REFERENCES change_impact_rounds(id),
        FOREIGN KEY (event_id) REFERENCES change_impact_events(id),
        FOREIGN KEY (revision_id) REFERENCES notice_revisions(id),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS change_impact_actions (
        id TEXT PRIMARY KEY,
        round_id TEXT NOT NULL,
        impact_item_id TEXT,
        revision_id TEXT NOT NULL,
        notice_id TEXT NOT NULL,
        action_key TEXT NOT NULL,
        action_type TEXT NOT NULL,
        title TEXT NOT NULL,
        priority TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        owner_id TEXT NOT NULL DEFAULT '',
        owner_name TEXT NOT NULL DEFAULT '',
        due_at TEXT NOT NULL DEFAULT '',
        idempotency_key TEXT NOT NULL UNIQUE,
        message_status TEXT NOT NULL DEFAULT 'pending_confirmation',
        message_id TEXT NOT NULL DEFAULT '',
        task_status TEXT NOT NULL DEFAULT 'pending_confirmation',
        task_guid TEXT NOT NULL DEFAULT '',
        calendar_status TEXT NOT NULL DEFAULT 'pending_confirmation',
        calendar_event_id TEXT NOT NULL DEFAULT '',
        retry_count INTEGER NOT NULL DEFAULT 0,
        last_error TEXT NOT NULL DEFAULT '',
        last_attempt_at TEXT NOT NULL DEFAULT '',
        confirmed_by TEXT,
        confirmation_note TEXT,
        confirmed_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (round_id, action_key),
        FOREIGN KEY (round_id) REFERENCES change_impact_rounds(id),
        FOREIGN KEY (impact_item_id) REFERENCES change_impact_items(id),
        FOREIGN KEY (revision_id) REFERENCES notice_revisions(id),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS change_impact_audit_events (
        id TEXT PRIMARY KEY,
        round_id TEXT NOT NULL,
        action_id TEXT,
        notice_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        actor TEXT NOT NULL,
        note TEXT NOT NULL DEFAULT '',
        payload_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (round_id) REFERENCES change_impact_rounds(id),
        FOREIGN KEY (action_id) REFERENCES change_impact_actions(id),
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
    CREATE TABLE IF NOT EXISTS evidence_sources (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        source_type TEXT NOT NULL,
        source_id TEXT NOT NULL,
        source_site TEXT,
        source_url TEXT,
        file_name TEXT,
        page_number INTEGER,
        section_path TEXT,
        paragraph_index INTEGER,
        selector TEXT,
        text_coordinates_json TEXT NOT NULL DEFAULT '{}',
        quote TEXT NOT NULL,
        context_before TEXT,
        context_after TEXT,
        content_hash TEXT NOT NULL,
        parent_content_hash TEXT,
        revision_id TEXT,
        captured_at TEXT,
        extraction_method TEXT NOT NULL DEFAULT 'text',
        locator_confidence INTEGER NOT NULL DEFAULT 0,
        verified_status TEXT NOT NULL DEFAULT 'pending',
        confirmed_by TEXT,
        confirmed_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (notice_id, source_type, source_id, content_hash),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS evidence_claims (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        claim_type TEXT NOT NULL,
        claim_key TEXT NOT NULL,
        title TEXT NOT NULL,
        conclusion TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (notice_id, claim_type, claim_key),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS evidence_claim_links (
        claim_id TEXT NOT NULL,
        evidence_id TEXT NOT NULL,
        stance TEXT NOT NULL DEFAULT 'supports',
        rationale TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (claim_id, evidence_id),
        FOREIGN KEY (claim_id) REFERENCES evidence_claims(id),
        FOREIGN KEY (evidence_id) REFERENCES evidence_sources(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS evidence_audit_events (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        evidence_id TEXT,
        claim_id TEXT,
        action TEXT NOT NULL,
        actor TEXT NOT NULL,
        reason TEXT NOT NULL,
        previous_status TEXT,
        new_status TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (notice_id) REFERENCES notices(id),
        FOREIGN KEY (evidence_id) REFERENCES evidence_sources(id),
        FOREIGN KEY (claim_id) REFERENCES evidence_claims(id)
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
    CREATE TABLE IF NOT EXISTS opportunity_digital_twin_snapshots (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        state_hash TEXT NOT NULL,
        summary_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (notice_id) REFERENCES notices(id),
        UNIQUE (notice_id, state_hash)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS opportunity_digital_twin_history (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        state_hash TEXT NOT NULL,
        summary_json TEXT NOT NULL DEFAULT '{}',
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
    CREATE TABLE IF NOT EXISTS bid_requirement_history (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        requirement_id TEXT NOT NULL,
        action TEXT NOT NULL,
        before_json TEXT NOT NULL DEFAULT '{}',
        after_json TEXT NOT NULL DEFAULT '{}',
        actor TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (notice_id) REFERENCES notices(id),
        FOREIGN KEY (requirement_id) REFERENCES opportunity_requirements(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bid_deliverables (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        requirement_id TEXT NOT NULL,
        deliverable_key TEXT NOT NULL,
        title TEXT NOT NULL,
        file_type TEXT NOT NULL DEFAULT 'document',
        status TEXT NOT NULL DEFAULT 'pending',
        owner_member_id TEXT,
        evidence_ref TEXT NOT NULL DEFAULT '',
        due_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (notice_id, deliverable_key),
        FOREIGN KEY (notice_id) REFERENCES notices(id),
        FOREIGN KEY (requirement_id) REFERENCES opportunity_requirements(id),
        FOREIGN KEY (owner_member_id) REFERENCES opportunity_team_members(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bid_responsibility_assignments (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        requirement_id TEXT NOT NULL,
        responsibility_type TEXT NOT NULL,
        member_id TEXT,
        person_label TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (requirement_id, responsibility_type, person_label),
        FOREIGN KEY (notice_id) REFERENCES notices(id),
        FOREIGN KEY (requirement_id) REFERENCES opportunity_requirements(id),
        FOREIGN KEY (member_id) REFERENCES opportunity_team_members(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bid_plan_tasks (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        requirement_id TEXT,
        task_key TEXT NOT NULL,
        title TEXT NOT NULL,
        milestone_type TEXT NOT NULL,
        due_at TEXT,
        status TEXT NOT NULL DEFAULT 'open',
        dependency_keys_json TEXT NOT NULL DEFAULT '[]',
        formal INTEGER NOT NULL DEFAULT 0,
        feishu_task_guid TEXT,
        feishu_task_status TEXT NOT NULL DEFAULT 'not_created',
        feishu_sync_error TEXT NOT NULL DEFAULT '',
        feishu_receipt_json TEXT NOT NULL DEFAULT '{}',
        feishu_task_synced_at TEXT,
        completed_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (notice_id, task_key),
        FOREIGN KEY (notice_id) REFERENCES notices(id),
        FOREIGN KEY (requirement_id) REFERENCES opportunity_requirements(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bid_pricing_items (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        requirement_id TEXT,
        item_key TEXT NOT NULL,
        title TEXT NOT NULL,
        quantity REAL NOT NULL DEFAULT 1,
        unit TEXT NOT NULL DEFAULT '项',
        unit_price REAL NOT NULL DEFAULT 0,
        cost REAL NOT NULL DEFAULT 0,
        tax_rate REAL NOT NULL DEFAULT 0,
        owner_member_id TEXT,
        status TEXT NOT NULL DEFAULT 'draft',
        note TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (notice_id, item_key),
        FOREIGN KEY (notice_id) REFERENCES notices(id),
        FOREIGN KEY (requirement_id) REFERENCES opportunity_requirements(id),
        FOREIGN KEY (owner_member_id) REFERENCES opportunity_team_members(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS enterprise_capabilities (
        id TEXT PRIMARY KEY,
        capability_key TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL,
        capability_type TEXT NOT NULL,
        evidence_text TEXT NOT NULL,
        source_url TEXT NOT NULL,
        source_locator TEXT NOT NULL,
        verification_status TEXT NOT NULL DEFAULT 'draft',
        owner TEXT NOT NULL DEFAULT '',
        valid_until TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS requirement_capability_matches (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        requirement_id TEXT NOT NULL,
        capability_id TEXT NOT NULL DEFAULT '',
        verdict TEXT NOT NULL,
        confidence INTEGER NOT NULL DEFAULT 0,
        rationale TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'proposed',
        decided_by TEXT,
        decision_note TEXT,
        decided_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (requirement_id, capability_id),
        FOREIGN KEY (notice_id) REFERENCES notices(id),
        FOREIGN KEY (requirement_id) REFERENCES opportunity_requirements(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS capability_versions (
        id TEXT PRIMARY KEY,
        capability_id TEXT NOT NULL,
        version_number INTEGER NOT NULL,
        content_hash TEXT NOT NULL,
        snapshot_json TEXT NOT NULL,
        actor TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (capability_id, version_number),
        UNIQUE (capability_id, content_hash),
        FOREIGN KEY (capability_id) REFERENCES enterprise_capabilities(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS opportunity_capability_scopes (
        notice_id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL DEFAULT 'default',
        bound_by TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS capability_project_snapshots (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL,
        capability_id TEXT NOT NULL,
        capability_version_id TEXT NOT NULL,
        confirmation_status TEXT NOT NULL DEFAULT 'captured',
        confirmed_by TEXT,
        confirmed_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (notice_id, capability_id, capability_version_id),
        FOREIGN KEY (notice_id) REFERENCES notices(id),
        FOREIGN KEY (capability_id) REFERENCES enterprise_capabilities(id),
        FOREIGN KEY (capability_version_id) REFERENCES capability_versions(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS capability_gap_actions (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        requirement_id TEXT NOT NULL,
        match_id TEXT NOT NULL,
        action_type TEXT NOT NULL,
        title TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        assignee_member_id TEXT,
        due_at TEXT,
        bid_plan_task_id TEXT,
        created_by TEXT NOT NULL,
        completed_by TEXT,
        completion_note TEXT,
        completed_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (notice_id) REFERENCES notices(id),
        FOREIGN KEY (requirement_id) REFERENCES opportunity_requirements(id),
        FOREIGN KEY (match_id) REFERENCES requirement_capability_matches(id),
        FOREIGN KEY (assignee_member_id) REFERENCES opportunity_team_members(id),
        FOREIGN KEY (bid_plan_task_id) REFERENCES bid_plan_tasks(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS capability_performance_records (
        id TEXT PRIMARY KEY,
        capability_id TEXT NOT NULL,
        notice_id TEXT NOT NULL,
        project_title TEXT NOT NULL,
        industry TEXT NOT NULL DEFAULT '',
        region TEXT NOT NULL DEFAULT '',
        amount REAL NOT NULL DEFAULT 0,
        product_model TEXT NOT NULL DEFAULT '',
        result TEXT NOT NULL,
        evidence_url TEXT NOT NULL DEFAULT '',
        occurred_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (capability_id, notice_id),
        FOREIGN KEY (capability_id) REFERENCES enterprise_capabilities(id),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS capability_audit_events (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        capability_id TEXT,
        notice_id TEXT,
        action TEXT NOT NULL,
        actor TEXT NOT NULL,
        payload_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (capability_id) REFERENCES enterprise_capabilities(id),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS business_measurements (
        id TEXT PRIMARY KEY,
        task_type TEXT NOT NULL,
        sample_ref TEXT NOT NULL,
        experiment_id TEXT NOT NULL DEFAULT 'tendertrace-value-lab-v1',
        experiment_version INTEGER NOT NULL DEFAULT 1,
        participant TEXT NOT NULL DEFAULT '',
        document_type TEXT NOT NULL DEFAULT '',
        file_count INTEGER NOT NULL DEFAULT 1,
        sequence_order TEXT NOT NULL DEFAULT 'manual_first',
        conditions TEXT NOT NULL DEFAULT '',
        source_url TEXT NOT NULL DEFAULT '',
        raw_record_url TEXT NOT NULL DEFAULT '',
        gold_standard_url TEXT NOT NULL DEFAULT '',
        baseline_minutes REAL NOT NULL,
        assisted_minutes REAL NOT NULL,
        baseline_active_minutes REAL NOT NULL DEFAULT 0,
        assisted_active_minutes REAL NOT NULL DEFAULT 0,
        baseline_machine_wait_seconds REAL NOT NULL DEFAULT 0,
        assisted_machine_wait_seconds REAL NOT NULL DEFAULT 0,
        baseline_omissions INTEGER NOT NULL DEFAULT 0,
        assisted_omissions INTEGER NOT NULL DEFAULT 0,
        baseline_false_satisfied INTEGER NOT NULL DEFAULT 0,
        assisted_false_satisfied INTEGER NOT NULL DEFAULT 0,
        baseline_rework_count INTEGER NOT NULL DEFAULT 0,
        assisted_rework_count INTEGER NOT NULL DEFAULT 0,
        is_outlier INTEGER NOT NULL DEFAULT 0,
        outlier_reason TEXT NOT NULL DEFAULT '',
        quality_status TEXT NOT NULL DEFAULT 'not_reviewed',
        reviewer TEXT NOT NULL DEFAULT '',
        note TEXT NOT NULL DEFAULT '',
        recorded_by TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (task_type, sample_ref)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS business_measurement_events (
        id TEXT PRIMARY KEY,
        measurement_id TEXT NOT NULL,
        snapshot_json TEXT NOT NULL,
        actor TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (measurement_id) REFERENCES business_measurements(id)
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
    CREATE TABLE IF NOT EXISTS review_agent_runs (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        review_id TEXT NOT NULL,
        requirement_id TEXT NOT NULL,
        notice_revision_id TEXT NOT NULL DEFAULT '',
        evidence_scope_hash TEXT NOT NULL,
        prompt_version TEXT NOT NULL,
        requested_roles_json TEXT NOT NULL DEFAULT '[]',
        input_snapshot_json TEXT NOT NULL DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'running',
        completed_count INTEGER NOT NULL DEFAULT 0,
        failed_count INTEGER NOT NULL DEFAULT 0,
        checkpoint_json TEXT NOT NULL DEFAULT '{}',
        created_by TEXT NOT NULL,
        started_at TEXT NOT NULL DEFAULT (datetime('now')),
        finished_at TEXT,
        FOREIGN KEY (notice_id) REFERENCES notices(id),
        FOREIGN KEY (review_id) REFERENCES requirement_review_cases(id),
        FOREIGN KEY (requirement_id) REFERENCES opportunity_requirements(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS review_agent_run_events (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        review_id TEXT NOT NULL,
        agent_role TEXT NOT NULL DEFAULT '',
        event_type TEXT NOT NULL,
        detail TEXT NOT NULL DEFAULT '',
        payload_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (run_id) REFERENCES review_agent_runs(id),
        FOREIGN KEY (review_id) REFERENCES requirement_review_cases(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS decision_scenarios (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        name TEXT NOT NULL,
        scenario_mode TEXT NOT NULL DEFAULT 'self_bid',
        params_json TEXT NOT NULL,
        baseline_hash TEXT NOT NULL,
        baseline_json TEXT NOT NULL,
        rules_version TEXT NOT NULL,
        output_json TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'saved',
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS decision_scenario_suggestions (
        id TEXT PRIMARY KEY,
        scenario_id TEXT NOT NULL UNIQUE,
        notice_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        actions_json TEXT NOT NULL DEFAULT '[]',
        requested_by TEXT NOT NULL,
        decided_by TEXT,
        decision_note TEXT,
        decided_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (scenario_id) REFERENCES decision_scenarios(id),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS decision_sandbox_events (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        scenario_id TEXT,
        action TEXT NOT NULL,
        actor TEXT NOT NULL,
        payload_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (notice_id) REFERENCES notices(id),
        FOREIGN KEY (scenario_id) REFERENCES decision_scenarios(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS feishu_war_rooms (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL UNIQUE,
        workspace_id TEXT NOT NULL DEFAULT '',
        receive_id TEXT NOT NULL DEFAULT '',
        receive_id_type TEXT NOT NULL DEFAULT 'chat_id',
        status TEXT NOT NULL DEFAULT 'planned',
        launch_count INTEGER NOT NULL DEFAULT 0,
        created_by TEXT NOT NULL DEFAULT 'admin',
        last_success_at TEXT,
        last_sync_at TEXT,
        archived_at TEXT,
        archive_memory_id TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS feishu_war_room_steps (
        id TEXT PRIMARY KEY,
        war_room_id TEXT NOT NULL,
        notice_id TEXT NOT NULL,
        step_key TEXT NOT NULL,
        label TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        idempotency_key TEXT NOT NULL UNIQUE,
        resource_type TEXT NOT NULL DEFAULT '',
        resource_id TEXT NOT NULL DEFAULT '',
        resource_url TEXT NOT NULL DEFAULT '',
        reused INTEGER NOT NULL DEFAULT 0,
        attempt_count INTEGER NOT NULL DEFAULT 0,
        last_error TEXT NOT NULL DEFAULT '',
        receipt_json TEXT NOT NULL DEFAULT '{}',
        last_attempt_at TEXT,
        completed_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (war_room_id, step_key),
        FOREIGN KEY (war_room_id) REFERENCES feishu_war_rooms(id),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS feishu_war_room_sync_events (
        id TEXT PRIMARY KEY,
        war_room_id TEXT NOT NULL,
        notice_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        direction TEXT NOT NULL DEFAULT 'outbound',
        status TEXT NOT NULL,
        actor TEXT NOT NULL,
        payload_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (war_room_id) REFERENCES feishu_war_rooms(id),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS requirement_review_human_opinions (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        requirement_id TEXT NOT NULL,
        content TEXT NOT NULL,
        actor TEXT NOT NULL,
        channel TEXT NOT NULL,
        source_message_id TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (source_message_id),
        FOREIGN KEY (notice_id) REFERENCES notices(id),
        FOREIGN KEY (requirement_id) REFERENCES opportunity_requirements(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS requirement_review_actions (
        id TEXT PRIMARY KEY,
        opinion_id TEXT NOT NULL UNIQUE,
        notice_id TEXT NOT NULL,
        requirement_id TEXT NOT NULL,
        assignee_member_id TEXT,
        due_at TEXT,
        action_note TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        completed_by TEXT,
        completion_note TEXT,
        completed_at TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (opinion_id) REFERENCES requirement_review_human_opinions(id),
        FOREIGN KEY (requirement_id) REFERENCES opportunity_requirements(id),
        FOREIGN KEY (assignee_member_id) REFERENCES opportunity_team_members(id)
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
    CREATE TABLE IF NOT EXISTS integration_runtime_heartbeats (
        integration_name TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        detail TEXT NOT NULL DEFAULT '',
        started_at TEXT NOT NULL DEFAULT (datetime('now')),
        heartbeat_at TEXT NOT NULL DEFAULT (datetime('now')),
        stopped_at TEXT
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
    CREATE TABLE IF NOT EXISTS bid_memory_projects (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        notice_id TEXT NOT NULL,
        outcome_result TEXT NOT NULL,
        outcome_reason_code TEXT NOT NULL DEFAULT '',
        summary TEXT NOT NULL,
        lessons TEXT NOT NULL,
        tags_json TEXT NOT NULL DEFAULT '[]',
        status TEXT NOT NULL DEFAULT 'active',
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (workspace_id, notice_id),
        FOREIGN KEY (workspace_id) REFERENCES organization_workspaces(id),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bid_memory_assets (
        id TEXT PRIMARY KEY,
        project_memory_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL,
        source_notice_id TEXT NOT NULL,
        asset_key TEXT NOT NULL,
        asset_type TEXT NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        source_url TEXT NOT NULL DEFAULT '',
        version_number INTEGER NOT NULL DEFAULT 1,
        valid_until TEXT,
        reuse_status TEXT NOT NULL DEFAULT 'reference',
        permission_scope TEXT NOT NULL DEFAULT 'workspace',
        sensitivity TEXT NOT NULL DEFAULT 'normal',
        confirmed_by TEXT NOT NULL DEFAULT '',
        confirmed_at TEXT,
        withdrawn_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (project_memory_id, asset_key),
        FOREIGN KEY (project_memory_id) REFERENCES bid_memory_projects(id),
        FOREIGN KEY (workspace_id) REFERENCES organization_workspaces(id),
        FOREIGN KEY (source_notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bid_memory_audit_events (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        project_memory_id TEXT,
        asset_id TEXT,
        action TEXT NOT NULL,
        actor_open_id TEXT NOT NULL,
        note TEXT NOT NULL DEFAULT '',
        before_json TEXT NOT NULL DEFAULT '{}',
        after_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (workspace_id) REFERENCES organization_workspaces(id),
        FOREIGN KEY (project_memory_id) REFERENCES bid_memory_projects(id),
        FOREIGN KEY (asset_id) REFERENCES bid_memory_assets(id)
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
    """
    CREATE TABLE IF NOT EXISTS opportunity_radar_snapshots (
        id TEXT PRIMARY KEY,
        scope TEXT NOT NULL,
        window_days INTEGER NOT NULL,
        category TEXT NOT NULL DEFAULT '',
        notice_count INTEGER NOT NULL DEFAULT 0,
        source_count INTEGER NOT NULL DEFAULT 0,
        payload_json TEXT NOT NULL,
        created_by TEXT NOT NULL DEFAULT 'admin',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS live_challenge_sessions (
        id TEXT PRIMARY KEY,
        category TEXT NOT NULL,
        region TEXT NOT NULL,
        time_window TEXT NOT NULL,
        keyword TEXT NOT NULL DEFAULT '',
        normalized_query TEXT NOT NULL,
        intent_json TEXT NOT NULL DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'local_ready',
        local_duration_ms INTEGER NOT NULL DEFAULT 0,
        online_duration_ms INTEGER NOT NULL DEFAULT 0,
        local_result_count INTEGER NOT NULL DEFAULT 0,
        online_result_count INTEGER NOT NULL DEFAULT 0,
        source_summary_json TEXT NOT NULL DEFAULT '[]',
        cancel_requested INTEGER NOT NULL DEFAULT 0,
        error_text TEXT NOT NULL DEFAULT '',
        created_by TEXT NOT NULL DEFAULT 'judge',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        completed_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS live_challenge_results (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        notice_id TEXT NOT NULL,
        origin TEXT NOT NULL,
        verification_status TEXT NOT NULL,
        source_site TEXT NOT NULL,
        title TEXT NOT NULL,
        publish_time TEXT NOT NULL DEFAULT '',
        region TEXT NOT NULL DEFAULT '',
        purchaser TEXT NOT NULL DEFAULT '',
        source_url TEXT NOT NULL DEFAULT '',
        indexed_at TEXT NOT NULL DEFAULT '',
        position INTEGER NOT NULL DEFAULT 0,
        payload_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (session_id) REFERENCES live_challenge_sessions(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS demo_reliability_cases (
        id TEXT PRIMARY KEY,
        role TEXT NOT NULL UNIQUE,
        label TEXT NOT NULL,
        source_type TEXT NOT NULL,
        source_id TEXT NOT NULL,
        source_version TEXT NOT NULL,
        snapshot_hash TEXT NOT NULL,
        snapshot_json TEXT NOT NULL,
        data_as_of TEXT NOT NULL,
        evidence_kind TEXT NOT NULL,
        verification_status TEXT NOT NULL DEFAULT 'verified',
        verified_at TEXT NOT NULL DEFAULT (datetime('now')),
        created_by TEXT NOT NULL DEFAULT 'admin',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS demo_replay_artifacts (
        id TEXT PRIMARY KEY,
        case_id TEXT NOT NULL,
        source_type TEXT NOT NULL,
        source_id TEXT NOT NULL,
        source_version TEXT NOT NULL,
        snapshot_hash TEXT NOT NULL,
        request_json TEXT NOT NULL DEFAULT '{}',
        result_json TEXT NOT NULL,
        receipt_json TEXT NOT NULL DEFAULT '{}',
        recorded_at TEXT NOT NULL,
        verified_at TEXT NOT NULL DEFAULT (datetime('now')),
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (case_id) REFERENCES demo_reliability_cases(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS demo_rehearsals (
        id TEXT PRIMARY KEY,
        case_id TEXT NOT NULL,
        requested_mode TEXT NOT NULL,
        actual_mode TEXT NOT NULL,
        switch_reason TEXT NOT NULL DEFAULT '',
        scenario TEXT NOT NULL DEFAULT 'standard',
        status TEXT NOT NULL,
        browser_online INTEGER NOT NULL DEFAULT 1,
        viewport_width INTEGER NOT NULL DEFAULT 0,
        viewport_height INTEGER NOT NULL DEFAULT 0,
        opened_in_ms INTEGER NOT NULL DEFAULT 0,
        actor TEXT NOT NULL DEFAULT 'admin',
        started_at TEXT NOT NULL DEFAULT (datetime('now')),
        completed_at TEXT,
        FOREIGN KEY (case_id) REFERENCES demo_reliability_cases(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS demo_rehearsal_events (
        id TEXT PRIMARY KEY,
        rehearsal_id TEXT NOT NULL,
        seq INTEGER NOT NULL,
        step_key TEXT NOT NULL,
        label TEXT NOT NULL,
        status TEXT NOT NULL,
        duration_ms INTEGER NOT NULL DEFAULT 0,
        detail TEXT NOT NULL DEFAULT '',
        receipt_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (rehearsal_id) REFERENCES demo_rehearsals(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS demo_layout_audits (
        id TEXT PRIMARY KEY,
        profile TEXT NOT NULL,
        viewport_width INTEGER NOT NULL,
        viewport_height INTEGER NOT NULL,
        scroll_width INTEGER NOT NULL,
        critical_overflows_json TEXT NOT NULL DEFAULT '[]',
        status TEXT NOT NULL,
        user_agent TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS visual_system_audits (
        id TEXT PRIMARY KEY,
        profile TEXT NOT NULL,
        viewport_width INTEGER NOT NULL,
        viewport_height INTEGER NOT NULL,
        notice_id TEXT NOT NULL,
        scroll_width INTEGER NOT NULL,
        critical_overflows_json TEXT NOT NULL DEFAULT '[]',
        checks_json TEXT NOT NULL DEFAULT '{}',
        status TEXT NOT NULL,
        user_agent TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS company_entities (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        legal_name TEXT NOT NULL,
        unified_credit_code TEXT NOT NULL DEFAULT '',
        region TEXT NOT NULL DEFAULT '',
        legal_representative TEXT NOT NULL DEFAULT '',
        entity_type TEXT NOT NULL DEFAULT 'company',
        identity_status TEXT NOT NULL DEFAULT 'pending',
        verification_status TEXT NOT NULL DEFAULT 'pending',
        verification_evidence_id TEXT,
        last_verified_at TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS company_aliases (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        alias TEXT NOT NULL,
        alias_type TEXT NOT NULL DEFAULT 'name',
        source_type TEXT NOT NULL DEFAULT 'manual',
        confirmed INTEGER NOT NULL DEFAULT 0,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (entity_id, alias, alias_type),
        FOREIGN KEY (entity_id) REFERENCES company_entities(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS company_evidence (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        notice_id TEXT,
        evidence_item_id TEXT,
        evidence_type TEXT NOT NULL,
        title TEXT NOT NULL,
        source_type TEXT NOT NULL,
        source_name TEXT NOT NULL DEFAULT '',
        source_url TEXT NOT NULL DEFAULT '',
        source_locator TEXT NOT NULL DEFAULT '',
        source_license TEXT NOT NULL DEFAULT '',
        access_policy TEXT NOT NULL DEFAULT 'public',
        access_frequency TEXT NOT NULL DEFAULT 'on_demand',
        snapshot_sha256 TEXT NOT NULL DEFAULT '',
        occurred_at TEXT,
        valid_from TEXT,
        valid_until TEXT,
        evidence_status TEXT NOT NULL DEFAULT 'pending',
        confidence INTEGER NOT NULL DEFAULT 0,
        subject_match_basis_json TEXT NOT NULL DEFAULT '{}',
        content_text TEXT NOT NULL DEFAULT '',
        redacted_content TEXT NOT NULL DEFAULT '',
        content_hash TEXT NOT NULL,
        sensitive INTEGER NOT NULL DEFAULT 0,
        created_by TEXT NOT NULL,
        captured_at TEXT NOT NULL DEFAULT (datetime('now')),
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (workspace_id, entity_id, content_hash),
        FOREIGN KEY (entity_id) REFERENCES company_entities(id) ON DELETE CASCADE,
        FOREIGN KEY (notice_id) REFERENCES notices(id),
        FOREIGN KEY (evidence_item_id) REFERENCES evidence_items(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS company_risk_signals (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        evidence_id TEXT,
        rule_key TEXT NOT NULL,
        dimension TEXT NOT NULL,
        signal_kind TEXT NOT NULL DEFAULT 'risk',
        fact_signal TEXT NOT NULL,
        risk_interpretation TEXT NOT NULL DEFAULT '',
        business_impact TEXT NOT NULL DEFAULT '',
        due_diligence_question TEXT NOT NULL DEFAULT '',
        mitigation TEXT NOT NULL DEFAULT '',
        severity TEXT NOT NULL DEFAULT 'info',
        confidence INTEGER NOT NULL DEFAULT 0,
        signal_status TEXT NOT NULL DEFAULT 'pending',
        valid_until TEXT,
        manually_confirmed_by TEXT,
        manually_confirmed_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (workspace_id, entity_id, rule_key, fact_signal),
        FOREIGN KEY (entity_id) REFERENCES company_entities(id) ON DELETE CASCADE,
        FOREIGN KEY (evidence_id) REFERENCES company_evidence(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS company_relationships (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        from_entity_id TEXT NOT NULL,
        to_entity_id TEXT,
        related_object_type TEXT NOT NULL DEFAULT 'company',
        related_object_id TEXT NOT NULL DEFAULT '',
        related_label TEXT NOT NULL,
        relationship_type TEXT NOT NULL,
        basis_type TEXT NOT NULL DEFAULT 'inferred',
        evidence_id TEXT,
        confidence INTEGER NOT NULL DEFAULT 0,
        relationship_status TEXT NOT NULL DEFAULT 'pending',
        valid_from TEXT,
        valid_until TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (from_entity_id) REFERENCES company_entities(id) ON DELETE CASCADE,
        FOREIGN KEY (to_entity_id) REFERENCES company_entities(id),
        FOREIGN KEY (evidence_id) REFERENCES company_evidence(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS due_diligence_reviews (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        notice_id TEXT,
        recommendation TEXT NOT NULL,
        reason TEXT NOT NULL,
        conditions_json TEXT NOT NULL DEFAULT '[]',
        valid_until TEXT NOT NULL,
        review_status TEXT NOT NULL DEFAULT 'confirmed',
        previous_review_id TEXT,
        confirmed_by TEXT NOT NULL,
        confirmed_at TEXT NOT NULL DEFAULT (datetime('now')),
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (entity_id) REFERENCES company_entities(id) ON DELETE CASCADE,
        FOREIGN KEY (notice_id) REFERENCES notices(id),
        FOREIGN KEY (previous_review_id) REFERENCES due_diligence_reviews(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS company_due_diligence_tasks (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        notice_id TEXT,
        risk_signal_id TEXT,
        title TEXT NOT NULL,
        question TEXT NOT NULL,
        task_type TEXT NOT NULL DEFAULT 'verification',
        assignee_open_id TEXT NOT NULL DEFAULT '',
        assignee_name TEXT NOT NULL DEFAULT '',
        due_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        feishu_task_guid TEXT,
        feishu_task_status TEXT NOT NULL DEFAULT 'not_created',
        feishu_sync_error TEXT NOT NULL DEFAULT '',
        created_by TEXT NOT NULL,
        completed_by TEXT,
        completed_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (entity_id) REFERENCES company_entities(id) ON DELETE CASCADE,
        FOREIGN KEY (notice_id) REFERENCES notices(id),
        FOREIGN KEY (risk_signal_id) REFERENCES company_risk_signals(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS company_change_subscriptions (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        event_types_json TEXT NOT NULL DEFAULT '[]',
        status TEXT NOT NULL DEFAULT 'active',
        last_checked_at TEXT,
        last_change_at TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (workspace_id, entity_id),
        FOREIGN KEY (entity_id) REFERENCES company_entities(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS company_due_diligence_snapshots (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        state_hash TEXT NOT NULL,
        snapshot_json TEXT NOT NULL,
        verified INTEGER NOT NULL DEFAULT 0,
        verified_by TEXT,
        verified_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (workspace_id, entity_id, state_hash),
        FOREIGN KEY (entity_id) REFERENCES company_entities(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS company_due_diligence_audit_events (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        entity_id TEXT,
        action TEXT NOT NULL,
        actor TEXT NOT NULL,
        payload_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (entity_id) REFERENCES company_entities(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS company_due_diligence_answers (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        evidence_ids_json TEXT NOT NULL DEFAULT '[]',
        missing_items_json TEXT NOT NULL DEFAULT '[]',
        worst_impact TEXT NOT NULL DEFAULT '',
        mitigation TEXT NOT NULL DEFAULT '',
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (entity_id) REFERENCES company_entities(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS geo_events (
        id TEXT PRIMARY KEY,
        event_type TEXT NOT NULL,
        object_type TEXT NOT NULL,
        object_id TEXT NOT NULL,
        notice_id TEXT,
        title TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT '',
        region_name TEXT NOT NULL DEFAULT '',
        country_code TEXT NOT NULL DEFAULT '',
        latitude REAL,
        longitude REAL,
        china_x REAL,
        china_y REAL,
        world_x REAL NOT NULL,
        world_y REAL NOT NULL,
        coordinate_precision TEXT NOT NULL DEFAULT 'unknown',
        event_time TEXT NOT NULL,
        source_name TEXT NOT NULL,
        source_url TEXT NOT NULL,
        source_license TEXT NOT NULL DEFAULT '',
        evidence_status TEXT NOT NULL DEFAULT 'pending',
        amount REAL,
        currency TEXT NOT NULL DEFAULT '',
        counterparty TEXT NOT NULL DEFAULT '',
        payload_json TEXT NOT NULL DEFAULT '{}',
        captured_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (event_type, object_type, object_id),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS business_flows (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        flow_type TEXT NOT NULL DEFAULT 'award',
        from_label TEXT NOT NULL,
        from_latitude REAL,
        from_longitude REAL,
        from_china_x REAL,
        from_china_y REAL,
        from_world_x REAL NOT NULL,
        from_world_y REAL NOT NULL,
        from_precision TEXT NOT NULL DEFAULT 'unknown',
        to_label TEXT NOT NULL,
        to_latitude REAL,
        to_longitude REAL,
        to_china_x REAL,
        to_china_y REAL,
        to_world_x REAL NOT NULL,
        to_world_y REAL NOT NULL,
        to_precision TEXT NOT NULL DEFAULT 'unknown',
        amount REAL,
        currency TEXT NOT NULL DEFAULT '',
        occurred_at TEXT NOT NULL,
        source_name TEXT NOT NULL,
        source_url TEXT NOT NULL,
        source_license TEXT NOT NULL DEFAULT '',
        evidence_status TEXT NOT NULL DEFAULT 'pending',
        payload_json TEXT NOT NULL DEFAULT '{}',
        captured_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (notice_id, flow_type, from_label, to_label),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS external_events (
        id TEXT PRIMARY KEY,
        source_event_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        title TEXT NOT NULL,
        summary TEXT NOT NULL DEFAULT '',
        severity TEXT NOT NULL DEFAULT 'watch',
        magnitude REAL,
        region_name TEXT NOT NULL DEFAULT '',
        country_code TEXT NOT NULL DEFAULT '',
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        world_x REAL NOT NULL,
        world_y REAL NOT NULL,
        coordinate_precision TEXT NOT NULL DEFAULT 'exact',
        impact_radius_km REAL NOT NULL DEFAULT 0,
        event_time TEXT NOT NULL,
        source_name TEXT NOT NULL,
        source_url TEXT NOT NULL,
        source_license TEXT NOT NULL,
        access_policy TEXT NOT NULL DEFAULT 'public',
        access_frequency TEXT NOT NULL DEFAULT 'manual',
        evidence_status TEXT NOT NULL DEFAULT 'candidate',
        snapshot_sha256 TEXT NOT NULL,
        raw_json TEXT NOT NULL DEFAULT '{}',
        captured_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (source_name, source_event_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS impact_links (
        id TEXT PRIMARY KEY,
        external_event_id TEXT NOT NULL,
        target_type TEXT NOT NULL,
        target_id TEXT NOT NULL,
        target_title TEXT NOT NULL,
        relation_basis TEXT NOT NULL,
        rule_key TEXT NOT NULL,
        match_basis_json TEXT NOT NULL DEFAULT '{}',
        impact_scope TEXT NOT NULL DEFAULT '',
        severity TEXT NOT NULL DEFAULT 'watch',
        confidence INTEGER NOT NULL DEFAULT 0,
        explanation TEXT NOT NULL,
        suggested_action TEXT NOT NULL,
        review_status TEXT NOT NULL DEFAULT 'pending',
        review_note TEXT NOT NULL DEFAULT '',
        reviewed_by TEXT,
        reviewed_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (external_event_id, target_type, target_id, rule_key),
        FOREIGN KEY (external_event_id) REFERENCES external_events(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS map_replay_frames (
        id TEXT PRIMARY KEY,
        scope TEXT NOT NULL,
        window_hours INTEGER NOT NULL,
        category TEXT NOT NULL DEFAULT '',
        data_as_of TEXT NOT NULL,
        state_hash TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        verified INTEGER NOT NULL DEFAULT 0,
        verified_by TEXT,
        verified_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (scope, window_hours, category, state_hash)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS training_scenarios (
        id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        scenario_key TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL,
        project_alias TEXT NOT NULL,
        scenario_type TEXT NOT NULL,
        target_roles_json TEXT NOT NULL DEFAULT '[]',
        allowed_modes_json TEXT NOT NULL DEFAULT '["learning","preparation"]',
        difficulty TEXT NOT NULL DEFAULT 'standard',
        estimated_minutes INTEGER NOT NULL DEFAULT 7,
        state_machine_json TEXT NOT NULL DEFAULT '[]',
        questions_json TEXT NOT NULL DEFAULT '[]',
        source_snapshot_json TEXT NOT NULL DEFAULT '{}',
        approval_status TEXT NOT NULL DEFAULT 'approved',
        approved_by TEXT NOT NULL,
        approved_at TEXT NOT NULL DEFAULT (datetime('now')),
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS training_sessions (
        id TEXT PRIMARY KEY,
        scenario_id TEXT NOT NULL,
        notice_id TEXT NOT NULL,
        mode TEXT NOT NULL,
        role TEXT NOT NULL,
        difficulty TEXT NOT NULL,
        participant_key TEXT NOT NULL,
        participant_display TEXT NOT NULL,
        sample_kind TEXT NOT NULL DEFAULT 'live',
        status TEXT NOT NULL DEFAULT 'ready',
        current_phase TEXT NOT NULL DEFAULT 'opening',
        current_question_index INTEGER NOT NULL DEFAULT 0,
        scoring_version TEXT NOT NULL,
        source_hash TEXT NOT NULL,
        started_at TEXT,
        finished_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (scenario_id) REFERENCES training_scenarios(id),
        FOREIGN KEY (notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS training_turns (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        sequence INTEGER NOT NULL,
        phase TEXT NOT NULL,
        question_id TEXT NOT NULL,
        prompt TEXT NOT NULL,
        answer TEXT NOT NULL DEFAULT '',
        first_answer TEXT NOT NULL DEFAULT '',
        hint_level INTEGER NOT NULL DEFAULT 0,
        evidence_refs_json TEXT NOT NULL DEFAULT '[]',
        rule_score_json TEXT NOT NULL DEFAULT '{}',
        model_evaluation_json TEXT NOT NULL DEFAULT '{}',
        feedback_json TEXT NOT NULL DEFAULT '{}',
        next_question_id TEXT NOT NULL DEFAULT '',
        started_at TEXT NOT NULL DEFAULT (datetime('now')),
        answered_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (session_id, sequence),
        FOREIGN KEY (session_id) REFERENCES training_sessions(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS training_rubrics (
        id TEXT PRIMARY KEY,
        scenario_id TEXT NOT NULL,
        question_id TEXT NOT NULL,
        version TEXT NOT NULL,
        target_competency TEXT NOT NULL,
        reference_facts_json TEXT NOT NULL DEFAULT '[]',
        allowed_evidence_json TEXT NOT NULL DEFAULT '[]',
        scoring_rules_json TEXT NOT NULL DEFAULT '{}',
        follow_up_conditions_json TEXT NOT NULL DEFAULT '{}',
        stop_conditions_json TEXT NOT NULL DEFAULT '{}',
        approved_by TEXT NOT NULL,
        approved_at TEXT NOT NULL DEFAULT (datetime('now')),
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (scenario_id, question_id, version),
        FOREIGN KEY (scenario_id) REFERENCES training_scenarios(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS training_results (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL UNIQUE,
        scoring_version TEXT NOT NULL,
        dimension_scores_json TEXT NOT NULL DEFAULT '{}',
        total_score INTEGER NOT NULL DEFAULT 0,
        readiness_level TEXT NOT NULL DEFAULT 'needs_practice',
        strengths_json TEXT NOT NULL DEFAULT '[]',
        weaknesses_json TEXT NOT NULL DEFAULT '[]',
        remediation_tasks_json TEXT NOT NULL DEFAULT '[]',
        replay_json TEXT NOT NULL DEFAULT '{}',
        score_hash TEXT NOT NULL,
        model_review_status TEXT NOT NULL DEFAULT 'not_used',
        reviewed_by TEXT,
        reviewed_at TEXT,
        anonymized INTEGER NOT NULL DEFAULT 1,
        duration_seconds INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (session_id) REFERENCES training_sessions(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS notice_relation_decisions (
        pair_key TEXT PRIMARY KEY,
        left_notice_id TEXT NOT NULL,
        right_notice_id TEXT NOT NULL,
        decision TEXT NOT NULL,
        locked INTEGER NOT NULL DEFAULT 0,
        actor TEXT NOT NULL,
        reason TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (left_notice_id) REFERENCES notices(id),
        FOREIGN KEY (right_notice_id) REFERENCES notices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS notice_relation_audit_events (
        id TEXT PRIMARY KEY,
        pair_key TEXT NOT NULL,
        action TEXT NOT NULL,
        actor TEXT NOT NULL,
        reason TEXT NOT NULL,
        before_json TEXT NOT NULL DEFAULT '{}',
        after_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (pair_key) REFERENCES notice_relation_decisions(pair_key)
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
    "CREATE INDEX IF NOT EXISTS idx_change_impact_rounds_notice ON change_impact_rounds(notice_id, round_number)",
    "CREATE INDEX IF NOT EXISTS idx_change_impact_events_round ON change_impact_events(round_id, change_type)",
    "CREATE INDEX IF NOT EXISTS idx_change_impact_items_round ON change_impact_items(round_id, impact_status)",
    "CREATE INDEX IF NOT EXISTS idx_change_impact_actions_round ON change_impact_actions(round_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_change_impact_audit_round ON change_impact_audit_events(round_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_clusters_project_no ON clusters(project_no)",
    "CREATE INDEX IF NOT EXISTS idx_evidence_items_cluster ON evidence_items(cluster_key)",
    "CREATE INDEX IF NOT EXISTS idx_evidence_items_notice ON evidence_items(notice_id)",
    "CREATE INDEX IF NOT EXISTS idx_evidence_sources_notice ON evidence_sources(notice_id, verified_status, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_evidence_sources_identity ON evidence_sources(notice_id, source_type, source_id)",
    "CREATE INDEX IF NOT EXISTS idx_evidence_claims_notice ON evidence_claims(notice_id, claim_type, status)",
    "CREATE INDEX IF NOT EXISTS idx_evidence_claim_links_evidence ON evidence_claim_links(evidence_id)",
    "CREATE INDEX IF NOT EXISTS idx_evidence_audit_notice ON evidence_audit_events(notice_id, created_at)",
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
    "CREATE INDEX IF NOT EXISTS idx_digital_twin_snapshots_notice ON opportunity_digital_twin_snapshots(notice_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_digital_twin_history_notice ON opportunity_digital_twin_history(notice_id, created_at)",
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
    "CREATE INDEX IF NOT EXISTS idx_bid_requirement_history_notice ON bid_requirement_history(notice_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_bid_deliverables_notice ON bid_deliverables(notice_id, status, due_at)",
    "CREATE INDEX IF NOT EXISTS idx_bid_plan_tasks_notice ON bid_plan_tasks(notice_id, status, due_at)",
    "CREATE INDEX IF NOT EXISTS idx_bid_pricing_items_notice ON bid_pricing_items(notice_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_enterprise_capabilities_status ON enterprise_capabilities(verification_status, capability_type)",
    "CREATE INDEX IF NOT EXISTS idx_requirement_capability_matches_notice ON requirement_capability_matches(notice_id, requirement_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_requirement_capability_matches_capability ON requirement_capability_matches(capability_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_capability_versions_capability ON capability_versions(capability_id, version_number)",
    "CREATE INDEX IF NOT EXISTS idx_capability_snapshots_notice ON capability_project_snapshots(notice_id, capability_id)",
    "CREATE INDEX IF NOT EXISTS idx_capability_gap_actions_notice ON capability_gap_actions(notice_id, status, action_type)",
    "CREATE INDEX IF NOT EXISTS idx_capability_performance_capability ON capability_performance_records(capability_id, result, occurred_at)",
    "CREATE INDEX IF NOT EXISTS idx_capability_audit_workspace ON capability_audit_events(workspace_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_business_measurements_task_quality ON business_measurements(task_type, quality_status, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_business_measurement_events_measurement ON business_measurement_events(measurement_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_requirement_review_cases_notice ON requirement_review_cases(notice_id, status, reviewer_role)",
    "CREATE INDEX IF NOT EXISTS idx_requirement_review_opinions_review ON requirement_review_opinions(review_id, agent_role)",
    "CREATE INDEX IF NOT EXISTS idx_requirement_review_opinions_notice ON requirement_review_opinions(notice_id, agent_role)",
    "CREATE INDEX IF NOT EXISTS idx_review_agent_runs_notice ON review_agent_runs(notice_id, started_at)",
    "CREATE INDEX IF NOT EXISTS idx_review_agent_run_events_run ON review_agent_run_events(run_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_decision_scenarios_notice ON decision_scenarios(notice_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_decision_suggestions_notice ON decision_scenario_suggestions(notice_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_decision_sandbox_events_notice ON decision_sandbox_events(notice_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_feishu_war_rooms_notice ON feishu_war_rooms(notice_id, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_feishu_war_room_steps_notice ON feishu_war_room_steps(notice_id, status, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_feishu_war_room_sync_events_notice ON feishu_war_room_sync_events(notice_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_requirement_review_human_opinions_notice ON requirement_review_human_opinions(notice_id, requirement_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_requirement_review_actions_notice ON requirement_review_actions(notice_id, status, due_at)",
    "CREATE INDEX IF NOT EXISTS idx_feishu_lead_import_runs_time ON feishu_lead_import_runs(started_at)",
    "CREATE INDEX IF NOT EXISTS idx_feishu_message_events_status ON feishu_message_events(status, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_organization_workspaces_status ON organization_workspaces(status, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_organization_members_workspace ON organization_members(workspace_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_organization_memories_workspace ON organization_memories(workspace_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_organization_memories_notice ON organization_memories(related_notice_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_organization_memory_events_workspace ON organization_memory_events(workspace_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_bid_memory_projects_workspace ON bid_memory_projects(workspace_id, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_bid_memory_projects_notice ON bid_memory_projects(notice_id, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_bid_memory_assets_workspace ON bid_memory_assets(workspace_id, reuse_status, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_bid_memory_assets_notice ON bid_memory_assets(source_notice_id, asset_type)",
    "CREATE INDEX IF NOT EXISTS idx_bid_memory_audit_workspace ON bid_memory_audit_events(workspace_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_source_incidents_status ON source_incidents(status, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_source_observations_site_time ON source_observations(source_site, observed_at)",
    "CREATE INDEX IF NOT EXISTS idx_opportunity_radar_snapshots_scope ON opportunity_radar_snapshots(scope, window_days, category, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_live_challenge_sessions_time ON live_challenge_sessions(created_at, status)",
    "CREATE INDEX IF NOT EXISTS idx_live_challenge_results_session ON live_challenge_results(session_id, position, origin)",
    "CREATE INDEX IF NOT EXISTS idx_demo_cases_role ON demo_reliability_cases(role, verification_status, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_demo_replays_case ON demo_replay_artifacts(case_id, source_version, verified_at)",
    "CREATE INDEX IF NOT EXISTS idx_demo_rehearsals_case ON demo_rehearsals(case_id, started_at, status)",
    "CREATE INDEX IF NOT EXISTS idx_demo_rehearsal_events_run ON demo_rehearsal_events(rehearsal_id, seq)",
    "CREATE INDEX IF NOT EXISTS idx_demo_layout_audits_profile ON demo_layout_audits(profile, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_visual_system_audits_profile ON visual_system_audits(profile, created_at)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_company_entities_credit_code ON company_entities(workspace_id, unified_credit_code) WHERE unified_credit_code <> ''",
    "CREATE INDEX IF NOT EXISTS idx_company_entities_name ON company_entities(workspace_id, legal_name, region)",
    "CREATE INDEX IF NOT EXISTS idx_company_aliases_lookup ON company_aliases(workspace_id, alias)",
    "CREATE INDEX IF NOT EXISTS idx_company_evidence_entity ON company_evidence(workspace_id, entity_id, evidence_status, captured_at)",
    "CREATE INDEX IF NOT EXISTS idx_company_risks_entity ON company_risk_signals(workspace_id, entity_id, dimension, signal_status)",
    "CREATE INDEX IF NOT EXISTS idx_company_relationships_from ON company_relationships(workspace_id, from_entity_id, relationship_type)",
    "CREATE INDEX IF NOT EXISTS idx_company_reviews_entity ON due_diligence_reviews(workspace_id, entity_id, confirmed_at)",
    "CREATE INDEX IF NOT EXISTS idx_company_tasks_entity ON company_due_diligence_tasks(workspace_id, entity_id, status, due_at)",
    "CREATE INDEX IF NOT EXISTS idx_company_snapshots_entity ON company_due_diligence_snapshots(workspace_id, entity_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_company_audits_entity ON company_due_diligence_audit_events(workspace_id, entity_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_company_answers_entity ON company_due_diligence_answers(workspace_id, entity_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_geo_events_time ON geo_events(event_type, event_time)",
    "CREATE INDEX IF NOT EXISTS idx_geo_events_notice ON geo_events(notice_id)",
    "CREATE INDEX IF NOT EXISTS idx_business_flows_time ON business_flows(occurred_at)",
    "CREATE INDEX IF NOT EXISTS idx_external_events_time ON external_events(event_type, event_time)",
    "CREATE INDEX IF NOT EXISTS idx_impact_links_event ON impact_links(external_event_id, review_status)",
    "CREATE INDEX IF NOT EXISTS idx_map_replay_scope ON map_replay_frames(scope, window_hours, category, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_training_scenarios_notice ON training_scenarios(notice_id, scenario_type)",
    "CREATE INDEX IF NOT EXISTS idx_training_sessions_scenario ON training_sessions(scenario_id, status, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_training_sessions_participant ON training_sessions(participant_key, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_training_turns_session ON training_turns(session_id, sequence)",
    "CREATE INDEX IF NOT EXISTS idx_training_results_score ON training_results(readiness_level, total_score, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_notice_relation_decisions_left ON notice_relation_decisions(left_notice_id, decision, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_notice_relation_decisions_right ON notice_relation_decisions(right_notice_id, decision, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_notice_relation_audit_pair ON notice_relation_audit_events(pair_key, created_at)",
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
        "weight REAL NOT NULL DEFAULT 0",
        "source_revision_id TEXT NOT NULL DEFAULT ''",
        "parent_requirement_id TEXT NOT NULL DEFAULT ''",
        "confirmed_at TEXT",
        "extraction_mode TEXT NOT NULL DEFAULT 'manual'",
    ),
    "enterprise_capabilities": (
        "workspace_id TEXT NOT NULL DEFAULT 'default'",
        "applicable_entity TEXT NOT NULL DEFAULT ''",
        "product_model TEXT NOT NULL DEFAULT ''",
        "regions_json TEXT NOT NULL DEFAULT '[]'",
        "authorization_scope TEXT NOT NULL DEFAULT ''",
        "source_file_name TEXT NOT NULL DEFAULT ''",
        "valid_from TEXT",
        "industry TEXT NOT NULL DEFAULT ''",
        "sample_redacted INTEGER NOT NULL DEFAULT 0",
        "content_hash TEXT NOT NULL DEFAULT ''",
        "version_number INTEGER NOT NULL DEFAULT 1",
    ),
    "requirement_capability_matches": (
        "workspace_id TEXT NOT NULL DEFAULT 'default'",
        "capability_version_id TEXT NOT NULL DEFAULT ''",
        "project_snapshot_id TEXT NOT NULL DEFAULT ''",
        "rule_details_json TEXT NOT NULL DEFAULT '{}'",
        "conflict_code TEXT NOT NULL DEFAULT ''",
    ),
    "requirement_review_cases": (
        "notice_revision_id TEXT NOT NULL DEFAULT ''",
        "evidence_scope_hash TEXT NOT NULL DEFAULT ''",
        "prompt_version TEXT NOT NULL DEFAULT ''",
        "last_run_id TEXT NOT NULL DEFAULT ''",
    ),
    "requirement_review_opinions": (
        "run_id TEXT NOT NULL DEFAULT ''",
        "notice_revision_id TEXT NOT NULL DEFAULT ''",
        "evidence_ids_json TEXT NOT NULL DEFAULT '[]'",
        "risks_json TEXT NOT NULL DEFAULT '[]'",
        "pending_items_json TEXT NOT NULL DEFAULT '[]'",
        "recommended_actions_json TEXT NOT NULL DEFAULT '[]'",
        "error_text TEXT NOT NULL DEFAULT ''",
        "attempt_number INTEGER NOT NULL DEFAULT 1",
    ),
    "business_measurements": (
        "experiment_id TEXT NOT NULL DEFAULT 'tendertrace-value-lab-v1'",
        "experiment_version INTEGER NOT NULL DEFAULT 1",
        "participant TEXT NOT NULL DEFAULT ''",
        "document_type TEXT NOT NULL DEFAULT ''",
        "file_count INTEGER NOT NULL DEFAULT 1",
        "sequence_order TEXT NOT NULL DEFAULT 'manual_first'",
        "conditions TEXT NOT NULL DEFAULT ''",
        "source_url TEXT NOT NULL DEFAULT ''",
        "raw_record_url TEXT NOT NULL DEFAULT ''",
        "gold_standard_url TEXT NOT NULL DEFAULT ''",
        "baseline_active_minutes REAL NOT NULL DEFAULT 0",
        "assisted_active_minutes REAL NOT NULL DEFAULT 0",
        "baseline_machine_wait_seconds REAL NOT NULL DEFAULT 0",
        "assisted_machine_wait_seconds REAL NOT NULL DEFAULT 0",
        "baseline_omissions INTEGER NOT NULL DEFAULT 0",
        "assisted_omissions INTEGER NOT NULL DEFAULT 0",
        "baseline_false_satisfied INTEGER NOT NULL DEFAULT 0",
        "assisted_false_satisfied INTEGER NOT NULL DEFAULT 0",
        "baseline_rework_count INTEGER NOT NULL DEFAULT 0",
        "assisted_rework_count INTEGER NOT NULL DEFAULT 0",
        "is_outlier INTEGER NOT NULL DEFAULT 0",
        "outlier_reason TEXT NOT NULL DEFAULT ''",
    ),
    "company_evidence": (
        "access_frequency TEXT NOT NULL DEFAULT 'on_demand'",
        "snapshot_sha256 TEXT NOT NULL DEFAULT ''",
    ),
    "company_due_diligence_tasks": (
        "feishu_receipt_json TEXT NOT NULL DEFAULT '{}'",
        "feishu_task_synced_at TEXT",
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
            INSERT OR IGNORE INTO opportunity_digital_twin_history(
                id, notice_id, state_hash, summary_json, created_at
            )
            SELECT id, notice_id, state_hash, summary_json, created_at
            FROM opportunity_digital_twin_snapshots
            """
        )
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
