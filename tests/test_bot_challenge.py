"""
CookieRadar — telling "we were not allowed to look" from "there is nothing there".

`page_not_served` already covers the honest refusal: a status of 400 or more, as
Akamai gives for canon.it and msi.com. Measured on 2026-09-29, msi.com answers 403
with a 363-byte Access Denied page — and identically to `httpx` with no browser at
all, with and without a Chrome User-Agent, so nothing about headless Chromium is
being detected there. That block is at the network edge.

The case that slips through is the other one: a bot-management challenge that
answers **200**. Cloudflare's "Just a moment…", AWS WAF's JavaScript challenge,
DataDome's interstitial. The browser loads it like any other page and finds no
trackers, no banner and one or two cookies — and reporting that as "0 trackers
before consent" is a claim assembled entirely out of never having seen the site,
which is the mistake `page_not_served` exists to prevent one status code lower.

The trap this file mostly exists to pin: **a bot-management cookie is not a
challenge.** Cloudflare sets `__cf_bm` on a large share of ordinary sites that
serve their own pages perfectly well, and treating that cookie as proof of a block
would make cookieradar refuse to audit them. So a cookie or a vendor host is only
ever corroboration; what decides is the page itself, or a status that means "not
the page you asked for".
"""
from __future__ import annotations

import pytest

from cookieradar.scanner import (
    ScanResult,
    SessionResult,
    bot_challenge,
    page_not_served,
)

JUST_A_MOMENT = "Just a moment..."
CF_BODY = "Checking your browser before accessing example.com. Please enable JavaScript."


def scan(*, status: int | None = 200, title: str = "Example Domain",
         text: str = "Welcome to Example, our products are below.",
         cookies: list[dict] | None = None,
         hosts: list[str] | None = None) -> ScanResult:
    """A ScanResult whose pre-consent session is the only one that matters here."""
    pre = SessionResult("pre-consent")
    pre.status = status
    pre.title = title
    pre.text = text
    pre.cookies = cookies or []
    for host in hosts or []:
        pre.external.append(_external(host))
    return ScanResult(url="https://example.com", pre_consent=pre)


def _external(host: str):
    from cookieradar.scanner import ExternalRequest
    return ExternalRequest(url=f"https://{host}/x", host=host,
                           resource_type="script", timestamp=0.0,
                           domain=None, tracker=None)


def cookie(name: str) -> dict:
    return {"name": name, "value": "x", "domain": ".example.com"}


# ── the page itself is what decides ─────────────────────────────────────────

def test_an_ordinary_page_is_not_a_challenge():
    assert bot_challenge(scan()).seen is False


@pytest.mark.parametrize("title, text", [
    (JUST_A_MOMENT, "example.com needs to review the security of your connection"),
    ("Attention Required! | Cloudflare", "Please enable cookies."),
    ("Example Domain", CF_BODY),
    ("Example Domain", "Verifying you are human. This may take a few seconds."),
    ("Pardon Our Interruption", "you're a power user moving through this website"),
    ("Example Domain", "Request unsuccessful. Incapsula incident ID: 123-456"),
    ("Example Domain", "Enable JavaScript and cookies to continue"),
])
def test_a_challenge_page_is_recognised_however_it_is_worded(title, text):
    found = bot_challenge(scan(title=title, text=text))

    assert found.seen is True
    assert found.signals, "a verdict with no signal cannot be checked by a reader"


def test_the_success_status_that_carries_a_challenge_is_recognised():
    """AWS WAF answers 202 with a JavaScript challenge: a success status carrying
    something that is not the page, so nothing downstream would question it."""
    found = bot_challenge(scan(status=202))

    assert found.seen is True
    assert "202" in " ".join(found.signals)


