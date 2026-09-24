"""
CookieRadar — Cookie compliance auditor.
GDPR art.5/6/7 — pre-consent, post-reject, GTM analysis
"""
import asyncio
import io
import re
import sys
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from enum import IntEnum
from pathlib import Path

import typer
from rich import box
from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.text import Text
from typer.core import TyperGroup

from cookieradar.scanner import Violations, find_violations


def enable_utf8_output() -> None:
    """Make stdout and stderr accept characters the console cannot encode.

    On Windows the console code page is cp1252, and Python encodes output with
    it: the first emoji — the one in this CLI's own help text — ended the
    program with UnicodeEncodeError before any command had run. It was never
    the command failing, only the printing of its output.

    errors="replace" rather than "strict": a glyph the terminal cannot show
    should come out as a question mark, never as a traceback.

    Streams that cannot be reconfigured are left alone. pytest's capture and
    anything wrapping a pipe are not TextIOWrapper, and replacing them would
    break whatever is reading them; a cosmetic setting is not worth raising
    over, so this gives up quietly.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if encoding == "utf8":
            continue
        with suppress(ValueError, OSError):
            reconfigure(encoding="utf-8", errors="replace")

enable_utf8_output()



class ExitCode(IntEnum):
    """Process exit status: the verdict, so scripts and CI can act on it."""
    OK = 0
    VIOLATION = 1
    UNVERIFIED = 2
    ERROR = 3


def _worst(codes) -> ExitCode:
    """A violation found matters most; a URL not audited outweighs an unverified one."""
    for code in (ExitCode.VIOLATION, ExitCode.ERROR, ExitCode.UNVERIFIED):
        if code in codes:
            return code
    return ExitCode.OK


class _Group(TyperGroup):
    """Command-line usage errors exit with ERROR, not Click's 2 (= UNVERIFIED)."""

    def make_context(self, *args, **kwargs):
        with _usage_error_is_error():
            return super().make_context(*args, **kwargs)

    def invoke(self, ctx):
        with _usage_error_is_error():
            return super().invoke(ctx)


# Click's UsageError: bundled inside Typer by recent versions, so reach it
# through the public BadParameter instead of importing click.
_UsageError = next(c for c in typer.BadParameter.__mro__ if c.__name__ == "UsageError")


@contextmanager
def _usage_error_is_error():
    try:
        yield
    except _UsageError as e:
        e.exit_code = ExitCode.ERROR
        raise


app = typer.Typer(
    name="cookieradar",
    help="🍪 Cookie compliance auditor — GDPR art.5/6/7",
    add_completion=False,
    cls=_Group,
)

console = Console()


def _version_callback(value: bool):
    if value:
        import cookieradar  # read at call time, never a hardcoded copy

        typer.echo(f"CookieRadar {cookieradar.__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Show the version and exit",
    ),
):
    pass

_SCHEME_URL = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*)://")
# "about:blank", "javascript:…" — but not "localhost:8080" (colon + port)
_SCHEME_ONLY = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*):(?!\d)")


def normalize_url(url: str) -> str:
    """Add https:// when no scheme is given; only http(s) URLs are allowed."""
    url = url.strip()
    if not url:
        raise ValueError("Empty URL")
    match = _SCHEME_URL.match(url) or _SCHEME_ONLY.match(url)
    if not match:
        return f"https://{url}"
    if match.group(1).lower() not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {match.group(1)}")
    return url


@contextmanager
def _status(message: str):
    """console.status() that flushes output before the spinner stops.

    While the spinner runs Rich wraps sys.stdout/sys.stderr in a FileProxy and
    does not flush it when restoring them: a partial line left in its buffer
    is printed only when the proxy is garbage-collected, possibly during
    interpreter shutdown ("ImportError: sys.meta_path is None").
    """
    with console.status(message):
        try:
            yield
        finally:
            sys.stdout.flush()
            sys.stderr.flush()
    console.file.flush()


def _read_urls(path: str) -> list[str]:
    """Non-empty lines of the file, skipping comments (also indented ones)."""
    with open(path, encoding="utf-8-sig") as f:  # -sig: skip a Windows BOM
        lines = [line.strip() for line in f]
    return [line for line in lines if line and not line.startswith("#")]


