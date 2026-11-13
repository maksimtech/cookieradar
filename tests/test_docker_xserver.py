"""The image carries no X server.

`playwright install-deps chromium` installs xvfb, and xserver-common with it,
for running a headed browser on a machine without a display. CookieRadar never
starts one: an audit runs chrome-headless-shell, and --no-headless needs a
display the image does not have. Measured on 2026-11-13 in the image built from
this Dockerfile: nothing else installed depends on either package.

On 2026-11-13 Trivy reported six X.Org Server CVEs against both
(CVE-2026-109091, -109092, -109093, -109095, -109096, -109903), fixed in sid and
open in trixie. Removing the server closes them for good rather than recording
them. The removal names the two packages and nothing more: with --auto-remove
apt would also take Mesa, libgl and libvulkan, which install-deps had pulled in
for xvfb and which Chromium may load.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"


def run_instructions() -> list[str]:
    """Each RUN instruction, continuation lines joined, comments dropped."""
    lines = [line for line in DOCKERFILE.read_text(encoding="utf-8").splitlines()
             if not line.lstrip().startswith("#")]
    joined = re.sub(r"\\\n\s*", " ", "\n".join(lines))
    return [line.strip()[4:].strip() for line in joined.splitlines() if line.strip().startswith("RUN ")]


def test_xvfb_and_xserver_common_are_purged_after_install_deps():
    runs = run_instructions()
    install = next(i for i, r in enumerate(runs) if "playwright install-deps chromium" in r)
    purges = [r for r in runs[install:] if re.search(r"apt-get (-\S+ )*purge", r)]
    assert purges, "no apt-get purge after `playwright install-deps chromium`"
    words = set(" ".join(purges).split())
    assert {"xvfb", "xserver-common"} <= words, f"the purge does not name both packages: {purges}"


def test_the_purge_takes_nothing_else():
    for run in run_instructions():
        if re.search(r"apt-get (-\S+ )*purge", run):
            assert "--auto-remove" not in run and "autoremove" not in run, run
