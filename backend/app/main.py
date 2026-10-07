import asyncio
import hashlib
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError
from backend.app.config import Settings
from backend.app.runtime import Runtime
from backend.app.schemas import CommandRequest, Heartbeat, Login, VisionEvent
from backend.app.security import Auth
from backend.app.store import Store, utcnow


def create_app(settings=None):
    settings = settings or Settings.load()
    if settings.database_url.startswith("sqlite"):
        Path("data").mkdir(exist_ok=True)
    store = Store(settings.database_url)
    runtime = Runtime(settings, store)
    auth = Auth(settings)

    @asynccontextmanager
    async def lifespan(app):
        await runtime.start()
        yield
        await runtime.stop()

    app = FastAPI(title="SENTINEL-X", version="1.0.0", lifespan=lifespan)
    app.state.runtime, app.state.auth = runtime, auth

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        return JSONResponse({"detail": "E006 — Base indisponible : opération non confirmée"}, status_code=503)

    @app.middleware("http")
    async def guard(request, call_next):
        if request.method in ("POST", "PUT", "PATCH"):
            try:
                declared = int(request.headers.get("content-length", "0"))
            except ValueError:
                return JSONResponse({"detail": "Taille invalide"}, status_code=400)
            if declared > 16384:
                return JSONResponse({"detail": "Payload trop grand"}, status_code=413)
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 16384:
                    return JSONResponse({"detail": "Payload trop grand"}, status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health/live")
    async def live():
        return {"status": "alive"}

    @app.get("/health/ready")
    async def ready():
        await runtime.db("ping")
        return {"status": "ready"}

    @app.post("/api/v1/login")
    async def login(payload: Login, request: Request, response: Response):
        token, csrf = await asyncio.to_thread(auth.login, request, payload.username, payload.password)
        response.set_cookie("sentinel_session", token, httponly=True, secure=settings.secure_cookies, samesite="strict", max_age=8*3600)
        return {"csrf_token": csrf, "username": "operateur"}

    @app.get("/api/v1/session", dependencies=[Depends(auth.read)])
    async def session(request: Request):
        return {"csrf_token": auth.read(request)["csrf"], "username": "operateur"}

    @app.post("/api/v1/logout", dependencies=[Depends(auth.write)])
    async def logout(request: Request, response: Response):
        auth.sessions.pop(hashlib.sha256(request.cookies["sentinel_session"].encode()).hexdigest(), None)
        response.delete_cookie("sentinel_session", secure=settings.secure_cookies, httponly=True, samesite="strict")
        return {"ok": True}

    @app.get("/api/v1/status", dependencies=[Depends(auth.read)])
    async def status():
        return runtime.status()

    @app.get("/api/v1/measurements", dependencies=[Depends(auth.read)])
    async def measurements(seconds: int = Query(60, ge=1, le=604800), limit: int = Query(500, ge=1, le=1000),
                           offset: int = Query(0, ge=0), device_id: str | None = None, since: datetime | None = None, until: datetime | None = None):
        if (since and not since.tzinfo) or (until and not until.tzinfo):
            raise HTTPException(422, "Dates avec fuseau requises")
        start = since.astimezone(timezone.utc) if since else datetime.now(timezone.utc)-timedelta(seconds=seconds)
        rows = await runtime.db("list_rows", "measurements", limit, offset, device_id, start.isoformat(), until.astimezone(timezone.utc).isoformat() if until else None)
        return {"items": rows, "offset": offset, "limit": limit, "next_offset": offset+limit if len(rows) == limit else None}

    @app.get("/api/v1/alerts", dependencies=[Depends(auth.read)])
    async def alerts(limit: int = Query(50, ge=1, le=1000), offset: int = Query(0, ge=0)):
        return {"items": await runtime.db("list_rows", "alerts", limit, offset), "offset": offset, "limit": limit}

    @app.post("/api/v1/alerts", dependencies=[Depends(auth.service)])
    async def ingest_event(event: VisionEvent):
        # The service secret cannot impersonate telemetry or drive arbitrary commands.
        try:
            return await runtime.vision_event(event)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/v1/vision/heartbeat", dependencies=[Depends(auth.service)])
    async def vision_heartbeat(heartbeat: Heartbeat):
        runtime.vision_at, runtime.vision = time.monotonic(), heartbeat.model_dump()
        return {"ok": True}

    @app.post("/api/v1/alerts/{id_}/ack", dependencies=[Depends(auth.write)])
    async def acknowledge(id_: str):
        async with runtime.lock:
            row = await runtime.db("get", "alerts", id_)
            if not row:
                raise HTTPException(404, "Alerte inconnue")
            row = {**row, "acknowledged_at": row.get("acknowledged_at") or utcnow()}
            await runtime.db("put", "alerts", id_, row)
            if id_ in runtime.alerts:
                runtime.alerts[id_] = row
            return row

    @app.post("/api/v1/commands", status_code=202, dependencies=[Depends(auth.write)])
    async def command(payload: CommandRequest):
        async with runtime.lock:
            try:
                return await runtime.command(payload.model_dump())
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.get("/api/v1/commands", dependencies=[Depends(auth.read)])
    async def commands(limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0)):
        return {"items": await runtime.db("list_rows", "commands", limit, offset)}

    @app.get("/api/v1/commands/{id_}", dependencies=[Depends(auth.read)])
    async def command_result(id_: str):
        row = await runtime.db("get", "commands", id_)
        if not row:
            raise HTTPException(404, "Commande inconnue")
        return row

    @app.post("/api/v1/model/retrain", dependencies=[Depends(auth.write)])
    async def retrain():
        try:
            return await runtime.retrain()
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(503, "Sauvegarde du modèle impossible : précédent modèle conservé.") from exc

    @app.get("/api/v1/video", dependencies=[Depends(auth.read)])
    async def video():
        if time.monotonic()-runtime.vision_at >= 5 or not runtime.vision["camera"]:
            raise HTTPException(503, "E004 — Flux caméra indisponible")
        client = httpx.AsyncClient(timeout=httpx.Timeout(10, read=5))
        try:
            upstream = await client.send(client.build_request("GET", settings.vision_url+"/stream", headers={"Authorization": "Bearer " + settings.vision_token}), stream=True)
            upstream.raise_for_status()
        except httpx.HTTPError as exc:
            await client.aclose()
            raise HTTPException(503, "Flux vision inaccessible") from exc
        async def chunks():
            try:
                async for chunk in upstream.aiter_bytes():
                    yield chunk
            finally:
                await upstream.aclose()
                await client.aclose()
        return StreamingResponse(chunks(), media_type="multipart/x-mixed-replace; boundary=frame")

    @app.websocket("/api/v1/ws")
    async def websocket(ws: WebSocket):
        try:
            auth.session(ws.cookies.get("sentinel_session"))
            auth.check_origin(ws.headers.get("origin"))
        except HTTPException:
            await ws.close(code=1008)
            return
        await ws.accept()
        try:
            while True:
                auth.session(ws.cookies.get("sentinel_session"))
                # Full live snapshot + heartbeat; REST reload fills gaps after reconnection.
                await asyncio.wait_for(ws.send_json({"type": "snapshot", "data": runtime.status()}), timeout=2)
                await asyncio.sleep(1)
        except HTTPException:
            await ws.close(code=1008)
        except (WebSocketDisconnect, RuntimeError, asyncio.TimeoutError):
            pass

    static = Path(settings.static_path)
    if static.exists():
        app.mount("/assets", StaticFiles(directory=static/"assets"), name="assets")
        @app.get("/")
        async def index():
            return FileResponse(static/"index.html")
    return app