def _print_session(out: Console, title: str, session):
    """Print session results."""
    table = Table(
        title=title,
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Tracker Domain", style="red")
    table.add_column("URL", style="dim", max_width=60)
    table.add_column("Type", style="yellow")

    seen = set()
    for t in session.trackers:
        if t.domain not in seen:
            seen.add(t.domain)
            table.add_row(Text(t.domain), Text(t.url[:60]), Text(t.resource_type))

    if not session.trackers:
        table.add_row("[green]✅ No trackers detected[/green]", "", "")

    out.print(table)
    out.print(f"[dim]Banner found: {'✅' if session.banner_found else '❌'}[/dim]")
    out.print(f"[dim]Cookies: {len(session.cookies)}[/dim]")
    if session.cookies:
        _print_cookies(out, session.cookies)
    if session.error:
        out.print(f"[yellow]⚠️  Error: {escape(session.error)}[/yellow]")
    out.print()


def _cookie_expiry(cookie: dict) -> str:
    expires = cookie.get("expires", -1)
    if expires is None or expires < 0:
        return "session"
    return datetime.fromtimestamp(expires, tz=UTC).strftime("%Y-%m-%d")


def _print_cookies(out: Console, cookies: list[dict]):
    table = Table(box=box.SIMPLE, show_header=True, header_style="dim")
    table.add_column("Cookie")
    table.add_column("Domain", style="dim")
    table.add_column("Expires", style="dim")
    for c in sorted(cookies, key=lambda c: (c.get("domain", ""), c.get("name", ""))):
        table.add_row(Text(c.get("name", "")), Text(c.get("domain", "")), Text(_cookie_expiry(c)))
    out.print(table)


def _session_errors(result) -> list:
    sessions = [result.pre_consent, result.post_accept, result.post_reject]
    return [s for s in sessions if s.error]


ACCEPT_NOT_APPLIED = "accept button not found: this session shows the page without consent"
REJECT_NOT_APPLIED = "reject button not found: this session is equivalent to pre-consent"


def _unique_domains(session) -> set[str]:
    return {t.domain for t in session.trackers}


def _print_consent_header(out: Console, label: str, style: str, session, not_applied: str):
    unique = len(_unique_domains(session))
    status = "" if session.consent_clicked else " NOT APPLIED"
    out.print(f"[bold {style}]{label}{status} ({unique} unique trackers)[/bold {style}]")
    if not session.consent_clicked:
        out.print(f"[yellow]⚠️  {not_applied}[/yellow]")


def _print_violations(out: Console, violations: Violations, indent: str):
    for d in sorted(violations.persistent):
        out.print(f"{indent}[red]→ {escape(d)}[/red] [dim](persists from pre-consent)[/dim]")
    for d in sorted(violations.new):
        out.print(f"{indent}[red]→ {escape(d)}[/red] [dim](new after rejection)[/dim]")


def _verdict(result) -> ExitCode:
    if not result.post_reject.consent_clicked:
        return ExitCode.UNVERIFIED
    return ExitCode.VIOLATION if find_violations(result).all else ExitCode.OK


def _render_report(out: Console, url: str, result, law=None):
    """Full report of the three sessions and the verdict, then the provisions
    applied when `law` (a law_checker result) is given."""
    out.print(f"\n[bold]📊 CookieRadar Report — {escape(url)}[/bold]\n")

    # Pre-consent
    pre = result.pre_consent
    out.print(f"[bold red]🔴 Session 1 — Pre-consent ({len(_unique_domains(pre))} unique trackers)[/bold red]")
    _print_session(out, "Pre-consent trackers", pre)

    # Post-accept
    post_acc = result.post_accept
    _print_consent_header(out, "🟡 Session 2 — Post-accept", "yellow", post_acc, ACCEPT_NOT_APPLIED)
    _print_session(out, "Post-accept trackers", post_acc)

    # Post-reject
    post_rej = result.post_reject
    _print_consent_header(out, "🟢 Session 3 — Post-reject", "green", post_rej, REJECT_NOT_APPLIED)
    _print_session(out, "Post-reject trackers", post_rej)

    # Summary
    violations = find_violations(result)
    verdict = _verdict(result)

    if verdict is ExitCode.UNVERIFIED:
        out.print(
            "[bold yellow]⚠️  UNVERIFIED — could not reject cookies, "
            "no verdict on post-reject trackers[/bold yellow]"
        )
    elif verdict is ExitCode.VIOLATION:
        out.print(f"[bold red]⚠️  VIOLATION — {len(violations.all)} tracker(s) loaded after rejection:[/bold red]")
        _print_violations(out, violations, "  ")
    else:
        out.print("[bold green]✅ No trackers loaded after rejection[/bold green]")

    if _session_errors(result):
        out.print("[yellow]⚠️  Result may be incomplete: some sessions reported errors[/yellow]")

    if law is not None:
        out.print()
        _print_law_check(law, out)


def _save_report(url: str, result, path: Path, law=None):
    """Write the report as HTML (.html/.htm) or plain text; raises OSError."""
    recorder = Console(file=io.StringIO(), record=True, width=120, force_terminal=True)
    _render_report(recorder, url, result, law)
    if path.suffix.lower() in (".html", ".htm"):
        recorder.save_html(str(path))
    else:
        recorder.save_text(str(path))


def _report_filename(url: str, used: set[str]) -> str:
    """Filesystem-safe, unique report name for a URL: https://a.com/b?x=1 → a.com_b_x_1.txt"""
    base = _SCHEME_URL.sub("", url)
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")[:100] or "report"
    name, n = base, 2
    while name in used:
        name, n = f"{base}-{n}", n + 1
    used.add(name)
    return f"{name}.txt"



def _law_check(subject, out=None, **context):
    """Run the law check; any failure is reported and never fails the command."""
    from cookieradar import law_checker

    try:
        return law_checker.check(subject, **context)
    except Exception as e:
        (out or console).print(f"[yellow]⚠️  Law check failed: {escape(str(e))}[/yellow]\n")
        return None


def _print_law_check(law, out=None) -> None:
    """Cite the provisions applied to the findings, with their SHA-256."""
    from cookieradar.law_checker import FINDING_TITLES, format_citation

    out = out or console
    if law is None or not (law.citations or law.notes):
        return

    out.print("[bold]⚖️  Provisions applied[/bold]")
    for status in law.acts:
        act = status.act
        name, source = escape(act.name), escape(act.source)
        if status.source == "verified":
            out.print(f"[dim]{name}: verified against {source} ({act.id_label} {escape(act.celex)})[/dim]")
        elif status.source == "cache":
            out.print(
                f"[yellow]{name}: {source} unreachable, "
                "text from the cached copy, not re-verified[/yellow]"
            )
        else:
            # The missing SHA-256 below is the consequence of this line, and
            # the two used to sit apart: a reader who saw the gap went looking
            # for a bug in the hashing. There is no verified text to hash, and
            # printing one anyway would assert a verification never made.
            out.print(
                f"[yellow]{name}: {source} unreachable and nothing cached, "
                "text not verifiable: the citations below have no SHA-256[/yellow]"
            )
        if act.note:
            out.print(f"[dim]  {escape(act.note)}[/dim]")
        if status.error:
            out.print(f"[dim]  {escape(status.error)}[/dim]")
    for provision, previous in law.changed.items():
        out.print(f"[yellow]⚠️  Il testo di {escape(provision)} è cambiato dall'ultimo audit[/yellow]")
        out.print(f"[dim]   precedente: {previous}[/dim]")
    for note in law.notes:
        out.print(f"[yellow]⚠️  {escape(note)}[/yellow]")

    out.print()
    finding = None
    for citation in law.citations:
        if citation.finding != finding:
            finding = citation.finding
            out.print(f"[bold]{escape(FINDING_TITLES[finding])}[/bold]")
            if law.evidence.get(finding):
                out.print(f"[dim]{escape(', '.join(law.evidence[finding]))}[/dim]")
        out.print(format_citation(citation), markup=False, highlight=False)
        out.print()


@app.command()
def audit(
    url: str = typer.Argument(..., help="URL to audit (e.g. https://tim.it)"),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="Run browser headless"),
    output: Path = typer.Option(None, "--output", "-o", help="Save report to file (.html for HTML, text otherwise)"),
):
    """
    Audit a website for cookie compliance.
    Runs 3 sessions: pre-consent, post-accept, post-reject+reload.
    """
    from cookieradar.scanner import scan

    try:
        url = normalize_url(url)
    except ValueError as e:
        console.print(f"[red]❌ {escape(str(e))}[/red]")
        raise typer.Exit(ExitCode.ERROR) from None

    console.print(f"\n[dim]Auditing [bold]{escape(url)}[/bold]...[/dim]")

    try:
        with _status("[cyan]Running 3 browser sessions: pre-consent, post-accept, post-reject...[/cyan]"):
            result = asyncio.run(scan(url, headless=headless))
    except Exception as e:
        console.print(f"[red]❌ Error: {escape(str(e))}[/red]")
        raise typer.Exit(ExitCode.ERROR) from None

    law = _law_check(result)
    _render_report(console, url, result, law)
    codes = {_verdict(result)}

    if output:
        try:
            _save_report(url, result, output, law)
        except OSError as e:
            console.print(f"[red]❌ Cannot write report {escape(str(output))}: {escape(e.strerror or str(e))}[/red]")
            codes.add(ExitCode.ERROR)
        else:
            console.print(f"\n[dim]Report saved to {escape(str(output))}[/dim]")

    raise typer.Exit(_worst(codes))


