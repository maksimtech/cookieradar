"""
After a refusal, what a request shows and what it does not.

Every tracker host contacted after the refusal was cited as a violation of GDPR
art. 5(1)(a), ePrivacy art. 5(3), art. 7 and the Consumer Code. Two kinds of
request show nothing those provisions are about, and the README already said so
for the session before any choice:

- a tag manager's own library, fetched as a script: Google Tag Manager's
  gtm.js and gtag/js, Adobe Launch from assets.adobedtm.com, Tealium's utag,
  TagCommander. Downloading code is not storing or reading anything on the
  device; what the code then does is a beacon or a cookie, and those are cited;
- a Google Consent Mode ping whose `gcs` is G100: ad_storage and
  analytics_storage both denied, the cookieless ping Consent Mode sends after a
  refusal.

Measured on 2026-11-17, all three after a refusal that was clicked:

- www.köln.de: gtm.js, gtag/js and a GA4 collect with gcs=G100, nothing else.
  Verdict VIOLATION, with four provisions cited.
- www.comune.milano.it: nine scripts from assets.adobedtm.com (the Launch
  library, its AppMeasurement extensions, its rules), no Adobe beacon. VIOLATION.
- www.aranzulla.it: gtag/js and a GA4 collect with gcs=G100, beside real
  advertising requests to doubleclick.net and googlesyndication.com, which stay
  cited.

They are now reported as loaded after the refusal and not cited, the rule the
report already applied before any choice. The rule is narrow on purpose: a
script and nothing else, a G100 and nothing else, and neither when the session
holds a tracking cookie that the same tools write.
"""
from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console

from cookieradar.cli import ExitCode, _render_report, _verdict
from cookieradar.law_checker import findings_of
from cookieradar.scanner import (
    ScanResult,
    SessionResult,
    TrackerRequest,
    find_violations,
    not_cited_after_rejection,
    tracker_domain,
)

# The requests as the runs recorded them (_hunt/runs/<site>/result.json), with
# the query strings shortened where they carry identifiers.
KOELN = [
    ("script", "https://www.googletagmanager.com/gtm.js?id=GTM-5SM8DZ"),
    ("script", "https://www.googletagmanager.com/gtag/js?id=G-5Y09SYB3WL&cx=c&gtm=4e6bg0"),
    ("fetch", "https://region1.google-analytics.com/g/collect?v=2&tid=G-5Y09SYB3WL&gcs=G100"
              "&gcd=13q3qPq2q5l1&npa=1&dma=1&cid=938410298.1794941046&en=page_view"),
]
MILANO = [
    ("script", "https://assets.adobedtm.com/77a8d71c8627/4047148a865e/launch-e15d87e4218c.min.js"),
    ("script", "https://assets.adobedtm.com/extensions/EPb56e12d7054b4acea984e91c910051cc/AppMeasurement.min.js"),
    ("script", "https://assets.adobedtm.com/extensions/EPb56e12d7054b4acea984e91c910051cc/"
               "AppMeasurement_Module_ActivityMap.min.js"),
    ("script", "https://assets.adobedtm.com/77a8d71c8627/4047148a865e/ebe484fb2058/"
               "RC3e0e342c3881458b8a6ff927bdcf36b5-source.min.js"),
]
ARANZULLA = [
    ("script", "https://securepubads.g.doubleclick.net/tag/js/gpt.js"),
    ("script", "https://www.googletagmanager.com/gtag/js?id=G-9D6DKK0Y09"),
    ("fetch", "https://pagead2.googlesyndication.com/gampad/ads?pvsid=287239045001372&gdfp_req=1"),
    ("fetch", "https://region1.google-analytics.com/g/collect?v=2&tid=G-9D6DKK0Y09&gcs=G100&npa=1&en=page_view"),
]


def _cookie(name, domain):
    return {"name": name, "value": "x", "domain": domain, "path": "/", "expires": -1,
            "httpOnly": False, "secure": False, "sameSite": "Lax"}


def _requests(pairs):
    return [TrackerRequest(url, tracker_domain(url), kind, 0.0) for kind, url in pairs]


def _result(after, *, pre=(), cookies=(), rejected=True, host="www.example.it"):
    return ScanResult(
        url=f"https://{host}/",
        pre_consent=SessionResult("pre-consent", trackers=_requests(pre), banner_found=True, status=200),
        post_accept=SessionResult("post-accept", consent_clicked=True, banner_found=True, status=200),
        post_reject=SessionResult("post-reject", trackers=_requests(after), cookies=list(cookies),
                                  consent_clicked=rejected, banner_found=True, status=200),
    )


def _report(result) -> str:
    out = Console(file=StringIO(), width=400, color_system=None)
    _render_report(out, result.url, result)
    return " ".join(out.file.getvalue().split())


# ─── the three sites ─────────────────────────────────────────────────────────

def test_koeln_tag_manager_and_a_denied_ping_are_not_a_violation():
    result = _result(KOELN, pre=KOELN, cookies=[_cookie("CookieConsent", "www.koeln.de")])

    assert find_violations(result).all == set()
    assert not_cited_after_rejection(result) == {
        "googletagmanager.com": "tag manager library",
        "google-analytics.com": "Consent Mode ping, storage denied",
    }
    assert _verdict(result) is ExitCode.OK
    assert findings_of(result) == {}


