"""Tests for mapping CookieRadar findings to GDPR and ePrivacy provisions."""
from datetime import UTC, datetime

import pytest

from cookieradar import law_fetcher
from cookieradar.law_cache import LawCache
from cookieradar.law_checker import (
    FINDING_ARTICLES,
    FINDING_TITLES,
    UNVERIFIED_NOTE,
    check,
    findings_of,
    notes_of,
)
from cookieradar.law_fetcher import (
    CONSUMER_CODE,
    DIGITAL_CONTENT,
    EPRIVACY,
    GDPR,
    LawFetchError,
    Provision,
)
from cookieradar.scanner import ScanResult, SessionResult, TrackerRequest

DAY1 = datetime(2026, 9, 19, 14, 0, tzinfo=UTC)
DAY2 = datetime(2026, 10, 1, 9, 30, tzinfo=UTC)


def _session(name, domains, clicked=True):
    return SessionResult(
        session=name,
        trackers=[TrackerRequest(f"https://{d}/t.js", d, "script", 0.0) for d in domains],
        consent_clicked=clicked,
    )


def scan_result(pre=(), rejected=(), clicked=True):
    return ScanResult(
        url="https://example.com",
        pre_consent=_session("pre-consent", pre, clicked=False),
        post_accept=_session("post-accept", (), clicked=clicked),
        post_reject=_session("post-reject", rejected, clicked=clicked),
    )


def _fake_fetch(suffix=""):
    calls = []

    def fake(act, articles, now=None, **kwargs):
        calls.append((act, articles))
        stamp = law_fetcher.utc_stamp(now)
        refs = {ref for pairs in FINDING_ARTICLES.values() for a, ref in pairs if a == act}
        return {
            ref: Provision.from_text(ref, f"{act.name} {ref}{suffix}", stamp, act.celex)
            for ref in refs if ref.split("(")[0] in articles
        }

    fake.calls = calls
    return fake


@pytest.fixture
def cache(tmp_path):
    return LawCache(tmp_path / "law_cache.json")


@pytest.fixture
def online(monkeypatch):
    fake = _fake_fetch()
    monkeypatch.setattr(law_fetcher, "fetch_provisions", fake)
    return fake.calls


# ─── mapping ──────────────────────────────────────────────────────────────────

def test_mapping():
    assert FINDING_ARTICLES == {
        "violation": ((GDPR, "5(1)(a)"), (EPRIVACY, "5(3)")),
        "unfair_practice": ((CONSUMER_CODE, "20"), (CONSUMER_CODE, "21")),
        "post_reject": ((GDPR, "7"),),
        "invalid_consent": ((DIGITAL_CONTENT, "3(8)"),),
        # Evidence about the banner, not about the trackers: art. 4(11) is the
        # definition of consent as freely given, art. 5(3) is what requires it.
        "no_refusal": ((GDPR, "4(11)"), (EPRIVACY, "5(3)")),
    }
    assert set(FINDING_TITLES) == set(FINDING_ARTICLES)


def test_clean_site_has_no_findings():
    assert findings_of(scan_result(pre=["google-analytics.com"], rejected=[])) == {}
    assert notes_of(scan_result()) == []


def test_violation_lists_the_trackers():
    result = scan_result(pre=["google-analytics.com"], rejected=["google-analytics.com", "hotjar.com"])
    assert findings_of(result) == {
        "violation": ["google-analytics.com", "hotjar.com"],
        "unfair_practice": ["2 trackers active despite consent being rejected"],
        "post_reject": [
            "google-analytics.com (already present before consent)",
            "hotjar.com (new after rejection)",
        ],
        "invalid_consent": ["2 trackers active despite consent being rejected"],
    }


def _accept_only(trackers=("adobedtm.com", "demdex.net")):
    """The banner was found, accept was applied, no refusal control was found.

    Modelled on kyoceradocumentsolutions.it as measured on 2026-09-26.
    """
    result = ScanResult(
        url="https://example.com",
        pre_consent=_session("pre-consent", (), clicked=False),
        post_accept=_session("post-accept", trackers, clicked=True),
        post_reject=_session("post-reject", (), clicked=False),
    )
    for session in (result.pre_consent, result.post_accept, result.post_reject):
        session.banner_found = True
    return result


def test_a_banner_that_accepts_and_cannot_refuse_is_a_finding():
    """Not a limitation of the audit: an observation about the mechanism.

    Acceptance was exercised and worked. Refusal could not be exercised because
    no control for it was found. That asymmetry is the evidence, and it is
    evidence about the consent mechanism rather than about the trackers.
    """
    found = findings_of(_accept_only())

    assert "no_refusal" in found
    assert any("accept" in line.lower() for line in found["no_refusal"])
    assert any("refus" in line.lower() for line in found["no_refusal"])


def test_the_finding_says_what_was_observed_and_not_what_the_site_offers():
    """The audit cannot tell "there is no reject button" from "this tool did
    not find one". Anything that claims the former is a verdict the evidence
    does not support."""
    lines = " ".join(findings_of(_accept_only())["no_refusal"]).lower()

    assert "not found" in lines or "no refusal control was found" in lines
    assert "does not offer" not in lines
    assert "no reject button exists" not in lines


