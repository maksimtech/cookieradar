"""The image leaves pip behind once it has installed cookieradar.

pip installs Playwright and cookieradar while the image is built; the image it
leaves runs `cookieradar` and nothing else, and no workflow, script or document
starts pip inside it (checked on 2026-11-13).

On 2026-11-13, on the move to python:3.14-slim-trixie, Trivy reported five high
findings against packages pip carries inside itself, in pip/_vendor: msgpack
1.1.2 (CVE-2026-114613, GHSA-6v7p-g79w-8964), urllib3 2.7.0 (CVE-2026-97687,
CVE-2026-97689) and setuptools 70.3.0 (CVE-2025-47273). The 3.12 image had
shipped pip 25.0.1, whose vendored packages Trivy did not report; 3.14 ships pip
26.2.2, and pip 26.3 still vendors setuptools 70.3.0. Removing pip closes the
five rather than recording them, and the next pip with the next vendored package
too.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"

UNINSTALL = re.compile(r"\bpip (-\S+ )*uninstall (-\S+ )*pip\b")


def run_instructions() -> list[str]:
    """Each RUN instruction, continuation lines joined, comments dropped."""
    lines = [line for line in DOCKERFILE.read_text(encoding="utf-8").splitlines()
             if not line.lstrip().startswith("#")]
    joined = re.sub(r"\\\n\s*", " ", "\n".join(lines))
    return [line.strip()[4:].strip() for line in joined.splitlines() if line.strip().startswith("RUN ")]


def test_pip_uninstalls_itself_without_asking():
    removals = [run for run in run_instructions() if UNINSTALL.search(run)]
    assert removals, "nothing in the Dockerfile uninstalls pip"
    assert all(re.search(r"(^|\s)(-y|--yes)(\s|$)", run) for run in removals), removals


def test_pip_goes_in_the_layer_that_installs_cookieradar():
    """In a later layer pip would still sit in the one below, and the image
    would carry it twice over."""
    runs = run_instructions()
    install = next(run for run in runs if "pip install" in run and "/app/src" in run)
    assert UNINSTALL.search(install), "pip is not removed where cookieradar is installed"
    assert install.index("/app/src") < UNINSTALL.search(install).start()


def test_nothing_runs_pip_after_it_is_gone():
    runs = run_instructions()
    last = max(i for i, run in enumerate(runs) if UNINSTALL.search(run))
    for run in runs[last + 1:]:
        assert not re.search(r"\bpip\b", run), run
