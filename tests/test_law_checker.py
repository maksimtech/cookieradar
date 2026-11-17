"""Tests for mapping CookieRadar findings to GDPR and ePrivacy provisions."""
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from cookieradar import law_fetcher
from cookieradar.law_cache import LawCache
from cookieradar.law_checker import (
    CHALLENGED_NOTE,
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
    PRIVACY_CODE,
    LawFetchError,
    Provision,
)
from cookieradar.scanner import ScanResult, SessionResult, TrackerRequest

DAY1 = datetime(2026, 9, 19, 14, 0, tzinfo=UTC)
DAY2 = datetime(2026, 10, 1, 9, 30, tzinfo=UTC)
REAL_FETCH_HTML = law_fetcher.fetch_html


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
        }, "Cellar"

    fake.calls = calls
    return fake


@pytest.fixture
def cache(tmp_path):
    # In a folder of its own, so that read_only_cache freezes that folder and
    # not pytest's tmp_path.
    return LawCache(tmp_path / "law-cache" / "law_cache.json")


@pytest.fixture
def online(monkeypatch):
    fake = _fake_fetch()
    monkeypatch.setattr(law_fetcher, "fetch_provisions_from", fake)
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
        # Evidence about the device before any choice: a tracking cookie stored
        # without consent, art. 122(1) Codice privacy and the rule it transposes.
        "pre_consent": ((PRIVACY_CODE, "122(1)"), (EPRIVACY, "5(3)")),
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
    """The banner was found, accept was applied, no refusal control was found,
    and there was nothing else on the banner to click.

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
    result.post_accept.other_controls = 0
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
    assert "no cookie banner was recognised" in no_banner


def test_the_note_does_not_claim_there_was_no_banner():
    """The hint reads ids and classes, and on 2026-10-17 it missed Cookiebot's
    dialog and Didomi's notice, both on screen. "Not found" is a claim about
    the page; "not recognised" is what the tool can actually say."""
    note = " ".join(notes_of(scan_result(clicked=False))).lower()
    assert "no cookie banner was found" not in note


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


def _not_the_site(kind):
    """A result whose pages were not the site: an error status, or a challenge
    served with 200."""
    result = ScanResult(url="https://example.com")
    if kind == "403":
        for session in (result.pre_consent, result.post_accept, result.post_reject):
            session.status = 403
    else:
        result.pre_consent.status = 200
        result.pre_consent.title = "Just a moment..."
    return result


def test_law_notes_do_not_blame_the_banner_when_a_challenge_answered(cache):
    """`notes_of` looked only at `page_not_served` (status >= 400). With a
    challenge served with 200 the report said NOT MEASURED and, under the
    provisions, "UNVERIFIED: no cookie banner was found": a statement about a
    site nobody saw, exactly what the tests already rule out for a 403."""
    law = check(_not_the_site("challenge"), cache=cache, now=DAY1)

    assert UNVERIFIED_NOTE not in law.notes
    assert law.notes == [CHALLENGED_NOTE]


@pytest.mark.parametrize("kind", ["403", "challenge"])
def test_no_finding_is_drawn_from_a_page_that_is_not_the_site(cache, kind):
    """`notes_of` said NOT MEASURED, but `findings_of` did not look at the same
    fact: with an error page (or a challenge) carrying a reject button and a
    tracker after the reload, the report said NOT MEASURED and cited the
    provisions of the violation alongside."""
    result = _not_the_site(kind)
    result.post_reject.consent_clicked = True
    result.post_reject.trackers = [TrackerRequest("https://x.doubleclick.net/", "doubleclick.net", "script", 0.0)]

    assert findings_of(result) == {}
    law = check(result, cache=cache, now=DAY1)
    assert law.citations == []
    # Nothing to cite, so no act was even looked up: nothing downloaded, and
    # nothing written to the cache.
    assert law.acts == []
    assert not cache.path.exists()


def test_one_act_offline_other_online(cache, monkeypatch):
    online = _fake_fetch()

    def eprivacy_down(act, articles, now=None, **kwargs):
        if act == EPRIVACY:
            raise LawFetchError("EUR-Lex answered HTTP 503")
        return online(act, articles, now=now)

    monkeypatch.setattr(law_fetcher, "fetch_provisions_from", eprivacy_down)
    law = check(scan_result(rejected=["doubleclick.net"]), cache=cache, now=DAY1)

    assert [(s.act, s.source) for s in law.acts] == [
        (GDPR, "verified"), (EPRIVACY, "unavailable"),
        (CONSUMER_CODE, "verified"), (DIGITAL_CONTENT, "verified"),
    ]
    assert law.citations[0].sha256 is not None
    assert law.citations[1].sha256 is None


def test_changed_eprivacy_text_is_reported_by_act(cache, monkeypatch):
    monkeypatch.setattr(law_fetcher, "fetch_provisions_from", _fake_fetch())
    first = check(scan_result(rejected=["doubleclick.net"]), cache=cache, now=DAY1)
    monkeypatch.setattr(law_fetcher, "fetch_provisions_from", _fake_fetch(" (modificato)"))
    law = check(scan_result(rejected=["doubleclick.net"]), cache=cache, now=DAY2)

    assert law.changed["ePrivacy dir. 2002/58/CE art. 5(3)"] == first.citations[1].sha256
    assert law.changed["GDPR art. 5(1)(a)"] == first.citations[0].sha256


def test_default_cache_location(tmp_path, online):
    check(scan_result(rejected=["doubleclick.net"]), now=DAY1)
    assert (tmp_path / "cookieradar-home" / "law_cache.json").is_file()


# ─── a cited reference must be in the text downloaded now ────────────────────

def _whole_articles_only(act, articles, now=None, **kwargs):
    """A source that answered, and a text in which the parser found the
    articles and none of their paragraphs or points."""
    stamp = law_fetcher.utc_stamp(now)
    return {a: Provision.from_text(a, f"{act.name} {a}", stamp, act.celex) for a in articles}, "Cellar"


def _status(law, act):
    return next(status for status in law.acts if status.act == act)


def _citation(law, article):
    return next(citation for citation in law.citations if citation.article == article)


def test_a_reference_missing_from_the_fresh_text_is_not_verified(cache, monkeypatch):
    """Cellar answered and article 5 parsed, but 5(1)(a) was not in it: the act
    was "verified against Cellar" beside "SHA256: not available"."""
    monkeypatch.setattr(law_fetcher, "fetch_provisions_from", _whole_articles_only)
    law = check(scan_result(rejected=["doubleclick.net"]), cache=cache, now=DAY1)

    status = _status(law, GDPR)
    assert status.source == "unavailable", status
    assert "5(1)(a)" in (status.error or "")
    assert _citation(law, "5(1)(a)").sha256 is None


def test_a_cached_reference_is_not_served_as_verified(cache, monkeypatch):
    """The same, with the point cached by an earlier audit: its old SHA-256 and
    date came back under the "verified" label."""
    monkeypatch.setattr(law_fetcher, "fetch_provisions_from", _fake_fetch())
    first = check(scan_result(rejected=["doubleclick.net"]), cache=cache, now=DAY1)
    monkeypatch.setattr(law_fetcher, "fetch_provisions_from", _whole_articles_only)
    law = check(scan_result(rejected=["doubleclick.net"]), cache=cache, now=DAY2)

    assert _status(law, GDPR).source == "cache"
    assert _citation(law, "5(1)(a)").sha256 == _citation(first, "5(1)(a)").sha256
    assert _citation(law, "5(1)(a)").version_date == "2026-09-19"


GDPR_PAGE = (Path(__file__).parent / "fixtures" / "gdpr_it_excerpt.html").read_text(encoding="utf-8")
# Derived from the recorded page: point a) of art. 5(1) labelled "a." instead of
# "a)", so the parser finds article 5 and 5(1), and not the reference 5(1)(a)
GDPR_PAGE_POINT_A_UNLABELLED = GDPR_PAGE.replace('<p class="oj-normal">a)</p>', '<p class="oj-normal">a.</p>', 1)


def _cellar(page):
    """Cellar serving `page` for the GDPR; every other act and source is down."""
    def answer(request):
        if request.url.host == "publications.europa.eu" and "32016R0679" in request.url.path:
            return httpx.Response(200, text=page)
        return httpx.Response(503)

    return httpx.Client(transport=httpx.MockTransport(answer))


@pytest.fixture
def real_fetch(monkeypatch):
    """conftest disables fetch_html so that no test reaches the network; the
    clients these tests pass answer only from the recorded page."""
    monkeypatch.setattr(law_fetcher, "fetch_html", REAL_FETCH_HTML)


def test_the_derived_page_lacks_only_the_point():
    assert GDPR_PAGE_POINT_A_UNLABELLED != GDPR_PAGE
    texts = law_fetcher.parse_articles(GDPR_PAGE_POINT_A_UNLABELLED, ("5", "7"))
    assert "5(1)" in texts and "5(1)(b)" in texts
    assert "5(1)(a)" not in texts


def test_end_to_end_a_point_the_parser_missed_is_not_verified(cache, real_fetch):
    law = check(scan_result(rejected=["doubleclick.net"]), cache=cache, now=DAY1,
                client=_cellar(GDPR_PAGE_POINT_A_UNLABELLED))

    status = _status(law, GDPR)
    assert (status.source, status.origin) == ("unavailable", None)
    assert (status.tried, status.failure) == ("Cellar", "not_in_text")
    assert _citation(law, "5(1)(a)").sha256 is None


def test_end_to_end_the_recorded_page_is_verified(cache, real_fetch):
    law = check(scan_result(rejected=["doubleclick.net"]), cache=cache, now=DAY1, client=_cellar(GDPR_PAGE))

    status = _status(law, GDPR)
    assert (status.source, status.origin) == ("verified", "Cellar")
    assert (status.tried, status.failure, status.reason) == (None, None, None)
    assert _citation(law, "5(1)(a)").sha256 is not None


# ─── statuses name the source that was tried ─────────────────────────────────

def test_a_status_says_the_source_answered_without_the_text(cache, monkeypatch):
    """The CLI printed "EUR-Lex unreachable" for this: Cellar was reached, and
    only the reference cited was missing from its page."""
    monkeypatch.setattr(law_fetcher, "fetch_provisions_from", _fake_fetch())
    check(scan_result(rejected=["doubleclick.net"]), cache=cache, now=DAY1)
    monkeypatch.setattr(law_fetcher, "fetch_provisions_from", _whole_articles_only)
    status = _status(check(scan_result(rejected=["doubleclick.net"]), cache=cache, now=DAY2), GDPR)

    assert (status.source, status.tried, status.failure) == ("cache", "Cellar", "not_in_text")
    assert status.reason == "Cellar answered without the text cited"


def test_a_status_names_both_sources_when_neither_answered(cache, monkeypatch):
    def down(act, articles, now=None, **kwargs):
        raise LawFetchError("Cellar answered HTTP 503; and EUR-Lex answered HTTP 202", source="Cellar and EUR-Lex")

    monkeypatch.setattr(law_fetcher, "fetch_provisions_from", down)
    status = _status(check(scan_result(rejected=["doubleclick.net"]), cache=cache, now=DAY1), GDPR)

    assert (status.source, status.tried, status.failure) == ("unavailable", "Cellar and EUR-Lex", "unreachable")
    assert status.reason == "Cellar and EUR-Lex unreachable"


def test_a_status_without_a_named_source_falls_back_to_the_act_source(cache, monkeypatch):
    def down(act, articles, now=None, **kwargs):
        raise LawFetchError("offline")

    monkeypatch.setattr(law_fetcher, "fetch_provisions_from", down)
    law = check(scan_result(rejected=["doubleclick.net"]), cache=cache, now=DAY1)

    assert _status(law, GDPR).reason == f"{GDPR.source} unreachable"
    assert _status(law, CONSUMER_CODE).reason == "Normattiva unreachable"


# ─── a cache that cannot be written ──────────────────────────────────────────

@pytest.fixture
def read_only_cache(cache):
    """Call it after a first audit: it makes `cache` read-only, the file (what
    stops os.replace on Windows) and its folder (what stops it on POSIX)."""
    import os
    import stat

    def freeze():
        cache.path.chmod(stat.S_IREAD)
        cache.path.parent.chmod(stat.S_IREAD | stat.S_IEXEC)
        try:
            cache.update({}, checked_at="2026-10-01T09:30:00Z")
        except OSError:
            return
        pytest.skip("this user can write a read-only file (root?)")

    yield freeze
    os.chmod(cache.path.parent, stat.S_IRWXU)
    if cache.path.exists():
        os.chmod(cache.path, stat.S_IREAD | stat.S_IWRITE)


def test_a_changed_text_is_reported_when_the_cache_cannot_be_written(cache, read_only_cache, monkeypatch):
    """The change used to be computed only by a successful save: with the cache
    read-only, a law whose text changed was cited with no warning."""
    monkeypatch.setattr(law_fetcher, "fetch_provisions_from", _fake_fetch())
    first = check(scan_result(rejected=["doubleclick.net"]), cache=cache, now=DAY1)
    read_only_cache()

    monkeypatch.setattr(law_fetcher, "fetch_provisions_from", _fake_fetch(" (modificato)"))
    law = check(scan_result(rejected=["doubleclick.net"]), cache=cache, now=DAY2)

    assert law.changed["GDPR art. 5(1)(a)"] == _citation(first, "5(1)(a)").sha256
    assert _citation(law, "5(1)(a)").sha256 != _citation(first, "5(1)(a)").sha256
    assert _citation(law, "5(1)(a)").version_date == "2026-10-01"


def test_an_unchanged_text_keeps_its_version_date_when_the_cache_cannot_be_written(
    cache, read_only_cache, online
):
    """The date of a wording is its first download, saved or not."""
    check(scan_result(rejected=["doubleclick.net"]), cache=cache, now=DAY1)
    read_only_cache()

    law = check(scan_result(rejected=["doubleclick.net"]), cache=cache, now=DAY2)

    assert law.changed == {}
    assert _citation(law, "5(1)(a)").version_date == "2026-09-19"