def test_no_banner_at_all_stays_a_limitation_of_the_audit():
    """Neither button was reached, so the mechanism was never located. That is
    this tool admitting what it could not do, and it must not turn into a
    statement about the site."""
    result = scan_result(pre=["doubleclick.net"], rejected=["doubleclick.net"], clicked=False)

    assert findings_of(result) == {}


def test_a_site_where_both_buttons_worked_has_no_refusal_finding():
    assert "no_refusal" not in findings_of(scan_result(pre=["a.com"], rejected=[]))


def test_the_note_says_which_of_the_two_situations_happened():
    """One sentence covering both described neither, and described the wrong
    one out loud as soon as the banner-only case started carrying citations."""
    accepted_only = " ".join(notes_of(_accept_only())).lower()
    assert "the banner was found and accepted" in accepted_only
    assert "no refusal control was found" in accepted_only

    no_banner = " ".join(notes_of(scan_result(clicked=False))).lower()
    assert "no cookie banner was found" in no_banner


def test_unverified_cites_nothing_and_notes_why():
    # The reject button was not found: trackers after "rejection" prove nothing
    result = scan_result(pre=["doubleclick.net"], rejected=["doubleclick.net"], clicked=False)
    assert findings_of(result) == {}
    assert notes_of(result) == [UNVERIFIED_NOTE]
    assert "banner" in UNVERIFIED_NOTE


# ─── check ────────────────────────────────────────────────────────────────────

def test_violation_cites_gdpr_and_eprivacy(cache, online):
    law = check(scan_result(rejected=["doubleclick.net"]), cache=cache, now=DAY1)

    assert [(c.finding, c.law, c.article) for c in law.citations] == [
        ("violation", "GDPR", "5(1)(a)"),
        ("violation", "ePrivacy dir. 2002/58/CE", "5(3)"),
        ("unfair_practice", "Codice del Consumo D.Lgs. 206/2005", "20"),
        ("unfair_practice", "Codice del Consumo D.Lgs. 206/2005", "21"),
        ("post_reject", "GDPR", "7"),
        ("invalid_consent", "Contenuti digitali dir. 2019/770", "3(8)"),
    ]
    # One download per act, only the articles cited
    assert online == [
        (GDPR, ("5", "7")),
        (EPRIVACY, ("5",)),
        (CONSUMER_CODE, ("20", "21")),
        (DIGITAL_CONTENT, ("3",)),
    ]
    assert [s.source for s in law.acts] == ["verified"] * 4


def test_same_number_in_two_acts_gets_two_hashes(cache, online):
    law = check(scan_result(rejected=["doubleclick.net"]), cache=cache, now=DAY1)
    gdpr, eprivacy = law.citations[0], law.citations[1]
    assert gdpr.sha256 != eprivacy.sha256
    assert set(cache.load()) >= {("32016R0679", "5(1)(a)"), ("02002L0058-20091219", "5(3)")}


def test_unverified_downloads_nothing(cache, online):
    law = check(scan_result(rejected=["doubleclick.net"], clicked=False), cache=cache, now=DAY1)
    assert law.citations == []
    assert law.notes == [UNVERIFIED_NOTE]
    assert online == []


def test_one_act_offline_other_online(cache, monkeypatch):
    online = _fake_fetch()

    def eprivacy_down(act, articles, now=None, **kwargs):
        if act == EPRIVACY:
            raise LawFetchError("EUR-Lex answered HTTP 503")
        return online(act, articles, now=now)

    monkeypatch.setattr(law_fetcher, "fetch_provisions", eprivacy_down)
    law = check(scan_result(rejected=["doubleclick.net"]), cache=cache, now=DAY1)

    assert [(s.act, s.source) for s in law.acts] == [
        (GDPR, "verified"), (EPRIVACY, "unavailable"),
        (CONSUMER_CODE, "verified"), (DIGITAL_CONTENT, "verified"),
    ]
    assert law.citations[0].sha256 is not None
    assert law.citations[1].sha256 is None


def test_changed_eprivacy_text_is_reported_by_act(cache, monkeypatch):
    monkeypatch.setattr(law_fetcher, "fetch_provisions", _fake_fetch())
    first = check(scan_result(rejected=["doubleclick.net"]), cache=cache, now=DAY1)
    monkeypatch.setattr(law_fetcher, "fetch_provisions", _fake_fetch(" (modificato)"))
    law = check(scan_result(rejected=["doubleclick.net"]), cache=cache, now=DAY2)

    assert law.changed["ePrivacy dir. 2002/58/CE art. 5(3)"] == first.citations[1].sha256
    assert law.changed["GDPR art. 5(1)(a)"] == first.citations[0].sha256


def test_default_cache_location(tmp_path, online):
    check(scan_result(rejected=["doubleclick.net"]), now=DAY1)
    assert (tmp_path / "cookieradar-home" / "law_cache.json").is_file()
