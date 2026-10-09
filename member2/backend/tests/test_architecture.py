"""Layering is a rule, not a habit: each layer may only import from the layers below it.

    api/routers  ->  services  ->  repositories  ->  models  ->  core
                         \\-> schemas (validation shapes; they may only use the shared enums)
"""
import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"

# layer -> the layers it is allowed to import from (itself is always allowed)
ALLOWED = {
    "core": set(),
    "models": {"core"},
    "repositories": {"core", "models"},
    "schemas": {"models"},                               # only models.enums, checked below
    "services": {"core", "models", "repositories", "schemas"},
    "api": {"core", "models", "repositories", "schemas", "services"},
}
# Packages owned by other members: only the layers that talk to calls and analytics may use them.
OUTSIDE_OK = {"services", "api"}
# Sample-data tooling writes and wipes directly; it is not part of the request path.
QUERY_CODE_EXEMPT = {"services/demo.py"}


def _py_files():
    return [p for p in APP.rglob("*.py") if "__pycache__" not in p.parts]


def _layer(path: Path) -> str | None:
    rel = path.relative_to(APP)
    return rel.parts[0] if len(rel.parts) > 1 and rel.parts[0] in ALLOWED else None


def _targets(path: Path):
    """(layer-or-package, dotted target) for every import in a file, resolved to the app tree."""
    pkg = list(path.relative_to(APP).parts[:-1])              # package the file lives in, below app/
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name.split(".")[0], a.name
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                yield (node.module or "").split(".")[0], node.module or ""
                continue
            up = node.level - 1
            if up > len(pkg):                                  # climbs out of the app (to backend/migrations)
                yield "outside-app", node.module or ""
                continue
            base = pkg[:len(pkg) - up]
            parts = base + (node.module.split(".") if node.module else [])
            for a in (node.names if not node.module else [None]):
                full = parts + ([a.name] if a is not None else [])
                yield (full[0] if full else "app"), ".".join(full)


@pytest.mark.parametrize("path", _py_files(), ids=lambda p: p.relative_to(APP).as_posix())
def test_each_module_imports_only_from_layers_below(path):
    layer = _layer(path)
    if layer is None:
        return
    bad = []
    for top, dotted in _targets(path):
        if top in ALLOWED and top != layer and top not in ALLOWED[layer]:
            bad.append(dotted)
        if top in ("member3", "member4") and layer not in OUTSIDE_OK:
            bad.append(dotted)
        if layer == "schemas" and top == "models" and not dotted.startswith("models.enums"):
            bad.append(dotted)
    assert bad == [], f"{path.relative_to(APP).as_posix()} reaches up the layers: {bad}"


def _calls(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            yield node.func.attr, node.func.value
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            yield node.func.id, None


QUERY_METHODS = {"scalar", "scalars", "execute", "query", "get"}


def test_routers_contain_no_query_code():
    offenders = []
    for path in (APP / "api" / "routers").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("sqlalchemy") \
                    and any(a.name not in ("Session",) for a in node.names):
                offenders.append(f"{path.name}: imports {[a.name for a in node.names]} from {node.module}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in QUERY_METHODS \
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == "db":
                offenders.append(f"{path.name}:{node.lineno}: db.{node.func.attr}(...)")
    assert offenders == []


def test_services_build_no_queries_except_sample_data_tooling():
    offenders = []
    for path in (APP / "services").glob("*.py"):
        if f"services/{path.name}" in QUERY_CODE_EXEMPT:
            continue
        for name, owner in _calls(path):
            if name == "select" and owner is None:
                offenders.append(f"{path.name}: select(...)")
            if name in {"scalar", "scalars", "execute", "query"} and isinstance(owner, ast.Name) and owner.id == "db":
                offenders.append(f"{path.name}: db.{name}(...)")
    assert offenders == [], "queries belong in repositories/"


def test_repositories_never_commit():
    offenders = [p.name for p in (APP / "repositories").glob("*.py") if ".commit(" in p.read_text(encoding="utf-8")]
    assert offenders == []


def test_logging_is_configured_in_one_place_only():
    offenders = [p.relative_to(APP).as_posix() for p in _py_files()
                 if "basicConfig(" in p.read_text(encoding="utf-8") and p.name != "logs.py"]
    assert offenders == []


def test_no_module_prints(capsys):
    printers = [p.relative_to(APP).as_posix() for p in _py_files()
                if p.name != "cli.py" and any(n == "print" for n, o in _calls(p) if o is None)]
    assert printers == []
