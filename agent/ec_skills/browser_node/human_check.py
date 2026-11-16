"""Pause a browser run on a site's human check (CAPTCHA, "verify yourself") until a person clears it.

eCan never solves these. Before each agent step the page is looked at; on a check page
the owner is told (the run's chat, a Windows notification, an in-app notice), the
window is brought to the front, and the run waits. Once the page is no longer a check
the step goes ahead from where it stopped. Unsolved within the wait, the step goes ahead
anyway and the skill's own handling (stop and report) takes over.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from typing import Any

from utils.logger_helper import logger_helper as logger

WAIT_S = 15 * 60
POLL_S = 5.0

# Lowercase. A URL part or a title part names a check page only on its own terms:
# no generic word like "verify" that ordinary pages use.
_URL_MARKS = (
    "/splashui/challenge", "/splashui/captcha",          # eBay
    "/errors/validatecaptcha", "/ap/cvf/",               # Amazon
    "google.com/sorry/",                                 # Google
    "/cdn-cgi/challenge-platform",                       # Cloudflare
)
_TITLE_MARKS = (
    "security measure",                                  # eBay
    "pardon our interruption",
    "just a moment...", "attention required! | cloudflare",
    "robot check", "verify you are human", "are you a robot",
)


def human_check_on(url: str, title: str) -> str:
    """What gives the page away as a human check ("" when it isn't one)."""
    u, t = (url or "").lower(), (title or "").lower()
    for mark in _URL_MARKS:
        if mark in u:
            return mark
    for mark in _TITLE_MARKS:
        if mark in t:
            return mark
    return ""


async def _page(bs: Any) -> tuple[str, str]:
    try:
        return await bs.get_current_page_url(), await bs.get_current_page_title()
    except Exception:
        return "", ""


async def _bring_to_front(bs: Any) -> None:
    try:
        cdp = await bs.get_or_create_cdp_session()
        await cdp.cdp_client.send.Page.bringToFront(session_id=cdp.session_id)
    except Exception as exc:
        logger.debug(f"[HumanCheck] could not bring the window to the front: {exc}")


def _chat_id(state: dict | None) -> str:
    attrs = (state or {}).get("attributes") or {}
    params = attrs.get("params") if isinstance(attrs.get("params"), dict) else {}
    chat_id = (attrs.get("chat_id") or params.get("chatId")
               or ((params.get("metadata") or {}).get("params") or {}).get("chatId"))
    msgs = (state or {}).get("messages")
    if not chat_id and isinstance(msgs, list) and len(msgs) > 1 and isinstance(msgs[1], str):
        chat_id = msgs[1]
    return chat_id or ""


def _tell_chat(state: dict | None, text: str) -> None:
    chat_id = _chat_id(state)
    if not chat_id:
        return
    try:
        from agent.ec_tasks.message_sender import ChatMessageSender
        agent_obj = None
        msgs = (state or {}).get("messages")
        if isinstance(msgs, list) and msgs and msgs[0]:
            from agent.agent_service import get_agent_by_id
            agent_obj = get_agent_by_id(msgs[0])
        ChatMessageSender(agent_obj).send_text(chat_id, text)
    except Exception as exc:
        logger.warning(f"[HumanCheck] could not post to chat {chat_id}: {exc}")


def _toast(title: str, text: str) -> None:
    """A Windows notification, via PowerShell's own app id (nothing to install)."""
    if sys.platform != "win32":
        return
    esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("'", "''")
    script = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null;"
        "$x = New-Object Windows.Data.Xml.Dom.XmlDocument;"
        f"$x.LoadXml('<toast scenario=\"reminder\"><visual><binding template=\"ToastGeneric\"><text>{esc(title)}</text>"
        f"<text>{esc(text)}</text></binding></visual><actions><action content=\"OK\" arguments=\"ok\"/></actions></toast>');"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
        "'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe').Show("
        "[Windows.UI.Notifications.ToastNotification]::new($x))"
    )
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        logger.debug(f"[HumanCheck] Windows notification failed: {exc}")


def _broadcast(event: str, payload: dict) -> None:
    try:
        from gui.LocalServer import app_ws_manager
        app_ws_manager.broadcast_sync(event, payload)
    except Exception:
        pass


async def wait_out_human_check(agent: Any, state: dict | None, profile_id: str = "",
                               cancellation_event: Any = None,
                               wait_s: float | None = None, poll_s: float | None = None) -> bool:
    """Hold the run while the page is a human check. True if one was met and cleared."""
    wait_s = WAIT_S if wait_s is None else wait_s
    poll_s = POLL_S if poll_s is None else poll_s
    bs = getattr(agent, "browser_session", None)
    if bs is None:
        return False
    url, title = await _page(bs)
    mark = human_check_on(url, title)
    if not mark:
        return False

    where = f"the '{profile_id}' browser window" if profile_id else "the store's browser window"
    mins = int(wait_s // 60)
    text = (f"The site is asking for a human check ({title or url}). Please complete it in {where}; "
            f"this run is paused and carries on by itself once it's done (waiting up to {mins} min).")
    logger.warning(f"[HumanCheck] {profile_id or '?'}: human check on {url!r} ({mark!r}); waiting for the owner")
    payload = {"profile_id": profile_id, "url": url, "title": title, "wait_s": wait_s}
    _broadcast("browser.humanCheck", payload)
    _toast("eCan: please complete a human check", text)
    _tell_chat(state, text)
    await _bring_to_front(bs)

    deadline = time.time() + wait_s
    while time.time() < deadline:
        if cancellation_event is not None and cancellation_event.is_set():
            break
        await asyncio.sleep(poll_s)
        url, title = await _page(bs)
        if url and not human_check_on(url, title):
            logger.info(f"[HumanCheck] {profile_id or '?'}: check cleared (now {url!r}); carrying on")
            _broadcast("browser.humanCheckCleared", {**payload, "url": url, "title": title})
            _tell_chat(state, "Thanks, the check is done; the run is carrying on.")
            return True
    logger.warning(f"[HumanCheck] {profile_id or '?'}: check not cleared within {mins} min; going on")
    _broadcast("browser.humanCheckCleared", {**payload, "timed_out": True})
    return False


def install(agent: Any, state: dict | None, profile_id: str = "", cancellation_event: Any = None):
    """Make each step first wait out a human check; returns ``(attr, original)`` to restore.

    browser-use's ``_execute_step`` runs ``step`` under a 180 s timeout, so the wait goes
    around ``_execute_step`` (outside that timeout) when the agent has one.
    """
    attr = "_execute_step" if hasattr(agent, "_execute_step") else "step"
    orig = getattr(agent, attr)

    async def _after_human_check(*a, **kw):
        try:
            await wait_out_human_check(agent, state, profile_id, cancellation_event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # never block a step
            logger.debug(f"[HumanCheck] check failed (non-fatal): {exc}")
        return await orig(*a, **kw)

    setattr(agent, attr, _after_human_check)
    return attr, orig
