"""
CookieRadar — "no refusal" is cited only where the banner offered one choice.

Measured on 2026-10-17. On aranzulla.it (iubenda) the refusal is the banner's
"×", whose text says "Chiudi questa informativa per continuare senza
accettare"; on repubblica.it it is "Rifiuta e abbonati". CookieRadar recognised
neither, clicked "Accetta", and cited GDPR art. 4(11) — consent freely given —
with ePrivacy art. 5(3) against both sites, under the title "Accept was applied
and no refusal control was found".

The finding rested on two observations, the accept click and the absence of a
recognised refusal, and the second is a statement about this tool's labels
rather than about the banner. The provision is about a choice with one option.
So the finding now also needs the banner to have had nothing else to click
beside Accept, counted in the session where Accept was clicked; a banner with
other controls, none recognised, is reported as exactly that, without a
citation. A refusal offered only with a subscription is named for what it is:
whether that leaves consent free is not something an audit of requests can
settle, and the note says so instead of citing either way.

The `ScanResult` is built the way `scan()` builds it; no stand-in. The browser
side — the counting, the X, the subscription label — is in
tests/test_integration_cmp.py, against the banners captured that day.
"""
from cookieradar.law_checker import findings_of, notes_of, refusal_not_offered
from cookieradar.scanner import ScanResult, SessionResult, TrackerRequest

ADS = [TrackerRequest("https://securepubads.g.doubleclick.net/tag/js/gpt.js", "doubleclick.net",
                      "script", 0.0)]


def _accepted_not_refused(other_controls: int | None, pay_to_refuse: str = "") -> ScanResult:
    def session(name, clicked, trackers=()):
        return SessionResult(session=name, trackers=list(trackers), banner_found=True,
                             consent_clicked=clicked)

    result = ScanResult(
        url="https://www.aranzulla.it",
        pre_consent=session("pre-consent", False),
        post_accept=session("post-accept", True, ADS),
        post_reject=session("post-reject", False, ADS),
    )
    result.post_accept.other_controls = other_controls
    result.post_reject.pay_to_refuse = pay_to_refuse
    return result


def test_accept_as_the_only_control_is_still_the_finding():
    result = _accepted_not_refused(other_controls=0)

    assert refusal_not_offered(result)
    assert "no_refusal" in findings_of(result)


def test_a_banner_with_other_controls_is_not_cited_for_offering_no_refusal():
    """aranzulla.it: five controls beside Accept, the refusal among them."""
    result = _accepted_not_refused(other_controls=5)

    assert not refusal_not_offered(result)
    assert findings_of(result) == {}


def test_the_note_says_what_was_there_and_not_recognised():
    notes = " ".join(notes_of(_accepted_not_refused(other_controls=5)))

    assert "5 other controls" in notes
    assert "none was recognised as a refusal" in notes
    assert "no refusal control was found" not in notes
    assert "no provision is cited" in notes


def test_one_other_control_is_said_in_the_singular():
    assert "1 other control beside" in " ".join(notes_of(_accepted_not_refused(other_controls=1)))


def test_controls_that_could_not_be_counted_are_no_evidence_of_a_single_choice():
    """None: the accept button was clicked but nothing around it could be read,
    which proves nothing about what else the banner offered."""
    result = _accepted_not_refused(other_controls=None)

    assert findings_of(result) == {}
    assert notes_of(result) and "no refusal control was found" not in " ".join(notes_of(result))


def test_a_refusal_sold_with_a_subscription_is_named_and_not_cited():
    """repubblica.it: "Accetta" and "Rifiuta e abbonati". The banner does offer
    to refuse; what it asks for in exchange is the question, and not this
    audit's to answer."""
    result = _accepted_not_refused(other_controls=3, pay_to_refuse="Rifiuta e abbonati")

    assert findings_of(result) == {}
    note = " ".join(notes_of(result))
    assert "Rifiuta e abbonati" in note
    assert "subscription" in note
    assert "no provision is cited" in note


def test_a_refusal_sold_with_a_subscription_is_not_no_refusal_even_alone():
    """Whatever the count says, a refusal is on the banner, and "no refusal
    control was found" would be false about it: the subscription label decides."""
    result = _accepted_not_refused(other_controls=0, pay_to_refuse="Rifiuta e abbonati")

    assert not refusal_not_offered(result)
    assert "no_refusal" not in findings_of(result)
