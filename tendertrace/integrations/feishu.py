from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

import httpx

from tendertrace.config import Settings


class FeishuError(RuntimeError):
    """Raised when Feishu integration is disabled, misconfigured, or rejected."""


@dataclass(frozen=True)
class FeishuStatus:
    enabled: bool
    configured: bool
    base_url: str
    app_id_configured: bool
    app_secret_configured: bool
    default_receive_id_configured: bool
    default_receive_id_type: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class FeishuAgentStatus:
    enabled: bool
    configured: bool
    base_url: str
    app_id_configured: bool
    app_secret_configured: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class FeishuClient:
    def __init__(self, settings: Settings, *, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._client = client or httpx.Client(timeout=settings.model_request_timeout)

    def get_tenant_access_token(self) -> str:
        self._require_credentials()
        response = self._client.post(
            self._url("/open-apis/auth/v3/tenant_access_token/internal"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            json={
                "app_id": self.settings.feishu_message_app_id(),
                "app_secret": self.settings.feishu_message_app_secret(),
            },
        )
        payload = self._parse_response(response)
        token = str(payload.get("tenant_access_token") or "")
        if not token:
            raise FeishuError("Feishu tenant_access_token is missing in response")
        return token

    def send_text(
        self,
        text: str,
        *,
        receive_id: str | None = None,
        receive_id_type: str | None = None,
    ) -> dict[str, Any]:
        receive_id = (receive_id or self.settings.feishu_default_receive_id).strip()
        receive_id_type = (receive_id_type or self.settings.feishu_default_receive_id_type).strip()
        if not text.strip():
            raise FeishuError("text is required")
        if not receive_id:
            raise FeishuError("receive_id is required; set FEISHU_DEFAULT_RECEIVE_ID or pass one")
        token = self.get_tenant_access_token()
        response = self._client.post(
            self._url("/open-apis/im/v1/messages"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            params={"receive_id_type": receive_id_type},
            json={
                "receive_id": receive_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        )
        return self._parse_response(response)

    def list_chats(self, *, page_size: int = 20, page_token: str | None = None) -> dict[str, Any]:
        token = self.get_tenant_access_token()
        params: dict[str, object] = {"page_size": min(max(page_size, 1), 100)}
        if page_token:
            params["page_token"] = page_token
        response = self._client.get(
            self._url("/open-apis/im/v1/chats"),
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        payload = self._parse_response(response)
        data = payload.get("data")
        return data if isinstance(data, dict) else {"items": []}

    def _require_credentials(self) -> None:
        if not self.settings.feishu_enabled:
            raise FeishuError("Feishu integration is disabled; set FEISHU_ENABLED=true")
        if (
            not self.settings.feishu_message_app_id_present
            or not self.settings.feishu_message_app_secret_present
        ):
            raise FeishuError("FEISHU_APP_ID and FEISHU_APP_SECRET are required")

    def _parse_response(self, response: httpx.Response) -> dict[str, Any]:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise FeishuError(f"Feishu HTTP {response.status_code}: {response.text[:200]}") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise FeishuError("Feishu response is not JSON") from exc
        if not isinstance(payload, dict):
            raise FeishuError("Feishu response JSON must be an object")
        code = payload.get("code", 0)
        if code != 0:
            raise FeishuError(f"Feishu API error {code}: {payload.get('msg') or 'unknown error'}")
        return payload

    def _url(self, path: str) -> str:
        return f"{self.settings.feishu_base_url}{path}"


def feishu_status(settings: Settings) -> FeishuStatus:
    return FeishuStatus(
        enabled=settings.feishu_enabled,
        configured=(
            settings.feishu_enabled
            and settings.feishu_message_app_id_present
            and settings.feishu_message_app_secret_present
        ),
        base_url=settings.feishu_base_url,
        app_id_configured=settings.feishu_message_app_id_present,
        app_secret_configured=settings.feishu_message_app_secret_present,
        default_receive_id_configured=bool(settings.feishu_default_receive_id.strip()),
        default_receive_id_type=settings.feishu_default_receive_id_type,
    )


def feishu_agent_status(settings: Settings) -> FeishuAgentStatus:
    return FeishuAgentStatus(
        enabled=settings.feishu_agent_enabled,
        configured=(
            settings.feishu_agent_enabled
            and settings.feishu_agent_app_id_present
            and settings.feishu_agent_app_secret_present
        ),
        base_url=settings.feishu_agent_base_url,
        app_id_configured=settings.feishu_agent_app_id_present,
        app_secret_configured=settings.feishu_agent_app_secret_present,
    )
