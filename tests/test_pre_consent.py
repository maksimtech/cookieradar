"""
CookieRadar — tracking stored on the device before any choice is a finding (audit F-04)

The verdict looked at the session after the refusal only. A site that wrote
Google Analytics' `_ga` before the banner was answered — repubblica.it on
2026-10-17, with the TCF string still empty — could end in exit 0, "All sites
respect the refusal".

Art. 122(1) of the Codice privacy (d.lgs. 196/2003) allows storing information
on the user's device, or reading what is stored there, "unicamente a condizione
che il contraente o l'utente abbia espresso il proprio consenso"; art. 5(3) of
the ePrivacy directive is the rule it transposes. What the audit records that
meets those words is a cookie: a tracking cookie present before any choice is
storage on the device without consent. A request to a tracker's host is not,
by itself — Google Tag Manager loading, or Consent Mode's pings with storage
denied, can be lawful — so a request alone is reported, not cited.

The finding is a VIOLATION with its own cause and the same exit code, so a CI
that reads the codes keeps reading them the same way.
"""
from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console

from cookieradar.cli import ExitCode, _render_report, _verdict
from cookieradar.law_checker import FINDING_ARTICLES, FINDING_TITLES, findings_of
from cookieradar.law_fetcher import EPRIVACY, PRIVACY_CODE
from cookieradar.scanner import ScanResult, SessionResult, TrackerRequest, stored_before_choice


def _cookie(name, domain):
    return {"name": name, "value": "x", "domain": domain, "path": "/", "expires": -1,
            "httpOnly": False, "secure": False, "sameSite": "Lax"}


GA = _cookie("_ga", ".repubblica.it")
IDE = _cookie("IDE", ".doubleclick.net")
CONSENT = _cookie("_iub_cs-281842", ".repubblica.it")      # iubenda's own consent record
SESSION = _cookie("PHPSESSID", "www.repubblica.it")
GTM = TrackerRequest("https://www.googletagmanager.com/gtm.js", "googletagmanager.com", "script", 0.0)


def _result(pre_cookies=(), pre_trackers=(), rejected=True, after=()):
    return ScanResult(
        url="https://www.repubblica.it",
        pre_consent=SessionResult("pre-consent", trackers=list(pre_trackers), cookies=list(pre_cookies),
                                  banner_found=True, status=200),
        post_accept=SessionResult("post-accept", consent_clicked=True, banner_found=True, status=200),
        post_reject=SessionResult("post-reject", consent_clicked=rejected, banner_found=True, status=200,
                                  trackers=list(after)),
    )


def _report(result) -> str:
    out = Console(file=StringIO(), width=400, color_system=None)
    _render_report(out, result.url, result)
    return " ".join(out.file.getvalue().split())


# ─── what counts as storage ──────────────────────────────────────────────────

def test_a_tracking_cookie_before_any_choice_is_storage():
    assert stored_before_choice(_result([GA, IDE, CONSENT, SESSION])) == [
        "cookie IDE (doubleclick.net)",
        "cookie _ga (repubblica.it)",
    ]


@pytest.mark.parametrize("name", ["_ga_X1Y2Z3", "_fbp", "_gcl_au"])
def test_the_other_cookies_measured_that_day_are_storage_too(name):
    """GA4's per-property `_ga_<id>`, Meta's `_fbp` (subito.it), Google Ads' `_gcl_au`."""
    assert stored_before_choice(_result([_cookie(name, ".subito.it")])) == [f"cookie {name} (subito.it)"]


def test_the_site_s_own_session_and_consent_cookies_are_not():
    assert stored_before_choice(_result([CONSENT, SESSION])) == []


def test_a_request_alone_is_not_storage():
    assert stored_before_choice(_result(pre_trackers=[GTM])) == []


# ─── the finding and what it cites ───────────────────────────────────────────

def test_storage_before_any_choice_is_a_finding_of_its_own():
    found = findings_of(_result([GA]))

    assert found["pre_consent"] == ["cookie _ga (repubblica.it)"]


def test_it_cites_article_122_1_of_the_codice_privacy_and_eprivacy_5_3():
    assert FINDING_ARTICLES["pre_consent"] == ((PRIVACY_CODE, "122(1)"), (EPRIVACY, "5(3)"))
    assert "before any choice" in FINDING_TITLES["pre_consent"]


def test_the_codice_privacy_is_read_from_normattiva():
    assert PRIVACY_CODE.source == "Normattiva"
    assert PRIVACY_CODE.celex == "urn:nir:stato:decreto.legislativo:2003-06-30;196"


def test_it_stands_beside_a_violation_after_the_refusal():
    found = findings_of(_result([GA], after=[GTM]))

    assert "pre_consent" in found and "violation" in found


def test_it_stands_when_no_refusal_could_be_applied():
    """Storage before the banner is a fact about session 1, whatever happened
    with the refusal in session 3."""
    assert "pre_consent" in findings_of(_result([GA], rejected=False))


def test_a_page_that_was_never_the_site_has_no_finding():
    result = _result([GA])
    result.pre_consent.status = 403

    assert findings_of(result) == {}


# ─── the verdict and the report ──────────────────────────────────────────────

def test_storage_before_any_choice_makes_an_otherwise_clean_site_a_violation():
    assert _verdict(_result([GA])) is ExitCode.VIOLATION


def test_it_is_a_violation_even_when_the_refusal_could_not_be_applied():
    assert _verdict(_result([GA], rejected=False)) is ExitCode.VIOLATION


def test_a_request_alone_before_any_choice_leaves_the_verdict_alone():
    assert _verdict(_result(pre_trackers=[GTM])) is ExitCode.OK


def test_the_report_names_what_was_stored_and_why_it_counts():
    text = _report(_result([GA]))

    assert "VIOLATION — tracking data stored on the device before any choice" in text
    assert "cookie _ga (repubblica.it)" in text
    assert "0 tracker(s) loaded after rejection" not in text


def test_the_report_says_a_request_alone_is_not_cited():
    text = _report(_result(pre_trackers=[GTM]))

    assert "Contacted before any choice: googletagmanager.com" in text
    assert "a request alone does not show that anything was stored on the device" in text


# ─── the real thing ──────────────────────────────────────────────────────────

@pytest.mark.integration
async def test_a_page_that_writes_ga_on_load_is_found(browser, site_url):
    from cookieradar.scanner import scan

    result = await scan(f"{site_url}/ga_before_choice.html")

    assert stored_before_choice(result) == ["cookie _ga (127.0.0.1)"]
    assert _verdict(result) is ExitCode.VIOLATION
    assert "pre_consent" in findings_of(result)


@pytest.mark.integration
def test_batch_says_why_a_site_with_only_this_finding_is_a_violation(browser, site_url, tmp_path):
    """A summary line that says VIOLATION and lists nothing after the refusal
    would leave the reader to guess."""
    from typer.testing import CliRunner

    from cookieradar.cli import app

    urls = tmp_path / "urls.txt"
    urls.write_text(f"{site_url}/ga_before_choice.html\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["batch", str(urls)], env={"COLUMNS": "200"})

    assert result.exit_code == ExitCode.VIOLATION, result.output
    assert "cookie _ga (127.0.0.1)" in result.output
    assert "before any choice" in result.output


def test_the_report_still_says_when_the_refusal_could_not_be_applied():
    """The violation is about session 1; that session 3 tested nothing is a
    separate fact the reader needs — said once, in session 3's own section."""
    text = _report(_result([GA], rejected=False))

    assert "VIOLATION — tracking data stored on the device before any choice" in text
    assert "reject button not found" in text
