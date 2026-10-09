"""Shared CSV reading/writing rules for imports and exports."""
import csv
import io

from pydantic import ValidationError

MAX_CSV_BYTES = 1_000_000


class CsvError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def read_rows(raw: bytes, *, header_hint: str) -> list[dict]:
    """Parse an uploaded CSV (UTF-8, with or without BOM). Requires `name` and `phone` columns."""
    if len(raw) > MAX_CSV_BYTES:
        raise CsvError(413, "too_large", "CSV limited to 1 MB")
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    except UnicodeDecodeError:
        raise CsvError(422, "bad_csv", "CSV must be UTF-8")
    if not rows or not {"name", "phone"} <= set(rows[0].keys()):
        raise CsvError(422, "bad_csv", header_hint)
    return rows


def row_error(exc: Exception) -> str:
    """One readable line for a rejected row."""
    if isinstance(exc, ValidationError):
        return exc.errors()[0]["msg"].removeprefix("Value error, ")
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict):
        return str(detail.get("message", exc))
    return str(exc)


_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


class Verbatim(str):
    """A value that is known to be safe as-is (for example a validated E.164 phone number)."""


def safe_cell(value) -> str:
    """Neutralise spreadsheet formula injection in exported free text (a name like `=HYPERLINK(...)`)."""
    text = "" if value is None else str(value)
    if isinstance(value, Verbatim):
        return text
    return "'" + text if text.startswith(_FORMULA_START) else text


def to_csv(header: list[str], rows: list[list]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for row in rows:
        w.writerow([safe_cell(v) for v in row])
    return buf.getvalue()
