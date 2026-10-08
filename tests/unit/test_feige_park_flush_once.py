"""ws170 park flush must deliver a parked card-identity reply at most once,
and not at all when the buyer was already answered under the real name.

Live 2026-10-08 (陆地飞鱼, 10:49): a nameless product card dispatched as
card:<talk> while the named sidebar row was answered too; the parked card reply
was then flushed by overlapping backstop ticks -- DELIVERED x3 in one second --
so the buyer saw four messages at once."""
import asyncio
import time
from types import SimpleNamespace
from unittest.mock import patch

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    dispatch_state, undeliverable,
)


class _Action:
    def __init__(self, calls, delay=0.0):
        self.calls, self.delay = calls, delay
        self.param_model = lambda **kw: SimpleNamespace(**kw)

        async def function(params):
            await asyncio.sleep(self.delay)
            self.calls.append(getattr(params, "text", None))
            return SimpleNamespace(error=None)
        self.function = function


def _run_flushes(n, sent, talk="7694123497521431855", name="陆地飞鱼"):
    acts = {"feige_open_session": _Action([]), "feige_send_message": _Action(sent, delay=0.05)}
    ctrl = SimpleNamespace(registry=SimpleNamespace(registry=SimpleNamespace(actions=acts)))
    wss = SimpleNamespace(_k=lambda s: "shop", _talk_in_shop=lambda t, s: True,
                          name_for_talk=lambda t: name, ws_thread_snapshot=lambda *a, **k: {})

    async def go():
        return await asyncio.gather(*[undeliverable.resolve_and_flush(object()) for _ in range(n)])
    with patch.dict("sys.modules", {
            "agent.ec_skills.browser_use_extension.extension_tools_service": SimpleNamespace(custom_controller=ctrl)}), \
            patch("agent.ec_skills.browser_use_extension.hooks.external.feige_chat.ws_session", wss, create=True):
        return asyncio.run(go())


def test_overlapping_flush_ticks_deliver_a_parked_reply_once():
    undeliverable._PARKED.clear()
    dispatch_state.recent_agent_replies_by_customer.clear()
    undeliverable.park("card:7694123497521431855", "您好，这款券后价38元，48小时内发货。")
    sent = []
    _run_flushes(3, sent)
    assert sent == ["您好，这款券后价38元，48小时内发货。"]


def test_a_buyer_already_answered_by_name_does_not_get_the_parked_twin():
    undeliverable._PARKED.clear()
    dispatch_state.recent_agent_replies_by_customer.clear()
    dispatch_state.remember_agent_reply("陆地飞鱼", "您好，这款活动价38元，券后可立减10元。")
    undeliverable.park("card:7694123497521431855", "您好，这款券后价38元，48小时内发货。")
    sent = []
    _run_flushes(1, sent)
    assert sent == [] and undeliverable._PARKED == {}
