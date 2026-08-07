from __future__ import annotations

from typing import Any


SENSITIVE_KEYS = {
    "api_key",
    "app_secret",
    "app_token",
    "authorization",
    "cookie",
    "cookies",
    "password",
    "smtp_password",
    "storage_state",
    "tenant_access_token",
}


def sanitize_for_output(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            sanitized[key_text] = "[redacted]" if _is_sensitive_key(key_text) and item else sanitize_for_output(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_for_output(item) for item in value]
    return value


def sanitize_stats(stats: dict[str, Any]) -> dict[str, Any]:
    sanitized = sanitize_for_output(stats)
    return sanitized if isinstance(sanitized, dict) else {}


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return (
        lowered in SENSITIVE_KEYS
        or lowered.endswith("_api_key")
        or lowered.endswith("_app_secret")
        or lowered.endswith("_app_token")
        or lowered.endswith("_password")
        or lowered.endswith("access_token")
    )
