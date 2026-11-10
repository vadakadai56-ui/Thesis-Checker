"""Separation rules (BUILD_PROMPT §7): the engine stays plain Python.

* never imports `js` / `pyodide` (browser-only modules),
* never imports pydantic / yaml (build-time only; not shipped to the browser).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "thesischeck"
FORBIDDEN = {"js", "pyodide", "pyodide_js", "pydantic", "yaml"}


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("path", sorted(PACKAGE.rglob("*.py")), ids=lambda p: p.name)
def test_no_forbidden_imports(path):
    assert not (_imported_roots(path) & FORBIDDEN)
