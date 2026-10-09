# Migrations

Alembic, SQLite. The app upgrades a file database to the latest revision every time it starts (and writes a backup
to `<data dir>/backups/` first if anything has to change). Revisions: `0001` baseline (the schema before migrations existed), `0002`
constraints, foreign-key rules, defaults and indexes.

## Day to day
```
python -m member2.backend.app.cli db current       # where is this database, and what is the code's head
python -m member2.backend.app.cli db upgrade       # migrate (automatic at app start; backup first)
python -m member2.backend.app.cli db downgrade 0001
python -m member2.backend.app.cli db check         # integrity + consistency rules
python -m member2.backend.app.cli db backup
alembic -c member2/backend/alembic.ini history     # the standard Alembic CLI works too
```

## Changing the schema
1. Edit the models (`app/models/*.py`).
2. Freeze the new schema: `python -m member2.backend.migrations.dump_schema models > member2/backend/migrations/snapshots/v3.json`
3. Add `versions/0003_<what>.py` (`down_revision = "0002"`). For anything SQLite cannot `ALTER` (constraints, foreign keys, defaults),
   call `rebuild.rebuild(op.get_bind(), rebuild.load("v3"), copy_from={...})`, which rebuilds each table from the snapshot and copies the rows.
   For a plain new column or index use `op.add_column` / `op.create_index`. Write the matching `downgrade` (rebuild from `v2`).
4. Run `pytest member2`. `test_migrations.py` fails until the models, the snapshot and the migrations agree
   (`test_head_schema_is_exactly_what_the_models_declare`), and it upgrades a legacy database with data to prove nothing is lost.

## Rules
* Never edit a revision that has been applied to a real database; add a new one.
* A migration that tightens a rule must stop with a clear message if existing rows break it (the rebuild helper does this and rolls
  everything back), not delete or rewrite rows silently.
* Migrations run with foreign keys OFF and `legacy_alter_table` ON inside a single transaction, and end with `PRAGMA foreign_key_check`.
* Tests build in-memory databases straight from the models for speed; the drift test proves that is equivalent to the migrations.

## Files
* `versions/` revisions. `snapshots/legacy.json` is the frozen baseline schema, `snapshots/v2.json` the schema at revision 0002.
* `rebuild.py` the table-rebuild helper. `dump_schema.py` dumps or compares schemas. `env.py` Alembic environment.
