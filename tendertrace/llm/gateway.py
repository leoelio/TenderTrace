from __future__ import annotations

from dataclasses import dataclass
import json
import re
import time
from typing import Any, Protocol

import httpx

from tendertrace.config import ModelMode, OpenAIAPIStyle, Settings


class ModelTransport(Protocol):
    def post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ModelStatus:
    mode: str
    provider: str
    model: str
    configured: bool
    enhancement_enabled: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "provider": self.provider,
            "model": self.model,
            "configured": self.configured,
            "enhancement_enabled": self.enhancement_enabled,
        }


@dataclass(frozen=True)
class ModelCallResult:
    mode: str
    provider: str
    model: str
    status: str
    text: str = ""
    parsed: dict[str, Any] | None = None
    error: str = ""
    latency_ms: int = 0

    def safe_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "provider": self.provider,
            "model": self.model,
            "status": self.status,
            "error": self.error,
            "latency_ms": self.latency_ms,
            "parsed_keys": sorted(self.parsed.keys()) if isinstance(self.parsed, dict) else [],
        }


class HttpxModelTransport:
    def post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()


class ModelGateway:
    def __init__(self, settings: Settings, transport: ModelTransport | None = None) -> None:
        self.settings = settings
        self.transport = transport or HttpxModelTransport()

    def generate_json(self, *, system: str, user: str) -> ModelCallResult:
        started = time.perf_counter()
        status = model_status(self.settings)
        if not self.settings.model_enhancement_enabled:
            return self._result(status, started, "skipped", error="model enhancement disabled")
        if self.settings.model_mode == ModelMode.DISABLED:
            return self._result(status, started, "skipped", error="model mode disabled")
        if not status.configured:
            return self._result(status, started, "skipped", error="model provider is not configured")
        try:
            if self.settings.model_mode == ModelMode.LOCAL:
                payload = self._call_ollama(system=system, user=user)
            else:
                payload = self._call_openai(system=system, user=user)
            text = _extract_text(payload)
            parsed = _parse_json_object(text)
            if parsed is None:
                return self._result(status, started, "failed", text=text, error="model returned non-json")
            return self._result(status, started, "ok", text=text, parsed=parsed)
        except Exception as exc:
            return self._result(
                status,
                started,
                "failed",
                error=_sanitize_error(f"{type(exc).__name__}: {exc}"),
            )

    def _call_ollama(self, *, system: str, user: str) -> dict[str, Any]:
        url = f"{self.settings.ollama_base_url.rstrip('/')}/api/chat"
        return self.transport.post_json(
            url,
            headers={"Content-Type": "application/json"},
            payload={
                "model": self.settings.ollama_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "format": "json",
                "stream": False,
            },
            timeout=self.settings.model_request_timeout,
        )

    def _call_openai(self, *, system: str, user: str) -> dict[str, Any]:
        api_key = self.settings.openai_api_key()
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not configured")
        if self.settings.openai_api_style == OpenAIAPIStyle.CHAT_COMPLETIONS:
            return self._call_openai_chat_completions(system=system, user=user, api_key=api_key)
        return self._call_openai_responses(system=system, user=user, api_key=api_key)

    def _call_openai_responses(self, *, system: str, user: str, api_key: str) -> dict[str, Any]:
        url = f"{self.settings.openai_base_url.rstrip('/')}/responses"
        return self.transport.post_json(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            payload={
                "model": self.settings.openai_model,
                "instructions": system,
                "input": user,
                "store": False,
            },
            timeout=self.settings.model_request_timeout,
        )

    def _call_openai_chat_completions(
        self,
        *,
        system: str,
        user: str,
        api_key: str,
    ) -> dict[str, Any]:
        url = f"{self.settings.openai_base_url.rstrip('/')}/chat/completions"
        return self.transport.post_json(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            payload={
                "model": self.settings.openai_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0,
            },
            timeout=self.settings.model_request_timeout,
        )

    def _result(
        self,
        status: ModelStatus,
        started: float,
        call_status: str,
        *,
        text: str = "",
        parsed: dict[str, Any] | None = None,
        error: str = "",
    ) -> ModelCallResult:
        return ModelCallResult(
            mode=status.mode,
            provider=status.provider,
            model=status.model,
            status=call_status,
            text=text,
            parsed=parsed,
            error=error,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


def model_status(settings: Settings) -> ModelStatus:
    if settings.model_mode == ModelMode.DISABLED:
        return ModelStatus(
            mode="disabled",
            provider="none",
            model="",
            configured=True,
            enhancement_enabled=settings.model_enhancement_enabled,
        )
    if settings.model_mode == ModelMode.LOCAL:
        return ModelStatus(
            mode="local",
            provider="ollama",
            model=settings.ollama_model,
            configured=bool(settings.ollama_base_url and settings.ollama_model),
            enhancement_enabled=settings.model_enhancement_enabled,
        )
    return ModelStatus(
        mode="cloud",
        provider="openai",
        model=settings.openai_model,
        configured=settings.openai_api_key_present and bool(settings.openai_model),
        enhancement_enabled=settings.model_enhancement_enabled,
    )


def _extract_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("message"), dict):
        return str(payload["message"].get("content") or "")
    if isinstance(payload.get("choices"), list) and payload["choices"]:
        message = payload["choices"][0].get("message") or {}
        return str(message.get("content") or "")
    if payload.get("output_text"):
        return str(payload["output_text"])
    output = payload.get("output")
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if isinstance(content, list):
                for content_item in content:
                    if isinstance(content_item, dict):
                        parts.append(str(content_item.get("text") or ""))
            elif content:
                parts.append(str(content))
        if parts:
            return "".join(parts)
    return str(payload.get("text") or "")


def _parse_json_object(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def _sanitize_error(value: str) -> str:
    sanitized = re.sub(r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer [redacted]", value)
    sanitized = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "sk-[redacted]", sanitized)
    return sanitized[:500]
