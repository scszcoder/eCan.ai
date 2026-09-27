"""``ebay_connect_account`` -- the seller's one-time OAuth consent, in this browser.

Opens eBay's consent page, waits while the seller signs in and clicks Agree,
reads the authorization code off the page eBay redirects to, and exchanges it
for tokens right here: the tokens go to the keyring and never into the result,
so they never reach an LLM.
"""
# No ``from __future__ import annotations`` here: browser-use matches the
# injected ``browser_session: BrowserSession`` parameter by its real type.
import asyncio
import json

from pydantic import BaseModel, Field

from browser_use import BrowserSession
from browser_use.agent.views import ActionResult

from utils.logger_helper import logger_helper as logger
from agent.ec_skills.browser_use_extension.extension_tools_service import custom_controller


class EbayConnectAccountAction(BaseModel):
    timeout_s: int = Field(300, description="Seconds to wait for the seller to sign in and agree")


def _done(out: dict) -> ActionResult:
    text = json.dumps(out, ensure_ascii=False)
    if out.get("ok"):
        return ActionResult(extracted_content=text, include_in_memory=True)
    return ActionResult(error=text)


@custom_controller.action(
    "eBay: connect the seller's eBay account to this app (one-time OAuth consent). Opens eBay's "
    "consent page; the SELLER signs in and clicks Agree themselves -- never type credentials. "
    "Waits until eBay redirects back, then stores the connection. Returns connected/expiry only.",
    param_model=EbayConnectAccountAction)
async def ebay_connect_account(params: EbayConnectAccountAction,
                               browser_session: BrowserSession) -> ActionResult:
    from agent.ec_skills.listing.ebay_api import auth
    try:
        url = auth.consent_url()
    except Exception as exc:
        return _done({"ok": False, "reason": str(exc)})
    try:
        await browser_session.navigate_to(url, new_tab=True)
        waited, last = 0.0, ""
        while waited < params.timeout_s:
            await asyncio.sleep(2)
            waited += 2
            try:
                last = await browser_session.get_current_page_url() or ""
            except Exception:
                continue
            try:
                code = auth.code_from_url(last)
            except auth.EbayAuthError as exc:
                return _done({"ok": False, "reason": str(exc)})
            if code:
                status = await auth.complete_consent(last)
                return _done({"ok": True, **status})
        return _done({"ok": False, "reason": f"no consent within {params.timeout_s}s -- is the seller "
                                             "signed in and did they click Agree? (page is still "
                                             f"{last.split('?')[0]})"})
    except Exception as exc:
        logger.warning(f"[ebay_listing] connect_account: {exc}")
        return _done({"ok": False, "reason": f"{type(exc).__name__}: {exc}"})
