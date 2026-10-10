"""Dashboard app: `python -m scripts.run_dashboard`. Serves the UI, the API, and (for real calls) the live-call WebSocket."""
import hmac
import json
import logging
import os
import threading
import time
import urllib.parse
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from member3.integrations.factory import build_provider

from .api import build_router
from .config import Settings
from .db import Db
from .service import Engine
from .v2 import build_v2

log = logging.getLogger("dashboard")
STATIC = Path(__file__).parent / "static"
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def create_app(settings: Settings | None = None, provider=None, start_reconciler: bool = True) -> FastAPI:
    settings = settings or Settings.from_env()
    db = Db(settings.db_path)
    if not settings.enforce_allowlist:
        settings.exotel_allowed_numbers = ""      # the dashboard dials whatever numbers are added to an event
    provider = provider or build_provider(settings)
    if not provider.is_simulated and hasattr(provider, "client"):
        import httpx

        def remember_error(resp: httpx.Response) -> None:
            """Exotel's reason for a rejection (the provider itself only reports 'HTTP 400')."""
            if resp.status_code >= 400:
                resp.read()
                provider.last_error_detail = " ".join(resp.text.split())[:300]
                log.warning("Exotel rejected the request: HTTP %s %s", resp.status_code, provider.last_error_detail)
        provider.client = httpx.Client(timeout=15, event_hooks={"response": [remember_error]})
    engine = Engine(db, provider, settings)
    app = FastAPI(title="Cadence Dashboard", docs_url=None, redoc_url=None)

    if not provider.is_simulated:
        # Real calls: embed the live voice agent. Results flow straight into the engine, no HTTP hop.
        from member3.live.config import LiveSettings
        from member3.live.service import LiveService
        live = LiveService(LiveSettings.from_env(), sink=engine.on_result, conversational=True, detect_voicemail=True, keypad_hint=True,
                           leave_voicemail=lambda: engine.get_voicemail()["leave_message"])
        engine.live = live
        # Exotel only needs the audio WebSocket. It gets its own port so the tunnel can expose just that, and the
        # dashboard (contact lists, results) is never reachable from the internet.
        stream_app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        stream_app.include_router(live.router)
        stream_port = int(os.getenv("STREAM_PORT") or 8003)

        @app.on_event("startup")
        def start_stream_server():
            import uvicorn
            server = uvicorn.Server(uvicorn.Config(stream_app, host="127.0.0.1", port=stream_port, access_log=False, log_config=None))
            server.install_signal_handlers = lambda: None
            threading.Thread(target=server.run, name="stream-server", daemon=True).start()
            log.info("live-audio WebSocket listening on 127.0.0.1:%s (tunnel this port, not the dashboard)", stream_port)
        if not settings.exotel_stream_url:
            log.warning("EXOTEL_STREAM_URL is not set: calls will use the flow URL and live results will not arrive")

    def require_auth(authorization: str = Header(default=""), x_dashboard_token: str = Header(default="")):
        if not settings.dashboard_token:
            return
        supplied = x_dashboard_token or authorization.removeprefix("Bearer ").strip()
        if not hmac.compare_digest(supplied.encode(), settings.dashboard_token.encode()):
            raise HTTPException(401, "Access token required")

    app.include_router(build_router(db, engine, settings, require_auth))
    app.mount("/api/v2", build_v2(db, engine, settings, require_auth))       # the API the React app (frontend/) talks to
    if start_reconciler:
        engine.start_scheduler()

    @app.post("/api/webhooks/exotel")
    async def exotel_status(request: Request, token: str = ""):
        if not settings.exotel_webhook_token or not hmac.compare_digest(token.encode(), settings.exotel_webhook_token.encode()):
            raise HTTPException(401, "bad token")
        raw = await request.body()
        try:
            if "json" in request.headers.get("content-type", ""):
                data = json.loads(raw or b"{}")
            else:                                       # application/x-www-form-urlencoded, as Exotel sends it
                data = {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode("utf-8", "replace")).items()}
        except Exception:
            data = {}
        sid, status = str(data.get("CallSid") or ""), str(data.get("Status") or "").lower()
        if sid and status:
            engine.on_status(sid, status)
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"ok": True}

    if start_reconciler and not provider.is_simulated:
        def loop():
            while True:
                time.sleep(30)
                try:
                    engine.reconcile()
                except Exception:
                    log.exception("reconcile failed")
        threading.Thread(target=loop, name="reconciler", daemon=True).start()

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    # The React app (frontend/), after `npm run build`. Unknown paths fall back to index.html so client-side routes work.
    @app.get("/app")
    @app.get("/app/{path:path}")
    def react_app(path: str = ""):
        root = FRONTEND_DIST.resolve()
        target = (root / path).resolve()
        if path and root in target.parents and target.is_file():
            return FileResponse(target)
        index = root / "index.html"
        if not index.is_file():
            raise HTTPException(404, "The React app is not built yet. Run: cd frontend && npm install && npm run build")
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
    app.state.engine, app.state.db = engine, db
    return app
