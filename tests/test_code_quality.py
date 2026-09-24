"""
Static checks on the package source.
"""
import ast
import re
import tomllib
from pathlib import Path

import pytest

SOURCES = sorted((Path(__file__).parent.parent / "cookieradar").glob("*.py"))


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_no_bare_or_base_exception_handlers(path):
    # A bare except (or BaseException) also swallows KeyboardInterrupt and
    # asyncio.CancelledError, so Ctrl-C and task cancellation stop working.
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ExceptHandler):
            where = f"{path.name}:{node.lineno}"
            assert node.type is not None, f"bare except at {where}"
            assert "BaseException" not in ast.unparse(node.type), f"BaseException at {where}"


# ─── M2: no empty placeholder modules ───────────────────────────────────────

@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_no_empty_modules(path):
    assert path.read_text(encoding="utf-8").strip(), f"{path.name} is empty"


# ─── M5: every runtime dependency is actually used ──────────────────────────

def _runtime_dependencies():
    pyproject = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text(encoding="utf-8"))
    return [re.split(r"[<>=!~\[ ;]", dep, maxsplit=1)[0] for dep in pyproject["project"]["dependencies"]]


def _imported_top_level_modules():
    modules = set()
    for path in SOURCES:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                modules.add(node.module.split(".")[0])
    return modules


@pytest.mark.parametrize("dependency", _runtime_dependencies())
def test_runtime_dependency_is_imported(dependency):
    assert dependency.replace("-", "_") in _imported_top_level_modules(), f"{dependency} is never imported"
