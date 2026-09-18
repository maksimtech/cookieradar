"""
Tests for CI helper scripts in .github/scripts/.
"""
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
WAIT_FOR_PYPI = ROOT / ".github" / "scripts" / "wait_for_pypi.sh"


@pytest.fixture
def fake_pip(tmp_path):
    """`pip` on PATH that fails until the attempt number reaches SUCCEED_AT."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    pip = bin_dir / "pip"
    pip.write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> "{log}"\n'
        f'n=$(wc -l < "{log}")\n'
        '[ "$n" -ge "$SUCCEED_AT" ]\n'
    )
    pip.chmod(0o755)

    def run(succeed_at, *args):
        env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "SUCCEED_AT": str(succeed_at)}
        proc = subprocess.run(
            ["bash", str(WAIT_FOR_PYPI), *args], env=env, capture_output=True, text=True, timeout=30
        )
        calls = log.read_text().splitlines() if log.exists() else []
        return proc, calls

    return run


def test_wait_for_pypi_succeeds_immediately(fake_pip):
    proc, calls = fake_pip(1, "cookieradar", "2026.09.5", "5", "0")

    assert proc.returncode == 0, proc.stderr
    assert len(calls) == 1
    assert "download" in calls[0]
    assert "--no-deps" in calls[0]
    assert "cookieradar==2026.09.5" in calls[0]


def test_wait_for_pypi_retries_until_available(fake_pip):
    proc, calls = fake_pip(3, "cookieradar", "2026.09.5", "5", "0")

    assert proc.returncode == 0, proc.stderr
    assert len(calls) == 3


def test_wait_for_pypi_fails_after_max_attempts(fake_pip):
    proc, calls = fake_pip(99, "cookieradar", "2026.09.5", "4", "0")

    assert proc.returncode != 0
    assert len(calls) == 4
    assert "cookieradar==2026.09.5" in proc.stderr


def test_wait_for_pypi_requires_arguments(fake_pip):
    proc, calls = fake_pip(1)

    assert proc.returncode != 0
    assert calls == []
    assert "Usage" in proc.stderr


# ─── W1/W2: workflow structure ──────────────────────────────────────────────

yaml = pytest.importorskip("yaml")
WORKFLOWS = ROOT / ".github" / "workflows"


def _workflow(name):
    wf = yaml.safe_load((WORKFLOWS / name).read_text())
    wf["on"] = wf.pop(True, wf.get("on"))  # PyYAML parses the `on` key as True
    return wf


def _steps_text(job):
    return "\n".join(str(step) for step in job["steps"])


def test_docker_workflow_is_not_triggered_by_tags_directly():
    triggers = _workflow("docker.yml")["on"]

    assert "push" not in triggers  # would race with the PyPI publish
    assert triggers["workflow_call"]["inputs"]["version"]["required"] is True
    assert "workflow_dispatch" in triggers  # manual rebuild of a published version


def test_publish_runs_docker_after_pypi_upload():
    jobs = _workflow("publish.yml")["jobs"]
    docker = jobs["docker"]

    assert docker["needs"] == "build-and-publish"
    assert docker["uses"] == "./.github/workflows/docker.yml"
    assert docker["secrets"] == "inherit"
    assert "needs.build-and-publish.outputs.version" in docker["with"]["version"]
    assert "version" in jobs["build-and-publish"]["outputs"]


def test_docker_release_waits_for_pypi_before_building():
    steps = _workflow("docker.yml")["jobs"]["docker"]["steps"]
    names = [s.get("name", "") for s in steps]
    wait = next(i for i, s in enumerate(steps) if "wait_for_pypi.sh" in s.get("run", ""))
    first_build = next(i for i, s in enumerate(steps) if "build-push-action" in s.get("uses", ""))

    assert wait < first_build, names


def test_docker_release_installs_from_pypi():
    job = _workflow("docker.yml")["jobs"]["docker"]

    assert "COOKIERADAR_SOURCE=pypi" in _steps_text(job)


def test_ci_builds_docker_image_from_local_source():
    job = _workflow("tests.yml")["jobs"]["docker"]
    text = _steps_text(job)

    assert "COOKIERADAR_SOURCE=local" in text
    assert "tests/docker/smoke.py" in text
    assert "push" not in [k for s in job["steps"] for k in s.get("with", {}) if s.get("with", {}).get(k) is True]
