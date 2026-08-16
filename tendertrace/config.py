from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import os
from pathlib import Path
from typing import Iterable


class ModelMode(StrEnum):
    DISABLED = "disabled"
    LOCAL = "local"
    CLOUD = "cloud"


class OpenAIAPIStyle(StrEnum):
    RESPONSES = "responses"
    CHAT_COMPLETIONS = "chat_completions"


class ConfigError(ValueError):
    """Raised when local configuration is invalid."""


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _first_value(key: str, env_files: Iterable[dict[str, str]], default: str = "") -> str:
    if key in os.environ:
        return os.environ[key]
    for values in env_files:
        if key in values:
            return values[key]
    return default


def _bool_secret_present(value: str) -> bool:
    return bool(value and value.strip())


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _parse_bool(value: str) -> bool:
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _resolve_path(root: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    return path


@dataclass(frozen=True)
class Settings:
    workspace_root: Path
    app_env: str
    host: str
    port: int
    timezone: str
    delivery_channels: tuple[str, ...]
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_from: str
    smtp_to: tuple[str, ...]
    smtp_use_tls: bool
    smtp_password_present: bool
    smtp_timeout: float
    feishu_app_id: str
    feishu_app_secret_present: bool
    feishu_bitable_app_token: str
    feishu_bitable_table_id: str
    feishu_bitable_base_url: str
    feishu_timeout: float
    feishu_lead_import_enabled: bool
    feishu_lead_import_cron: str
    public_base_url: str
    db_path: Path
    outputs_dir: Path
    outbox_dir: Path
    snapshots_dir: Path
    traces_dir: Path
    secrets_dir: Path
    model_mode: ModelMode
    model_enhancement_enabled: bool
    model_request_timeout: float
    ollama_base_url: str
    ollama_model: str
    openai_api_key_present: bool
    openai_base_url: str
    openai_model: str
    openai_api_style: OpenAIAPIStyle
    feishu_enabled: bool
    feishu_base_url: str
    feishu_message_app_id_present: bool
    feishu_message_app_secret_present: bool
    feishu_default_receive_id: str
    feishu_default_receive_id_type: str
    feishu_calendar_id: str
    feishu_callback_verification_token_present: bool
    feishu_task_sync_enabled: bool
    feishu_task_sync_cron: str
    opportunity_change_alert_enabled: bool
    opportunity_change_alert_cron: str
    source_alert_enabled: bool
    source_alert_cron: str
    source_alert_min_reliability: float
    source_alert_stale_hours: int
    source_incident_sla_hours: int
    feishu_agent_enabled: bool
    feishu_agent_base_url: str
    feishu_agent_app_id_present: bool
    feishu_agent_app_secret_present: bool
    scheduler_enabled: bool
    ingest_enabled: bool
    ingest_cron: str
    ingest_topics: tuple[str, ...]
    ingest_regions: tuple[str, ...]
    vector_enabled: bool
    vector_model: str
    vector_top_k: int
    qualification_min_opportunity_score: int
    qualification_min_credibility: int
    qualification_min_completeness: int
    qualification_min_requirement_coverage: int
    decision_sla_hours: int
    opportunity_escalation_enabled: bool
    opportunity_escalation_cron: str
    opportunity_briefing_enabled: bool
    opportunity_briefing_cron: str
    attachment_max_per_notice: int
    attachment_max_bytes: int
    api_token_present: bool

    @classmethod
    def load(cls, workspace_root: Path | None = None) -> "Settings":
        root = (workspace_root or Path.cwd()).resolve()
        env_files = [_read_env_file(root / ".env.local"), _read_env_file(root / ".env")]

        mode_raw = _first_value("TENDERTRACE_MODEL_MODE", env_files, "local").lower()
        try:
            model_mode = ModelMode(mode_raw)
        except ValueError as exc:
            raise ConfigError(
                "TENDERTRACE_MODEL_MODE must be one of: disabled, local, cloud"
            ) from exc

        port_raw = _first_value("TENDERTRACE_PORT", env_files, "8000")
        try:
            port = int(port_raw)
        except ValueError as exc:
            raise ConfigError("TENDERTRACE_PORT must be an integer") from exc
        if not 1 <= port <= 65535:
            raise ConfigError("TENDERTRACE_PORT must be between 1 and 65535")
        attachment_max_per_notice = _parse_positive_int(
            _first_value("TENDERTRACE_ATTACHMENT_MAX_PER_NOTICE", env_files, "3"),
            "TENDERTRACE_ATTACHMENT_MAX_PER_NOTICE",
        )
        attachment_max_bytes = _parse_positive_int(
            _first_value("TENDERTRACE_ATTACHMENT_MAX_BYTES", env_files, "8388608"),
            "TENDERTRACE_ATTACHMENT_MAX_BYTES",
        )

        openai_key = _first_value("OPENAI_API_KEY", env_files, "")
        openai_model = _first_value("OPENAI_MODEL", env_files, "gpt-5.5")
        if model_mode == ModelMode.CLOUD and not _bool_secret_present(openai_key):
            raise ConfigError("cloud model mode requires OPENAI_API_KEY")
        api_style_raw = _first_value("TENDERTRACE_OPENAI_API_STYLE", env_files, "responses").lower()
        try:
            openai_api_style = OpenAIAPIStyle(api_style_raw)
        except ValueError as exc:
            raise ConfigError(
                "TENDERTRACE_OPENAI_API_STYLE must be one of: responses, chat_completions"
            ) from exc
        model_timeout = _parse_positive_float(
            _first_value("TENDERTRACE_MODEL_REQUEST_TIMEOUT", env_files, "8"),
            "TENDERTRACE_MODEL_REQUEST_TIMEOUT",
        )
        smtp_password = _first_value("TENDERTRACE_SMTP_PASSWORD", env_files, "")
        public_base_url = _first_value(
            "TENDERTRACE_PUBLIC_BASE_URL",
            env_files,
            f"http://{_first_value('TENDERTRACE_HOST', env_files, '127.0.0.1')}:{port}",
        )
        app_env = _first_value("TENDERTRACE_APP_ENV", env_files, "dev")
        api_token = _first_value("TENDERTRACE_API_TOKEN", env_files, "")
        if app_env.strip().lower() in {"prod", "production"} and not _bool_secret_present(
            api_token
        ):
            raise ConfigError("TENDERTRACE_API_TOKEN is required when TENDERTRACE_APP_ENV=prod")
        feishu_enabled = _parse_bool(_first_value("FEISHU_ENABLED", env_files, "false"))
        feishu_message_app_id = _first_value("FEISHU_APP_ID", env_files, "")
        feishu_message_app_secret = _first_value("FEISHU_APP_SECRET", env_files, "")
        feishu_bitable_app_id = _first_value(
            "TENDERTRACE_FEISHU_APP_ID", env_files, feishu_message_app_id
        )
        feishu_bitable_app_secret = _first_value(
            "TENDERTRACE_FEISHU_APP_SECRET", env_files, feishu_message_app_secret
        )
        feishu_bitable_app_token = _first_value(
            "TENDERTRACE_FEISHU_BITABLE_APP_TOKEN", env_files, ""
        )
        feishu_bitable_table_id = _first_value(
            "TENDERTRACE_FEISHU_BITABLE_TABLE_ID", env_files, ""
        )
        feishu_lead_import_enabled = _parse_bool(
            _first_value("TENDERTRACE_FEISHU_LEAD_IMPORT_ENABLED", env_files, "false")
        )
        if feishu_lead_import_enabled and not all(
            (
                feishu_bitable_app_id,
                _bool_secret_present(feishu_bitable_app_secret),
                feishu_bitable_app_token,
                feishu_bitable_table_id,
            )
        ):
            raise ConfigError(
                "TENDERTRACE_FEISHU_LEAD_IMPORT_ENABLED=true requires complete "
                "Feishu Bitable configuration"
            )
        if feishu_enabled and (
            not _bool_secret_present(feishu_message_app_id)
            or not _bool_secret_present(feishu_message_app_secret)
        ):
            raise ConfigError("FEISHU_ENABLED=true requires FEISHU_APP_ID and FEISHU_APP_SECRET")
        feishu_receive_id_type = _first_value(
            "FEISHU_DEFAULT_RECEIVE_ID_TYPE",
            env_files,
            "chat_id",
        ).strip() or "chat_id"
        _validate_feishu_receive_id_type(feishu_receive_id_type)
        feishu_task_sync_enabled = _parse_bool(
            _first_value("TENDERTRACE_FEISHU_TASK_SYNC_ENABLED", env_files, "false")
        )
        if feishu_task_sync_enabled and not feishu_enabled:
            raise ConfigError(
                "TENDERTRACE_FEISHU_TASK_SYNC_ENABLED=true requires FEISHU_ENABLED=true"
            )
        opportunity_change_alert_enabled = _parse_bool(
            _first_value(
                "TENDERTRACE_OPPORTUNITY_CHANGE_ALERT_ENABLED",
                env_files,
                "false",
            )
        )
        if opportunity_change_alert_enabled and not feishu_enabled:
            raise ConfigError(
                "TENDERTRACE_OPPORTUNITY_CHANGE_ALERT_ENABLED=true requires "
                "FEISHU_ENABLED=true"
            )
        source_alert_enabled = _parse_bool(
            _first_value("TENDERTRACE_SOURCE_ALERT_ENABLED", env_files, "false")
        )
        if source_alert_enabled and not feishu_enabled:
            raise ConfigError(
                "TENDERTRACE_SOURCE_ALERT_ENABLED=true requires FEISHU_ENABLED=true"
            )
        source_alert_min_reliability = _parse_ratio(
            _first_value("TENDERTRACE_SOURCE_ALERT_MIN_RELIABILITY", env_files, "0.75"),
            "TENDERTRACE_SOURCE_ALERT_MIN_RELIABILITY",
        )
        source_alert_stale_hours = _parse_positive_int(
            _first_value("TENDERTRACE_SOURCE_ALERT_STALE_HOURS", env_files, "24"),
            "TENDERTRACE_SOURCE_ALERT_STALE_HOURS",
        )
        source_incident_sla_hours = _parse_positive_int(
            _first_value("TENDERTRACE_SOURCE_INCIDENT_SLA_HOURS", env_files, "4"),
            "TENDERTRACE_SOURCE_INCIDENT_SLA_HOURS",
        )
        feishu_agent_enabled = _parse_bool(
            _first_value("FEISHU_AGENT_ENABLED", env_files, "false")
        )
        feishu_agent_app_id = _first_value("FEISHU_AGENT_APP_ID", env_files, "")
        feishu_agent_app_secret = _first_value("FEISHU_AGENT_APP_SECRET", env_files, "")
        if feishu_agent_enabled and (
            not _bool_secret_present(feishu_agent_app_id)
            or not _bool_secret_present(feishu_agent_app_secret)
        ):
            raise ConfigError(
                "FEISHU_AGENT_ENABLED=true requires FEISHU_AGENT_APP_ID and "
                "FEISHU_AGENT_APP_SECRET"
            )

        return cls(
            workspace_root=root,
            app_env=app_env,
            host=_first_value("TENDERTRACE_HOST", env_files, "127.0.0.1"),
            port=port,
            timezone=_first_value("TENDERTRACE_TIMEZONE", env_files, "Asia/Shanghai"),
            delivery_channels=_split_csv(
                _first_value("TENDERTRACE_DELIVERY_CHANNELS", env_files, "web,outbox")
            ),
            smtp_host=_first_value("TENDERTRACE_SMTP_HOST", env_files, ""),
            smtp_port=_parse_positive_int(
                _first_value("TENDERTRACE_SMTP_PORT", env_files, "587"),
                "TENDERTRACE_SMTP_PORT",
            ),
            smtp_username=_first_value("TENDERTRACE_SMTP_USERNAME", env_files, ""),
            smtp_from=_first_value("TENDERTRACE_SMTP_FROM", env_files, ""),
            smtp_to=_split_csv(_first_value("TENDERTRACE_SMTP_TO", env_files, "")),
            smtp_use_tls=_parse_bool(_first_value("TENDERTRACE_SMTP_USE_TLS", env_files, "true")),
            smtp_password_present=_bool_secret_present(smtp_password),
            smtp_timeout=_parse_positive_float(
                _first_value("TENDERTRACE_SMTP_TIMEOUT", env_files, "15"),
                "TENDERTRACE_SMTP_TIMEOUT",
            ),
            feishu_app_id=feishu_bitable_app_id,
            feishu_app_secret_present=_bool_secret_present(feishu_bitable_app_secret),
            feishu_bitable_app_token=feishu_bitable_app_token,
            feishu_bitable_table_id=feishu_bitable_table_id,
            feishu_bitable_base_url=_first_value(
                "TENDERTRACE_FEISHU_BITABLE_BASE_URL",
                env_files,
                "",
            ),
            feishu_timeout=_parse_positive_float(
                _first_value("TENDERTRACE_FEISHU_TIMEOUT", env_files, "20"),
                "TENDERTRACE_FEISHU_TIMEOUT",
            ),
            feishu_lead_import_enabled=feishu_lead_import_enabled,
            feishu_lead_import_cron=_first_value(
                "TENDERTRACE_FEISHU_LEAD_IMPORT_CRON", env_files, "*/15 * * * *"
            ),
            public_base_url=public_base_url.rstrip("/"),
            db_path=_resolve_path(
                root, _first_value("TENDERTRACE_DB_PATH", env_files, "data/tendertrace.sqlite3")
            ),
            outputs_dir=_resolve_path(
                root, _first_value("TENDERTRACE_OUTPUTS_DIR", env_files, "outputs")
            ),
            outbox_dir=_resolve_path(
                root, _first_value("TENDERTRACE_OUTBOX_DIR", env_files, "outbox")
            ),
            snapshots_dir=_resolve_path(
                root, _first_value("TENDERTRACE_SNAPSHOTS_DIR", env_files, "snapshots")
            ),
            traces_dir=_resolve_path(
                root, _first_value("TENDERTRACE_TRACES_DIR", env_files, "traces")
            ),
            secrets_dir=_resolve_path(
                root, _first_value("TENDERTRACE_SECRETS_DIR", env_files, "secrets")
            ),
            model_mode=model_mode,
            model_enhancement_enabled=_parse_bool(
                _first_value("TENDERTRACE_MODEL_ENHANCEMENT_ENABLED", env_files, "false")
            ),
            model_request_timeout=model_timeout,
            ollama_base_url=_first_value(
                "TENDERTRACE_OLLAMA_BASE_URL", env_files, "http://127.0.0.1:11434"
            ),
            ollama_model=_first_value("TENDERTRACE_OLLAMA_MODEL", env_files, "qwen3:8b"),
            openai_api_key_present=_bool_secret_present(openai_key),
            openai_base_url=_first_value("OPENAI_BASE_URL", env_files, "https://api.openai.com/v1"),
            openai_model=openai_model,
            openai_api_style=openai_api_style,
            feishu_enabled=feishu_enabled,
            feishu_base_url=_first_value(
                "FEISHU_BASE_URL",
                env_files,
                "https://open.feishu.cn",
            ).rstrip("/"),
            feishu_message_app_id_present=_bool_secret_present(feishu_message_app_id),
            feishu_message_app_secret_present=_bool_secret_present(feishu_message_app_secret),
            feishu_default_receive_id=_first_value("FEISHU_DEFAULT_RECEIVE_ID", env_files, ""),
            feishu_default_receive_id_type=feishu_receive_id_type,
            feishu_calendar_id=_first_value("FEISHU_CALENDAR_ID", env_files, ""),
            feishu_callback_verification_token_present=_bool_secret_present(
                _first_value("FEISHU_CALLBACK_VERIFICATION_TOKEN", env_files, "")
            ),
            feishu_task_sync_enabled=feishu_task_sync_enabled,
            feishu_task_sync_cron=_first_value(
                "TENDERTRACE_FEISHU_TASK_SYNC_CRON", env_files, "*/10 * * * *"
            ),
            opportunity_change_alert_enabled=opportunity_change_alert_enabled,
            opportunity_change_alert_cron=_first_value(
                "TENDERTRACE_OPPORTUNITY_CHANGE_ALERT_CRON",
                env_files,
                "*/15 * * * *",
            ),
            source_alert_enabled=source_alert_enabled,
            source_alert_cron=_first_value(
                "TENDERTRACE_SOURCE_ALERT_CRON", env_files, "15 */2 * * *"
            ),
            source_alert_min_reliability=source_alert_min_reliability,
            source_alert_stale_hours=source_alert_stale_hours,
            source_incident_sla_hours=source_incident_sla_hours,
            feishu_agent_enabled=feishu_agent_enabled,
            feishu_agent_base_url=_first_value(
                "FEISHU_AGENT_BASE_URL",
                env_files,
                "https://open.feishu.cn",
            ).rstrip("/"),
            feishu_agent_app_id_present=_bool_secret_present(feishu_agent_app_id),
            feishu_agent_app_secret_present=_bool_secret_present(feishu_agent_app_secret),
            scheduler_enabled=_parse_bool(
                _first_value("TENDERTRACE_SCHEDULER_ENABLED", env_files, "true")
            ),
            ingest_enabled=_parse_bool(
                _first_value("TENDERTRACE_INGEST_ENABLED", env_files, "false")
            ),
            ingest_cron=_first_value("TENDERTRACE_INGEST_CRON", env_files, "0 */6 * * *"),
            ingest_topics=_split_csv(
                _first_value(
                    "TENDERTRACE_INGEST_TOPICS",
                    env_files,
                    "服务器,充电桩,空调,储能,医疗设备,电梯,消防,安防,网络设备",
                )
            ),
            ingest_regions=_split_csv(
                _first_value(
                    "TENDERTRACE_INGEST_REGIONS",
                    env_files,
                    "北京,上海,广东,江苏,浙江,安徽,四川,河南",
                )
            ),
            vector_enabled=_parse_bool(
                _first_value("TENDERTRACE_VECTOR_ENABLED", env_files, "false")
            ),
            vector_model=_first_value(
                "TENDERTRACE_VECTOR_MODEL",
                env_files,
                "BAAI/bge-small-zh-v1.5",
            ),
            vector_top_k=_parse_positive_int(
                _first_value("TENDERTRACE_VECTOR_TOP_K", env_files, "30"),
                "TENDERTRACE_VECTOR_TOP_K",
            ),
            qualification_min_opportunity_score=_parse_percentage(
                _first_value(
                    "TENDERTRACE_QUALIFICATION_MIN_OPPORTUNITY_SCORE", env_files, "65"
                ),
                "TENDERTRACE_QUALIFICATION_MIN_OPPORTUNITY_SCORE",
            ),
            qualification_min_credibility=_parse_percentage(
                _first_value(
                    "TENDERTRACE_QUALIFICATION_MIN_CREDIBILITY", env_files, "60"
                ),
                "TENDERTRACE_QUALIFICATION_MIN_CREDIBILITY",
            ),
            qualification_min_completeness=_parse_percentage(
                _first_value(
                    "TENDERTRACE_QUALIFICATION_MIN_COMPLETENESS", env_files, "55"
                ),
                "TENDERTRACE_QUALIFICATION_MIN_COMPLETENESS",
            ),
            qualification_min_requirement_coverage=_parse_percentage(
                _first_value(
                    "TENDERTRACE_QUALIFICATION_MIN_REQUIREMENT_COVERAGE",
                    env_files,
                    "40",
                ),
                "TENDERTRACE_QUALIFICATION_MIN_REQUIREMENT_COVERAGE",
            ),
            decision_sla_hours=_parse_positive_int(
                _first_value("TENDERTRACE_DECISION_SLA_HOURS", env_files, "24"),
                "TENDERTRACE_DECISION_SLA_HOURS",
            ),
            opportunity_escalation_enabled=_parse_bool(
                _first_value(
                    "TENDERTRACE_OPPORTUNITY_ESCALATION_ENABLED",
                    env_files,
                    "false",
                )
            ),
            opportunity_escalation_cron=_first_value(
                "TENDERTRACE_OPPORTUNITY_ESCALATION_CRON",
                env_files,
                "0 9,14 * * 1-5",
            ),
            opportunity_briefing_enabled=_parse_bool(
                _first_value(
                    "TENDERTRACE_OPPORTUNITY_BRIEFING_ENABLED",
                    env_files,
                    "false",
                )
            ),
            opportunity_briefing_cron=_first_value(
                "TENDERTRACE_OPPORTUNITY_BRIEFING_CRON",
                env_files,
                "45 8 * * 1-5",
            ),
            attachment_max_per_notice=attachment_max_per_notice,
            attachment_max_bytes=attachment_max_bytes,
            api_token_present=_bool_secret_present(api_token),
        )

    def ensure_directories(self) -> None:
        for path in (
            self.db_path.parent,
            self.outputs_dir,
            self.outbox_dir,
            self.snapshots_dir,
            self.traces_dir,
            self.secrets_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def safe_summary(self) -> dict[str, object]:
        return {
            "app_env": self.app_env,
            "host": self.host,
            "port": self.port,
            "timezone": self.timezone,
            "delivery_channels": list(self.delivery_channels),
            "smtp_host": self.smtp_host,
            "smtp_port": self.smtp_port,
            "smtp_username_configured": bool(self.smtp_username),
            "smtp_from": self.smtp_from,
            "smtp_to_configured": bool(self.smtp_to),
            "smtp_use_tls": self.smtp_use_tls,
            "smtp_password_configured": self.smtp_password_present,
            "smtp_timeout": self.smtp_timeout,
            "feishu_app_id_configured": bool(self.feishu_app_id),
            "feishu_app_secret_configured": self.feishu_app_secret_present,
            "feishu_bitable_app_token_configured": bool(self.feishu_bitable_app_token),
            "feishu_bitable_table_id": self.feishu_bitable_table_id,
            "feishu_bitable_base_url": self.feishu_bitable_base_url,
            "feishu_timeout": self.feishu_timeout,
            "feishu_lead_import_enabled": self.feishu_lead_import_enabled,
            "feishu_lead_import_cron": self.feishu_lead_import_cron,
            "public_base_url": self.public_base_url,
            "db_path": str(self.db_path),
            "outputs_dir": str(self.outputs_dir),
            "outbox_dir": str(self.outbox_dir),
            "snapshots_dir": str(self.snapshots_dir),
            "traces_dir": str(self.traces_dir),
            "secrets_dir": str(self.secrets_dir),
            "model_mode": self.model_mode.value,
            "model_enhancement_enabled": self.model_enhancement_enabled,
            "model_request_timeout": self.model_request_timeout,
            "ollama_base_url": self.ollama_base_url,
            "ollama_model": self.ollama_model,
            "openai_key_configured": self.openai_api_key_present,
            "openai_base_url": self.openai_base_url,
            "openai_model": self.openai_model,
            "openai_api_style": self.openai_api_style.value,
            "feishu_enabled": self.feishu_enabled,
            "feishu_base_url": self.feishu_base_url,
            "feishu_message_app_id_configured": self.feishu_message_app_id_present,
            "feishu_message_app_secret_configured": self.feishu_message_app_secret_present,
            "feishu_default_receive_id_configured": bool(self.feishu_default_receive_id),
            "feishu_default_receive_id_type": self.feishu_default_receive_id_type,
            "feishu_calendar_id_configured": bool(self.feishu_calendar_id),
            "feishu_callback_verification_token_configured": (
                self.feishu_callback_verification_token_present
            ),
            "feishu_task_sync_enabled": self.feishu_task_sync_enabled,
            "feishu_task_sync_cron": self.feishu_task_sync_cron,
            "opportunity_change_alert_enabled": self.opportunity_change_alert_enabled,
            "opportunity_change_alert_cron": self.opportunity_change_alert_cron,
            "source_alert_enabled": self.source_alert_enabled,
            "source_alert_cron": self.source_alert_cron,
            "source_alert_min_reliability": self.source_alert_min_reliability,
            "source_alert_stale_hours": self.source_alert_stale_hours,
            "source_incident_sla_hours": self.source_incident_sla_hours,
            "feishu_agent_enabled": self.feishu_agent_enabled,
            "feishu_agent_base_url": self.feishu_agent_base_url,
            "feishu_agent_app_id_configured": self.feishu_agent_app_id_present,
            "feishu_agent_app_secret_configured": self.feishu_agent_app_secret_present,
            "scheduler_enabled": self.scheduler_enabled,
            "ingest_enabled": self.ingest_enabled,
            "ingest_cron": self.ingest_cron,
            "ingest_topics": list(self.ingest_topics),
            "ingest_regions": list(self.ingest_regions),
            "vector_enabled": self.vector_enabled,
            "vector_model": self.vector_model,
            "vector_top_k": self.vector_top_k,
            "qualification_policy": {
                "minimum_opportunity_score": self.qualification_min_opportunity_score,
                "minimum_credibility": self.qualification_min_credibility,
                "minimum_completeness": self.qualification_min_completeness,
                "minimum_requirement_coverage": (
                    self.qualification_min_requirement_coverage
                ),
                "decision_sla_hours": self.decision_sla_hours,
                "escalation_enabled": self.opportunity_escalation_enabled,
                "escalation_cron": self.opportunity_escalation_cron,
                "briefing_enabled": self.opportunity_briefing_enabled,
                "briefing_cron": self.opportunity_briefing_cron,
            },
            "attachment_max_per_notice": self.attachment_max_per_notice,
            "attachment_max_bytes": self.attachment_max_bytes,
            "api_token_configured": self.api_token_present,
        }

    def openai_api_key(self) -> str:
        env_files = [
            _read_env_file(self.workspace_root / ".env.local"),
            _read_env_file(self.workspace_root / ".env"),
        ]
        return _first_value("OPENAI_API_KEY", env_files, "")

    def smtp_password(self) -> str:
        env_files = [
            _read_env_file(self.workspace_root / ".env.local"),
            _read_env_file(self.workspace_root / ".env"),
        ]
        return _first_value("TENDERTRACE_SMTP_PASSWORD", env_files, "")

    def feishu_app_secret(self) -> str:
        env_files = [
            _read_env_file(self.workspace_root / ".env.local"),
            _read_env_file(self.workspace_root / ".env"),
        ]
        return _first_value(
            "TENDERTRACE_FEISHU_APP_SECRET",
            env_files,
            _first_value("FEISHU_APP_SECRET", env_files, ""),
        )

    def api_token(self) -> str:
        env_files = [
            _read_env_file(self.workspace_root / ".env.local"),
            _read_env_file(self.workspace_root / ".env"),
        ]
        return _first_value("TENDERTRACE_API_TOKEN", env_files, "")

    def feishu_message_app_id(self) -> str:
        env_files = [
            _read_env_file(self.workspace_root / ".env.local"),
            _read_env_file(self.workspace_root / ".env"),
        ]
        return _first_value("FEISHU_APP_ID", env_files, "")

    def feishu_message_app_secret(self) -> str:
        env_files = [
            _read_env_file(self.workspace_root / ".env.local"),
            _read_env_file(self.workspace_root / ".env"),
        ]
        return _first_value("FEISHU_APP_SECRET", env_files, "")

    def feishu_callback_verification_token(self) -> str:
        env_files = [
            _read_env_file(self.workspace_root / ".env.local"),
            _read_env_file(self.workspace_root / ".env"),
        ]
        return _first_value("FEISHU_CALLBACK_VERIFICATION_TOKEN", env_files, "")

    def feishu_agent_app_id(self) -> str:
        env_files = [
            _read_env_file(self.workspace_root / ".env.local"),
            _read_env_file(self.workspace_root / ".env"),
        ]
        return _first_value("FEISHU_AGENT_APP_ID", env_files, "")

    def feishu_agent_app_secret(self) -> str:
        env_files = [
            _read_env_file(self.workspace_root / ".env.local"),
            _read_env_file(self.workspace_root / ".env"),
        ]
        return _first_value("FEISHU_AGENT_APP_SECRET", env_files, "")


def _parse_positive_int(value: str, name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if parsed < 1:
        raise ConfigError(f"{name} must be positive")
    return parsed


def _parse_positive_float(value: str, name: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number") from exc
    if parsed <= 0:
        raise ConfigError(f"{name} must be positive")
    return parsed


def _parse_percentage(value: str, name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if not 0 <= parsed <= 100:
        raise ConfigError(f"{name} must be between 0 and 100")
    return parsed


def _parse_ratio(value: str, name: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number") from exc
    if not 0 <= parsed <= 1:
        raise ConfigError(f"{name} must be between 0 and 1")
    return parsed


def _validate_feishu_receive_id_type(value: str) -> None:
    allowed = {"chat_id", "open_id", "user_id", "union_id", "email"}
    if value not in allowed:
        raise ConfigError(
            "FEISHU_DEFAULT_RECEIVE_ID_TYPE must be one of: "
            + ", ".join(sorted(allowed))
        )