def test_milano_adobe_launch_libraries_are_not_a_violation():
    result = _result(MILANO, pre=MILANO, cookies=[_cookie("demdex", ".demdex.net")])

    assert find_violations(result).all == set()
    assert not_cited_after_rejection(result) == {"adobedtm.com": "tag manager library"}
    assert _verdict(result) is ExitCode.OK


def test_aranzulla_advertising_stays_cited_and_the_rest_does_not():
    result = _result(ARANZULLA, pre=ARANZULLA)

    assert find_violations(result).all == {"doubleclick.net", "googlesyndication.com"}
    assert not_cited_after_rejection(result) == {
        "googletagmanager.com": "tag manager library",
        "google-analytics.com": "Consent Mode ping, storage denied",
    }
    assert _verdict(result) is ExitCode.VIOLATION
    assert findings_of(result)["violation"] == ["doubleclick.net", "googlesyndication.com"]


# ─── what stays cited ────────────────────────────────────────────────────────

@pytest.mark.parametrize("gcs", ["G111", "G101", "G110", "G1--"])
def test_a_collect_without_storage_denied_is_still_a_violation(gcs):
    """Granted, half granted, or not said: a beacon is a beacon."""
    url = f"https://region1.google-analytics.com/g/collect?v=2&tid=G-X&gcs={gcs}"
    result = _result([("fetch", url)])

    assert find_violations(result).all == {"google-analytics.com"}
    assert _verdict(result) is ExitCode.VIOLATION


def test_a_collect_with_no_consent_mode_at_all_is_still_a_violation():
    result = _result([("fetch", "https://www.google-analytics.com/g/collect?v=2&tid=G-X")])

    assert find_violations(result).all == {"google-analytics.com"}


def test_a_denied_ping_beside_a_written_ga_cookie_is_still_a_violation():
    """`_ga` in the jar after the refusal: something wrote it, and the code that
    writes it is the code that sent the ping."""
    result = _result(KOELN, cookies=[_cookie("_ga", ".koeln.de")])

    assert find_violations(result).all == {"googletagmanager.com", "google-analytics.com"}


def test_a_tag_manager_with_a_cookie_on_its_own_domain_is_still_a_violation():
    result = _result(MILANO, cookies=[_cookie("tracker", ".adobedtm.com")])

    assert find_violations(result).all == {"adobedtm.com"}


@pytest.mark.parametrize("kind, url", [
    # A tag manager host answering a beacon: Tag Manager's own diagnostics
    ("fetch", "https://www.googletagmanager.com/td?id=GTM-X&v=3"),
    # The library fetched as something other than a script
    ("image", "https://www.googletagmanager.com/gtm.js?id=GTM-X"),
    # A pixel, a script of an advertiser, a ping with G100 to a host that is no Google's
    ("image", "https://www.facebook.com/tr?id=1&ev=PageView"),
    ("script", "https://connect.facebook.net/en_US/fbevents.js"),
    ("image", "https://px.ads.linkedin.com/collect?gcs=G100"),
])
def test_anything_else_is_still_a_violation(kind, url):
    result = _result([(kind, url)])

    assert find_violations(result).all == {tracker_domain(url)}
    assert not_cited_after_rejection(result) == {}


def test_one_real_beacon_keeps_the_whole_domain_cited():
    result = _result([
        ("script", "https://www.googletagmanager.com/gtm.js?id=GTM-X"),
        ("fetch", "https://www.googletagmanager.com/td?id=GTM-X"),
    ])

    assert find_violations(result).all == {"googletagmanager.com"}
    assert not_cited_after_rejection(result) == {}


def test_nothing_is_set_aside_when_no_refusal_was_applied():
    result = _result(KOELN, rejected=False)

    assert not_cited_after_rejection(result) == {}


# ─── the report ──────────────────────────────────────────────────────────────

def test_the_report_names_them_as_loaded_and_not_cited():
    text = _report(_result(KOELN, pre=KOELN))

    assert "VIOLATION" not in text
    assert "No trackers loaded after rejection" not in text
    assert "Nothing cited after rejection" in text
    assert "Loaded after rejection, not cited: google-analytics.com (Consent Mode ping, storage denied), " \
           "googletagmanager.com (tag manager library)" in text


def test_a_violation_report_still_names_the_rest_as_not_cited():
    text = _report(_result(ARANZULLA, pre=ARANZULLA))

    assert "VIOLATION — 2 tracker(s) loaded after rejection" in text
    assert "Loaded after rejection, not cited: google-analytics.com" in text


def test_a_clean_session_is_still_called_clean():
    assert "No trackers loaded after rejection" in _report(_result([]))


def test_batch_says_ok_and_names_what_was_not_cited(tmp_path):
    from unittest.mock import patch

    from typer.testing import CliRunner

    import cookieradar.cli as cli
    import cookieradar.scanner as scanner

    async def fake(url, **kwargs):
        return _result(KOELN, pre=KOELN)

    urls = tmp_path / "urls.txt"
    urls.write_text("www.koeln.de\n", encoding="utf-8")
    with patch.object(scanner, "scan", fake), patch.object(cli, "console", Console(width=400)):
        res = CliRunner().invoke(cli.app, ["batch", str(urls)])

    assert res.exit_code == ExitCode.OK, res.output
    text = " ".join(res.output.split())
    assert "OK — pre: 2 trackers, post-reject: 2 trackers" in text
    assert "Loaded after rejection, not cited: google-analytics.com" in text
