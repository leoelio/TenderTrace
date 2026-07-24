from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
import json
from pathlib import Path
from threading import Thread
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection, database_health, init_db
from tendertrace.evaluation import build_agent_evaluation_report
from tendertrace.intent import compile_intent
from tendertrace.llm.doctor import model_doctor
from tendertrace.llm.gateway import model_status
from tendertrace.memory import (
    build_weekly_report,
    load_memory_profile,
    persist_weekly_report,
    record_activity,
)
from tendertrace.runlog import get_run, list_outbox_messages
from tendertrace.runner import run_once
from tendertrace.runtime.checkpoint import SqliteCheckpointer
from tendertrace.runtime.trace import SqliteTraceStore
from tendertrace.scheduling.scheduler import (
    schedule_ingest_subscription,
    schedule_subscription,
    start_subscription_scheduler,
)
from tendertrace.scheduling.ingest_subscriptions import (
    create_ingest_subscription,
    delete_ingest_subscription,
    list_ingest_subscriptions,
    run_ingest_subscription,
)
from tendertrace.scheduling.subscriptions import (
    create_subscription,
    list_subscriptions,
    run_subscription,
)
from tendertrace.vault.qianlima import QianlimaSessionVault


def create_app():
    try:
        from fastapi import Body, FastAPI, HTTPException
        from fastapi.responses import FileResponse
    except ImportError as exc:
        raise RuntimeError("FastAPI is not installed. Run: python -m pip install -e .[dev]") from exc

    settings = Settings.load()
    init_db(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.scheduler = None
        if settings.scheduler_enabled:
            app.state.scheduler = start_subscription_scheduler(settings)
        try:
            yield
        finally:
            scheduler = app.state.scheduler
            if scheduler is not None:
                scheduler.shutdown(wait=False)

    app = FastAPI(title="TenderTrace", version="0.1.0", lifespan=lifespan)
    app.state.scheduler = None

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "config": settings.safe_summary(),
            "database": database_health(settings),
        }

    @app.get("/api/sources")
    def sources() -> dict[str, object]:
        qianlima = QianlimaSessionVault(settings)
        return {
            "items": [
                {"site": "ccgp", "engine": "http", "status": "configured"},
                {"site": "ggzy", "engine": "http", "status": "configured"},
                {
                    **qianlima.status().to_dict(),
                    "engine": "playwright",
                    "status": "configured" if qianlima.has_storage_state() else "login_required",
                },
            ]
        }

    @app.get("/api/model")
    def model() -> dict[str, object]:
        return model_status(settings).to_dict()

    @app.get("/api/model/doctor")
    def model_doctor_api(live: bool = False) -> dict[str, object]:
        return model_doctor(settings, live=live).to_dict()

    @app.post("/api/intent/parse")
    def parse_intent(request: dict[str, object] = Body(...)) -> dict[str, object]:
        query = str(request.get("query") or "")
        now_raw = request.get("now")
        now = datetime.fromisoformat(str(now_raw)) if now_raw else None
        return compile_intent(query, now=now)

    @app.post("/api/runs")
    def create_run(request: dict[str, object] = Body(...)) -> dict[str, object]:
        query = str(request.get("query") or "").strip()
        if not query:
            raise HTTPException(status_code=400, detail="query is required")
        now_raw = request.get("now")
        now = datetime.fromisoformat(str(now_raw)) if now_raw else None
        max_pages, max_results = _parse_limits(request)
        result = run_once(
            settings=settings,
            query=query,
            now=now,
            max_pages=max_pages,
            max_results=max_results,
            model_strategy=_model_strategy_from_request(request),
        ).to_dict()
        record_activity(
            settings,
            event_type="run_start",
            target="api",
            label=query,
            metadata={"query": query, "run_id": result.get("run_id"), "sync": True},
        )
        return result

    @app.post("/api/runs/start")
    def start_run_api(
        request: dict[str, object] = Body(...),
    ) -> dict[str, object]:
        query = str(request.get("query") or "").strip()
        if not query:
            raise HTTPException(status_code=400, detail="query is required")
        now_raw = request.get("now")
        now = datetime.fromisoformat(str(now_raw)) if now_raw else None
        max_pages, max_results = _parse_limits(request)
        run_id = str(uuid4())
        thread = Thread(
            target=run_once,
            kwargs={
                "settings": settings,
                "query": query,
                "now": now,
                "max_pages": max_pages,
                "max_results": max_results,
                "model_strategy": _model_strategy_from_request(request),
                "run_id": run_id,
            },
            daemon=True,
        )
        thread.start()
        record_activity(
            settings,
            event_type="run_start",
            target="web",
            label=query,
            metadata={"query": query, "run_id": run_id, "async": True},
        )
        return {"run_id": run_id, "status": "queued"}

    @app.post("/api/subscriptions")
    def create_subscription_api(request: dict[str, object] = Body(...)) -> dict[str, object]:
        query = str(request.get("query") or "").strip()
        if not query:
            raise HTTPException(status_code=400, detail="query is required")
        now_raw = request.get("now")
        now = datetime.fromisoformat(str(now_raw)) if now_raw else None
        max_pages, max_results = _parse_limits(request)
        try:
            subscription = create_subscription(
                settings,
                query=query,
                now=now,
                max_pages=max_pages,
                max_results=max_results,
                schedule_override=_schedule_override_from_request(request),
                model_strategy=_model_strategy_from_request(request),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if app.state.scheduler is not None:
            schedule_subscription(app.state.scheduler, settings, subscription)
        record_activity(
            settings,
            event_type="subscription_create",
            target="web",
            label=query,
            metadata={"query": query, "subscription_id": subscription.id},
        )
        return subscription.to_dict()

    @app.get("/api/subscriptions")
    def subscriptions() -> dict[str, object]:
        return {"items": [item.to_dict() for item in list_subscriptions(settings)]}

    @app.post("/api/ingest-subscriptions")
    def create_ingest_subscription_api(request: dict[str, object] = Body(...)) -> dict[str, object]:
        topics = _string_list(request.get("topics"))
        regions = _string_list(request.get("regions"))
        if not topics or not regions:
            raise HTTPException(status_code=400, detail="topics and regions are required")
        try:
            subscription = create_ingest_subscription(
                settings,
                name=str(request.get("name") or "ingest"),
                topics=topics,
                regions=regions,
                cron=str(request.get("cron") or settings.ingest_cron),
                window_days=int(request.get("window_days") or 30),
                max_pages=int(request.get("max_pages") or 1),
                max_results=int(request.get("max_results") or 20),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if app.state.scheduler is not None:
            schedule_ingest_subscription(app.state.scheduler, settings, subscription)
        return subscription.to_dict()

    @app.get("/api/ingest-subscriptions")
    def ingest_subscriptions() -> dict[str, object]:
        return {"items": [item.to_dict() for item in list_ingest_subscriptions(settings)]}

    @app.post("/api/ingest-subscriptions/{subscription_id}/run")
    def run_ingest_subscription_api(subscription_id: str) -> dict[str, object]:
        try:
            return run_ingest_subscription(settings, subscription_id=subscription_id).to_dict()
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete("/api/ingest-subscriptions/{subscription_id}")
    def delete_ingest_subscription_api(subscription_id: str) -> dict[str, object]:
        if not delete_ingest_subscription(settings, subscription_id):
            raise HTTPException(status_code=404, detail="ingest subscription not found")
        scheduler = app.state.scheduler
        if scheduler is not None:
            try:
                scheduler.remove_job(f"ingest_subscription:{subscription_id}")
            except Exception:
                pass
        return {"status": "deleted", "id": subscription_id}

    @app.post("/api/subscriptions/{subscription_id}/run")
    def run_subscription_api(subscription_id: str) -> dict[str, object]:
        try:
            result = run_subscription(settings, subscription_id=subscription_id).to_dict()
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        record_activity(
            settings,
            event_type="subscription_run",
            target="subscription",
            label=subscription_id,
            metadata={"subscription_id": subscription_id, "run_id": result.get("run_id")},
        )
        return result

    @app.delete("/api/subscriptions/{subscription_id}")
    def delete_subscription_api(subscription_id: str) -> dict[str, object]:
        with connection(settings) as conn:
            row = conn.execute(
                "SELECT id FROM subscriptions WHERE id = ?",
                (subscription_id,),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="subscription not found")
            conn.execute(
                """
                UPDATE subscriptions
                SET status = 'deleted', updated_at = datetime('now')
                WHERE id = ?
                """,
                (subscription_id,),
            )
        scheduler = app.state.scheduler
        if scheduler is not None:
            try:
                scheduler.remove_job(f"subscription:{subscription_id}")
            except Exception:
                pass
        record_activity(
            settings,
            event_type="subscription_delete",
            target="subscription",
            label=subscription_id,
            metadata={"subscription_id": subscription_id},
        )
        return {"status": "deleted", "id": subscription_id}

    @app.get("/api/runs")
    def runs() -> dict[str, object]:
        with connection(settings) as conn:
            rows = conn.execute(
                """
                SELECT id, subscription_id, original_query, mode, status, window_start, window_end,
                       started_at, finished_at, output_docx_path, stats_json, error
                FROM runs
                WHERE status != 'deleted'
                ORDER BY started_at DESC
                LIMIT 100
                """
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["stats"] = json.loads(item.pop("stats_json") or "{}")
            item["outbox_path"] = _outbox_path_for_run(item["id"], settings)
            items.append(item)
        return {"items": items}

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: str) -> dict[str, object]:
        run = get_run(settings, run_id)
        if run is None or run.get("status") == "deleted":
            raise HTTPException(status_code=404, detail="run not found")
        run["outbox_path"] = _outbox_path_for_run(run_id, settings)
        stats = run.get("stats")
        if isinstance(stats, dict):
            run["notice_count"] = stats.get("notice_count", 0)
            run["trace_events"] = stats.get("trace_events", 0)
        return run

    @app.delete("/api/runs/{run_id}")
    def delete_run_api(run_id: str) -> dict[str, object]:
        with connection(settings) as conn:
            row = conn.execute("SELECT id FROM runs WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="run not found")
            conn.execute("DELETE FROM outbox_messages WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM model_audits WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM trace_events WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM run_checkpoints WHERE run_id = ?", (run_id,))
            conn.execute(
                """
                UPDATE runs
                SET status = 'deleted',
                    finished_at = COALESCE(finished_at, datetime('now')),
                    error = COALESCE(error, 'deleted by user')
                WHERE id = ?
                """,
                (run_id,),
            )
        record_activity(
            settings,
            event_type="run_delete",
            target="run",
            label=run_id,
            metadata={"run_id": run_id},
        )
        return {"status": "deleted", "id": run_id}

    @app.get("/api/outbox")
    def outbox() -> dict[str, object]:
        tracked = list_outbox_messages(settings)
        tracked_paths = {str(Path(item.docx_path).resolve()) for item in tracked}
        files = sorted(settings.outbox_dir.glob("*.docx"), key=lambda p: p.stat().st_mtime, reverse=True)
        untracked = [file for file in files if str(file.resolve()) not in tracked_paths]
        return {
            "items": [
                {
                    "id": item.id,
                    "run_id": item.run_id,
                    "subscription_id": item.subscription_id,
                    "name": Path(item.docx_path).name,
                    "path": item.docx_path,
                    "size": Path(item.docx_path).stat().st_size,
                    "status": item.status,
                    "created_at": item.created_at,
                    "download_url": f"/api/outbox/{Path(item.docx_path).name}",
                }
                for item in tracked
                if Path(item.docx_path).exists()
            ]
            + [
                {
                    "id": None,
                    "run_id": None,
                    "subscription_id": None,
                    "name": file.name,
                    "path": str(file),
                    "size": file.stat().st_size,
                    "status": "ready",
                    "created_at": None,
                    "download_url": f"/api/outbox/{file.name}",
                }
                for file in untracked
            ]
        }

    @app.get("/api/outbox/{filename}")
    def download_outbox(filename: str):
        path = (settings.outbox_dir / filename).resolve()
        if settings.outbox_dir.resolve() not in path.parents or path.suffix.lower() != ".docx":
            raise HTTPException(status_code=400, detail="invalid outbox path")
        if not path.exists():
            raise HTTPException(status_code=404, detail="file not found")
        record_activity(
            settings,
            event_type="download",
            target="outbox",
            label=path.name,
            metadata={"filename": path.name},
        )
        return FileResponse(path, filename=path.name)

    @app.delete("/api/outbox/{filename}")
    def delete_outbox(filename: str) -> dict[str, object]:
        path = (settings.outbox_dir / filename).resolve()
        if settings.outbox_dir.resolve() not in path.parents or path.suffix.lower() != ".docx":
            raise HTTPException(status_code=400, detail="invalid outbox path")
        deleted_file = False
        if path.exists():
            path.unlink()
            deleted_file = True
        with connection(settings) as conn:
            rows = conn.execute(
                "SELECT id, docx_path FROM outbox_messages",
            ).fetchall()
            for row in rows:
                if Path(row["docx_path"]).name == filename:
                    conn.execute("DELETE FROM outbox_messages WHERE id = ?", (row["id"],))
        record_activity(
            settings,
            event_type="outbox_delete",
            target="outbox",
            label=filename,
            metadata={"filename": filename, "file_deleted": deleted_file},
        )
        return {"status": "deleted", "filename": filename, "file_deleted": deleted_file}

    @app.get("/api/evaluations/agent")
    def agent_evaluation() -> dict[str, object]:
        return build_agent_evaluation_report(settings)

    @app.post("/api/memory/events")
    def memory_event(request: dict[str, object] = Body(...)) -> dict[str, object]:
        event_type = str(request.get("event_type") or "").strip()
        if not event_type:
            raise HTTPException(status_code=400, detail="event_type is required")
        metadata = request.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise HTTPException(status_code=400, detail="metadata must be an object")
        try:
            return record_activity(
                settings,
                event_type=event_type,
                target=str(request.get("target") or ""),
                label=str(request.get("label") or ""),
                metadata=metadata,
                user_id=str(request.get("user_id") or "admin"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/memory/weekly")
    def weekly_memory(user_id: str = "admin", days: int = 7, save: bool = False) -> dict[str, object]:
        if days < 1 or days > 31:
            raise HTTPException(status_code=400, detail="days must be between 1 and 31")
        report = build_weekly_report(settings, user_id=user_id, days=days)
        if save:
            return persist_weekly_report(settings, report)
        return report

    @app.post("/api/memory/weekly")
    def save_weekly_memory(request: dict[str, object] | None = Body(default=None)) -> dict[str, object]:
        request = request or {}
        try:
            days = int(request.get("days") or 7)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="days must be an integer") from exc
        if days < 1 or days > 31:
            raise HTTPException(status_code=400, detail="days must be between 1 and 31")
        report = build_weekly_report(
            settings,
            user_id=str(request.get("user_id") or "admin"),
            days=days,
        )
        return persist_weekly_report(settings, report)

    @app.get("/api/memory/profile")
    def memory_profile(user_id: str = "admin") -> dict[str, object]:
        profile = load_memory_profile(settings, user_id=user_id)
        if profile is None:
            return {"user_id": user_id, "status": "empty"}
        return {"status": "ready", **profile}

    @app.get("/api/traces/{run_id}")
    def trace_events(run_id: str) -> dict[str, object]:
        store = SqliteTraceStore(settings)
        return {
            "run_id": run_id,
            "events": [
                {
                    "seq": event.seq,
                    "event_type": event.event_type,
                    "node": event.node,
                    "payload": event.payload,
                    "created_at": event.created_at,
                }
                for event in store.list_events(run_id)
            ],
        }

    @app.get("/api/checkpoints/{run_id}")
    def checkpoints(run_id: str) -> dict[str, object]:
        checkpointer = SqliteCheckpointer(settings)
        return {
            "run_id": run_id,
            "checkpoints": [
                {
                    "seq": checkpoint.seq,
                    "node": checkpoint.node,
                    "status": checkpoint.status,
                    "state": checkpoint.state.to_dict(),
                }
                for checkpoint in checkpointer.list(run_id)
            ],
        }

    web_dist = settings.workspace_root / "web" / "dist"
    if web_dist.exists():
        try:
            from fastapi.staticfiles import StaticFiles
        except ImportError:
            StaticFiles = None
        if StaticFiles is not None:
            app.mount("/", StaticFiles(directory=Path(web_dist), html=True), name="web")

    return app


def _parse_limits(request: dict[str, object]) -> tuple[int, int]:
    try:
        max_pages = int(request.get("max_pages") or 1)
        max_results = int(request.get("max_results") or 10)
    except (TypeError, ValueError) as exc:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail="max_pages and max_results must be integers",
        ) from exc
    if max_pages < 1 or max_results < 1:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="max_pages and max_results must be positive")
    return max_pages, max_results


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def _model_strategy_from_request(request: dict[str, object]) -> str | None:
    value = request.get("model_strategy")
    if value in (None, ""):
        return None
    strategy = str(value).strip().lower()
    allowed = {"config", "rules", "local", "cloud", "hybrid"}
    if strategy not in allowed:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail="model_strategy must be one of: config, rules, local, cloud, hybrid",
        )
    return strategy


def _schedule_override_from_request(request: dict[str, object]) -> dict[str, object] | None:
    value = request.get("schedule")
    if value is None:
        return None
    if not isinstance(value, dict):
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="schedule must be an object")
    return value


def _outbox_path_for_run(run_id: str, settings: Settings) -> str | None:
    for item in list_outbox_messages(settings):
        if item.run_id == run_id:
            return item.docx_path
    return None
