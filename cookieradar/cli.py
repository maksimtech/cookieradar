"""
CookieRadar — Cookie compliance auditor.
GDPR art.5/6/7 — pre-consent, post-reject, GTM analysis
"""
import typer
from rich.console import Console

app = typer.Typer(
    name="cookieradar",
    help="🍪 Cookie compliance auditor — GDPR art.5/6/7",
    add_completion=False,
)

console = Console()


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
    console.print(f"\n[dim]Auditing [bold]{url}[/bold]...[/dim]")
    console.print("[yellow]🚧 CookieRadar v2026.09.1 — Work in progress[/yellow]")


@app.command()
def batch(
    file: str = typer.Argument(..., help="File with URLs to audit (one per line)"),
    lang: str = typer.Option("it", "--lang", "-l", help="Report language (it/en)"),
    output: str = typer.Option(None, "--output", "-o", help="Save reports to directory"),
):
    """
    Audit multiple URLs from a file.
    """
    console.print(f"\n[dim]Loading URLs from [bold]{file}[/bold]...[/dim]")
    console.print("[yellow]🚧 CookieRadar v2026.09.1 — Work in progress[/yellow]")


if __name__ == "__main__":
    app()
