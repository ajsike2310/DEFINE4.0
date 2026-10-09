"""The data-model document must describe the database that actually exists."""
import re
from pathlib import Path

from member2.backend.migrations.dump_schema import models_schema

DOC = Path(__file__).resolve().parents[3] / "docs" / "DATA_MODEL.md"


def _documented_index_names() -> set[str]:
    text = DOC.read_text(encoding="utf-8")
    table = text.split("## Indexes", 1)[1].split("Measured on", 1)[0]
    return set(re.findall(r"`((?:ix|uq)_[a-z0-9_]+)`", table))


def _real_index_names() -> set[str]:
    schema = models_schema()
    names = {o["name"] for o in schema if o["type"] == "index"}
    for o in schema:                                           # named UNIQUE constraints inside CREATE TABLE
        if o["type"] == "table":
            names |= set(re.findall(r"CONSTRAINT (uq_[a-z0-9_]+) UNIQUE", o["sql"]))
    return names


def test_every_index_and_unique_constraint_is_documented_and_nothing_extra():
    documented, real = _documented_index_names(), _real_index_names()
    assert real - documented == set(), f"in the database but not in docs/DATA_MODEL.md: {sorted(real - documented)}"
    assert documented - real == set(), f"documented but not in the database: {sorted(documented - real)}"


def test_every_table_is_documented():
    text = DOC.read_text(encoding="utf-8")
    tables = {o["name"] for o in models_schema() if o["type"] == "table"}
    assert {t for t in tables if f"`{t}`" not in text} == set()
