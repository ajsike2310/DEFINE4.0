"""Backend command line.

Database:
    python -m member2.backend.app.cli db current            which revision the database is at, and the code's head
    python -m member2.backend.app.cli db upgrade [rev]      migrate (a backup is written first); default: head
    python -m member2.backend.app.cli db downgrade <rev>    step back (a backup is written first)
    python -m member2.backend.app.cli db history            list revisions
    python -m member2.backend.app.cli db check              integrity + consistency rules; exit code 1 if anything is wrong
    python -m member2.backend.app.cli db backup             consistent copy into <data dir>/backups
    python -m member2.backend.app.cli db stats              row counts, size, indexes
    python -m member2.backend.app.cli db optimize           refresh planner statistics

Exotel:
    python -m member2.backend.app.cli exotel doctor [--probe]   is the backend ready for real calls? (names only, no secrets)
    python -m member2.backend.app.cli exotel webhooks [-n 20]   the last callbacks Exotel sent us, masked

Use `--url sqlite:///path/to/file.db` to act on another database (default: DATABASE_URL / data/app.db).
"""
import argparse
import json
import sys

from alembic.script import ScriptDirectory
from sqlalchemy.orm import sessionmaker

from .core import dbtools, migrate
from .core.config import get_settings
from .core.db import make_engine
from .repositories import webhook_logs as log_repo
from .services import readiness


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _doctor(engine, probe: bool) -> int:
    with sessionmaker(bind=engine)() as db:
        report = readiness.exotel_readiness(db, get_settings(), probe=probe)
    for c in report["checks"]:
        mark = "ok     " if c["ok"] else ("MISSING" if c["required"] else "optional")
        show = c.get("detail") and (not c["ok"] or "region" in c["name"] or "reachable" in c["name"])
        extra = f"  ({c['detail']})" if show else ""
        print(f"[{mark}] {c['name']}{extra}")
    print()
    for step in report["next_steps"]:
        print("to do:", step)
    urls = report["urls"]
    if urls["status_callback"]:
        print("StatusCallback URL :", urls["status_callback"])
        print("Passthru (GET) URL :", urls["passthru_response"])
    seen = report["webhooks_seen_last_24h"]
    print(f"callbacks received from Exotel in the last 24 h: {seen['status']} status, {seen['response']} keypad")
    print("READY for a test call" if report["ready"] else "NOT ready yet")
    return 0 if report["ready"] else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cadence", description="Cadence backend tools")
    ap.add_argument("--url", help="database URL (default: DATABASE_URL / data/app.db)")
    groups = ap.add_subparsers(dest="group", required=True)
    db_cmds = groups.add_parser("db", help="database commands").add_subparsers(dest="cmd", required=True)
    up = db_cmds.add_parser("upgrade")
    up.add_argument("revision", nargs="?", default="head")
    down = db_cmds.add_parser("downgrade")
    down.add_argument("revision")
    for name in ("current", "history", "check", "backup", "stats", "optimize"):
        db_cmds.add_parser(name)
    ex_cmds = groups.add_parser("exotel", help="Exotel integration helpers").add_subparsers(dest="cmd", required=True)
    doc = ex_cmds.add_parser("doctor")
    doc.add_argument("--probe", action="store_true", help="also check that PUBLIC_BASE_URL reaches this backend")
    hooks = ex_cmds.add_parser("webhooks")
    hooks.add_argument("-n", type=int, default=20)
    args = ap.parse_args(argv)
    url = args.url or get_settings().database_url

    if args.group == "db" and args.cmd == "upgrade":
        _print(migrate.upgrade_database(url, args.revision))
    elif args.group == "db" and args.cmd == "downgrade":
        _print(migrate.downgrade_database(url, args.revision))
    elif args.group == "db" and args.cmd == "history":
        for rev in ScriptDirectory.from_config(migrate.alembic_config()).walk_revisions():
            print(f"{rev.revision}  {(rev.doc or '').splitlines()[0]}")
    elif args.group == "db" and args.cmd == "backup":
        print(migrate.backup_database(url, label="manual"))
    else:
        if args.group == "exotel":
            migrate.upgrade_database(url) if ":memory:" not in url else None   # the log table must exist
        engine = make_engine(url)
        try:
            if args.group == "exotel" and args.cmd == "doctor":
                return _doctor(engine, args.probe)
            if args.group == "exotel" and args.cmd == "webhooks":
                with sessionmaker(bind=engine)() as db:
                    rows = log_repo.recent(db, provider="exotel", limit=args.n)
                for r in rows:
                    print(f"{r.received_at:%Y-%m-%d %H:%M:%S} {r.endpoint:8} {'ok ' if r.ok else 'ERR'} {r.result:28} "
                          f"attempt={r.call_attempt_id} {json.dumps(r.payload, ensure_ascii=False)}")
                if not rows:
                    print("no Exotel callbacks received yet")
                return 0
            if args.cmd == "current":
                _print(migrate.status(engine))
            elif args.cmd == "stats":
                _print(dbtools.stats(engine))
            elif args.cmd == "optimize":
                dbtools.optimize(engine)
                print("statistics refreshed")
            elif args.cmd == "check":
                report = dbtools.integrity_report(engine)
                _print(report)
                return 0 if report["ok"] else 1
        finally:
            engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
