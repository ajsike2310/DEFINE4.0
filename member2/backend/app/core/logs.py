"""Logging is configured here and nowhere else.

Loggers in use: `access` (one line per request: id, method, path, status, time; never query strings or bodies),
`migrate`, `scheduler`, `events`, `campaigns`.
"""
import logging

FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format=FORMAT)
    logging.getLogger("alembic").setLevel(logging.WARNING)      # per-request status checks would log twice a call
    logging.getLogger("httpx").setLevel(logging.WARNING)        # client libraries stay quiet unless something is wrong
    logging.getLogger("uvicorn.access").disabled = True         # our own `access` logger replaces it (no query strings)
