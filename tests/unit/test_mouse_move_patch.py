"""A mouse move in a background tab is answered only after ~5 s (KEN 2026-10-30);
the click must not wait for that answer, and every other input event still does."""
import asyncio
import time

from cdp_use.cdp.input.library import InputClient

from agent.ec_skills.browser_use_extension import mouse_move_patch


class _SlowMoveClient:
    def __init__(self):
        self.sent = []

    async def send_raw(self, method, params, session_id=None):
        self.sent.append(params["type"])
        await asyncio.sleep(1.0 if params["type"] == "mouseMoved" else 0.01)
        return {"ok": params["type"]}


def _click():
    async def go():
        client = _SlowMoveClient()
        inp = InputClient(client)
        t0 = time.monotonic()
        results = []
        for kind in ("mouseMoved", "mousePressed", "mouseReleased"):
            results.append(await inp.dispatchMouseEvent({"type": kind, "x": 1, "y": 1}))
        took = time.monotonic() - t0
        await asyncio.sleep(1.0)       # the late move answer arrives and is dropped
        return took, client.sent, results
    return asyncio.run(go())


def test_the_click_does_not_wait_for_the_move_answer():
    assert mouse_move_patch.install()
    took, sent, results = _click()
    assert took < 0.6
    assert sent == ["mouseMoved", "mousePressed", "mouseReleased"]
    assert results[1:] == [{"ok": "mousePressed"}, {"ok": "mouseReleased"}]


def test_install_is_idempotent():
    assert mouse_move_patch.install() and mouse_move_patch.install()
