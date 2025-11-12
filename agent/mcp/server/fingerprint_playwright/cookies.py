import json
import os

COOKIE_DIR = "playwright_cookies"

async def save_cookies(context, profile_id):
    path = os.path.join(COOKIE_DIR, f"{profile_id}.json")
    cookies = await context.cookies()
    with open(path, "w") as f:
        json.dump(cookies, f)

async def load_cookies(context, profile_id):
    path = os.path.join(COOKIE_DIR, f"{profile_id}.json")
    if os.path.exists(path):
        with open(path, "r") as f:
            cookies = json.load(f)
        await context.add_cookies(cookies)
