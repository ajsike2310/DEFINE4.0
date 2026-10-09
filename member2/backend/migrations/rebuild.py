"""Helpers for SQLite migrations that change constraints, foreign keys or defaults.

SQLite cannot alter those in place, so a table is rebuilt (SQLite's documented procedure): rename the old table,
create the new one from a frozen DDL snapshot, copy the rows, drop the old table. Migrations run inside one
transaction on a connection with foreign keys OFF and `legacy_alter_table` ON (so renaming does not rewrite the
foreign keys of other tables); `PRAGMA foreign_key_check` must be clean before the transaction commits.
"""
import json
from pathlib import Path

from sqlalchemy.exc import IntegrityError

SNAPSHOTS = Path(__file__).parent / "snapshots"


class MigrationDataError(RuntimeError):
    """Existing rows break a rule the new schema enforces. Nothing was changed."""


def load(name: str) -> list[dict]:
    return json.loads((SNAPSHOTS / f"{name}.json").read_text(encoding="utf-8"))


def _tables(snapshot):
    return [o for o in snapshot if o["type"] == "table"]


def _indexes(snapshot, table: str):
    return [o for o in snapshot if o["type"] == "index" and o["tbl_name"] == table]


def existing_tables(conn) -> set[str]:
    return {r[0] for r in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")}


def _columns(conn, table: str) -> list[str]:
    return [r[1] for r in conn.exec_driver_sql(f'PRAGMA table_info("{table}")')]


def ensure_tables(conn, snapshot) -> list[str]:
    """Create any table (with its indexes) from the snapshot that does not exist yet. Returns the names created."""
    have, made = existing_tables(conn), []
    for t in _tables(snapshot):
        if t["name"] not in have:
            conn.exec_driver_sql(t["sql"])
            for ix in _indexes(snapshot, t["name"]):
                conn.exec_driver_sql(ix["sql"])
            made.append(t["name"])
    return made


def drop_all(conn, snapshot) -> None:
    for t in reversed(_tables(snapshot)):
        conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{t["name"]}"')


def check_foreign_keys(conn) -> None:
    bad = conn.exec_driver_sql("PRAGMA foreign_key_check").all()
    if bad:
        sample = ", ".join(f"{r[0]} row {r[1]} -> {r[2]}" for r in bad[:5])
        raise MigrationDataError(f"{len(bad)} rows point at records that do not exist ({sample}). "
                                 "Fix or remove them, then run the migration again. Nothing was changed.")


def rebuild(conn, snapshot, copy_from: dict[str, dict[str, str]] | None = None) -> None:
    """Rebuild every table in `snapshot` to match it, keeping all rows.

    `copy_from` maps table -> {new column: SQL expression over the old row} for columns that need a value
    that is not simply copied (for example a backfilled new column)."""
    copy_from = copy_from or {}
    ensure_tables(conn, snapshot)
    conn.exec_driver_sql("PRAGMA legacy_alter_table=ON")
    for t in _tables(snapshot):
        name, old = t["name"], f'{t["name"]}__old'
        conn.exec_driver_sql(f'ALTER TABLE "{name}" RENAME TO "{old}"')
        for (ix,) in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=? "
                                          "AND sql IS NOT NULL", (old,)).all():
            conn.exec_driver_sql(f'DROP INDEX "{ix}"')
        conn.exec_driver_sql(t["sql"])
        old_cols, new_cols = set(_columns(conn, old)), _columns(conn, name)
        exprs = copy_from.get(name, {})
        cols = [c for c in new_cols if c in old_cols or c in exprs]
        select = ", ".join(exprs.get(c, '"%s"' % c) for c in cols)
        col_list = ", ".join('"%s"' % c for c in cols)
        try:
            conn.exec_driver_sql(f'INSERT INTO "{name}" ({col_list}) SELECT {select} FROM "{old}"')
        except IntegrityError as exc:
            raise MigrationDataError(f"existing rows in '{name}' break a rule the new schema enforces: "
                                     f"{str(exc.orig)}. Fix those rows, then run the migration again. "
                                     "Nothing was changed.") from exc
        conn.exec_driver_sql(f'DROP TABLE "{old}"')
        for ix in _indexes(snapshot, name):
            conn.exec_driver_sql(ix["sql"])
    check_foreign_keys(conn)
