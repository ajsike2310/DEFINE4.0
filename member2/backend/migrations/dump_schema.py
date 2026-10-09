"""Dump a SQLite database's schema as frozen JSON (the format migrations use) or compare two schemas.

    python -m member2.backend.migrations.dump_schema models   > snapshots/vN.json   # schema the models produce now
    python -m member2.backend.migrations.dump_schema file path/to/app.db

Each object is {"type": "table"|"index", "name", "tbl_name", "sql"}. Automatic indexes (no SQL) are skipped.
"""
import json
import re
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, text


def dump(engine) -> list[dict]:
    with engine.connect() as c:
        rows = c.execute(text("SELECT type, name, tbl_name, sql FROM sqlite_master "
                              "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version' "
                              "ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END, name")).all()
    return [{"type": t, "name": n, "tbl_name": tbl, "sql": sql} for t, n, tbl, sql in rows]


def normalise(objects: list[dict]) -> list[tuple]:
    """Whitespace- and order-insensitive form used to compare two schemas."""
    return sorted((o["type"], o["name"], o["tbl_name"], re.sub(r"\s+", " ", o["sql"]).strip()) for o in objects)


def models_schema() -> list[dict]:
    """The schema `Base.metadata` produces, created in a scratch database."""
    from member2.backend.app import models  # noqa: F401  (register tables)
    from member2.backend.app.core.db import Base
    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine(f"sqlite:///{(Path(tmp) / 'scratch.db').as_posix()}")
        Base.metadata.create_all(engine)
        out = dump(engine)
        engine.dispose()
    return out


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "models"
    if what == "models":
        data = models_schema()
    elif what == "file":
        data = dump(create_engine(f"sqlite:///{Path(sys.argv[2]).as_posix()}"))
    else:
        raise SystemExit(__doc__)
    print(json.dumps(data, indent=1, ensure_ascii=False))
