from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from tendertrace.runtime.bus import EventBus, RunContext, RuntimeEvent
from tendertrace.runtime.checkpoint import SqliteCheckpointer
from tendertrace.runtime.state import RunState


class GraphNode(Protocol):
    def __call__(self, state: RunState, context: RunContext) -> RunState: ...


Router = Callable[[RunState], str]


class GraphError(RuntimeError):
    pass


class TenderGraph:
    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[str, str] = {}
        self._routers: dict[str, Router] = {}
        self._entrypoint: str | None = None

    def add_node(self, name: str, node: GraphNode) -> "TenderGraph":
        if name in self._nodes:
            raise GraphError(f"duplicate node: {name}")
        self._nodes[name] = node
        if self._entrypoint is None:
            self._entrypoint = name
        return self

    def add_edge(self, from_node: str, to_node: str) -> "TenderGraph":
        self._edges[from_node] = to_node
        return self

    def add_conditional_edge(self, from_node: str, router: Router) -> "TenderGraph":
        self._routers[from_node] = router
        return self

    def run(
        self,
        state: RunState,
        *,
        checkpointer: SqliteCheckpointer,
        event_bus: EventBus,
        resume: bool = False,
    ) -> RunState:
        self._validate()
        current = self._entrypoint
        if resume:
            latest = checkpointer.latest(state.run_id)
            if latest is not None:
                state = latest.state
                current = self._next_node(latest.node, state)
        while current is not None:
            if current not in self._nodes:
                raise GraphError(f"unknown node routed to: {current}")
            context = RunContext(run_id=state.run_id, node=current, bus=event_bus)
            event_bus.publish(
                RuntimeEvent(run_id=state.run_id, event_type="node_started", node=current)
            )
            try:
                next_state = self._nodes[current](state, context)
            except Exception as exc:
                event_bus.publish(
                    RuntimeEvent(
                        run_id=state.run_id,
                        event_type="node_failed",
                        node=current,
                        payload={"error": str(exc)},
                    )
                )
                event_bus.publish(
                    RuntimeEvent(
                        run_id=state.run_id,
                        event_type="run_finished",
                        payload={"status": "failed"},
                    )
                )
                raise GraphError(f"node failed: {current}") from exc
            state = next_state.with_updates(current_node=current, status="running")
            checkpointer.save(node=current, state=state)
            event_bus.publish(
                RuntimeEvent(
                    run_id=state.run_id,
                    event_type="node_finished",
                    node=current,
                    payload={"status": state.status},
                )
            )
            current = self._next_node(current, state)
        state = state.with_updates(status="finished")
        event_bus.publish(
            RuntimeEvent(run_id=state.run_id, event_type="run_finished", payload={"status": state.status})
        )
        return state

    def _next_node(self, node: str, state: RunState) -> str | None:
        if node in self._routers:
            return self._routers[node](state)
        return self._edges.get(node)

    def _validate(self) -> None:
        if self._entrypoint is None:
            raise GraphError("graph has no nodes")
        for from_node, to_node in self._edges.items():
            if from_node not in self._nodes:
                raise GraphError(f"edge starts at unknown node: {from_node}")
            if to_node not in self._nodes:
                raise GraphError(f"edge routes to unknown node: {to_node}")
        for from_node in self._routers:
            if from_node not in self._nodes:
                raise GraphError(f"conditional edge starts at unknown node: {from_node}")
