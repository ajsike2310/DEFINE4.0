import asyncio
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import models  # noqa: F401  (register tables)
from .api.routes import router
from .core.config import get_settings
from .core import migrate
from .core.db import Base, make_session_factory
from .core.errors import ApiError
from .core.logs import configure_logging
from .core.ratelimit import SlidingWindowLimiter
from .services import scheduler

configure_logging(get_settings().log_level)
access_log = logging.getLogger("access")
REQUEST_ID = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


def create_app(database_url: str | None = None, provider_override=None) -> FastAPI:
    s = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = None
        if s.scheduler_enabled:
            task = asyncio.create_task(scheduler.run_forever(app, s))
            logging.getLogger("scheduler").info("background scheduler on (every %ss)", s.scheduler_interval_seconds)
        yield
        if task:
            task.cancel()

    app = FastAPI(title="Cadence API", version="0.2.0", lifespan=lifespan,
                  description="Backend for Cadence: events, campaigns, participants, leads, calls, follow-ups, analytics.")
    url = database_url or s.database_url
    if ":memory:" in url:                       # tests: straight from the models (a test proves it matches the migrations)
        engine, factory = make_session_factory(url)
        Base.metadata.create_all(engine)
    else:                                       # real databases: always migrated to the latest revision first
        migrate.upgrade_database(url)
        engine, factory = make_session_factory(url)
    app.state.engine = engine
    app.state.session_factory = factory
    app.state.provider_override = provider_override
    app.state.started_at = time.time()
    app.state.signup_limiter = SlidingWindowLimiter(s.signup_limit, s.signup_window_seconds)
    app.state.scheduler = {"enabled": s.scheduler_enabled, "ticks": 0, "last_tick_at": None, "last_result": None}
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_list, allow_methods=["*"], allow_headers=["*"],
                       expose_headers=["X-Request-ID", "X-Spoken-Text", "Retry-After"])

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        """Tag every request, and log method, path, status and time. Query strings and bodies are never logged
        (webhook tokens and phone numbers can appear there)."""
        incoming = request.headers.get("x-request-id", "")
        rid = incoming if REQUEST_ID.match(incoming) else uuid.uuid4().hex[:12]
        request.state.request_id = rid
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            if request.url.path != "/api/health":
                access_log.info("%s %s %s %s %.0fms", rid, request.method, request.url.path, status,
                                (time.perf_counter() - started) * 1000)

    def err(status, code, message, details=None, headers=None):
        return JSONResponse(status_code=status, headers=headers,
                            content={"error": {"code": code, "message": message, "details": details}})

    @app.exception_handler(ApiError)
    async def _api(_: Request, exc: ApiError):
        return err(exc.status_code, headers=exc.headers, **exc.detail)

    @app.exception_handler(RequestValidationError)
    async def _val(_: Request, exc: RequestValidationError):
        items = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
        return err(422, "validation_error", "Request validation failed", items)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        return err(exc.status_code, "http_error", str(exc.detail))

    app.include_router(router)
    return app


app = create_app()
