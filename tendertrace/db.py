from __future__ import annotations

from contextlib import contextmanager
import json
import sqlite3
from pathlib import Path
from typing import Iterator

from tendertrace.config import Settings


SCHEMA_VERSION = 20


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
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
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
        feishu_event_id TEXT,
        feishu_message_id TEXT,
        qualification_score INTEGER NOT NULL DEFAULT 0,
        qualification_status TEXT NOT NULL DEFAULT 'pending',
        decision TEXT NOT NULL DEFAULT 'pending',
        decision_reason TEXT,
        decision_by TEXT,
        decision_at TEXT,
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
    "CREATE INDEX IF NOT EXISTS idx_opportunity_fact_overrides_notice ON opportunity_fact_overrides(notice_id, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_feishu_lead_import_runs_time ON feishu_lead_import_runs(started_at)",
    "CREATE INDEX IF NOT EXISTS idx_feishu_message_events_status ON feishu_message_events(status, created_at)",
)

REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "notices": (
        "purchaser TEXT",
        "core_content TEXT",
        "attachments_json TEXT NOT NULL DEFAULT '[]'",
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
        "stage_changed_at TEXT NOT NULL DEFAULT ''",
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
