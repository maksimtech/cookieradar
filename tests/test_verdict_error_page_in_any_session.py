"""
An error page in any session means the site was not measured, whichever session it was.

`page_not_served` read the pre-consent status only. Measured on 2026-10-09 in
the batch run of the demo (_analisi/demo/cookieradar/batch.cli.txt), on
www.zalando.it: the pre-consent session got no response at all within the
timeout (status None, no request seen), and the post-reject session got the
Akamai edge's 403 page, with a Usercentrics banner over it and Google Tag
Manager loading once "Solo gli essenziali" was clicked and the page reloaded.
The verdict came out as

    VIOLATION — pre: 0 trackers, post-reject: 2 trackers
      → googlesyndication.com (new after rejection)
      → googletagmanager.com (new after rejection)

a violation assembled from one session that saw nothing and one that saw an
error page. The verdict rests on session 3; when session 3 is an error page
there is nothing to rest it on.

The results below are built the way `scan()` builds them, with the statuses,
errors and requests those sessions had. No stand-in.
"""
from io import StringIO

from rich.console import Console

from cookieradar.cli import ExitCode, _render_report, _verdict
from cookieradar.law_checker import findings_of, notes_of
from cookieradar.scanner import ScanResult, SessionResult, TrackerRequest, page_not_served


def _tracker(domain):
    return TrackerRequest(f"https://www.{domain}/x", domain, "script", 0.0)


def zalando_batch_run() -> ScanResult:
    result = ScanResult(url="https://www.zalando.it")
    result.pre_consent = SessionResult("pre-consent", status=None,
                                       error="Page.goto: Timeout 30000ms exceeded.")
    result.post_accept = SessionResult("post-accept", status=None, consent_clicked=True,
                                       error="Page.goto: Timeout 30000ms exceeded.",
                                       trackers=[_tracker("googletagmanager.com")])
    result.post_reject = SessionResult("post-reject", status=403, consent_clicked=True,
                                       trackers=[_tracker("googlesyndication.com"),
                                                 _tracker("googletagmanager.com")])
    return result


def test_an_error_page_in_the_post_reject_session_is_not_served():
    assert page_not_served(zalando_batch_run()) is True


def test_the_verdict_is_not_measured_and_not_a_violation():
    assert _verdict(zalando_batch_run()) is ExitCode.ERROR


def test_no_finding_is_drawn_from_it():
    result = zalando_batch_run()

    assert findings_of(result) == {}
    assert any("NOT MEASURED" in note for note in notes_of(result))


def test_the_report_names_the_status_and_the_session():
    out = Console(file=StringIO(), width=200, force_terminal=False)
    _render_report(out, "https://www.zalando.it", zalando_batch_run())
    text = out.file.getvalue()

    assert "NOT MEASURED" in text
    assert "HTTP 403" in text
    assert "post-reject" in text
    assert "VIOLATION" not in text
    assert "new after rejection" not in text


def test_a_site_served_in_every_session_is_unchanged():
    result = zalando_batch_run()
    for session in (result.pre_consent, result.post_accept, result.post_reject):
        session.status = 200

    assert page_not_served(result) is False
    assert _verdict(result) is ExitCode.VIOLATION


def test_a_session_with_no_response_at_all_is_not_an_error_page():
    """None is a timeout, which the session already reports; it is not a status
    and must not be read as one."""
    result = zalando_batch_run()
    result.post_reject.status = None

    assert page_not_served(result) is False
