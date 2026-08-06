from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import init_db
from tendertrace.runtime.bus import EventBus
from tendertrace.runtime.checkpoint import SqliteCheckpointer
from tendertrace.runtime.graph import GraphError, TenderGraph
from tendertrace.runtime.state import RunState
from tendertrace.runtime.trace import SqliteTraceStore


def runtime_parts(root: Path):
    settings = Settings.load(root)
    init_db(settings)
    bus = EventBus()
    trace = SqliteTraceStore(settings)
    bus.subscribe(trace.record)
    return settings, bus, trace, SqliteCheckpointer(settings)


class TenderGraphTests(unittest.TestCase):
    def test_graph_runs_nodes_and_persists_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, bus, trace, checkpointer = runtime_parts(Path(tmp))

            def intent(state: RunState, context) -> RunState:
                context.emit_tool_call("parse", {"ok": True})
                return state.with_updates(intent={"topic": ["服务器"]})

            def report(state: RunState, context) -> RunState:
                context.emit_tool_call("write_docx")
                return state.with_updates(artifacts={"docx": "outbox/demo.docx"})

            graph = (
                TenderGraph()
                .add_node("intent", intent)
                .add_node("report", report)
                .add_edge("intent", "report")
            )
            final = graph.run(
                RunState.new("最近1个月安徽服务器"),
                checkpointer=checkpointer,
                event_bus=bus,
            )
            checkpoints = checkpointer.list(final.run_id)
            events = trace.list_events(final.run_id)

        self.assertEqual(final.status, "finished")
        self.assertEqual([item.node for item in checkpoints], ["intent", "report"])
        self.assertEqual(
            [event.event_type for event in events],
            [
                "node_started",
                "tool_called",
                "node_finished",
                "node_started",
                "tool_called",
                "node_finished",
                "run_finished",
            ],
        )

    def test_conditional_edge_routes_repair_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, bus, _, checkpointer = runtime_parts(Path(tmp))

            def collect(state: RunState, context) -> RunState:
                return state.with_updates(candidates=[{"title": "demo"}])

            def verify(state: RunState, context) -> RunState:
                if state.repair_rounds == 0:
                    return state.with_updates(quality={"passed": False})
                return state.with_updates(quality={"passed": True})

            def repair(state: RunState, context) -> RunState:
                return state.with_updates(repair_rounds=state.repair_rounds + 1)

            def report(state: RunState, context) -> RunState:
                return state.with_updates(artifacts={"ready": True})

            graph = (
                TenderGraph()
                .add_node("collect", collect)
                .add_node("verify", verify)
                .add_node("repair", repair)
                .add_node("report", report)
                .add_edge("collect", "verify")
                .add_conditional_edge(
                    "verify",
                    lambda state: "report" if state.quality.get("passed") else "repair",
                )
                .add_edge("repair", "collect")
            )
            final = graph.run(RunState.new("q"), checkpointer=checkpointer, event_bus=bus)
            checkpoints = checkpointer.list(final.run_id)

        self.assertEqual(final.repair_rounds, 1)
        self.assertEqual(
            [checkpoint.node for checkpoint in checkpoints],
            ["collect", "verify", "repair", "collect", "verify", "report"],
        )

    def test_resume_continues_after_latest_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, bus, trace, checkpointer = runtime_parts(Path(tmp))
            run_id = "resume-demo"

            def first(state: RunState, context) -> RunState:
                return state.with_updates(context={"first": True})

            def broken_second(state: RunState, context) -> RunState:
                raise RuntimeError("planned stop")

            graph = (
                TenderGraph()
                .add_node("first", first)
                .add_node("second", broken_second)
                .add_edge("first", "second")
            )
            with self.assertRaises(GraphError):
                graph.run(
                    RunState.new("q", run_id=run_id),
                    checkpointer=checkpointer,
                    event_bus=bus,
                )

            def second(state: RunState, context) -> RunState:
                return state.with_updates(context={**state.context, "second": True})

            resumed_graph = (
                TenderGraph()
                .add_node("first", first)
                .add_node("second", second)
                .add_edge("first", "second")
            )
            final = resumed_graph.run(
                RunState.new("q", run_id=run_id),
                checkpointer=checkpointer,
                event_bus=bus,
                resume=True,
            )
            checkpoints = checkpointer.list(run_id)
            events = trace.list_events(run_id)

        self.assertEqual(final.status, "finished")
        self.assertEqual(final.context, {"first": True, "second": True})
        self.assertEqual([checkpoint.node for checkpoint in checkpoints], ["first", "second"])
        self.assertIn("node_failed", [event.event_type for event in events])


if __name__ == "__main__":
    unittest.main()
