"""The image installs the Playwright that uv.lock resolves, and no other.

The Dockerfile installed "playwright>=1.40.0", so each build took the newest
release on PyPI. On 2026-11-12 that was 1.65.1, published the day before:
its Node driver needs libatomic.so.1, which python:3.12-slim-trixie does not
ship, `playwright install-deps chromium` stopped with exit code 127, and the
image could not be built, on main as for a release. The build of 2026-11-09,
on the same base image digest, had taken 1.64.1. Neither was the 1.63.0 that
uv.lock resolves, and 1.65.1 was thirteen days short of the age the Radar wait
for before taking a release (tests/test_dependabot_config.py).

Pinning the image to the locked version makes what ships the version the lock
records, which Dependabot only moves 14 days after a release; a lock update
that leaves the Dockerfile behind fails here, naming both.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"
LOCK = ROOT / "uv.lock"


def locked_version(name: str) -> str:
    lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    versions = {p["version"] for p in lock["package"] if p["name"] == name}
    assert len(versions) == 1, f"uv.lock resolves {name} to {sorted(versions) or 'nothing'}"
    return versions.pop()


def dockerfile_playwright_specs() -> list[str]:
    """The requirement strings the Dockerfile hands to pip for playwright."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    return re.findall(r"""pip install[^\n]*?["']?(playwright[^"'\s]*)""", text)


def test_the_dockerfile_installs_playwright_once():
    specs = dockerfile_playwright_specs()
    assert len(specs) == 1, f"the Dockerfile installs playwright as {specs}"


def test_the_image_installs_the_playwright_uv_lock_resolves():
    (spec,) = dockerfile_playwright_specs()
    expected = f"playwright=={locked_version('playwright')}"
    assert spec == expected, f"the Dockerfile installs {spec!r}, uv.lock resolves {expected!r}"


def test_the_nis2_document_names_the_one_dependency_the_image_pins():
    """docs/nis2-compliance.md tells a customer that the image resolves its
    dependencies at build time and does not read uv.lock. Both stay true of
    everything but Playwright, so the document has to name the exception and
    the test that keeps it in step with the lock."""
    doc = " ".join((ROOT / "docs" / "nis2-compliance.md").read_text(encoding="utf-8").split())
    assert "tranne Playwright" in doc
    assert "tests/test_docker_playwright.py" in doc
