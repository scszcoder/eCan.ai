"""千牛 replies go out from the reply path itself (alpha yt 2026-10-12: a reply
spent 5 s waiting for a browser 千牛 doesn't have, 2.4 s in a front-desk LLM
turn and up to 10 s queued behind the previous send)."""
import json
from types import SimpleNamespace
from unittest.mock import patch

from agent.ec_skills.browser_use_extension.hooks.external.qianniu_chat import name_map, observer
from agent.ec_skills.browser_use_extension.hooks.external.qianniu_chat.runner_bridge import QianniuRunnerBridge
from agent.ec_skills.browser_use_extension.hooks.external.qianniu_chat.typing_lock import get_lock
from agent.mcp.server.qianniu import qianniu_tools

REPLY = {"customer_id": "678614304", "customer_name": "678614304",
         "response_text": "有的，您可以发下想看的款式，我帮您看看。", "source_latest_message": "有格子衫吗？"}


def test_the_bridge_sends_the_reply_to_the_buyer_it_answers():
    calls = []
    with patch.object(name_map, "name_for", return_value="sctisz"), \
            patch.object(qianniu_tools, "send_reply",
                         side_effect=lambda b, m, e: calls.append((b, m, e)) or {"chat_sent": True}):
        assert QianniuRunnerBridge().deliver_reply(dict(REPLY)) is True
    assert calls == [("sctisz", REPLY["response_text"], "有格子衫吗？")]


def test_an_unsent_reply_is_left_to_the_front_desk():
    with patch.object(name_map, "name_for", return_value=""), \
            patch.object(qianniu_tools, "send_reply", return_value={"chat_sent": False, "error": "x"}):
        assert QianniuRunnerBridge().deliver_reply(dict(REPLY)) is False


def test_a_busy_desktop_is_not_sent_and_says_so():
    lock = get_lock()
    lock.release("")
    assert lock.try_acquire("backstop")
    try:
        with patch.object(qianniu_tools, "_LOCK_WAIT_S", 0.3), \
                patch.object(qianniu_tools, "_send_locked") as typed:
            out = qianniu_tools.send_reply("sctisz", "您好", "有格子衫吗？")
    finally:
        lock.release("backstop")
    assert out["chat_sent"] is False and "busy" in out["error"] and not typed.called


def test_the_reply_path_uses_the_sites_own_delivery():
    from agent.ec_tasks import runner as runner_mod
    sent = []
    bridge = SimpleNamespace(deliver_reply=lambda p: sent.append(p) or True)
    task = SimpleNamespace(name="天猫客服前台001", id="t1", skill=None)
    with patch.object(runner_mod, "_live_chat_bridge", return_value=bridge), \
            patch.object(runner_mod, "_is_live_chat_shutdown_drain_finalized", return_value=False):
        ok = runner_mod.TaskRunner._try_direct_live_chat_delivery_impl(
            SimpleNamespace(), task, {"human_text": json.dumps(REPLY, ensure_ascii=False)})
    assert ok is True and sent and sent[0]["response_text"] == REPLY["response_text"]


def test_the_backstop_waits_while_a_chat_is_live():
    obs = observer.QianniuMemObserver.__new__(observer.QianniuMemObserver)
    obs._stop = SimpleNamespace(wait=None)
    ticks = iter([False, True])
    obs._stop.wait = lambda _s: next(ticks)
    obs._last_live_dispatch = observer.time.monotonic()        # a buyer message just went out
    with patch.object(observer, "_backstop_interval_s", return_value=1.0), \
            patch.object(observer, "route_ready", return_value=True), \
            patch.object(qianniu_tools, "backstop_sweep") as sweep:
        obs._cold_dispatch = obs._already_handled = None
        obs._backstop_loop()
    assert not sweep.called
