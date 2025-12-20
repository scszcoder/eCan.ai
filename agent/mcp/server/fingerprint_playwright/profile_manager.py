# profile_manager.py

import os
import json
from pathlib import Path
from playwright.async_api import async_playwright
from fingerprint_manager import FingerprintManager

# Load fingerprint
fp_manager = FingerprintManager()
fingerprint = fp_manager.get_random_fingerprint()

context_args = {
    "user_agent": fingerprint["userAgent"],
    "locale": fingerprint["locale"],
    "viewport": fingerprint["viewport"],
    "timezone_id": fingerprint["timezone"],
}

PROFILE_ROOT = Path("./profiles")

async def launch_stealth_browser(
    profile_name: str,
    proxy: dict = None,
    timezone: str = "America/Los_Angeles",
    locale: str = "en-US",
    user_agent: str = None,
    viewport: dict = None
):
    profile_dir = PROFILE_ROOT / profile_name
    profile_dir.mkdir(parents=True, exist_ok=True)

    playwright = await async_playwright().start()
    chromium = playwright.chromium

    user_data_dir = f"user_profiles/{profile_id}"
    launch_args = {
        "headless": False,
        "user_data_dir": user_data_dir,
        "proxy": proxy if proxy else None,
        "args": [
            f"--lang={locale}",
            "--disable-blink-features=AutomationControlled",
        ]
    }

    browser = await chromium.launch(**launch_args)

    har_path = f"sessions/{profile_id}.har"

    context_args = {
        "locale": locale,
        "timezone_id": timezone,
        "user_agent": user_agent,
        "record_har_path": har_path,
        "viewport": viewport or {"width": 1280, "height": 800},
        "storage_state": str(profile_dir / "state.json") if (profile_dir / "state.json").exists() else None,
    }

    context = await browser.new_context(**{k: v for k, v in context_args.items() if v is not None})

    # Inject stealth
    stealth_script_path = Path("stealth_injection.js").resolve()
    with open(stealth_script_path, "r", encoding="utf-8") as f:
        script_content = f.read()

    await context.add_init_script(script_content)

    page = await context.new_page()

    return playwright, browser, context, page, profile_dir