@pytest.mark.parametrize("status", [429, 503])
def test_a_bare_retry_status_is_not_called_a_challenge(status):
    """A challenge often uses 429 or 503, and a genuine outage uses 503 too.
    Both are above 400, so `page_not_served` already says "this is not the site",
    which is all that is known. Naming a cause nobody established is the defect
    this project keeps finding in other people's tools."""
    result = scan(status=status)

    assert page_not_served(result) is True
    assert bot_challenge(result).seen is False


@pytest.mark.parametrize("status", [429, 503])
def test_a_retry_status_that_also_says_so_is_a_challenge(status):
    """The text is what turns it from "not the site" into "we were challenged"."""
    assert bot_challenge(scan(status=status, title=JUST_A_MOMENT)).seen is True


def test_the_two_checks_leave_no_gap_and_do_not_both_fire():
    """202 is the one status a challenge can hide behind: below 400, so
    `page_not_served` lets it through."""
    result = scan(status=202)

    assert not page_not_served(result), "202 is a success as far as that check goes"
    assert bot_challenge(result).seen, "so this one has to catch it"


# ── the trap: a bot-management cookie is not a block ────────────────────────

def test_a_cloudflare_cookie_on_a_working_site_is_not_a_challenge():
    """`__cf_bm` is set on a large share of ordinary sites. Reading it as a block
    would make cookieradar refuse to audit them — the failure that would look
    like caution and be a silent loss of coverage."""
    found = bot_challenge(scan(cookies=[cookie("__cf_bm"), cookie("session")]))

    assert found.seen is False


def test_a_vendor_host_alone_is_not_a_challenge_either():
    found = bot_challenge(scan(hosts=["challenges.cloudflare.com"]))

    assert found.seen is False


def test_a_cookie_corroborates_a_challenge_page_and_is_named():
    """Once the page says it, the cookie is worth printing: it names the vendor,
    which is what an operator needs to ask for an allowlist."""
    found = bot_challenge(scan(title=JUST_A_MOMENT, cookies=[cookie("cf_clearance")]))

    assert found.seen is True
    assert any("cf_clearance" in s for s in found.signals)


def test_a_host_corroborates_a_challenge_page_and_is_named():
    found = bot_challenge(
        scan(status=202, hosts=["geo.captcha-delivery.com"]))

    assert found.seen is True
    assert any("captcha-delivery.com" in s for s in found.signals)


# ── what it must never do ───────────────────────────────────────────────────

def test_a_site_whose_own_words_mention_cookies_is_not_a_challenge():
    """The word "cookies" is everywhere on the sites this tool audits — it is a
    cookie auditor. A marker that fires on a consent banner would block every
    compliant site in the corpus."""
    banner = ("We use cookies to improve your experience. Please enable cookies "
              "to continue. Accept all / Reject all")
    assert bot_challenge(scan(text=banner)).seen is False


def test_an_empty_page_is_not_asserted_to_be_a_challenge():
    """A timeout leaves no title and no text, and the session already reports the
    timeout. Guessing "challenge" from silence would put a cause on a failure
    that has one."""
    assert bot_challenge(scan(status=None, title="", text="")).seen is False


def test_the_signals_say_what_was_found_and_not_merely_that_something_was():
    found = bot_challenge(scan(title=JUST_A_MOMENT, text=CF_BODY,
                               cookies=[cookie("__cf_bm")],
                               hosts=["challenges.cloudflare.com"]))

    joined = " ".join(found.signals).lower()
    assert "title" in joined or "just a moment" in joined
    assert len(found.signals) >= 2, "four signals were present; it reported one"


def test_an_error_page_is_left_to_page_not_served():
    """403 from an edge is not a challenge: nothing was asked of the visitor, the
    request was refused. Both report "the site was not seen", and conflating them
    would tell an operator to change their browser when the answer is to ask for
    access from this address."""
    result = scan(status=403, title="Access Denied",
                  text='You don\'t have permission to access "http://www.msi.com/"')

    assert page_not_served(result) is True
    assert bot_challenge(result).seen is False
