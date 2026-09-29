import asyncio
from contextlib import asynccontextmanager, suppress, ExitStack
import logging
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import Field, ValidationError

from . import __version__
from .config import ROOT
from .catalog import Catalog, CreateEvent, SelectEvent, ImportPreview, ImportEvent
from .models import Count, ID, Model
from .service import Conflict, live_view
from .storage import FileLease
from .auth import Auth, AuthConfig, COOKIE
from .auth_web import install_auth, same_origin


class EventContext(Model):
    event_id: ID | None = None
    selection_token: UUID | None = None


class Command(EventContext):
    request_id: UUID
    expected_revision: Count


class MatchCommand(Command):
    match_id: ID


class Prepare(MatchCommand):
    participant_1: ID
    participant_2: ID
    side_l: ID
    side_r: ID


class Score(EventContext):
    request_id: UUID
    match_id: ID
    control_revision: Count
    participant_id: ID
    side: Literal["L", "R"]
    delta: int = Field(strict=True, ge=-1, le=1)


class ConfigCommand(Command):
    data: dict


class Counter(EventContext):
    request_id: UUID
    match_id: ID
    control_revision: Count
    participant_id: ID
    counter_id: ID
    period: int = Field(strict=True, ge=1)
    delta: int = Field(strict=True, ge=-1, le=1)


class Period(MatchCommand):
    period: int = Field(strict=True, ge=1)


