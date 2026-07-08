from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from tendertrace.runtime.state import utc_now_iso


@dataclass(frozen=True)
class RuntimeEvent:
    run_id: str
    event_type: str
    node: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)


EventHandler = Callable[[RuntimeEvent], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: list[EventHandler] = []
        self._events: list[RuntimeEvent] = []

    def subscribe(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

    def publish(self, event: RuntimeEvent) -> None:
        self._events.append(event)
        for handler in self._handlers:
            handler(event)

    def events(self) -> list[RuntimeEvent]:
        return list(self._events)


@dataclass(frozen=True)
class RunContext:
    run_id: str
    node: str
    bus: EventBus

    def emit_tool_call(self, tool_name: str, payload: dict[str, Any] | None = None) -> None:
        self.bus.publish(
            RuntimeEvent(
                run_id=self.run_id,
                event_type="tool_called",
                node=self.node,
                payload={"tool": tool_name, **(payload or {})},
            )
        )

