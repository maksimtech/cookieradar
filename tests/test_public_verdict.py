"""
CookieRadar — the verdict is public, so a caller cannot get a narrower one.

The verdict lived in `cli._verdict`, a private name. APKRadar's `--full`, which
runs this scanner on an app's domains, could not import it and decided the
verdict by itself, as "trackers seen both before consent and after rejection".
That missed three of the four ways a site is not OK: a tracker new after
rejection, a tracking cookie stored before any choice, and a refusal that could
not be clicked — each printed by APKRadar as a green "none persist".

`scanner.verdict` is now the one place the decision is made; the command line
uses it, and so can anyone who calls `scan()`.
"""
from __future__ import annotations

import pytest

from cookieradar import cli
from cookieradar.scanner import ScanResult, SessionResult, TrackerRequest, Verdict, verdict


def _tracker(domain: str) -> TrackerRequest:
    return TrackerRequest(url=f"https://{domain}/t.js", domain=domain,
                          resource_type="script", timestamp=0.0)


def _result(pre=(), rej=(), *, reject_clicked=True, status=200, pre_cookies=()) -> ScanResult:
    return ScanResult(
        url="https://site.example",
        pre_consent=SessionResult("pre-consent", trackers=[_tracker(d) for d in pre],
                                  cookies=list(pre_cookies), banner_found=True, status=status),
        post_accept=SessionResult("post-accept", banner_found=True, consent_clicked=True, status=status),
        post_reject=SessionResult("post-reject", trackers=[_tracker(d) for d in rej],
                                  banner_found=True, consent_clicked=reject_clicked, status=status),
    )


CASES = {
    "persistent": (_result(pre=["doubleclick.net"], rej=["doubleclick.net"]), Verdict.VIOLATION),
    "new after rejection": (_result(rej=["doubleclick.net"]), Verdict.VIOLATION),
    "cookie before choice": (_result(pre_cookies=[{"name": "_ga", "domain": ".site.example"}]),
                             Verdict.VIOLATION),
    "refusal not clicked": (_result(pre=["doubleclick.net"], reject_clicked=False), Verdict.UNVERIFIED),
    "error page": (_result(status=403), Verdict.ERROR),
    "clean": (_result(), Verdict.OK),
}


@pytest.mark.parametrize("name", CASES)
def test_verdict(name):
    result, expected = CASES[name]
    assert verdict(result) is expected


@pytest.mark.parametrize("name", CASES)
def test_the_command_line_gives_the_same_verdict(name):
    result, _ = CASES[name]
    assert cli._verdict(result) == verdict(result)


def test_exit_codes_are_the_verdicts():
    """Scripts read the exit status as the verdict: the numbers must not drift apart."""
    for v in Verdict:
        assert cli.ExitCode[v.name] == v.value
