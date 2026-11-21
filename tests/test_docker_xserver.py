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

The X server's font libraries go too. On 2026-11-20 Trivy reported
CVE-2026-109908 (libfontenc1, font file parsing, no fix in trixie). Measured that
day in the image built from this Dockerfile: neither Playwright Chromium binary
(`chrome`, `chrome-headless-shell`) links libfontenc or libXfont2; in the whole
image only mkfontscale and fonttosfnt do, from xfonts-utils, which builds X font
indexes and which nothing runs. libfontenc1 cannot leave alone: libxfont2 and
xfonts-utils depend on it, and xfonts-scalable, installed by install-deps, on
xfonts-utils; nothing depends on xfonts-scalable. So all four go, and with it the
eight Type1 faces it adds to fontconfig (Bitstream Charter, Courier 10 Pitch, four
styles each), which a page asking for them by name gets substituted. An audit
reads cookies and requests, and takes no screenshot.

They go with dpkg rather than apt: apt would remove whatever else depends on
them without a word, dpkg refuses and fails the build.
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


X_FONT_PACKAGES = {"xfonts-scalable", "xfonts-utils", "libxfont2", "libfontenc1"}


def test_the_x_font_libraries_are_purged_with_dpkg_after_install_deps():
    runs = run_instructions()
    install = next(i for i, r in enumerate(runs) if "playwright install-deps chromium" in r)
    purges = [r for r in runs[install:] if re.search(r"dpkg (-\S+ )*--purge", r)]
    assert purges, "no dpkg --purge after `playwright install-deps chromium`"
    words = set(" ".join(purges).split())
    assert words >= X_FONT_PACKAGES, f"the purge does not name all four: {purges}"


def test_the_x_font_libraries_are_not_left_to_apt():
    # apt would take their dependents along without a word; dpkg refuses.
    for run in run_instructions():
        for command in re.split(r"&&|;", run):
            if re.search(r"apt-get (-\S+ )*(purge|remove)", command):
                assert not X_FONT_PACKAGES & set(command.split()), command


def test_the_purge_does_not_force_past_dependencies():
    for run in run_instructions():
        if re.search(r"dpkg (-\S+ )*--purge", run):
            assert "--force" not in run, run
