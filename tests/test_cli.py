"""
CLI tests with a mocked scanner (no browser).
"""
import os
import subprocess
import sys
from unittest.mock import patch

import pytest
from rich.console import Console
from typer.testing import CliRunner

import cookieradar
import cookieradar.cli as cli
import cookieradar.scanner as scanner
from cookieradar.cli import app, normalize_url
from cookieradar.scanner import ScanResult, TrackerRequest

runner = CliRunner()


def _tracker(domain, url=None):
    return TrackerRequest(url=url or f"https://{domain}/x", domain=domain, resource_type="script", timestamp=0.0)


def _fake_scan(build):
    async def fake(url, **kwargs):
        r = ScanResult(url=url)
        # By default the consent buttons were found and clicked
        r.post_accept.consent_clicked = True
        r.post_reject.consent_clicked = True
        build(r)
        return r
    return fake


def _invoke(args, build=lambda r: None, scan=None):
    # Wide console so Rich tables don't wrap the values under test
    with patch.object(scanner, "scan", scan or _fake_scan(build)), patch.object(cli, "console", Console(width=250)):
        return runner.invoke(app, args)


# ─── G1: violations = everything loaded after rejection ─────────────────────

def test_audit_reports_persistent_and_new_trackers():
    def build(r):
        r.pre_consent.trackers = [_tracker("a.doubleclick.net"), _tracker("b.hotjar.com")]
        r.post_reject.trackers = [_tracker("b.hotjar.com"), _tracker("c.facebook.com")]

    res = _invoke(["audit", "example.com"], build)

    assert res.exit_code == 1, res.output
    assert "VIOLATION" in res.output
    assert "b.hotjar.com" in res.output.split("VIOLATION", 1)[1]
    assert "c.facebook.com" in res.output.split("VIOLATION", 1)[1]
    assert "a.doubleclick.net" not in res.output.split("VIOLATION", 1)[1]


def test_audit_no_violation_when_post_reject_clean():
    def build(r):
        r.pre_consent.trackers = [_tracker("a.doubleclick.net")]

    res = _invoke(["audit", "example.com"], build)

    assert res.exit_code == 0, res.output
    assert "VIOLATION" not in res.output


