"""
Tests for CI helper scripts in .github/scripts/.
"""
import os
import tomllib
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


# ─── W3/W4: no expressions interpolated into shell, no GPG signing ──────────

ALL_WORKFLOWS = sorted(p.name for p in WORKFLOWS.glob("*.yml"))


def _all_steps(wf):
    for job in wf["jobs"].values():
        yield from job.get("steps", [])


@pytest.mark.parametrize("name", ALL_WORKFLOWS)
def test_no_expressions_interpolated_in_run_scripts(name):
    # ${{ }} inside run: is pasted into the script before the shell parses it:
    # a secret or input with quotes/$()/backticks breaks or injects commands.
    # Values must reach scripts through env: instead.
    for step in _all_steps(_workflow(name)):
        assert "${{" not in step.get("run", ""), f"{name}: {step.get('name', step)}"


def test_publish_does_not_sign_with_gpg():
    # PyPI dropped PGP signatures in 2023: signing only exposed the private key
    text = (WORKFLOWS / "publish.yml").read_text()

    assert "gpg" not in text.lower()
    assert "GPG_" not in text


# ─── W9: security scans must not hide crashes or upload missing SARIF ───────

@pytest.mark.parametrize("name", ALL_WORKFLOWS)
def test_no_errors_swallowed_with_or_true(name):
    for step in _all_steps(_workflow(name)):
        assert "|| true" not in step.get("run", ""), f"{name}: {step.get('name')}"


def _sarif_uploads():
    for name in ALL_WORKFLOWS:
        for step in _all_steps(_workflow(name)):
            if "codeql-action/upload-sarif" in step.get("uses", ""):
                yield name, step


def test_sarif_uploads_exist():
    assert {name for name, _ in _sarif_uploads()} == {"bandit.yml", "docker-scout.yml", "trivy.yml"}


@pytest.mark.parametrize("name,step", list(_sarif_uploads()), ids=lambda v: v if isinstance(v, str) else "")
def test_sarif_upload_only_when_file_exists(name, step):
    sarif = step["with"]["sarif_file"]
    condition = step.get("if", "")

    assert f"hashFiles('{sarif}')" in condition, f"{name}: if: {condition!r}"
    assert "always()" in condition  # still upload findings when the scan step fails


def test_bandit_reports_findings_without_failing_but_fails_on_crash():
    step = next(s for s in _all_steps(_workflow("bandit.yml")) if "bandit -r" in s.get("run", ""))

    assert "--exit-zero" in step["run"]


# ─── W10: actions are never referenced by a moving branch ───────────────────

def _action_refs():
    for name in ALL_WORKFLOWS:
        for job in _workflow(name)["jobs"].values():
            refs = [job["uses"]] if "uses" in job else []
            refs += [s["uses"] for s in job.get("steps", []) if "uses" in s]
            for ref in refs:
                if not ref.startswith("./"):
                    yield name, ref


@pytest.mark.parametrize("name,ref", list(_action_refs()))
def test_actions_not_pinned_to_default_branch(name, ref):
    _, _, version = ref.partition("@")
    assert version not in {"master", "main", "HEAD", ""}, f"{name}: {ref}"


def test_trivy_action_pinned_to_commit_sha():
    # trivy-action tags were force-pushed to malware in March 2026
    # (GHSA-69fq-xp46-6x23): pin the commit, keep the tag as a comment
    # so Dependabot can still propose updates.
    line = next(l for l in (WORKFLOWS / "trivy.yml").read_text().splitlines() if "trivy-action@" in l)
    ref = line.split("@", 1)[1]
    sha, _, comment = ref.partition("#")

    assert len(sha.strip()) == 40 and all(c in "0123456789abcdef" for c in sha.strip()), line
    assert comment.strip().startswith("v"), line


# ─── M10: consistent CI — versions, Python matrix, Sonar version ────────────

def test_each_action_uses_one_version_everywhere():
    versions = {}
    for name, ref in _action_refs():
        action, _, version = ref.partition("@")
        versions.setdefault(action, set()).add(version)
    mixed = {action: v for action, v in versions.items() if len(v) > 1}
    assert not mixed, mixed


def _classifier_pythons():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    prefix = "Programming Language :: Python :: 3."
    return pyproject, sorted(
        (c.rsplit(":: ", 1)[1] for c in pyproject["project"]["classifiers"] if c.startswith(prefix)),
        key=lambda v: tuple(map(int, v.split("."))),
    )


def test_tests_run_on_every_supported_python():
    pyproject, classifiers = _classifier_pythons()
    matrix = _workflow("tests.yml")["jobs"]["test"]["strategy"]["matrix"]["python-version"]
    minimum = pyproject["project"]["requires-python"].removeprefix(">=")

    assert [str(v) for v in matrix] == classifiers
    assert classifiers[0] == minimum


def test_sonar_version_comes_from_the_package():
    properties = (ROOT / "sonar-project.properties").read_text()
    step = next(s for s in _all_steps(_workflow("sonarcloud.yml")) if "sonarqube-scan-action" in s.get("uses", ""))

    assert "sonar.projectVersion" not in properties  # was stale (2026.09.1)
    assert "-Dsonar.projectVersion=" in step["with"]["args"]


# ─── M11: Dockerfile hygiene ────────────────────────────────────────────────

DOCKERFILE = (ROOT / "Dockerfile").read_text()


def test_dockerfile_uses_standard_oci_license_label():
    assert 'org.opencontainers.image.licenses="MIT"' in DOCKERFILE
    assert "org.opencontainers.image.license=" not in DOCKERFILE


def test_dockerfile_has_no_unused_packages_or_volumes():
    assert "gnupg" not in DOCKERFILE
    assert "VOLUME" not in DOCKERFILE  # nothing in cookieradar reads ~/.cookieradar
    assert ".cookieradar" not in DOCKERFILE
