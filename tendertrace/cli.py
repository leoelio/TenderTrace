from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

from tendertrace.acceptance import run_acceptance
from tendertrace.config import ConfigError, Settings
from tendertrace.db import database_health, init_db
from tendertrace.demo_check import run_demo_check, write_demo_evidence
from tendertrace.demo_incremental import run_incremental_demo
from tendertrace.demo_video import generate_demo_video
from tendertrace.delivery.feishu_bitable import check_feishu_bitable
from tendertrace.gold import build_gold_candidates, evaluate_gold_recall
from tendertrace.ingest import run_ingest_cycle
from tendertrace.intent import compile_intent
from tendertrace.llm.doctor import model_doctor
from tendertrace.llm.gateway import model_status
from tendertrace.memory import build_weekly_report, persist_weekly_report
from tendertrace.runner import run_once
from tendertrace.runtime.bus import EventBus
from tendertrace.runtime.checkpoint import SqliteCheckpointer
from tendertrace.runtime.graph import TenderGraph
from tendertrace.runtime.state import RunState
from tendertrace.runtime.trace import SqliteTraceStore
from tendertrace.scheduling.subscriptions import (
    create_subscription,
    list_subscriptions,
    run_subscription,
)
from tendertrace.scheduling.ingest_subscriptions import (
    create_ingest_subscription,
    list_ingest_subscriptions,
    run_ingest_subscription,
)
from tendertrace.submission import create_submission_package
from tendertrace.vault.qianlima import QianlimaSessionVault
from tendertrace.vector import build_notice_embeddings


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def _settings() -> Settings:
    return Settings.load()


def cmd_init_db(_: argparse.Namespace) -> int:
    settings = _settings()
    init_db(settings)
    print(json.dumps({"status": "ok", "db_path": str(settings.db_path)}, ensure_ascii=False))
    return 0


def cmd_config_check(_: argparse.Namespace) -> int:
    settings = _settings()
    settings.ensure_directories()
    print(json.dumps(settings.safe_summary(), ensure_ascii=False, indent=2))
    return 0


def cmd_model_status(_: argparse.Namespace) -> int:
    settings = _settings()
    print(json.dumps(model_status(settings).to_dict(), ensure_ascii=False, indent=2))
    return 0


def cmd_model_doctor(args: argparse.Namespace) -> int:
    settings = _settings()
    report = model_doctor(settings, live=args.live)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.status == "pass" else 1


def cmd_health(_: argparse.Namespace) -> int:
    settings = _settings()
    print(json.dumps(database_health(settings), ensure_ascii=False, indent=2))
    return 0


def cmd_acceptance_check(args: argparse.Namespace) -> int:
    settings = _settings()
    report = run_acceptance(settings, strict_runtime=not args.no_runtime)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.status == "pass" else 1


def cmd_demo_check(args: argparse.Namespace) -> int:
    settings = _settings()
    report = run_demo_check(settings)
    payload = report.to_dict()
    if args.out:
        path = Path(args.out)
        if not path.is_absolute():
            path = settings.workspace_root / path
        write_demo_evidence(report, path)
        payload["evidence_path"] = str(path)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if report.status == "pass" else 1


