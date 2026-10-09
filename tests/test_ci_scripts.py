"""
Tests for CI helper scripts in .github/scripts/.
"""
import os
import shutil
import subprocess
import time
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
WAIT_FOR_PYPI = ROOT / ".github" / "scripts" / "wait_for_pypi.sh"


def _bash() -> str:
    """The bash the script is written for: the one on PATH, and Git's on Windows.

    On Windows `bash` is also WSL's launcher in System32. CreateProcess looks
    there before PATH, and so does `shutil.which` from a shell that lists
    System32 first, and WSL drops the backslashes of the Windows path it is
    handed: "No such file or directory", exit 127, and every case below failed
    without the script running at all. Git for Windows ships a bash next to git.
    """
    found = shutil.which("bash")
    if os.name != "nt":
        return found or "bash"
    system32 = Path(os.environ.get("SYSTEMROOT", "C:/Windows")) / "System32"
    if found and Path(found).parent != system32:
        return found
    git = shutil.which("git")
    bundled = Path(git).resolve().parent.parent / "bin" / "bash.exe" if git else None
    return str(bundled) if bundled and bundled.is_file() else (found or "bash")


BASH = _bash()


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
, encoding="utf-8")
    pip.chmod(0o755)

    def run(succeed_at, *args):
        env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "SUCCEED_AT": str(succeed_at)}
        proc = subprocess.run(
            [BASH, str(WAIT_FOR_PYPI), *args], env=env, capture_output=True, text=True, timeout=30
, encoding="utf-8", errors="replace")
        calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        return proc, calls

    def start(succeed_at, *args):
        """The same script, left running, for the one case that is about *not* finishing."""
        env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
               "SUCCEED_AT": str(succeed_at)}
        return subprocess.Popen(
            [BASH, str(WAIT_FOR_PYPI), *args],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    run.start = start
    return run


def test_wait_for_pypi_succeeds_immediately(fake_pip):
    proc, calls = fake_pip(1, "cookieradar", "2026.09.5", "5", "0", "0")

    assert proc.returncode == 0, proc.stderr
    assert len(calls) == 1
    assert "download" in calls[0]
    assert "--no-deps" in calls[0]
    assert "cookieradar==2026.09.5" in calls[0]


def test_wait_for_pypi_retries_until_available(fake_pip):
    proc, calls = fake_pip(3, "cookieradar", "2026.09.5", "5", "0", "0")

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


def test_wait_for_pypi_allows_a_grace_once_the_version_is_there(fake_pip):
    """The margin is a wait that happens, not a line in the log.

    apkradar 2026.42 built fifteen seconds after this script reported the version
    available — 16:31:21 against 16:31:36 — because the runner and the buildx
    container resolve different edges of the index. A grace that is printed and not
    taken would leave that exactly as it was while looking fixed.
    """
    start = time.monotonic()
    proc, calls = fake_pip(1, "cookieradar", "2026.09.5", "5", "0", "2")
    elapsed = time.monotonic() - start

    assert proc.returncode == 0, proc.stderr
    assert elapsed >= 2, f"it reported a grace it did not take ({elapsed:.1f}s)"
    assert "agree with itself" in proc.stdout, "it waited without saying why"


def test_wait_for_pypi_with_no_grace_waits_for_nothing(fake_pip):
    """Zero has to mean zero, including in the log: a release that did not need the
    margin should not read as though it used one.

    Timed as a difference rather than against the clock. An absolute upper bound here
    read `< 2` and saw 21.4 seconds the first time five suites ran on one machine at
    once — measuring what the machine was doing rather than what the script was doing.
    The gap between a run that is given a grace and one that is not is the grace,
    whatever else is happening.
    """
    start = time.monotonic()
    proc, _ = fake_pip(1, "cookieradar", "2026.09.5", "5", "0", "0")
    without = time.monotonic() - start

    start = time.monotonic()
    waited, _ = fake_pip(1, "cookieradar", "2026.09.5", "5", "0", "3")
    with_grace = time.monotonic() - start

    assert proc.returncode == 0, proc.stderr
    assert waited.returncode == 0, waited.stderr
    assert "agree with itself" not in proc.stdout
    assert with_grace - without >= 2, (
        f"no grace took {without:.1f}s and a three second grace took "
        f"{with_grace:.1f}s, so the grace was not waited for"
    )


def test_wait_for_pypi_default_grace_is_a_wait_and_not_zero(fake_pip):
    """Measured, without the suite paying the whole default for it.

    Started with no grace argument against an index that answers on the first ask,
    the script must still be running a few seconds later. Remove the default, or set
    it to zero, and it exits immediately and this fails — which is the point: every
    other case here passes a grace explicitly, so without this one the default could
    be deleted and nothing would notice.
    """
    proc = fake_pip.start(1, "cookieradar", "2026.09.5", "5", "0")
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            proc.wait(timeout=3)
    finally:
        proc.kill()
        proc.wait(timeout=10)


# ─── W1/W2: workflow structure ──────────────────────────────────────────────

yaml = pytest.importorskip("yaml")
WORKFLOWS = ROOT / ".github" / "workflows"


def _workflow(name):
    wf = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
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


def test_the_release_image_is_built_from_the_tag_and_not_from_the_index():
    """What closes the race instead of narrowing it.

    This workflow installed `cookieradar==<the new version>` from PyPI while
    publish.yml was still uploading it, and waited on the index first to make that
    work. The wait is not wrong and not enough: it runs on the runner, while the
    multi-platform build resolves the index again, per platform, from whichever edge
    answers. apkradar lost that race on 2026-10-03 fifteen seconds *after* its poll
    had succeeded. Nothing that waits can close it; not asking does.

    `local` is also the branch tests.yml already builds on every run, with the smoke
    test behind it, so this moves the release onto the better exercised of the two
    paths rather than onto an untried one.
    """
    job = _workflow("docker.yml")["jobs"]["docker"]
    text = _steps_text(job)

    assert "COOKIERADAR_SOURCE=local" in text
    assert "COOKIERADAR_SOURCE=pypi" not in text
    assert "wait_for_pypi.sh" not in text, (
        "nothing here needs the index now, so nothing here should wait for it"
    )


def test_a_rebuild_stands_on_the_tag_it_was_asked_for():
    """Dispatched with the version of a published release, this has to check that
    release out.

    While the image installed that version from the index, where the job stood in the
    tree did not matter. Built from the checkout it decides what ships — and the smoke
    test, which compares the version in the image against the tag, would turn a
    rebuild from the default branch into a version mismatch rather than into a
    publish. Either way the feature does not work; this makes it work.
    """
    steps = _workflow("docker.yml")["jobs"]["docker"]["steps"]
    checkout = next(s for s in steps if "actions/checkout" in s.get("uses", ""))

    assert "inputs.version" in checkout.get("with", {}).get("ref", "")


def test_the_published_file_is_still_checked_where_it_was_published():
    """Taking the image off the index loses the one thing that arrangement proved by
    accident: that what lands on PyPI can be installed. publish.yml says it on
    purpose now, after the upload, where a slow index delays a check instead of
    failing a build that had nothing to do with it."""
    steps = _workflow("publish.yml")["jobs"]["build-and-publish"]["steps"]
    names = [s.get("name", s.get("uses", "")) for s in steps]

    upload = next(i for i, s in enumerate(steps) if "gh-action-pypi-publish" in s.get("uses", ""))
    wait = next(i for i, s in enumerate(steps) if "wait_for_pypi.sh" in s.get("run", ""))
    verify = next(i for i, s in enumerate(steps) if "--version" in s.get("run", ""))

    assert upload < wait < verify, names
    assert "cookieradar==" in steps[verify]["run"], "it has to be the version just uploaded"


def test_the_check_asks_for_no_margin_because_there_is_one_resolver():
    """The grace exists because the runner and the buildx container ask different
    edges of the index. Here there is only the runner, which has just had
    `pip download` answer, so a margin would buy nothing — and a wait that buys
    nothing is what this script was rewritten to stop doing."""
    steps = _workflow("publish.yml")["jobs"]["build-and-publish"]["steps"]
    wait = next(s for s in steps if "wait_for_pypi.sh" in s.get("run", ""))
    arguments = wait["run"].split("wait_for_pypi.sh", 1)[1].split()

    assert arguments[-1] == "0", wait["run"]


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
    text = (WORKFLOWS / "publish.yml").read_text(encoding="utf-8")

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
    assert {name for name, _ in _sarif_uploads()} == {
        "bandit.yml", "docker-scout.yml", "snyk.yml", "trivy.yml",
    }


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
    rows = (WORKFLOWS / "trivy.yml").read_text(encoding="utf-8").splitlines()
    line = next(row for row in rows if "trivy-action@" in row)
    ref = line.split("@", 1)[1]
    sha, _, comment = ref.partition("#")

    assert len(sha.strip()) == 40 and all(c in "0123456789abcdef" for c in sha.strip()), line
    assert comment.strip().startswith("v"), line


# ─── M10: consistent CI — versions, Python matrix, Sonar version ────────────

def test_each_action_uses_one_version_everywhere():
    versions = {}
    for _name, ref in _action_refs():
        action, _, version = ref.partition("@")
        versions.setdefault(action, set()).add(version)
    mixed = {action: v for action, v in versions.items() if len(v) > 1}
    assert not mixed, mixed


def _classifier_pythons():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
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


def test_the_next_python_runs_as_an_experimental_row():
    """The release after the last supported one runs too, and may fail.

    3.15.0 final is due 2026-10-09 (PEP 790); `actions/setup-python` resolves
    `3.15-dev` to the newest pre-release today and to the final tomorrow, so the
    suite meets the new interpreter before the classifier promises it. The row is
    an `include`, not a member of `python-version`: that list is the classifiers
    (test above) and the ruleset needs only the "Tests" summary. `continue-on-error`
    taken from the matrix keeps a red experimental row from failing the run —
    and from failing `summary`, which sees the job as succeeded.
    """
    _pyproject, classifiers = _classifier_pythons()
    major, minor = map(int, classifiers[-1].split("."))
    expected = f"{major}.{minor + 1}-dev"

    job = _workflow("tests.yml")["jobs"]["test"]
    matrix = job["strategy"]["matrix"]

    assert matrix["experimental"] == [False]
    assert matrix["include"] == [{"python-version": expected, "experimental": True}]
    assert job["continue-on-error"] == "${{ matrix.experimental }}"


def test_sonar_version_comes_from_the_package():
    properties = (ROOT / "sonar-project.properties").read_text(encoding="utf-8")
    step = next(s for s in _all_steps(_workflow("sonarcloud.yml")) if "sonarqube-scan-action" in s.get("uses", ""))

    assert "sonar.projectVersion" not in properties  # was stale (2026.09.1)
    assert "-Dsonar.projectVersion=" in step["with"]["args"]


# ─── M11: Dockerfile hygiene ────────────────────────────────────────────────

DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_dockerfile_uses_standard_oci_license_label():
    assert 'org.opencontainers.image.licenses="MIT"' in DOCKERFILE
    assert "org.opencontainers.image.license=" not in DOCKERFILE


def test_dockerfile_has_no_unused_packages_or_volumes():
    assert "gnupg" not in DOCKERFILE
    assert "VOLUME" not in DOCKERFILE  # nothing in cookieradar reads ~/.cookieradar
    assert ".cookieradar" not in DOCKERFILE


# ─── Branch protection: the ruleset requires a check named exactly "Tests" ──

def test_tests_summary_job_for_branch_protection():
    jobs = _workflow("tests.yml")["jobs"]
    summary_key, summary = next((k, j) for k, j in jobs.items() if j.get("name") == "Tests")
    others = set(jobs) - {summary_key}

    # exactly one check called "Tests"; the matrix jobs have their own names
    assert [j.get("name") for j in jobs.values()].count("Tests") == 1
    assert set(summary["needs"]) == others  # every other job, including Docker

    # a skipped required check counts as passed: the summary must always run
    # and fail explicitly when any needed job did not succeed
    assert summary["if"] == "always()"
    step_env = {k: v for s in summary["steps"] for k, v in s.get("env", {}).items()}
    assert any("needs.*.result" in v for v in step_env.values())


def test_matrix_jobs_are_named_by_python_version():
    job = _workflow("tests.yml")["jobs"]["test"]
    assert job["name"] == "Tests (Python ${{ matrix.python-version }})"


def test_the_mutation_run_skips_the_benchmarks() -> None:
    """A benchmark asserts nothing, so it can kill no mutant — and the runner it
    needs is installed by codspeed.yml alone and is deliberately not a project
    dependency, so under mutmut the fixture is missing entirely.

    On 2026-10-03 that killed the Saturday run in the stats phase, before a single
    mutant was tried. mutmut takes no pytest arguments on its command line, so the
    exclusion lives in its configuration — which means asserting on the workflow
    file would not have caught it.
    """
    import pathlib

    config = (pathlib.Path(__file__).resolve().parent.parent
              / "pyproject.toml").read_text(encoding="utf-8")

    assert "[tool.mutmut]" in config, "the mutation configuration moved"
    assert "--ignore=tests/benchmarks" in config.split("[tool.mutmut]", 1)[1]


def test_the_benchmarks_are_skipped_not_errors_without_their_runner():
    """The runner (pytest-codspeed) is installed by codspeed.yml alone, on
    purpose: "the suite must not need a benchmark runner to check correctness"
    (test_declared_imports.py). Yet `pytest`, as the README says to run it,
    ended in three `fixture 'benchmark' not found` errors. Without the runner
    they must be skipped, with the reason; `-p no:codspeed` stands in for the
    missing runner where it is installed."""
    import sys

    done = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/benchmarks", "-q", "-rs",
         "-p", "no:codspeed", "-p", "no:cacheprovider"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )

    assert done.returncode == 0, done.stdout + done.stderr
    assert "3 skipped" in done.stdout, done.stdout
    assert "codspeed" in done.stdout.lower(), "the skip reason must name the runner"


