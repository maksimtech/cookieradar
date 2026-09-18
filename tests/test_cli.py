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
