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
    scheduler_enabled: bool
    ingest_enabled: bool
    ingest_cron: str
    ingest_topics: tuple[str, ...]
    ingest_regions: tuple[str, ...]
    vector_enabled: bool
    vector_model: str
    vector_top_k: int
    attachment_max_per_notice: int
    attachment_max_bytes: int

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

        return cls(
            workspace_root=root,
            app_env=_first_value("TENDERTRACE_APP_ENV", env_files, "dev"),
            host=_first_value("TENDERTRACE_HOST", env_files, "127.0.0.1"),
            port=port,
            timezone=_first_value("TENDERTRACE_TIMEZONE", env_files, "Asia/Shanghai"),
            delivery_channels=_split_csv(
                _first_value("TENDERTRACE_DELIVERY_CHANNELS", env_files, "web,outbox")
            ),
            db_path=_resolve_path(root, _first_value("TENDERTRACE_DB_PATH", env_files, "data/tendertrace.sqlite3")),
            outputs_dir=_resolve_path(root, _first_value("TENDERTRACE_OUTPUTS_DIR", env_files, "outputs")),
            outbox_dir=_resolve_path(root, _first_value("TENDERTRACE_OUTBOX_DIR", env_files, "outbox")),
            snapshots_dir=_resolve_path(root, _first_value("TENDERTRACE_SNAPSHOTS_DIR", env_files, "snapshots")),
            traces_dir=_resolve_path(root, _first_value("TENDERTRACE_TRACES_DIR", env_files, "traces")),
            secrets_dir=_resolve_path(root, _first_value("TENDERTRACE_SECRETS_DIR", env_files, "secrets")),
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
            scheduler_enabled=_parse_bool(
                _first_value("TENDERTRACE_SCHEDULER_ENABLED", env_files, "true")
            ),
            ingest_enabled=_parse_bool(_first_value("TENDERTRACE_INGEST_ENABLED", env_files, "false")),
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
            attachment_max_per_notice=attachment_max_per_notice,
            attachment_max_bytes=attachment_max_bytes,
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
            "scheduler_enabled": self.scheduler_enabled,
            "ingest_enabled": self.ingest_enabled,
            "ingest_cron": self.ingest_cron,
            "ingest_topics": list(self.ingest_topics),
            "ingest_regions": list(self.ingest_regions),
            "vector_enabled": self.vector_enabled,
            "vector_model": self.vector_model,
            "vector_top_k": self.vector_top_k,
            "attachment_max_per_notice": self.attachment_max_per_notice,
            "attachment_max_bytes": self.attachment_max_bytes,
        }

    def openai_api_key(self) -> str:
        env_files = [
            _read_env_file(self.workspace_root / ".env.local"),
            _read_env_file(self.workspace_root / ".env"),
        ]
        return _first_value("OPENAI_API_KEY", env_files, "")


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
