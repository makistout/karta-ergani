from __future__ import annotations

import ast
from pathlib import Path

from scripts.run_scheduled_sync import compile_app_sources

ROOT = Path(__file__).resolve().parent.parent


def test_app_py_sources_compile():
    errors = compile_app_sources(ROOT / "app")
    assert errors == [], "\n".join(errors)


def test_app_init_does_not_import_routes_at_module_level():
    tree = ast.parse((ROOT / "app" / "__init__.py").read_text(encoding="utf-8"))
    top_level = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("app.routes"):
            top_level.append(node.module)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app.routes"):
                    top_level.append(alias.name)
    assert top_level == []


def test_importing_scheduled_sync_does_not_load_apologistic():
    import sys

    sys.modules.pop("app.apologistic", None)
    sys.modules.pop("app.scheduled_sync", None)
    sys.modules.pop("app.routes_employees", None)
    from app import scheduled_sync as scheduled

    assert "app.apologistic" not in sys.modules
    assert scheduled.run_scheduled_sync
