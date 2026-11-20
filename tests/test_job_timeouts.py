"""Every job says how long it may run, so a hung job cannot hold a pull request for six hours.

Without `timeout-minutes` a job runs for GitHub's default of 360 minutes. When it is a
required check the pull request waits that long, and so would an auto-merge
(maksimtech/apkradar#113).

The limits are about three times the longest run of the job in its last 40 runs
(2026-11-20), and never under ten minutes: a short job is mostly installs and image pulls,
which are slow on a bad day without being stuck.

A job that waits on purpose gets more than its runs suggest: its limit has to outlast its
own wait, or GitHub kills it before it can say what it was waiting for. The tests below
read those waits from the workflows, so a longer wait cannot outgrow its limit unseen.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
GITHUB_DEFAULT = 360
# What a waiting job does besides sleeping: the requests between the sleeps, the build.
MARGIN = 10 * 60


def jobs():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for name, job in (workflow.get("jobs") or {}).items():
            yield f"{path.name}:{name}", job


def script(job: dict) -> str:
    return "\n".join(step.get("run", "") for step in job.get("steps", []))


def test_there_are_jobs_to_look_at():
    assert len(list(jobs())) > 10


def test_every_job_declares_a_timeout_below_the_default():
    # A job that calls a reusable workflow cannot take `timeout-minutes`; the jobs of the
    # workflow it calls are in this directory and are held here like any other.
    wrong = {name: job.get("timeout-minutes") for name, job in jobs()
             if "uses" not in job
             and not (isinstance(job.get("timeout-minutes"), int) and 0 < job["timeout-minutes"] < GITHUB_DEFAULT)}
    assert wrong == {}, f"jobs without a timeout under {GITHUB_DEFAULT} minutes: {wrong}"


def test_reusable_workflows_called_here_are_local():
    # The exemption above holds only if the called workflow is one of ours.
    called = {name: job["uses"] for name, job in jobs() if "uses" in job}
    assert called, "nothing calls a reusable workflow: drop the exemption"
    for name, uses in called.items():
        assert uses.startswith("./.github/workflows/"), f"{name} calls {uses}"
        assert (WORKFLOWS.parents[1] / uses).is_file(), f"{name} calls {uses}, which is not here"


def test_security_posture_outlives_its_own_wait():
    # The gate waits for the scanners up to a deadline of its own and then says they did not
    # finish. A job timeout shorter than that would kill it first, with no such message.
    job = dict(jobs())["security-posture.yml:posture"]
    wait = int(re.search(r"deadline=\$\(\( SECONDS \+ (\d+) \)\)", script(job)).group(1))
    assert job["timeout-minutes"] * 60 >= wait + 5 * 60


def test_publishing_outlives_its_waits_for_pypi():
    # After the upload the job waits for the index to show the version (wait_for_pypi.sh:
    # attempts x interval, then a grace) and then installs it, asking again while a cache
    # lags (install_from_pypi.sh: attempts x interval). A limit under those would end the
    # job before either could say the version is not there.
    job = dict(jobs())["publish.yml:build-and-publish"]
    run = script(job)
    wait = re.search(r'wait_for_pypi\.sh \S+ "\$VERSION" (\d+) (\d+)(?: (\d+))?', run)
    install = re.search(r'install_from_pypi\.sh \S+ \S+ "\$VERSION" (\d+) (\d+)', run)
    assert wait and install, "publish.yml no longer calls the two scripts as this test reads them"
    seconds = int(wait[1]) * int(wait[2]) + int(wait[3] or 45) + int(install[1]) * int(install[2])
    assert job["timeout-minutes"] * 60 >= seconds + MARGIN