def cmd_demo_video(args: argparse.Namespace) -> int:
    settings = _settings()
    output_path = Path(args.out) if args.out else None
    evidence_path = Path(args.evidence_out) if args.evidence_out else None
    if output_path is not None and not output_path.is_absolute():
        output_path = settings.workspace_root / output_path
    if evidence_path is not None and not evidence_path.is_absolute():
        evidence_path = settings.workspace_root / evidence_path
    result = generate_demo_video(
        settings,
        url=args.url,
        output_path=output_path,
        evidence_path=evidence_path,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.status == "pass" else 1


def cmd_demo_incremental(args: argparse.Namespace) -> int:
    settings = _settings()
    result = run_incremental_demo(
        settings,
        query=args.query,
        now=_parse_now(args.now),
        max_pages=args.max_pages,
        max_results=args.max_results,
        model_strategy=args.model_strategy,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _parse_now(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def cmd_parse_intent(args: argparse.Namespace) -> int:
    bidql = compile_intent(args.query, now=_parse_now(args.now))
    print(json.dumps(bidql, ensure_ascii=False, indent=2))
    return 0


def cmd_ingest_once(args: argparse.Namespace) -> int:
    settings = _settings()
    result = run_ingest_cycle(
        settings,
        topics=args.topic or None,
        regions=args.region or None,
        now=_parse_now(args.now),
        window_days=args.window_days,
        max_pages=args.max_pages,
        max_results=args.max_results,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


def cmd_embed_notices(args: argparse.Namespace) -> int:
    settings = _settings()
    result = build_notice_embeddings(settings, limit=args.limit)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.status in {"finished", "disabled"} else 1


def cmd_evaluate_gold(args: argparse.Namespace) -> int:
    settings = _settings()
    result = evaluate_gold_recall(
        settings,
        gold_path=Path(args.gold) if args.gold else None,
        k_values=tuple(args.k),
    )
    payload = result.to_dict()
    if args.out:
        path = Path(args.out)
        if not path.is_absolute():
            path = settings.workspace_root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        payload["output_path"] = str(path)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_gold_candidates(args: argparse.Namespace) -> int:
    settings = _settings()
    payload = build_gold_candidates(
        settings,
        gold_path=Path(args.gold) if args.gold else None,
        max_pages=args.max_pages,
        max_results=args.max_results,
    )
    path = Path(args.out)
    if not path.is_absolute():
        path = settings.workspace_root / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["output_path"] = str(path)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_memory_weekly(args: argparse.Namespace) -> int:
    settings = _settings()
    init_db(settings)
    report = build_weekly_report(settings, user_id=args.user_id, days=args.days)
    if args.save:
        report = persist_weekly_report(settings, report)
    if args.out:
        path = Path(args.out)
        if not path.is_absolute():
            path = settings.workspace_root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["output_path"] = str(path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_create_ingest_subscription(args: argparse.Namespace) -> int:
    settings = _settings()
    subscription = create_ingest_subscription(
        settings,
        name=args.name,
        topics=args.topic,
        regions=args.region,
        cron=args.cron,
        window_days=args.window_days,
        max_pages=args.max_pages,
        max_results=args.max_results,
    )
    print(json.dumps(subscription.to_dict(), ensure_ascii=False, indent=2))
    return 0


def cmd_list_ingest_subscriptions(_: argparse.Namespace) -> int:
    settings = _settings()
    print(
        json.dumps(
            {"items": [item.to_dict() for item in list_ingest_subscriptions(settings)]},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_run_ingest_subscription(args: argparse.Namespace) -> int:
    settings = _settings()
    result = run_ingest_subscription(settings, subscription_id=args.subscription_id)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    settings = _settings()
    init_db(settings)
    try:
        import uvicorn
    except ImportError as exc:
        raise ConfigError("uvicorn is not installed. Run: python -m pip install -e .[dev]") from exc
    uvicorn.run(
        "tendertrace.app.api:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=args.reload,
    )
    return 0


def cmd_graph_smoke(_: argparse.Namespace) -> int:
    settings = _settings()
    init_db(settings)
    bus = EventBus()
    trace_store = SqliteTraceStore(settings)
    bus.subscribe(trace_store.record)
    checkpointer = SqliteCheckpointer(settings)

    def intent(state: RunState, context) -> RunState:
        context.emit_tool_call("intent.rule_parser", {"query_length": len(state.original_query)})
        return state.with_updates(intent=compile_intent(state.original_query))

    def plan_sources(state: RunState, context) -> RunState:
        context.emit_tool_call("source_planner.static_matrix", {"sources": 2})
        return state.with_updates(
            source_plan=[
                {"site": "ccgp", "engine": "http"},
                {"site": "qianlima", "engine": "browser", "login": True},
            ]
        )

    def report(state: RunState, context) -> RunState:
        context.emit_tool_call("report.outbox_probe", {"channel": "outbox"})
        return state.with_updates(artifacts={"outbox_ready": True})

    graph = (
        TenderGraph()
        .add_node("intent", intent)
        .add_node("plan_sources", plan_sources)
        .add_node("report", report)
        .add_edge("intent", "plan_sources")
        .add_edge("plan_sources", "report")
    )
    final_state = graph.run(
        RunState.new("最近1个月的安徽省区域内的服务器招标信息都有哪些"),
        checkpointer=checkpointer,
        event_bus=bus,
    )
    checkpoints = checkpointer.list(final_state.run_id)
    events = trace_store.list_events(final_state.run_id)
    print(
        json.dumps(
            {
                "run_id": final_state.run_id,
                "status": final_state.status,
                "checkpoint_nodes": [checkpoint.node for checkpoint in checkpoints],
                "event_types": [event.event_type for event in events],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_run_once(args: argparse.Namespace) -> int:
    settings = _settings()
    result = run_once(
        settings=settings,
        query=args.query,
        now=_parse_now(args.now),
        max_pages=args.max_pages,
        max_results=args.max_results,
        model_strategy=args.model_strategy,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


def cmd_create_subscription(args: argparse.Namespace) -> int:
    settings = _settings()
    subscription = create_subscription(
        settings,
        query=args.query,
        now=_parse_now(args.now),
        max_pages=args.max_pages,
        max_results=args.max_results,
        model_strategy=args.model_strategy,
    )
    print(json.dumps(subscription.to_dict(), ensure_ascii=False, indent=2))
    return 0


def cmd_list_subscriptions(_: argparse.Namespace) -> int:
    settings = _settings()
    print(
        json.dumps(
            {"items": [subscription.to_dict() for subscription in list_subscriptions(settings)]},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_run_subscription(args: argparse.Namespace) -> int:
    settings = _settings()
    result = run_subscription(settings, subscription_id=args.subscription_id)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


def cmd_feishu_bitable_check(args: argparse.Namespace) -> int:
    settings = _settings()
    result = check_feishu_bitable(settings, ensure_fields=args.ensure_fields)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.status in {"pass", "warn", "skipped"} else 1


def cmd_source_status(_: argparse.Namespace) -> int:
    settings = _settings()
    qianlima = QianlimaSessionVault(settings)
    print(
        json.dumps(
            {
                "sources": [
                    {"site": "ccgp", "engine": "http", "status": "configured"},
                    {"site": "ggzy", "engine": "http", "status": "configured"},
                    {
                        **qianlima.status().to_dict(),
                        "engine": "playwright",
                        "status": "configured"
                        if qianlima.has_storage_state()
                        else "login_required",
                    },
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_login_qianlima(_: argparse.Namespace) -> int:
    settings = _settings()
    status = QianlimaSessionVault(settings).save_interactive_login()
    print(json.dumps(status.to_dict(), ensure_ascii=False, indent=2))
    return 0


def cmd_verify_qianlima(args: argparse.Namespace) -> int:
    settings = _settings()
    vault = QianlimaSessionVault(settings)
    status = vault.status()
    payload: dict[str, object] = {"storage_state": status.to_dict()}
    exit_status = 0 if status.ready else 1
    if args.live:
        probe = vault.live_probe()
        payload["live_probe"] = probe
        if probe["status"] == "fail":
            exit_status = 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return exit_status


def cmd_package_submission(args: argparse.Namespace) -> int:
    settings = _settings()
    output_path = Path(args.out) if args.out else None
    if output_path is not None and not output_path.is_absolute():
        output_path = settings.workspace_root / output_path
    result = create_submission_package(settings.workspace_root, output_path=output_path)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.status == "pass" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tendertrace")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db", help="Create or migrate the local SQLite database.").set_defaults(
        func=cmd_init_db
    )
    sub.add_parser("config-check", help="Print safe, redacted runtime configuration.").set_defaults(
        func=cmd_config_check
    )
    sub.add_parser("model-status", help="Print safe model provider status.").set_defaults(
        func=cmd_model_status
    )
    model_doctor_parser = sub.add_parser(
        "model-doctor",
        help="Check model configuration and optionally run a live provider probe.",
    )
    model_doctor_parser.add_argument(
        "--live",
        action="store_true",
        help="Call the configured model once with a safe JSON probe.",
    )
    model_doctor_parser.set_defaults(func=cmd_model_doctor)
    sub.add_parser("health", help="Print local database health.").set_defaults(func=cmd_health)
    acceptance = sub.add_parser(
        "acceptance-check",
        help="Run delivery acceptance checks without printing secrets.",
    )
    acceptance.add_argument(
        "--no-runtime",
        action="store_true",
        help="Skip strict runtime artifact requirements for clean workspaces.",
    )
    acceptance.set_defaults(func=cmd_acceptance_check)
    demo_check = sub.add_parser(
        "demo-check",
        help="Audit current workspace evidence before recording the demo video.",
    )
    demo_check.add_argument("--out", help="Optional path for a JSON evidence package.")
    demo_check.set_defaults(func=cmd_demo_check)
    demo_video = sub.add_parser(
        "demo-video",
        help="Generate a demo MP4 from current evidence and the running Web UI.",
    )
    demo_video.add_argument("--url", default="http://127.0.0.1:8000/", help="Running Web UI URL.")
    demo_video.add_argument("--out", help="Optional MP4 output path.")
    demo_video.add_argument(
        "--evidence-out",
        default="docs/demo/demo_evidence_latest.json",
        help="Path for the refreshed demo evidence JSON.",
    )
    demo_video.set_defaults(func=cmd_demo_video)
    demo_incremental = sub.add_parser(
        "demo-incremental",
        help="Create a scheduled subscription and trigger two runs to demonstrate incremental delivery.",
    )
    demo_incremental.add_argument("query")
    demo_incremental.add_argument("--now", help="Optional ISO datetime used for the demo.")
    demo_incremental.add_argument("--max-pages", type=int, default=1)
    demo_incremental.add_argument("--max-results", type=int, default=10)
    demo_incremental.add_argument(
        "--model-strategy",
        choices=("config", "rules", "local", "cloud", "hybrid"),
        default="config",
        help="Override model enhancement for this demo.",
    )
    demo_incremental.set_defaults(func=cmd_demo_incremental)
    parse_intent = sub.add_parser("parse-intent", help="Compile a natural-language query to BidQL.")
    parse_intent.add_argument("query")
    parse_intent.add_argument(
        "--now", help="Optional ISO datetime used to resolve relative windows."
    )
    parse_intent.set_defaults(func=cmd_parse_intent)
    ingest_once = sub.add_parser(
        "ingest-once",
        help="Collect configured topic/region pool into notices without writing a report.",
    )
    ingest_once.add_argument("--topic", action="append", help="Topic to collect; repeatable.")
    ingest_once.add_argument("--region", action="append", help="Region to collect; repeatable.")
    ingest_once.add_argument("--now", help="Optional ISO datetime used for relative windows.")
    ingest_once.add_argument("--window-days", type=int, default=30)
    ingest_once.add_argument("--max-pages", type=int, default=1)
    ingest_once.add_argument("--max-results", type=int, default=20)
    ingest_once.set_defaults(func=cmd_ingest_once)
    embed_notices = sub.add_parser(
        "embed-notices",
        help="Build optional local vectors for notices when TENDERTRACE_VECTOR_ENABLED=true.",
    )
    embed_notices.add_argument("--limit", type=int, default=None)
    embed_notices.set_defaults(func=cmd_embed_notices)
    evaluate_gold = sub.add_parser(
        "evaluate-gold",
        help="Evaluate local retrieval against an annotated gold benchmark.",
    )
    evaluate_gold.add_argument("--gold", help="Gold benchmark JSON path.")
    evaluate_gold.add_argument("--k", type=int, action="append", default=[5, 10])
    evaluate_gold.add_argument("--out", help="Optional JSON output path.")
    evaluate_gold.set_defaults(func=cmd_evaluate_gold)
    gold_candidates = sub.add_parser(
        "gold-candidates",
        help="Generate source candidates for manual gold annotation without editing the gold file.",
    )
    gold_candidates.add_argument("--gold", help="Gold benchmark JSON path.")
    gold_candidates.add_argument("--out", default="docs/evaluation/gold_candidates_latest.json")
    gold_candidates.add_argument("--max-pages", type=int, default=1)
    gold_candidates.add_argument("--max-results", type=int, default=20)
    gold_candidates.set_defaults(func=cmd_gold_candidates)
    memory_weekly = sub.add_parser(
        "memory-weekly",
        help="Build the local user-memory weekly report from recorded activity events.",
    )
    memory_weekly.add_argument("--user-id", default="admin")
    memory_weekly.add_argument("--days", type=int, default=7)
    memory_weekly.add_argument("--save", action="store_true", help="Persist this report snapshot.")
    memory_weekly.add_argument("--out", help="Optional JSON output path.")
    memory_weekly.set_defaults(func=cmd_memory_weekly)
    create_ingest_sub = sub.add_parser(
        "create-ingest-subscription",
        help="Create a background ingest subscription that only grows the local notices DB.",
    )
    create_ingest_sub.add_argument("--name", default="ingest")
    create_ingest_sub.add_argument("--topic", action="append", required=True)
    create_ingest_sub.add_argument("--region", action="append", required=True)
    create_ingest_sub.add_argument(
        "--cron", default=None, help="Cron expression, default uses TENDERTRACE_INGEST_CRON."
    )
    create_ingest_sub.add_argument("--window-days", type=int, default=30)
    create_ingest_sub.add_argument("--max-pages", type=int, default=1)
    create_ingest_sub.add_argument("--max-results", type=int, default=20)
    create_ingest_sub.set_defaults(func=cmd_create_ingest_subscription)
    sub.add_parser(
        "list-ingest-subscriptions",
        help="List active background ingest subscriptions.",
    ).set_defaults(func=cmd_list_ingest_subscriptions)
    run_ingest_sub = sub.add_parser(
        "run-ingest-subscription",
        help="Manually trigger one background ingest subscription.",
    )
    run_ingest_sub.add_argument("subscription_id")
    run_ingest_sub.set_defaults(func=cmd_run_ingest_subscription)
    serve = sub.add_parser("serve", help="Start the FastAPI service.")
    serve.add_argument(
        "--reload", action="store_true", help="Enable uvicorn hot reload for development."
    )
    serve.set_defaults(func=cmd_serve)
    sub.add_parser("graph-smoke", help="Run a small graph and persist trace events.").set_defaults(
        func=cmd_graph_smoke
    )
    run_once = sub.add_parser(
        "run-once", help="Run one public-source collection and write a Word report."
    )
    run_once.add_argument("query")
    run_once.add_argument("--now", help="Optional ISO datetime used for the run.")
    run_once.add_argument("--max-pages", type=int, default=1)
    run_once.add_argument("--max-results", type=int, default=10)
    run_once.add_argument(
        "--model-strategy",
        choices=("config", "rules", "local", "cloud", "hybrid"),
        default="config",
        help="Override model enhancement for this run.",
    )
    run_once.set_defaults(func=cmd_run_once)
    create_sub = sub.add_parser(
        "create-subscription",
        help="Create a scheduled subscription from a query containing frequency/time.",
    )
    create_sub.add_argument("query")
    create_sub.add_argument("--now", help="Optional ISO datetime used for intent parsing.")
    create_sub.add_argument("--max-pages", type=int, default=1)
    create_sub.add_argument("--max-results", type=int, default=10)
    create_sub.add_argument(
        "--model-strategy",
        choices=("config", "rules", "local", "cloud", "hybrid"),
        default="config",
        help="Persist a model enhancement strategy for this subscription.",
    )
    create_sub.set_defaults(func=cmd_create_subscription)
    sub.add_parser("list-subscriptions", help="List active scheduled subscriptions.").set_defaults(
        func=cmd_list_subscriptions
    )
    run_sub = sub.add_parser("run-subscription", help="Manually trigger a subscription run.")
    run_sub.add_argument("subscription_id")
    run_sub.set_defaults(func=cmd_run_subscription)
    feishu_check = sub.add_parser(
        "feishu-bitable-check",
        help="Validate Feishu Bitable connectivity and required opportunity fields.",
    )
    feishu_check.add_argument(
        "--ensure-fields",
        action="store_true",
        help="Create missing TenderTrace opportunity fields in the configured table.",
    )
    feishu_check.set_defaults(func=cmd_feishu_bitable_check)
    sub.add_parser(
        "source-status", help="Show configured source and login-state status."
    ).set_defaults(func=cmd_source_status)
    sub.add_parser(
        "login-qianlima",
        help="Open a browser for manual Qianlima login and save Playwright storage_state.",
    ).set_defaults(func=cmd_login_qianlima)
    verify_qianlima = sub.add_parser(
        "verify-qianlima",
        help="Validate saved Qianlima Playwright storage_state without printing cookies.",
    )
    verify_qianlima.add_argument(
        "--live",
        action="store_true",
        help="Open the Qianlima search page headlessly with the saved storage_state.",
    )
    verify_qianlima.set_defaults(func=cmd_verify_qianlima)
    package_submission = sub.add_parser(
        "package-submission",
        help="Create a redacted competition submission zip and manifest.",
    )
    package_submission.add_argument("--out", help="Optional zip output path.")
    package_submission.set_defaults(func=cmd_package_submission)
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
