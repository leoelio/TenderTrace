from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
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
        return self._send_message(
            receive_id=receive_id,
            receive_id_type=receive_id_type,
            msg_type="text",
            content={"text": text},
        )

    def upload_file(self, path: Path | str) -> str:
        file_path = Path(path)
        if not file_path.is_file():
            raise FeishuError("report file does not exist")
        size = file_path.stat().st_size
        if size <= 0:
            raise FeishuError("report file is empty")
        if size > 30 * 1024 * 1024:
            raise FeishuError("report file exceeds Feishu's 30 MB limit")
        token = self.get_tenant_access_token()
        with file_path.open("rb") as file_handle:
            response = self._client.post(
                self._url("/open-apis/im/v1/files"),
                headers={"Authorization": f"Bearer {token}"},
                data={"file_type": "stream", "file_name": file_path.name},
                files={
                    "file": (
                        file_path.name,
                        file_handle,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                },
            )
        payload = self._parse_response(response)
        data = payload.get("data")
        file_key = str(data.get("file_key") or "") if isinstance(data, dict) else ""
        if not file_key:
            raise FeishuError("Feishu file_key is missing in response")
        return file_key

    def send_file(
        self,
        path: Path | str,
        *,
        receive_id: str | None = None,
        receive_id_type: str | None = None,
    ) -> dict[str, Any]:
        receive_id = (receive_id or self.settings.feishu_default_receive_id).strip()
        receive_id_type = (receive_id_type or self.settings.feishu_default_receive_id_type).strip()
        if not receive_id:
            raise FeishuError("receive_id is required; set FEISHU_DEFAULT_RECEIVE_ID or pass one")
        file_key = self.upload_file(path)
        return self._send_message(
            receive_id=receive_id,
            receive_id_type=receive_id_type,
            msg_type="file",
            content={"file_key": file_key},
        )

    def _send_message(
        self,
        *,
        receive_id: str,
        receive_id_type: str,
        msg_type: str,
        content: dict[str, str],
    ) -> dict[str, Any]:
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
                "msg_type": msg_type,
                "content": json.dumps(content, ensure_ascii=False),
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
            payload = response.json()
        except ValueError as exc:
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as http_exc:
                raise FeishuError(f"Feishu HTTP {response.status_code}") from http_exc
            raise FeishuError("Feishu response is not JSON") from exc
        if not isinstance(payload, dict):
            raise FeishuError("Feishu response JSON must be an object")
        code = payload.get("code", 0)
        if code != 0:
            messages = {
                232034: "应用在当前租户不可用或未启用，请先发布应用并确认租户已安装",
            }
            message = messages.get(code, str(payload.get("msg") or "unknown error"))
            raise FeishuError(f"Feishu API error {code}: {message}")
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise FeishuError(f"Feishu HTTP {response.status_code}") from exc
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
