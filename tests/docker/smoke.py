"""Docker smoke test: the container user must be able to launch Chromium."""
import asyncio

from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content("<p>ok</p>")
        assert await page.inner_text("p") == "ok"
        await browser.close()
    print("smoke: chromium OK")


asyncio.run(main())