def test_batch_reports_tracker_new_after_rejection(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text("example.com\n", encoding="utf-8")

    def build(r):
        r.post_reject.trackers = [_tracker("c.facebook.com")]

    res = _invoke(["batch", str(f)], build)

    assert res.exit_code == 1, res.output  # VIOLATION
    assert "VIOLATION" in res.output
    assert "c.facebook.com" in res.output


# ─── G3: external data must never be parsed as Rich markup ──────────────────

MARKUP = "[/b][link=https://evil.example]x[/link][/]"


def test_audit_url_argument_with_markup():
    res = _invoke(["audit", f"https://example.com/{MARKUP}"])

    assert res.exit_code == 0, res.output
    assert f"https://example.com/{MARKUP}" in res.output


def test_audit_tracker_url_and_domain_with_markup():
    def build(r):
        t = _tracker(f"evil{MARKUP}.doubleclick.net", url=f"https://a.net/?q={MARKUP}")
        r.pre_consent.trackers = [t]
        r.post_reject.trackers = [t]

    res = _invoke(["audit", "example.com"], build)

    assert res.exit_code == 1, res.output  # VIOLATION
    assert f"?q={MARKUP}" in res.output
    assert f"evil{MARKUP}.doubleclick.net" in res.output


def test_batch_error_message_with_markup_does_not_stop_batch(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text("first.example\nsecond.example\n", encoding="utf-8")
    seen = []

    async def scan(url, **kwargs):
        seen.append(url)
        if "first" in url:
            raise RuntimeError(f"net::ERR {MARKUP}")
        return ScanResult(url=url)

    res = _invoke(["batch", str(f)], scan=scan)

    assert res.exit_code == 3, res.output  # one URL failed
    assert seen == ["https://first.example", "https://second.example"]
    assert f"net::ERR {MARKUP}" in res.output


def test_batch_url_with_markup(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text(f"https://example.com/{MARKUP}\n", encoding="utf-8")

    res = _invoke(["batch", str(f)])

    assert res.exit_code == 0, res.output
    assert f"https://example.com/{MARKUP}" in res.output


# ─── G4: errors are reported, never crash the CLI ───────────────────────────

def test_audit_shows_session_error_and_incomplete_warning():
    def build(r):
        r.post_reject.error = "Timeout 30000ms exceeded [/]"

    res = _invoke(["audit", "example.com"], build)

    assert res.exit_code == 0, res.output
    assert "Timeout 30000ms exceeded [/]" in res.output
    assert "incomplete" in res.output


def test_audit_scan_failure_exits_cleanly():
    async def scan(url, **kwargs):
        raise RuntimeError("BrowserType.launch: Executable doesn't exist [/]")

    res = _invoke(["audit", "example.com"], scan=scan)

    assert res.exit_code == 3
    assert not isinstance(res.exception, RuntimeError)
    assert "Executable doesn't exist [/]" in res.output


def test_batch_shows_session_errors(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text("example.com\n", encoding="utf-8")

    def build(r):
        r.pre_consent.error = "Timeout 30000ms exceeded."

    res = _invoke(["batch", str(f)], build)

    assert res.exit_code == 0, res.output
    assert "pre-consent: Timeout 30000ms exceeded." in res.output


# ─── L3: failed accept/reject must be reported, not presented as done ───────

def test_audit_reject_not_applied_gives_no_verdict():
    def build(r):
        r.pre_consent.trackers = [_tracker("doubleclick.net")]
        r.post_reject.trackers = [_tracker("doubleclick.net")]
        r.post_reject.consent_clicked = False

    res = _invoke(["audit", "example.com"], build)

    assert res.exit_code == 2, res.output  # UNVERIFIED
    assert "VIOLATION" not in res.output
    assert "No trackers loaded after rejection" not in res.output
    assert "Session 3 — Post-reject NOT APPLIED" in res.output
    assert "reject button not found" in res.output


def test_the_report_weighs_a_banner_that_only_accepts():
    """The asymmetry has to reach the summary, not sit three screens up.

    Before this, a site whose banner accepted and could not refuse produced the
    same closing lines as a site whose banner was never found: UNVERIFIED and
    nothing else. The two deserve different endings.
    """
    def build(r):
        for s in (r.pre_consent, r.post_accept, r.post_reject):
            s.banner_found = True
        r.post_accept.consent_clicked = True
        r.post_accept.trackers = [_tracker("adobedtm.com"), _tracker("demdex.net")]
        r.post_reject.consent_clicked = False

    res = _invoke(["audit", "example.com"], build)

    assert "accept" in res.output.lower()
    assert "no refusal control was found" in res.output.lower()


def test_a_banner_never_found_does_not_get_the_refusal_finding():
    def build(r):
        for s in (r.pre_consent, r.post_accept, r.post_reject):
            s.banner_found = False
        r.post_accept.consent_clicked = False
        r.post_reject.consent_clicked = False

    res = _invoke(["audit", "example.com"], build)

    assert "no refusal control was found" not in res.output.lower()


def test_on_an_error_page_no_session_shows_a_clean_table():
    """All three describe the same 364-byte error page, so none of them gets a
    tick. The summary saying NOT MEASURED while the tables say "No trackers
    detected" is the contradiction this closes."""
    def build(r):
        for session in (r.pre_consent, r.post_accept, r.post_reject):
            session.status = 403
        r.post_reject.consent_clicked = False

    res = _invoke(["audit", "example.com"], build)

    assert "No trackers detected" not in res.output
    assert res.output.lower().count("error page") >= 2


def test_on_an_error_page_no_provision_is_cited_and_the_reason_is_the_page():
    """Not "no banner was found": that is a claim about a site nobody saw."""
    def build(r):
        for session in (r.pre_consent, r.post_accept, r.post_reject):
            session.status = 403
        r.post_reject.consent_clicked = False

    res = _invoke(["audit", "example.com"], build)

    assert "no cookie banner was found" not in res.output
    assert "NOT MEASURED" in res.output

def test_a_page_that_was_never_served_is_not_a_measurement():
    """Measured on canon.it, 2026-09-26: 403 Access Denied from the Akamai
    edge, 364 bytes, the same with and without a browser User-Agent. What the
    headless browser loaded was an error page, and the report said
    "Trackers measured: 0 before consent" — a number for a visit that did not
    happen.

    An error page has no trackers and no banner, and saying so as a finding is
    the strongest possible claim built out of never having looked.
    """
    def build(r):
        r.pre_consent.status = 403
        r.post_accept.status = 403
        r.post_reject.status = 403
        r.post_reject.consent_clicked = False

    res = _invoke(["audit", "example.com"], build)

    assert "403" in res.output
    assert "0 before consent" not in res.output
    assert "not measured" in res.output.lower() or "could not" in res.output.lower()


def test_a_page_that_was_never_served_exits_as_an_error():
    """Not UNVERIFIED: that means the site was seen and the refusal could not
    be exercised. Here nothing was seen at all, and a gate treating 2 as
    "inconclusive but fine" would wave through a site nobody audited."""
    def build(r):
        r.pre_consent.status = 403
        r.post_reject.consent_clicked = False

    res = _invoke(["audit", "example.com"], build)

    assert res.exit_code == 3, res.output


def test_a_served_page_still_reports_its_numbers():
    """The guard against over-correcting. A site that answers 200 and loads
    nothing before consent has been measured, and that is worth saying."""
    def build(r):
        r.pre_consent.status = 200
        r.post_accept.status = 200
        r.post_accept.trackers = [_tracker("a.example"), _tracker("b.example")]
        r.post_reject.status = 200
        r.post_reject.consent_clicked = False

    res = _invoke(["audit", "example.com"], build)

    assert "0 before consent" in res.output
    assert "2 after accepting" in res.output


def test_a_status_nobody_recorded_is_not_read_as_a_failure():
    """`status` is None when the navigation never produced a response object —
    a timeout, say, which the session already reports as an error. Treating
    the absence of a number as an error status would turn one failure into
    two."""
    def build(r):
        r.pre_consent.status = None
        r.post_accept.trackers = [_tracker("a.example")]
        r.post_reject.consent_clicked = False

    res = _invoke(["audit", "example.com"], build)

    assert res.exit_code == 2, res.output
    assert "0 before consent" in res.output


def test_a_session_that_never_happened_is_not_shown_as_clean():
    """Measured on kyoceradocumentsolutions.it, 2026-09-26.

    The banner was found and accept worked, but there was no reject button, so
    the third session never took place. It was printed as
    "Session 3 — Post-reject NOT APPLIED (0 unique trackers)" with a table
    saying "✅ No trackers detected" — a green tick for a rejection that never
    happened, three lines under a warning that it never happened.

    The page was loaded, so something was measured; what was not measured is
    the thing the session is named after.
    """
    def build(r):
        r.pre_consent.trackers = [_tracker("a.example")]
        r.post_accept.trackers = [_tracker("b.example")]
        r.post_reject.consent_clicked = False
        r.post_reject.trackers = []

    res = _invoke(["audit", "example.com"], build)

    assert res.exit_code == 2, res.output
    assert "No trackers detected" not in res.output, (
        "the only empty session is the one that never ran"
    )
    assert "nothing was rejected" in res.output.lower()


def test_a_session_that_did_happen_and_found_nothing_still_says_so():
    """The correction must not swallow a real result. A rejection that was
    applied and left nothing behind is the outcome this tool exists to
    confirm."""
    def build(r):
        r.pre_consent.trackers = [_tracker("a.example")]
        r.post_reject.consent_clicked = True
        r.post_reject.trackers = []

    res = _invoke(["audit", "example.com"], build)

    assert res.exit_code == 0, res.output
    assert "No trackers detected" in res.output


def test_an_accept_that_never_happened_gets_the_same_treatment():
    def build(r):
        r.pre_consent.trackers = [_tracker("a.example")]
        r.post_accept.consent_clicked = False
        r.post_accept.trackers = []
        r.post_reject.trackers = [_tracker("c.example")]

    res = _invoke(["audit", "example.com"], build)

    assert "nothing was accepted" in res.output.lower()


def test_the_unverified_summary_says_what_was_measured():
    """"Could not reject" is half the report. The other half is what the visit
    did establish, and on the site that prompted this it was the better half:
    nothing loaded before consent. A reader who sees only UNVERIFIED either
    scrolls back for it or leaves with nothing.
    """
    def build(r):
        r.pre_consent.trackers = []
        r.post_accept.trackers = [_tracker("a.example"), _tracker("b.example")]
        r.post_reject.consent_clicked = False

    res = _invoke(["audit", "example.com"], build)

    assert res.exit_code == 2, res.output
    assert "UNVERIFIED" in res.output
    assert "0 before consent" in res.output
    assert "2 after accepting" in res.output


def test_the_unverified_summary_is_not_a_clean_bill_of_health():
    """It says what was measured, and it must not let that read as a verdict:
    a site with no trackers before consent and an untested refusal is not a
    compliant site, it is a site that was half measured."""
    def build(r):
        r.pre_consent.trackers = []
        r.post_reject.consent_clicked = False

    res = _invoke(["audit", "example.com"], build)

    assert "compliant" not in res.output.lower()
    assert "not a verdict" in res.output.lower()


def test_audit_accept_not_applied_is_reported():
    def build(r):
        r.post_accept.consent_clicked = False

    res = _invoke(["audit", "example.com"], build)

    assert res.exit_code == 0, res.output
    assert "Session 2 — Post-accept NOT APPLIED" in res.output
    assert "accept button not found" in res.output


def test_batch_reject_not_applied_is_unverified(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text("example.com\n", encoding="utf-8")

    def build(r):
        r.post_reject.trackers = [_tracker("doubleclick.net")]
        r.post_reject.consent_clicked = False

    res = _invoke(["batch", str(f)], build)

    assert res.exit_code == 2, res.output  # UNVERIFIED
    assert "UNVERIFIED" in res.output
    assert "VIOLATION" not in res.output
    assert "reject button not found" in res.output


# ─── L4: real cookies shown in the report ───────────────────────────────────

def test_audit_shows_cookies():
    def build(r):
        r.pre_consent.cookies = [
            {"name": "_ga", "domain": ".example.com", "expires": 1893456000},
            {"name": "sess[/b]", "domain": "www.example.com", "expires": -1},
        ]

    res = _invoke(["audit", "example.com"], build)

    assert res.exit_code == 0, res.output
    assert "Cookies: 2" in res.output
    assert "_ga" in res.output and ".example.com" in res.output and "2030-01-01" in res.output
    assert "sess[/b]" in res.output and "session" in res.output


# ─── L7: scheme added when missing, only http(s) accepted ───────────────────

@pytest.mark.parametrize("raw,expected", [
    ("httpbin.org", "https://httpbin.org"),
    ("http-foo.it", "https://http-foo.it"),
    ("example.com/path?q=1", "https://example.com/path?q=1"),
    ("  example.com  ", "https://example.com"),
    ("localhost:8080", "https://localhost:8080"),
    ("http://example.com", "http://example.com"),
    ("HTTPS://Example.com/", "HTTPS://Example.com/"),
])
def test_normalize_url(raw, expected):
    assert normalize_url(raw) == expected


@pytest.mark.parametrize("raw", [
    "file:///etc/passwd", "ftp://example.com", "chrome://settings",
    "about:blank", "javascript:alert(1)", "data:text/html,x", "", "   ",
])
def test_normalize_url_rejects_other_schemes(raw):
    with pytest.raises(ValueError):
        normalize_url(raw)


def _recording_scan(seen):
    async def scan(url, **kwargs):
        seen.append(url)
        return ScanResult(url=url)
    return scan


def test_audit_adds_scheme_to_http_prefixed_host():
    seen = []
    res = _invoke(["audit", "httpbin.org"], scan=_recording_scan(seen))

    assert res.exit_code == 2, res.output  # _recording_scan: reject not clicked
    assert seen == ["https://httpbin.org"]


def test_audit_rejects_file_url():
    seen = []
    res = _invoke(["audit", "file:///etc/passwd"], scan=_recording_scan(seen))

    assert res.exit_code == 3
    assert seen == []
    assert "Unsupported URL scheme" in res.output


def test_batch_skips_invalid_url_and_continues(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text("httpbin.org\nfile:///etc/passwd\nexample.com\n", encoding="utf-8")
    seen = []

    res = _invoke(["batch", str(f)], scan=_recording_scan(seen))

    assert res.exit_code == 3, res.output  # one URL could not be audited
    assert seen == ["https://httpbin.org", "https://example.com"]
    assert "Unsupported URL scheme" in res.output


# ─── L8: comments and blank lines in batch files ────────────────────────────

def test_batch_ignores_indented_comments_and_blank_lines(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text("# header\n  # commento indentato\n\t# tab\n\n   \nexample.com\n", encoding="utf-8")
    seen = []

    res = _invoke(["batch", str(f)], scan=_recording_scan(seen))

    assert res.exit_code == 2, res.output  # _recording_scan: reject not clicked
    assert seen == ["https://example.com"]
    assert "Loaded 1 URLs" in res.output


# ─── W7: unreadable batch files give a clean error, not a traceback ─────────

def _assert_clean_failure(res, *fragments):
    assert res.exit_code == 3, res.output
    assert isinstance(res.exception, SystemExit), repr(res.exception)
    assert "Traceback" not in res.output
    for fragment in fragments:
        assert fragment in res.output


def test_batch_missing_file(tmp_path):
    # "[bold]" is Rich markup, so an unescaped filename loses it from the
    # message. The closing form "[/b]" would say the same thing, but Path()
    # reads its "/" as a separator: the name became "nope[\b].txt" on Windows
    # and the assertion could not match. An opening tag needs no slash.
    missing = tmp_path / "nope[bold].txt"
    res = _invoke(["batch", str(missing)])

    _assert_clean_failure(res, "Cannot read", "nope[bold].txt")


def test_batch_directory_instead_of_file(tmp_path):
    res = _invoke(["batch", str(tmp_path)])

    _assert_clean_failure(res, "Cannot read")


# geteuid() exists only on POSIX and this called it at import time, so on
# Windows the AttributeError took the whole module's collection down with it —
# 40-odd unrelated CLI cases stopped running. Windows also lets the owner read
# a file it has just chmod(0)'d, so there is nothing to assert there either.
_PERMISSIONS_ENFORCED = hasattr(os, "geteuid") and os.geteuid() != 0


@pytest.mark.skipif(not _PERMISSIONS_ENFORCED, reason="this OS does not enforce file permissions for the owner")
def test_batch_unreadable_file(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text("example.com\n", encoding="utf-8")
    f.chmod(0)

    res = _invoke(["batch", str(f)])

    _assert_clean_failure(res, "Cannot read")


def test_batch_non_utf8_file(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_bytes("caffè.it\n".encode("latin-1"))

    res = _invoke(["batch", str(f)])

    _assert_clean_failure(res, "not valid UTF-8")


def test_batch_utf8_bom_is_ignored(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_bytes("example.com\n".encode("utf-8-sig"))
    seen = []

    res = _invoke(["batch", str(f)], scan=_recording_scan(seen))

    assert res.exit_code == 2, res.output  # _recording_scan: reject not clicked
    assert seen == ["https://example.com"]


# ─── M7: single entry point for `python -m cookieradar` ─────────────────────

def test_python_dash_m_entry_point():
    proc = subprocess.run(
        [sys.executable, "-m", "cookieradar", "--help"],
        capture_output=True, text=True, timeout=60,
        encoding="utf-8", errors="replace",
    )

    assert proc.returncode == 0, proc.stderr
    assert "audit" in proc.stdout and "batch" in proc.stdout


# ─── M6: the spinner describes all three sessions ───────────────────────────

def test_audit_spinner_mentions_all_sessions():
    messages = []

    class RecordingConsole(Console):
        def status(self, status, *args, **kwargs):
            messages.append(str(status))
            return super().status(status, *args, **kwargs)

    with patch.object(scanner, "scan", _fake_scan(lambda r: None)), \
         patch.object(cli, "console", RecordingConsole(width=250)):
        res = runner.invoke(app, ["audit", "example.com"])

    assert res.exit_code == 0, res.output
    assert len(messages) == 1
    for session in ("pre-consent", "post-accept", "post-reject"):
        assert session in messages[0]


# ─── M1: --output saves the report, --lang is gone ──────────────────────────

def _violation(r):
    t = _tracker("doubleclick.net", url="https://stats.doubleclick.net/p?<script>alert(1)</script>")
    r.pre_consent.trackers = [t]
    r.post_reject.trackers = [t]


def test_audit_output_text(tmp_path):
    out = tmp_path / "report.txt"

    res = _invoke(["audit", "example.com", "-o", str(out)], _violation)

    assert res.exit_code == 1, res.output  # VIOLATION
    text = out.read_text(encoding="utf-8")
    assert "CookieRadar Report — https://example.com" in text
    assert "Session 3 — Post-reject" in text
    assert "VIOLATION" in text and "doubleclick.net" in text
    assert "\x1b[" not in text  # no ANSI escape codes in the file
    assert "Auditing" not in text  # progress messages are not part of the report
    assert str(out) in res.output


def test_audit_output_html_is_escaped(tmp_path):
    out = tmp_path / "report.html"

    res = _invoke(["audit", "example.com", "--output", str(out)], _violation)

    assert res.exit_code == 1, res.output  # VIOLATION
    html = out.read_text(encoding="utf-8")
    assert "<html" in html.lower()
    assert "VIOLATION" in html
    assert "<script>alert(1)</script>" not in html


def test_audit_output_unwritable_path(tmp_path):
    out = tmp_path / "missing-dir" / "report.txt"

    res = _invoke(["audit", "example.com", "-o", str(out)])

    assert res.exit_code == 3
    assert isinstance(res.exception, SystemExit)
    assert "Cannot write report" in res.output


@pytest.mark.parametrize("command", ["audit", "batch"])
def test_lang_option_removed(command):
    res = _invoke([command, "example.com", "--lang", "en"])

    assert res.exit_code == 3
    assert "No such option" in res.output


def test_batch_output_writes_one_report_per_url(tmp_path):
    urls = tmp_path / "urls.txt"
    urls.write_text("example.com\nhttps://example.com/a/b?x=1\nbroken.example\n", encoding="utf-8")
    out_dir = tmp_path / "reports"

    async def scan(url, **kwargs):
        if "broken" in url:
            raise RuntimeError("net::ERR_NAME_NOT_RESOLVED")
        r = ScanResult(url=url)
        r.post_accept.consent_clicked = r.post_reject.consent_clicked = True
        _violation(r)
        return r

    res = _invoke(["batch", str(urls), "-o", str(out_dir)], scan=scan)

    assert res.exit_code == 1, res.output  # VIOLATION outweighs the failed URL
    files = sorted(p.name for p in out_dir.iterdir())
    assert files == ["example.com.txt", "example.com_a_b_x_1.txt"]
    text = (out_dir / "example.com_a_b_x_1.txt").read_text(encoding="utf-8")
    assert "CookieRadar Report — https://example.com/a/b?x=1" in text
    assert "VIOLATION" in text


def test_batch_output_names_do_not_collide(tmp_path):
    urls = tmp_path / "urls.txt"
    urls.write_text("https://example.com/a\nhttp://example.com/a\n", encoding="utf-8")
    out_dir = tmp_path / "reports"

    res = _invoke(["batch", str(urls), "-o", str(out_dir)])

    assert res.exit_code == 0, res.output
    assert sorted(p.name for p in out_dir.iterdir()) == ["example.com_a-2.txt", "example.com_a.txt"]


# ─── Shutdown: Rich FileProxy must be flushed before interpreter teardown ───

_SHUTDOWN_SCRIPT = """
import sys
from unittest.mock import patch
from rich.console import Console
import cookieradar
import cookieradar.cli as cli
import cookieradar.scanner as scanner
from cookieradar.scanner import ScanResult

async def fake(url, **kwargs):
    # A library keeping a reference to sys.stdout keeps Rich's FileProxy
    # alive until module teardown; a partial line stays in its buffer.
    global held_stdout
    held_stdout = sys.stdout
    sys.stdout.write("partial-output")
    return ScanResult(url=url)

with patch.object(scanner, "scan", fake), \\
     patch.object(cli, "console", Console(force_terminal=True, width=250)):
    cli.app(["audit", "example.com"], standalone_mode=False)
"""


def test_audit_flushes_console_before_shutdown():
    proc = subprocess.run(
        [sys.executable, "-c", _SHUTDOWN_SCRIPT],
        capture_output=True, text=True, timeout=60,
        encoding="utf-8", errors="replace",
    )

    assert proc.returncode == 0, proc.stderr
    assert "sys.meta_path is None" not in proc.stderr
    assert "Exception ignored" not in proc.stderr
    assert "partial-output" in proc.stdout


# ─── --version ──────────────────────────────────────────────────────────────

def test_version_option():
    res = runner.invoke(app, ["--version"])

    assert res.exit_code == 0, res.output
    assert res.output == f"CookieRadar {cookieradar.__version__}\n"


def test_version_is_read_from_dunder_version():
    with patch.object(cookieradar, "__version__", "1999.01.1"):
        res = runner.invoke(app, ["--version"])

    assert res.output == "CookieRadar 1999.01.1\n"


# ─── Exit codes reflect the verdict ─────────────────────────────────────────
# 0 OK · 1 VIOLATION · 2 UNVERIFIED · 3 error

def _outcome(r, kind):
    if kind == "violation":
        r.post_reject.trackers = [_tracker("hotjar.com")]
    elif kind == "unverified":
        r.post_reject.consent_clicked = False


def _scan_by_host(outcomes):
    """Fake scan whose outcome depends on the host: ok, violation, unverified, error."""
    async def scan(url, **kwargs):
        kind = outcomes[url.removeprefix("https://")]
        if kind == "error":
            raise RuntimeError("net::ERR_NAME_NOT_RESOLVED")
        return await _fake_scan(lambda r: _outcome(r, kind))(url)
    return scan


@pytest.mark.parametrize("kind, code", [("ok", 0), ("violation", 1), ("unverified", 2), ("error", 3)])
def test_audit_exit_code_reflects_verdict(kind, code):
    res = _invoke(["audit", "example.com"], scan=_scan_by_host({"example.com": kind}))

    assert res.exit_code == code, res.output


def test_audit_invalid_url_exit_code():
    res = _invoke(["audit", "javascript:alert(1)"])

    assert res.exit_code == 3, res.output


def test_audit_unwritable_output_with_violation_still_exits_1(tmp_path):
    out = tmp_path / "missing-dir" / "report.txt"

    res = _invoke(["audit", "example.com", "-o", str(out)], lambda r: _outcome(r, "violation"))

    assert res.exit_code == 1, res.output
    assert "Cannot write report" in res.output


def test_usage_error_exit_code_is_not_unverified():
    res = _invoke(["audit", "example.com", "--no-such-option"])

    assert res.exit_code == 3, res.output
    assert "No such option" in res.output


@pytest.mark.parametrize("kinds, code", [
    (["ok", "ok"], 0),
    (["ok", "violation", "unverified", "error"], 1),
    (["ok", "unverified"], 2),
    (["ok", "error"], 3),
    (["unverified", "error"], 3),
])
def test_batch_exit_code_reflects_worst_verdict(tmp_path, kinds, code):
    outcomes = {f"site{i}.example": kind for i, kind in enumerate(kinds)}
    f = tmp_path / "urls.txt"
    f.write_text("\n".join(outcomes) + "\n", encoding="utf-8")

    res = _invoke(["batch", str(f)], scan=_scan_by_host(outcomes))

    assert res.exit_code == code, res.output
