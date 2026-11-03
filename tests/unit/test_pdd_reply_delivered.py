"""After a 拼多多 send times out, the runner asks the site whether the reply landed
(KEN 2026-10-29: it asked for Feige's dispatch_state, failed, and requeued every
timed-out send -- a duplicate whenever the first one had in fact gone out)."""
import asyncio
import json
import time

from agent.ec_skills.browser_use_extension.hooks.external.pdd_chat import site_tools, ws_observer
from agent.ec_skills.browser_use_extension.hooks.external.pdd_chat.runner_bridge import get_bridge


def _thread(uid, *msgs):
    async def evaluate(js):
        return json.dumps({"uid": uid, "messages": [{"who": w, "text": t} for w, t in msgs]})
    return evaluate


def _seen(ev, text="亲，有货的", since=0.0):
    return asyncio.run(site_tools._seen_sent(ev, "U1", text, since))


def test_the_newest_seller_message_is_the_reply():
    assert _seen(_thread("U1", ("customer", "有货吗"), ("agent", "亲，有货的"), ("customer", "几天发货"))) is True


def test_an_older_seller_message_does_not_count():
    assert _seen(_thread("U1", ("agent", "亲，有货的"), ("agent", "在的"))) is False


def test_another_buyers_thread_cannot_tell():
    assert _seen(_thread("U9", ("agent", "亲，有货的"))) is None


def test_the_servers_echo_proves_it_whatever_thread_is_open(monkeypatch):
    since = time.time() - 5
    monkeypatch.setattr(ws_observer, "echoed_since", lambda uid, text, s: uid == "U1" and s == since)
    assert _seen(_thread("U9"), since=since) is True


def test_the_bridge_offers_the_check():
    assert callable(getattr(get_bridge(), "reply_delivered", None))