@app.command()
def batch(
    file: str = typer.Argument(..., help="File with URLs to audit (one per line)"),
    output: Path = typer.Option(None, "--output", "-o", help="Save one text report per URL in this directory"),
):
    """
    Audit multiple URLs from a file.
    """
    from cookieradar.scanner import scan

    try:
        urls = _read_urls(file)
    except UnicodeDecodeError:
        console.print(f"[red]❌ Cannot read {escape(file)}: not valid UTF-8[/red]")
        raise typer.Exit(ExitCode.ERROR) from None
    except OSError as e:
        console.print(f"[red]❌ Cannot read {escape(file)}: {escape(e.strerror or str(e))}[/red]")
        raise typer.Exit(ExitCode.ERROR) from None

    if output:
        try:
            output.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            console.print(f"[red]❌ Cannot create {escape(str(output))}: {escape(e.strerror or str(e))}[/red]")
            raise typer.Exit(ExitCode.ERROR) from None
    used_names: set[str] = set()
    codes: set[ExitCode] = set()

    console.print(f"\n[dim]Loaded {len(urls)} URLs from {escape(file)}[/dim]\n")

    for url in urls:
        try:
            url = normalize_url(url)
        except ValueError as e:
            console.print(f"[red]❌ {escape(url)}: {escape(str(e))}[/red]\n")
            codes.add(ExitCode.ERROR)
            continue
        console.print(f"[cyan]Auditing {escape(url)}...[/cyan]")
        try:
            result = asyncio.run(scan(url))
            pre = _unique_domains(result.pre_consent)
            rej = _unique_domains(result.post_reject)
            verdict = _verdict(result)
            codes.add(verdict)
            status = {
                ExitCode.OK: "✅ OK",
                ExitCode.VIOLATION: "🔴 VIOLATION",
                ExitCode.UNVERIFIED: "⚠️  UNVERIFIED",
            }[verdict]
            console.print(f"  {status} — pre: {len(pre)} trackers, post-reject: {len(rej)} trackers")
            if verdict is not ExitCode.UNVERIFIED:
                _print_violations(console, find_violations(result), "    ")
            else:
                console.print(f"    [yellow]{REJECT_NOT_APPLIED}[/yellow]")
            for s in _session_errors(result):
                console.print(f"    [yellow]⚠️  {s.session}: {escape(s.error)}[/yellow]")
            if output:
                path = output / _report_filename(url, used_names)
                _save_report(url, result, path)
                console.print(f"    [dim]report: {escape(str(path))}[/dim]")
        except Exception as e:
            console.print(f"  [red]❌ Error: {escape(str(e))}[/red]")
            codes.add(ExitCode.ERROR)
        console.print()

    raise typer.Exit(_worst(codes))
