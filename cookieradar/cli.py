"""
CookieRadar — Cookie compliance auditor.
GDPR art.5/6/7 — pre-consent, post-reject, GTM analysis
"""
import asyncio
import re
from datetime import datetime, timezone

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.markup import escape
from rich import box

from cookieradar.scanner import Violations, find_violations

app = typer.Typer(
    name="cookieradar",
    help="🍪 Cookie compliance auditor — GDPR art.5/6/7",
    add_completion=False,
)

console = Console()

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


def _read_urls(path: str) -> list[str]:
    """Non-empty lines of the file, skipping comments (also indented ones)."""
    with open(path, encoding="utf-8") as f:
        lines = [line.strip() for line in f]
    return [line for line in lines if line and not line.startswith("#")]


def _print_session(title: str, session, console: Console):
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

    console.print(table)
    console.print(f"[dim]Banner found: {'✅' if session.banner_found else '❌'}[/dim]")
    console.print(f"[dim]Cookies: {len(session.cookies)}[/dim]")
    if session.cookies:
        _print_cookies(session.cookies)
    if session.error:
        console.print(f"[yellow]⚠️  Error: {escape(session.error)}[/yellow]")
    console.print()


def _cookie_expiry(cookie: dict) -> str:
    expires = cookie.get("expires", -1)
    if expires is None or expires < 0:
        return "session"
    return datetime.fromtimestamp(expires, tz=timezone.utc).strftime("%Y-%m-%d")


def _print_cookies(cookies: list[dict]):
    table = Table(box=box.SIMPLE, show_header=True, header_style="dim")
    table.add_column("Cookie")
    table.add_column("Domain", style="dim")
    table.add_column("Expires", style="dim")
    for c in sorted(cookies, key=lambda c: (c.get("domain", ""), c.get("name", ""))):
        table.add_row(Text(c.get("name", "")), Text(c.get("domain", "")), Text(_cookie_expiry(c)))
    console.print(table)


def _session_errors(result) -> list:
    sessions = [result.pre_consent, result.post_accept, result.post_reject]
    return [s for s in sessions if s.error]


ACCEPT_NOT_APPLIED = "accept button not found: this session shows the page without consent"
REJECT_NOT_APPLIED = "reject button not found: this session is equivalent to pre-consent"


def _print_consent_header(label: str, style: str, session, not_applied: str):
    unique = len(set(t.domain for t in session.trackers))
    status = "" if session.consent_clicked else " NOT APPLIED"
    console.print(f"[bold {style}]{label}{status} ({unique} unique trackers)[/bold {style}]")
    if not session.consent_clicked:
        console.print(f"[yellow]⚠️  {not_applied}[/yellow]")


def _print_violations(violations: Violations, indent: str):
    for d in sorted(violations.persistent):
        console.print(f"{indent}[red]→ {escape(d)}[/red] [dim](persists from pre-consent)[/dim]")
    for d in sorted(violations.new):
        console.print(f"{indent}[red]→ {escape(d)}[/red] [dim](new after rejection)[/dim]")


@app.command()
def audit(
    url: str = typer.Argument(..., help="URL to audit (e.g. https://tim.it)"),
    lang: str = typer.Option("it", "--lang", "-l", help="Report language (it/en)"),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="Run browser headless"),
    output: str = typer.Option(None, "--output", "-o", help="Save report to file"),
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
        raise typer.Exit(2)

    console.print(f"\n[dim]Auditing [bold]{escape(url)}[/bold]...[/dim]")

    try:
        with console.status("[cyan]Running pre-consent session...[/cyan]"):
            result = asyncio.run(scan(url, headless=headless))
    except Exception as e:
        console.print(f"[red]❌ Error: {escape(str(e))}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold]📊 CookieRadar Report — {escape(url)}[/bold]\n")

    # Pre-consent
    pre = result.pre_consent
    console.print(f"[bold red]🔴 Session 1 — Pre-consent ({len(set(t.domain for t in pre.trackers))} unique trackers)[/bold red]")
    _print_session("Pre-consent trackers", pre, console)

    # Post-accept
    post_acc = result.post_accept
    _print_consent_header("🟡 Session 2 — Post-accept", "yellow", post_acc, ACCEPT_NOT_APPLIED)
    _print_session("Post-accept trackers", post_acc, console)

    # Post-reject
    post_rej = result.post_reject
    _print_consent_header("🟢 Session 3 — Post-reject", "green", post_rej, REJECT_NOT_APPLIED)
    _print_session("Post-reject trackers", post_rej, console)

    # Summary
    violations = find_violations(result)

    if not post_rej.consent_clicked:
        console.print("[bold yellow]⚠️  UNVERIFIED — could not reject cookies, no verdict on post-reject trackers[/bold yellow]")
    elif violations.all:
        console.print(f"[bold red]⚠️  VIOLATION — {len(violations.all)} tracker(s) loaded after rejection:[/bold red]")
        _print_violations(violations, "  ")
    else:
        console.print("[bold green]✅ No trackers loaded after rejection[/bold green]")

    if _session_errors(result):
        console.print("[yellow]⚠️  Result may be incomplete: some sessions reported errors[/yellow]")


@app.command()
def batch(
    file: str = typer.Argument(..., help="File with URLs to audit (one per line)"),
    lang: str = typer.Option("it", "--lang", "-l", help="Report language (it/en)"),
    output: str = typer.Option(None, "--output", "-o", help="Save reports to directory"),
):
    """
    Audit multiple URLs from a file.
    """
    from cookieradar.scanner import scan

    urls = _read_urls(file)

    console.print(f"\n[dim]Loaded {len(urls)} URLs from {escape(file)}[/dim]\n")

    for url in urls:
        try:
            url = normalize_url(url)
        except ValueError as e:
            console.print(f"[red]❌ {escape(url)}: {escape(str(e))}[/red]\n")
            continue
        console.print(f"[cyan]Auditing {escape(url)}...[/cyan]")
        try:
            result = asyncio.run(scan(url))
            pre = set(t.domain for t in result.pre_consent.trackers)
            rej = set(t.domain for t in result.post_reject.trackers)
            violations = find_violations(result)
            if not result.post_reject.consent_clicked:
                status = "⚠️  UNVERIFIED"
            else:
                status = "🔴 VIOLATION" if violations.all else "✅ OK"
            console.print(f"  {status} — pre: {len(pre)} trackers, post-reject: {len(rej)} trackers")
            if result.post_reject.consent_clicked:
                _print_violations(violations, "    ")
            else:
                console.print(f"    [yellow]{REJECT_NOT_APPLIED}[/yellow]")
            for s in _session_errors(result):
                console.print(f"    [yellow]⚠️  {s.session}: {escape(s.error)}[/yellow]")
        except Exception as e:
            console.print(f"  [red]❌ Error: {escape(str(e))}[/red]")
        console.print()


if __name__ == "__main__":
    app()
