"""
Static checks on the package source.
"""
import ast
from pathlib import Path

import pytest

SOURCES = sorted((Path(__file__).parent.parent / "cookieradar").glob("*.py"))


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_no_bare_or_base_exception_handlers(path):
    # A bare except (or BaseException) also swallows KeyboardInterrupt and
    # asyncio.CancelledError, so Ctrl-C and task cancellation stop working.
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ExceptHandler):
            where = f"{path.name}:{node.lineno}"
            assert node.type is not None, f"bare except at {where}"
            assert "BaseException" not in ast.unparse(node.type), f"BaseException at {where}"
