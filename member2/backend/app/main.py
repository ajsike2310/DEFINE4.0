import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api.routes import ApiError, router
from .core.config import get_settings
from .core.db import Base, make_session_factory
from . import models  # noqa: F401  (register tables)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")


def create_app(database_url: str | None = None, provider_override=None) -> FastAPI:
    s = get_settings()
    app = FastAPI(title="Define Cadence API", version="0.1.0")
    engine, factory = make_session_factory(database_url or s.database_url)
    insp = inspect(engine)
    stale = ((insp.has_table("campaigns") and "event_id" not in {c["name"] for c in insp.get_columns("campaigns")})
             or (insp.has_table("call_attempts") and "mode" not in {c["name"] for c in insp.get_columns("call_attempts")}))
    if stale:
        raise RuntimeError("Database was created by an older version (no events). No migrations exist yet: "
                           "stop the app and delete the data/ folder (or point DATABASE_URL at a new file).")
    Base.metadata.create_all(engine)
    app.state.session_factory = factory
    app.state.provider_override = provider_override
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins.split(","),
                       allow_methods=["*"], allow_headers=["*"])

    def err(status, code, message, details=None):
        return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, "details": details}})

    @app.exception_handler(ApiError)
    async def _api(_: Request, exc: ApiError):
        return err(exc.status_code, **exc.detail)

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
