"""
CLI tests with a mocked scanner (no browser).
"""
from unittest.mock import patch

import pytest
from rich.console import Console
from typer.testing import CliRunner

import cookieradar.cli as cli
import cookieradar.scanner as scanner
from cookieradar.cli import app
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

    assert res.exit_code == 0, res.output
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
    f.write_text("example.com\n")

    def build(r):
        r.post_reject.trackers = [_tracker("c.facebook.com")]

    res = _invoke(["batch", str(f)], build)

    assert res.exit_code == 0, res.output
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

    assert res.exit_code == 0, res.output
    assert f"?q={MARKUP}" in res.output
    assert f"evil{MARKUP}.doubleclick.net" in res.output


def test_batch_error_message_with_markup_does_not_stop_batch(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text("first.example\nsecond.example\n")
    seen = []

    async def scan(url, **kwargs):
        seen.append(url)
        if "first" in url:
            raise RuntimeError(f"net::ERR {MARKUP}")
        return ScanResult(url=url)

    res = _invoke(["batch", str(f)], scan=scan)

    assert res.exit_code == 0, res.output
    assert seen == ["https://first.example", "https://second.example"]
    assert f"net::ERR {MARKUP}" in res.output


def test_batch_url_with_markup(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text(f"https://example.com/{MARKUP}\n")

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

    assert res.exit_code == 1
    assert not isinstance(res.exception, RuntimeError)
    assert "Executable doesn't exist [/]" in res.output


def test_batch_shows_session_errors(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text("example.com\n")

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

    assert res.exit_code == 0, res.output
    assert "VIOLATION" not in res.output
    assert "No trackers loaded after rejection" not in res.output
    assert "Session 3 — Post-reject NOT APPLIED" in res.output
    assert "reject button not found" in res.output


def test_audit_accept_not_applied_is_reported():
    def build(r):
        r.post_accept.consent_clicked = False

    res = _invoke(["audit", "example.com"], build)

    assert res.exit_code == 0, res.output
    assert "Session 2 — Post-accept NOT APPLIED" in res.output
    assert "accept button not found" in res.output


def test_batch_reject_not_applied_is_unverified(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text("example.com\n")

    def build(r):
        r.post_reject.trackers = [_tracker("doubleclick.net")]
        r.post_reject.consent_clicked = False

    res = _invoke(["batch", str(f)], build)

    assert res.exit_code == 0, res.output
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
    from cookieradar.cli import normalize_url
    assert normalize_url(raw) == expected


@pytest.mark.parametrize("raw", [
    "file:///etc/passwd", "ftp://example.com", "chrome://settings",
    "about:blank", "javascript:alert(1)", "data:text/html,x", "", "   ",
])
def test_normalize_url_rejects_other_schemes(raw):
    from cookieradar.cli import normalize_url
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

    assert res.exit_code == 0, res.output
    assert seen == ["https://httpbin.org"]


def test_audit_rejects_file_url():
    seen = []
    res = _invoke(["audit", "file:///etc/passwd"], scan=_recording_scan(seen))

    assert res.exit_code != 0
    assert seen == []
    assert "Unsupported URL scheme" in res.output


def test_batch_skips_invalid_url_and_continues(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text("httpbin.org\nfile:///etc/passwd\nexample.com\n")
    seen = []

    res = _invoke(["batch", str(f)], scan=_recording_scan(seen))

    assert res.exit_code == 0, res.output
    assert seen == ["https://httpbin.org", "https://example.com"]
    assert "Unsupported URL scheme" in res.output


# ─── L8: comments and blank lines in batch files ────────────────────────────

def test_batch_ignores_indented_comments_and_blank_lines(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text("# header\n  # commento indentato\n\t# tab\n\n   \nexample.com\n")
    seen = []

    res = _invoke(["batch", str(f)], scan=_recording_scan(seen))

    assert res.exit_code == 0, res.output
    assert seen == ["https://example.com"]
    assert "Loaded 1 URLs" in res.output


# ─── W7: unreadable batch files give a clean error, not a traceback ─────────

def _assert_clean_failure(res, *fragments):
    assert res.exit_code == 2, res.output
    assert isinstance(res.exception, SystemExit), repr(res.exception)
    assert "Traceback" not in res.output
    for fragment in fragments:
        assert fragment in res.output


def test_batch_missing_file(tmp_path):
    missing = tmp_path / "nope[/b].txt"
    res = _invoke(["batch", str(missing)])

    _assert_clean_failure(res, "Cannot read", "nope[/b].txt")


def test_batch_directory_instead_of_file(tmp_path):
    res = _invoke(["batch", str(tmp_path)])

    _assert_clean_failure(res, "Cannot read")


@pytest.mark.skipif(__import__("os").geteuid() == 0, reason="root ignores file permissions")
def test_batch_unreadable_file(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text("example.com\n")
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

    assert res.exit_code == 0, res.output
    assert seen == ["https://example.com"]
