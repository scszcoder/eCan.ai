from __future__ import annotations

import asyncio

from dotenv import load_dotenv

from browser_use import Agent, ChatGoogle
from browser_use.browser.profile import BrowserProfile

from .chrome_driver import default_chromedriver
from .selenium_session import SeleniumBrowserSession

load_dotenv()


def _build_selenium_session() -> SeleniumBrowserSession:
    """Create a BrowserSession backed by Selenium ChromeDriver."""

    profile = BrowserProfile(headless=False)

    return SeleniumBrowserSession(
        webdriver_factory=lambda: default_chromedriver(browser_profile=profile),
        browser_profile=profile,
    )


async def main() -> None:
    session = _build_selenium_session()

    agent = Agent(
        llm=ChatGoogle(model="gemini-flash-latest"),
        task="go to amazon.com and search for pens to draw on whiteboards",
        browser_session=session,
    )

    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
