"""
Tests for release.sh against throwaway git repositories (bare remote + clone).
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
CURRENT = "2026.09.4"

# release.sh calls python3 and bash. Git Bash on Windows provides bash but not
# python3, so the script exits 127 before reaching any of the checks these cases
# assert on — a missing toolchain reported as a failing release script. Skipped
# with a reason instead: Linux CI, where the release actually runs, is unaffected.
pytestmark = pytest.mark.skipif(
    shutil.which("python3") is None,
    reason="release.sh requires python3 on PATH (absent in Git Bash on Windows)",
)


def _git(cwd, *args, check=True):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=check,
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(
        "[user]\n\tname = Test\n\temail = test@example.com\n"
        "[commit]\n\tgpgsign = false\n[tag]\n\tgpgsign = false\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")

    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    work = tmp_path / "work"
    _git(tmp_path, "clone", "-q", str(remote), str(work))
    (work / "cookieradar").mkdir()
    (work / "cookieradar" / "__init__.py").write_text(f'__version__ = "{CURRENT}"\n', encoding="utf-8")
    shutil.copy(ROOT / "release.sh", work / "release.sh")
    _git(work, "add", ".")
    _git(work, "commit", "-q", "-m", "initial")
    _git(work, "push", "-q", "origin", "main")
    return work, remote


def _release(work, *args):
    return subprocess.run(["bash", "release.sh", *args], cwd=work, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60)


def _remote_tags(remote):
    return _git(remote, "tag").split()


def test_release_bumps_version_and_pushes_commit_and_tag(repo):
    work, remote = repo

    proc = _release(work, "2026.09.5")

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (work / "cookieradar" / "__init__.py").read_text(encoding="utf-8") == '__version__ = "2026.09.5"\n'
    assert _git(remote, "log", "-1", "--format=%s", "main") == "chore: bump version to 2026.09.5"
    assert _remote_tags(remote) == ["v2026.09.5"]
    assert _git(remote, "rev-parse", "v2026.09.5^{commit}") == _git(remote, "rev-parse", "main")
    assert _git(remote, "cat-file", "-t", "v2026.09.5") == "tag"  # annotated


def _assert_refused(proc, remote, message):
    assert proc.returncode != 0
    assert message in proc.stdout + proc.stderr
    assert _remote_tags(remote) == []
    assert _git(remote, "log", "-1", "--format=%s", "main") == "initial"


def test_release_requires_argument(repo):
    work, remote = repo
    _assert_refused(_release(work), remote, "Uso:")


@pytest.mark.parametrize("version", ["2026.9", "v2026.09.5", "2026.09.5-rc1", "latest", "2026.13.1"])
def test_release_rejects_invalid_version(repo, version):
    work, remote = repo
    _assert_refused(_release(work, version), remote, "Versione non valida")


def test_release_rejects_current_version(repo):
    work, remote = repo
    _assert_refused(_release(work, CURRENT), remote, "già la versione corrente")


def test_release_requires_main_branch(repo):
    work, remote = repo
    _git(work, "checkout", "-q", "-b", "feature")

    _assert_refused(_release(work, "2026.09.5"), remote, "Non sei su main")


def test_release_requires_clean_tree(repo):
    work, remote = repo
    (work / "notes.txt").write_text("wip", encoding="utf-8")

    _assert_refused(_release(work, "2026.09.5"), remote, "Working tree non pulito")


def test_release_refuses_when_behind_origin(repo, tmp_path):
    work, remote = repo
    other = tmp_path / "other"
    _git(tmp_path, "clone", "-q", str(remote), str(other))
    (other / "x.txt").write_text("x", encoding="utf-8")
    _git(other, "add", ".")
    _git(other, "commit", "-q", "-m", "someone else")
    _git(other, "push", "-q", "origin", "main")

    proc = _release(work, "2026.09.5")

    assert proc.returncode != 0
    assert "non è allineato con origin/main" in proc.stdout + proc.stderr
    assert _remote_tags(remote) == []


def test_release_refuses_unpushed_commits(repo):
    work, remote = repo
    (work / "x.txt").write_text("x", encoding="utf-8")
    _git(work, "add", ".")
    _git(work, "commit", "-q", "-m", "local only")

    _assert_refused(_release(work, "2026.09.5"), remote, "non è allineato con origin/main")


def test_release_refuses_tag_existing_only_on_remote(repo, tmp_path):
    work, remote = repo
    _git(remote, "tag", "v2026.09.5", "main")

    proc = _release(work, "2026.09.5")

    assert proc.returncode != 0
    assert "già esistente" in proc.stdout + proc.stderr
    assert _git(remote, "log", "-1", "--format=%s", "main") == "initial"
