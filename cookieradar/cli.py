"""
CookieRadar — Cookie compliance auditor.
GDPR art.5/6/7 — pre-consent, post-reject, GTM analysis
"""
import asyncio
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
    if session.error:
        console.print(f"[yellow]⚠️  Error: {escape(session.error)}[/yellow]")
    console.print()


def _session_errors(result) -> list:
    sessions = [result.pre_consent, result.post_accept, result.post_reject]
    return [s for s in sessions if s.error]


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

    if not url.startswith("http"):
        url = f"https://{url}"

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
    console.print(f"[bold yellow]🟡 Session 2 — Post-accept ({len(set(t.domain for t in post_acc.trackers))} unique trackers)[/bold yellow]")
    _print_session("Post-accept trackers", post_acc, console)

    # Post-reject
    post_rej = result.post_reject
    console.print(f"[bold green]🟢 Session 3 — Post-reject ({len(set(t.domain for t in post_rej.trackers))} unique trackers)[/bold green]")
    _print_session("Post-reject trackers", post_rej, console)

    # Summary
    violations = find_violations(result)

    if violations.all:
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

    with open(file) as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    console.print(f"\n[dim]Loaded {len(urls)} URLs from {escape(file)}[/dim]\n")

    for url in urls:
        if not url.startswith("http"):
            url = f"https://{url}"
        console.print(f"[cyan]Auditing {escape(url)}...[/cyan]")
        try:
            result = asyncio.run(scan(url))
            pre = set(t.domain for t in result.pre_consent.trackers)
            rej = set(t.domain for t in result.post_reject.trackers)
            violations = find_violations(result)
            status = "🔴 VIOLATION" if violations.all else "✅ OK"
            console.print(f"  {status} — pre: {len(pre)} trackers, post-reject: {len(rej)} trackers")
            _print_violations(violations, "    ")
            for s in _session_errors(result):
                console.print(f"    [yellow]⚠️  {s.session}: {escape(s.error)}[/yellow]")
        except Exception as e:
            console.print(f"  [red]❌ Error: {escape(str(e))}[/red]")
        console.print()


if __name__ == "__main__":
    app()
