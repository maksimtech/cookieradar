#!/bin/sh
# What the image actually contains, printed rather than taken from a scanner.
#
# This exists because Docker Desktop cannot be installed on the machine this is
# developed on — Windows 10 IoT Enterprise LTSC 2021 is build 19044 and Docker
# requires 19045, a build that edition will never receive. So the image can only
# be examined from inside a CI job, and that is a better place for it anyway: a
# Linux runner is what the image actually runs on.
#
# Every version in SECURITY-EXCEPTIONS.toml for this repository was copied out of
# Snyk's report rather than read from the image. That is an inherited claim, and
# the record says elsewhere that inherited claims get measured. These are the ones
# to check:
#
#   libxml2  2.12.7+dfsg+really2.9.14-2.1+deb13u3   seven CVEs, Debian bug 1146744
#   cups     2.4.10-3+deb13u2                       CVE-2026-34980, bug 1132716
#   expat    2.8.3-1~deb13u1                        CVE-2026-93990, bug 1148665
#
# All three arrive with `playwright install-deps chromium` and none can be removed
# — auditing cookies means loading pages, and loading pages means Chromium. What
# the numbers settle is whether a stable update has reached the image yet, which is
# the one thing that closes those ten findings.
#
# The second question is pip. Unlike patchradar, exeradar and mailradar, this
# Dockerfile does not remove the build tooling, so the copies vendored inside it
# are in the published image. Docker Scout does not currently report them here,
# which makes this a latent exposure and not a finding — and the version printed
# below is what a decision about it should rest on.
#
# Run by .github/workflows/docker-build-check.yml, which builds and publishes
# nothing:
#     docker run --rm -i --entrypoint sh cookieradar:build-check - < inspect.sh
#
# It reports and does not judge: a red step here would be a broken diagnostic, and
# what matters is whether the numbers and the record agree.
set -eu

echo "── the packages SECURITY-EXCEPTIONS.toml names ──"
# Patterns, not exact names. The first version asked for `libcups2` and got back a
# line with no version, which reads as "not installed" and actually meant "that
# name does not exist here": Debian trixie's 64-bit time_t transition renamed these
# libraries with a `t64` suffix, so the installed package is libcups2t64. A probe
# that answers "absent" when it means "I asked the wrong question" is the defect
# this whole file exists to avoid, and it produced exactly one wrong answer on
# 2026-09-30 before being caught.
#
# A line carrying a version is a real install. A line without one is a virtual
# package that something else provides, and says nothing about what is on disk.
for pattern in 'libxml2*' 'libcups*' 'libexpat1*' 'zlib1g*' 'perl-base'; do
    found=$(dpkg-query -W -f '  ${Package} ${Version} priority=${Priority}\n' "$pattern" 2>/dev/null || true)
    if [ -n "$found" ]; then
        echo "$found"
    else
        echo "  $pattern matched nothing installed"
    fi
done

echo
echo "── perl: which one is really here ──"
# Scout names the source package for CVE-2026-82560, and Debian's `perl` source
# produces `perl-base` — Essential, which dpkg depends on — as well as `perl`,
# which can be removed. Only the versioned lines below are real installs.
dpkg-query -W -f '  ${Package} ${Version} essential=${Essential} priority=${Priority}\n' \
    'perl*' 'libperl*' 2>/dev/null || echo "  none"

echo
echo "── build tooling: present here, unlike the other Radar ──"
for pkg in pip setuptools wheel; do
    if version=$(python -c "import importlib.metadata as m, sys; sys.stdout.write(m.version('$pkg'))" 2>/dev/null); then
        echo "  $pkg $version is in the published image"
    else
        echo "  $pkg absent"
    fi
done
echo "  (a vendored copy under pip/_vendor is what a pin cannot reach; see"
echo "   patchradar's Dockerfile for the removal, and verify Chromium still starts"
echo "   before copying it here)"

echo
echo "── Chromium: the reason the surface is larger ──"
if [ -d "$HOME/.cache/ms-playwright" ]; then
    find "$HOME/.cache/ms-playwright" -maxdepth 1 -mindepth 1 -printf '  %f\n' 2>/dev/null \
        || ls -1 "$HOME/.cache/ms-playwright" | sed 's/^/  /'
else
    echo "  no ms-playwright cache under $HOME — the browser is elsewhere or absent"
fi

echo
echo "── size of the installed set ──"
printf '  %s packages\n' "$(dpkg-query -f '.\n' -W | wc -l)"
