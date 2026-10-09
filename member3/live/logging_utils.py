import logging
import os
import re

_SECRET_PATH = re.compile(r"(/live/exotel/)[^\s/?\"]+")


def redact(text: str) -> str:
    return _SECRET_PATH.sub(r"\1<redacted>", text)


class RedactSecretPath(logging.Filter):
    """Uvicorn prints the request path, which here contains the stream secret."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        return True


def install(level: int = logging.INFO, log_file: str | None = "logs/live.log") -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=handlers)
    logging.getLogger("httpx").setLevel(logging.WARNING)            # request URLs are noise
    for name in ("uvicorn.access", "uvicorn.error", "uvicorn"):
        logging.getLogger(name).addFilter(RedactSecretPath())
    for h in logging.getLogger().handlers:
        h.addFilter(RedactSecretPath())