def test_every_test_file_pyproject_points_to_exists():
    """The [tool.mutmut] comment said the arrangement about the benchmark runner
    was written down in `tests/test_benchmark_contract.py`: a file that never
    existed in this repository's history. Whoever looked for it found nothing,
    and the rule seemed written down nowhere."""
    import re

    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    named = set(re.findall(r"tests/[\w/]+\.py", text))

    assert named, "pyproject.toml names no test file any more: the check is empty"
    assert sorted(p for p in named if not (ROOT / p).is_file()) == []


# ─── Line endings: bash reads a carriage return as part of the command ──────

def test_shell_scripts_are_pinned_to_lf_line_endings():
    """Without `.gitattributes` (`*.sh text eol=lf`) a Windows clone with
    core.autocrlf=true got release.sh and wait_for_pypi.sh with CRLF, and bash
    stopped at "set: pipefail\\r: invalid option name".

    Asked of git rather than searched for in the file: what counts is that the
    rule applies to every tracked script, not that the text contains certain
    words."""
    def git(*args):
        try:
            done = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=30)
        except (OSError, subprocess.SubprocessError):
            pytest.skip("git not available")
        if done.returncode != 0:
            pytest.skip(f"git cannot answer here: {done.stderr.strip()}")
        return done.stdout

    scripts = git("ls-files", "*.sh").split()
    assert scripts, "no tracked .sh script: the test would check nothing"
    for line in git("check-attr", "eol", "--", *scripts).splitlines():
        assert line.endswith(": eol: lf"), line


