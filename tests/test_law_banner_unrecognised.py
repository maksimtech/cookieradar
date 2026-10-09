"""
CookieRadar — the UNVERIFIED note must not contradict the report above it.

Measured on 2026-10-09 on it.wikipedia.org, www.subito.it and www.muenchen.de
(the demo audits in _analisi/demo/cookieradar): every session printed
"Banner found: ✅", neither button was clicked, and the law section then said
"UNVERIFIED: no cookie banner was found". Both lines were produced from the same
`ScanResult`, and one of them is false whichever way the banner heuristic was
right. On subito.it the banner was Didomi's, real and unclicked; on Wikipedia
the match was a site notice with "banner" in its class name and there is no
cookie banner at all. The note cannot tell those apart, and it must not claim
to: what it knows is that no refusal control was recognised.

The `ScanResult` is built the way `scan()` builds it; no stand-in.
"""
from cookieradar.law_checker import UNRECOGNISED_BANNER_NOTE, UNVERIFIED_NOTE, notes_of
from cookieradar.scanner import ScanResult, SessionResult, TrackerRequest


def _result(banner_found: bool) -> ScanResult:
    def session(name):
        return SessionResult(
            session=name,
            trackers=[TrackerRequest("https://www.googletagmanager.com/gtm.js", "googletagmanager.com",
                                     "script", 0.0)],
            banner_found=banner_found,
            consent_clicked=False,
        )
    return ScanResult(url="https://www.subito.it", pre_consent=session("pre-consent"),
                      post_accept=session("post-accept"), post_reject=session("post-reject"))


def test_when_something_like_a_banner_was_seen_the_note_does_not_deny_it():
    notes = notes_of(_result(banner_found=True))

    assert notes == [UNRECOGNISED_BANNER_NOTE]
    assert "no cookie banner was found" not in " ".join(notes)


def test_the_note_says_what_was_not_recognised():
    note = UNRECOGNISED_BANNER_NOTE.lower()

    assert "unverified" in note
    assert "banner" in note
    assert "no refusal control" in note or "no reject" in note
    assert "no provision is cited" in note


def test_when_nothing_like_a_banner_was_seen_the_old_note_stands():
    assert notes_of(_result(banner_found=False)) == [UNVERIFIED_NOTE]


def test_a_banner_seen_in_one_session_only_still_counts():
    """The heuristic is per session and a banner can be late: one sighting is
    enough to make "no banner was found" false."""
    result = _result(banner_found=False)
    result.post_reject.banner_found = True

    assert notes_of(result) == [UNRECOGNISED_BANNER_NOTE]
