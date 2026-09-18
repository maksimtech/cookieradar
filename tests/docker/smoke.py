"""
Docker smoke test: the container user must be able to launch Chromium.
If EXPECTED_VERSION is set, the installed cookieradar must match it
(e.g. the version in cookieradar/__init__.py for a local-source build).
"""
import asyncio
import os
from importlib.metadata import version

from playwright.async_api import async_playwright


def _normalize(v: str) -> str:
    # PEP 440 drops leading zeros: 2026.09.4 → 2026.9.4
    return ".".join(str(int(p)) if p.isdigit() else p for p in v.lstrip("v").split("."))


async def main():
    expected = os.environ.get("EXPECTED_VERSION")
    installed = version("cookieradar")
    if expected:
        assert _normalize(installed) == _normalize(expected), f"installed {installed}, expected {expected}"
    print(f"smoke: cookieradar {installed} OK")

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content("<p>ok</p>")
        assert await page.inner_text("p") == "ok"
        await browser.close()
    print("smoke: chromium OK")


asyncio.run(main())
