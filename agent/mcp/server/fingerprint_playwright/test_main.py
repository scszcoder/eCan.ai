# main.py

import asyncio
from profile_manager import launch_stealth_browser
from save_profile_state import save_state

async def ut_main():
    playwright, browser, context, page, profile_dir = await launch_stealth_browser(
        profile_name="ads_power_1",
        proxy={"server": "http://proxy.example.com:8000", "username": "user", "password": "pass"},
        timezone="Asia/Shanghai",
        locale="zh-CN",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/114.0.0.0 Safari/537.36",
    )

    await page.goto("https://www.whatismybrowser.com/")
    await page.wait_for_timeout(10000)

    await save_state(context, profile_dir)
    await browser.close()
    await playwright.stop()

asyncio.run(ut_main())
