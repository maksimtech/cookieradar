"""
CookieRadar — a saved report says when it was made, and by what.

The README calls the report "evidence of what the site did on a given day". The
file saved on 2026-10-09 for www.repubblica.it (the demo audits in
_analisi/demo/cookieradar) carried no day at all: the only dates in it were the
"Version of:" lines under the legal citations, which exist only when something
is cited, and nothing named the CookieRadar that produced it. A file opened a
year later, or forwarded to the site's owner, could not be placed in time.

No stand-in here: the report is rendered from a real `ScanResult`, the object
`scan()` returns, through the same functions `audit` uses.
"""
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from rich.console import Console

import cookieradar
from cookieradar.cli import _render_report, _save_report
from cookieradar.scanner import ScanResult


def _rendered(result) -> str:
    out = Console(file=StringIO(), width=200, force_terminal=False)
    _render_report(out, result.url, result)
    return out.file.getvalue()


def test_a_scan_result_records_when_it_was_made():
    before = datetime.now(UTC)
    result = ScanResult(url="https://www.repubblica.it")
    after = datetime.now(UTC)

    assert before <= result.scanned_at <= after
    assert result.scanned_at.tzinfo is not None, "a naive time cannot be placed in a time zone"


def test_the_report_states_the_day_and_hour_of_the_audit_in_utc():
    result = ScanResult(url="https://www.repubblica.it")
    result.scanned_at = datetime(2026, 10, 9, 12, 37, 5, tzinfo=UTC)

    text = _rendered(result)

    assert "2026-10-09 12:37 UTC" in text


def test_the_report_names_the_version_that_produced_it():
    text = _rendered(ScanResult(url="https://www.repubblica.it"))

    assert f"CookieRadar {cookieradar.__version__}" in text


def test_the_html_report_has_a_title_naming_the_site(tmp_path: Path):
    """A browser tab, a bookmark and an email attachment preview all show the
    <title>; Rich's default export has none, so they showed the file name."""
    out = tmp_path / "report.html"

    _save_report("https://www.repubblica.it", ScanResult(url="https://www.repubblica.it"), out)

    html = out.read_text(encoding="utf-8")
    assert "<title>CookieRadar — www.repubblica.it</title>" in html


def test_the_html_title_escapes_the_url(tmp_path: Path):
    out = tmp_path / "report.html"
    url = "https://example.com/</title><script>alert(1)</script>"

    _save_report(url, ScanResult(url=url), out)

    html = out.read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_the_text_report_carries_the_same_provenance(tmp_path: Path):
    out = tmp_path / "report.txt"
    result = ScanResult(url="https://example.com")
    result.scanned_at = datetime(2026, 10, 9, 12, 37, tzinfo=UTC)

    _save_report("https://example.com", result, out)

    text = out.read_text(encoding="utf-8")
    assert "2026-10-09 12:37 UTC" in text
    assert f"CookieRadar {cookieradar.__version__}" in text