def _build_steps(job):
    """Indexes of the steps that build an image: build-push-action or a bare docker build."""
    return [i for i, step in enumerate(job.get("steps", []))
            if "docker/build-push-action" in step.get("uses", "") or "docker build" in step.get("run", "")]


def test_every_image_build_logs_in_to_docker_hub_first():
    """An anonymous pull of the base image from a GitHub runner shares one rate
    limit with every other anonymous pull from that address. On 2026-10-09 a day
    of builds across the five Radar ended in `429 Too Many Requests` on
    python:3.12-slim-trixie, in this repository's Tests and Snyk jobs, three
    reruns in a row. Logging in first puts the pull under the account's own
    limit. `continue-on-error`, because a fork has no secrets and must still
    build anonymously."""
    for path in sorted(WORKFLOWS.glob("*.yml")):
        wf = _workflow(path.name)
        for job_name, job in wf["jobs"].items():
            builds = _build_steps(job)
            if not builds:
                continue
            steps = job["steps"]
            logins = [i for i, step in enumerate(steps) if "docker/login-action" in step.get("uses", "")]
            assert logins and logins[0] < builds[0], f"{path.name}:{job_name} builds an image before logging in"
            pushes = any(step.get("with", {}).get("push") is True for step in steps)
            if not pushes:
                # A job that pushes needs the login to succeed; one that only
                # builds must still work on a fork, where the secrets are absent.
                lenient = steps[logins[0]].get("continue-on-error") is True
                assert lenient, f"{path.name}:{job_name}: a fork without secrets must still build"