def create_app(data_file: Path | None = None, *, data_dir: Path | None = None, auth_config: AuthConfig | None = None):
    if data_dir is None:
        if data_file is None:
            raise ValueError("Datenverzeichnis fehlt.")
        data_dir = data_file.resolve().parent
    data_dir = data_dir.resolve()
    legacy = data_file.resolve() if data_file else data_dir / "tournament.json"
    auth_config = auth_config or AuthConfig(file=ROOT / 'config/auth.yml')

    @asynccontextmanager
    async def lifespan(app):
        with ExitStack() as cleanup:
            # One owner for the entire catalogue; also exclude a legacy single-event writer.
            for path in (data_dir / "active-event.json", legacy):
                lease = FileLease(path)
                lease.acquire()
                cleanup.callback(lease.release)
            app.state.service = Catalog(data_dir, legacy)
            if auth_config.enabled:
                lease = FileLease(auth_config.file)
                lease.acquire()
                cleanup.callback(lease.release)
            app.state.auth = Auth(auth_config)
            yield

    app = FastAPI(title="LiveScore", version=__version__, lifespan=lifespan)
    install_auth(app, ROOT)

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(request, exc):
        # Never echo submitted passwords or tokens in validation responses.
        return JSONResponse({"detail": "invalid_input"}, status_code=422)

    @app.exception_handler(Conflict)
    async def conflict_handler(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(ValidationError)
    async def validation_handler(request, exc):
        return JSONResponse({"detail": "; ".join(e["msg"] for e in exc.errors())}, status_code=422)

    @app.exception_handler(ValueError)
    async def value_handler(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(OSError)
    async def storage_handler(request, exc):
        logging.exception("Persistenz fehlgeschlagen")
        return JSONResponse({"detail": "Speichern fehlgeschlagen. Aktion wurde nicht übernommen."}, status_code=503)

    @app.middleware("http")
    async def no_cache(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.get("/api/v1/live")
    async def live():
        return live_view(app.state.service.state)

    @app.get("/api/version")
    async def version():
        return {"version": __version__}

    @app.get("/api/v1/tournament")
    async def tournament():
        return app.state.service.view()

    @app.get("/api/v1/event-catalog")
    async def catalog():
        return app.state.service.listing()

    @app.get("/api/v1/event-catalog/active")
    async def active_event():
        return app.state.service.selection

    @app.post("/api/v1/event-catalog/create")
    async def create_event(command: CreateEvent):
        return await app.state.service.catalog_apply("create", command)

    @app.post("/api/v1/event-catalog/select")
    async def select_event(command: SelectEvent):
        return await app.state.service.catalog_apply("select", command)

    @app.post("/api/v1/event-catalog/import/preview")
    async def preview_import(command: ImportPreview):
        return app.state.service.preview(command)

    @app.post("/api/v1/event-catalog/import")
    async def import_event(command: ImportEvent):
        return await app.state.service.catalog_apply("import", command)

    @app.get("/api/v1/event-catalog/{event_id}/export")
    async def export_event(event_id: ID):
        state = app.state.service.states.get(event_id)
        if state is None:
            return JSONResponse({"detail": "Veranstaltung nicht gefunden."}, status_code=404)
        return Response(state.model_dump_json(indent=2) + "\n", media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{event_id}.json"'})

    @app.get("/api/v1/matches")
    async def matches():
        return app.state.service.state.matches

    @app.get("/api/v1/events")
    async def events():
        return [e.model_dump(mode="json", exclude={"signature"}) for e in app.state.service.state.events]

    @app.post("/api/v1/config/{kind}")
    async def configure(kind: Literal["event", "play-areas", "participants", "referees", "matches"], command: ConfigCommand):
        return await app.state.service.apply("config/" + kind, command)

    @app.post("/api/v1/live/prepare")
    async def prepare(command: Prepare):
        return await app.state.service.apply("prepare", command)

    @app.post("/api/v1/live/score")
    async def score(command: Score):
        if command.delta == 0:
            return JSONResponse({"detail": "delta muss -1 oder 1 sein."}, status_code=422)
        return await app.state.service.apply("score", command)

    def add_action(operation):
        async def action(command: MatchCommand):
            return await app.state.service.apply(operation, command)
        app.add_api_route("/api/v1/live/" + operation, action, methods=["POST"], name=operation)

    @app.post("/api/v1/live/counter")
    async def counter(command: Counter):
        if command.delta == 0:
            return JSONResponse({"detail": "delta muss -1 oder 1 sein."}, status_code=422)
        return await app.state.service.apply("counter", command)

    @app.post("/api/v1/live/period")
    async def period(command: Period):
        return await app.state.service.apply("period", command)

    for operation in ("select", "unprepare", "start", "pause", "resume", "switch-sides", "undo", "finish"):
        add_action(operation)

    @app.websocket("/api/v1/ws")
    async def websocket(ws: WebSocket):
        auth = app.state.auth
        sid = ws.cookies.get(COOKIE)
        session = auth.session(sid) if auth.config.enabled else None
        if auth.config.enabled and (not session or auth.restricted(session) or not same_origin(ws)):
            await ws.close(code=4401)
            return
        await ws.accept()
        service = app.state.service
        queue = service.subscribe()

        async def send():
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=5)
                except TimeoutError:
                    data = {"heartbeat": True}
                if auth.config.enabled and auth.session(sid) is not session:
                    await ws.close(code=4401)
                    return
                await asyncio.wait_for(ws.send_json(data), timeout=5)

        async def receive():
            while True:
                await ws.receive_text()

        tasks = [asyncio.create_task(send()), asyncio.create_task(receive())]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except (WebSocketDisconnect, TimeoutError, OSError, RuntimeError, asyncio.CancelledError):
            pass
        finally:
            service.subscribers.discard(queue)
            for task in tasks:
                task.cancel()
            with suppress(asyncio.CancelledError):
                await asyncio.gather(*tasks, return_exceptions=True)
            with suppress(RuntimeError, OSError, WebSocketDisconnect, asyncio.CancelledError):
                await ws.close()

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(ROOT / "static/index.html")

    @app.get("/config", include_in_schema=False)
    async def config_page():
        return FileResponse(ROOT / "static/config.html")

    @app.get("/events", include_in_schema=False)
    async def events_page():
        return FileResponse(ROOT / "static/events.html")

    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    return app
