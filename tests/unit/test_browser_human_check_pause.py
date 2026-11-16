"""A site's human check pauses the browser run for the owner, who completes it by hand;
the run then carries on. eCan never solves it."""
import asyncio
from unittest.mock import patch

from agent.ec_skills.browser_node import human_check as hc


class FakeSession:
    def __init__(self, pages):
        self.pages = list(pages)

    async def get_current_page_url(self):
        return self.pages[0][0]

    async def get_current_page_title(self):
        url, title = self.pages[0]
        if len(self.pages) > 1:
            self.pages.pop(0)
        return title


class FakeAgent:
    def __init__(self, pages):
        self.browser_session = FakeSession(pages)
        self.steps = 0

    async def _execute_step(self, *a, **kw):
        self.steps += 1
        return False


EBAY_CHECK = ("https://www.ebay.com/splashui/challenge?ap=1", "Security Measure | eBay")
SELLER_HUB = ("https://www.ebay.com/sh/ord", "Seller Hub")


def test_check_pages_are_recognised_and_ordinary_pages_are_not():
    assert hc.human_check_on(*EBAY_CHECK)
    assert hc.human_check_on("https://www.amazon.com/errors/validateCaptcha", "Amazon.com")
    assert hc.human_check_on("https://x.com/", "Just a moment...")
    assert not hc.human_check_on(*SELLER_HUB)
    assert not hc.human_check_on("https://www.ebay.com/verify-your-item", "Verify your listing")


def _quiet():
    return (patch.object(hc, "_toast"), patch.object(hc, "_broadcast"),
            patch.object(hc, "_tell_chat"), patch.object(hc, "_bring_to_front", return_value=_noop()))


async def _noop():
    return None


def test_run_waits_on_a_check_and_carries_on_once_it_is_cleared():
    agent = FakeAgent([EBAY_CHECK, EBAY_CHECK, SELLER_HUB])
    toast, bc, chat, front = _quiet()
    with toast as t, bc as b, chat as c, front:
        attr, orig = hc.install(agent, {"attributes": {"chat_id": "c1"}}, "ebay_0")
        assert attr == "_execute_step"
        with patch.object(hc, "POLL_S", 0):
            asyncio.run(agent._execute_step())
        assert t.called and c.call_args_list[0].args[0]["attributes"]["chat_id"] == "c1"
        assert [x.args[0] for x in b.call_args_list] == ["browser.humanCheck", "browser.humanCheckCleared"]
    assert agent.steps == 1
    setattr(agent, attr, orig)


def test_cleared_page_is_detected_while_waiting():
    agent = FakeAgent([EBAY_CHECK, SELLER_HUB])
    toast, bc, chat, front = _quiet()
    with toast, bc, chat, front:
        assert asyncio.run(hc.wait_out_human_check(agent, None, "ebay_0", poll_s=0)) is True


def test_no_check_means_no_wait_and_no_notice():
    agent = FakeAgent([SELLER_HUB])
    toast, bc, chat, front = _quiet()
    with toast as t, bc as b, chat, front:
        assert asyncio.run(hc.wait_out_human_check(agent, None, "ebay_0")) is False
    assert not t.called and not b.called


def test_unsolved_check_gives_up_after_the_wait():
    agent = FakeAgent([EBAY_CHECK])
    toast, bc, chat, front = _quiet()
    with toast, bc as b, chat, front:
        assert asyncio.run(hc.wait_out_human_check(agent, None, "ebay_0", wait_s=0.05, poll_s=0.01)) is False
    assert b.call_args_list[-1].args[1].get("timed_out") is True


def test_startup_reconnects_only_open_browsers_with_a_dead_relay(tmp_path):
    from agent.ec_skills.browser_use_extension.fingerprint import fingerprint_browser as fb
    profiles = [{"id": p, "user_data_dir": str(tmp_path / p)} for p in ("open_dead", "open_alive", "closed", "no_proxy")]
    port_files = {"open_dead": {"relay_port": 1}, "open_alive": {"relay_port": 2},
                  "closed": {"relay_port": 3}, "no_proxy": {}}
    running = {"open_dead": {"healthy": True}, "open_alive": {"healthy": True}, "no_proxy": {"healthy": True}}
    with patch.object(fb.registry, "list_profiles", return_value=profiles), \
            patch.object(fb, "_read_port_file", side_effect=lambda d: port_files[d.name]), \
            patch.object(fb, "_port_open", side_effect=lambda port: port == 2), \
            patch.object(fb, "_running_browser_for", side_effect=lambda d: running.get(d.name)), \
            patch.object(fb, "launch_profile") as launch:
        assert fb.reconnect_open_proxied_profiles() == ["open_dead"]
    launch.assert_called_once_with("open_dead")
