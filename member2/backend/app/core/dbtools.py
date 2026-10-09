"""Read-only database diagnostics: integrity, consistency between related rows, size and index facts."""
from sqlalchemy import text

# Rules the schema cannot express as a single CHECK. Each query returns the rows that BREAK the rule.
CONSISTENCY_CHECKS: list[tuple[str, str, str]] = [
    ("attempt_matches_participant_campaign",
     "A call attempt belongs to the same campaign as its participant",
     "SELECT a.id FROM call_attempts a JOIN recipients r ON r.id = a.recipient_id WHERE a.campaign_id != r.campaign_id"),
    ("response_matches_attempt",
     "A response points at the same participant and campaign as its call attempt",
     "SELECT i.id FROM intent_results i JOIN call_attempts a ON a.id = i.call_attempt_id "
     "WHERE i.recipient_id != a.recipient_id OR i.campaign_id != a.campaign_id"),
    ("follow_up_matches_participant_campaign",
     "A follow-up belongs to the same campaign as its participant",
     "SELECT f.id FROM follow_ups f JOIN recipients r ON r.id = f.recipient_id WHERE f.campaign_id != r.campaign_id"),
    ("opt_out_wins",
     "Everyone opted out has outcome opted_out and consent revoked",
     "SELECT id FROM recipients WHERE opted_out = 1 AND (outcome != 'opted_out' OR consent_status != 'revoked')"),
    ("converted_lead_has_participant",
     "A converted lead points at an existing participant",
     "SELECT l.id FROM leads l LEFT JOIN recipients r ON r.id = l.recipient_id WHERE l.status = 'converted' AND r.id IS NULL"),
    ("sample_data_not_mixed",
     "A participant is flagged sample exactly when its campaign is",
     "SELECT r.id FROM recipients r JOIN campaigns c ON c.id = r.campaign_id WHERE r.is_demo != c.is_demo"),
]


def integrity_report(engine) -> dict:
    """SQLite's own checks plus our consistency rules. `ok` is true only when everything is clean."""
    with engine.connect() as c:
        integrity = [r[0] for r in c.exec_driver_sql("PRAGMA integrity_check")]
        fk = [{"table": r[0], "row": r[1], "references": r[2]} for r in c.exec_driver_sql("PRAGMA foreign_key_check")]
        rules = []
        for key, label, sql in CONSISTENCY_CHECKS:
            ids = [r[0] for r in c.execute(text(sql))]
            rules.append({"key": key, "label": label, "violations": len(ids), "sample_ids": ids[:5]})
    ok = integrity == ["ok"] and not fk and all(r["violations"] == 0 for r in rules)
    return {"ok": ok, "integrity_check": integrity, "foreign_key_violations": fk, "rules": rules}


def stats(engine) -> dict:
    with engine.connect() as c:
        tables = [r[0] for r in c.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table' "
                                                  "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        rows = {t: c.exec_driver_sql(f'SELECT COUNT(*) FROM "{t}"').scalar() for t in tables}
        indexes = c.exec_driver_sql("SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND sql IS NOT NULL").scalar()
        page_size = c.exec_driver_sql("PRAGMA page_size").scalar()
        pages = c.exec_driver_sql("PRAGMA page_count").scalar()
        free = c.exec_driver_sql("PRAGMA freelist_count").scalar()
        return {"rows": rows, "indexes": indexes, "size_bytes": page_size * pages, "free_bytes": page_size * free,
                "journal_mode": c.exec_driver_sql("PRAGMA journal_mode").scalar(),
                "foreign_keys": bool(c.exec_driver_sql("PRAGMA foreign_keys").scalar())}


def query_plan(engine, sql: str, params: dict | None = None) -> list[str]:
    """The SQLite plan lines for a query (used by tests to prove an index is used)."""
    with engine.connect() as c:
        return [r[3] for r in c.execute(text("EXPLAIN QUERY PLAN " + sql), params or {})]


def optimize(engine) -> None:
    """Refresh planner statistics and reclaim nothing destructive: ANALYZE + PRAGMA optimize."""
    with engine.connect() as c:
        c.exec_driver_sql("ANALYZE")
        c.exec_driver_sql("PRAGMA optimize")
        c.commit()
