"""Two live-chat platforms in one process (飞鸽 + 拼多多 front desks, run.env
ECAN_LIVE_CHAT_SITE=pdd_chat): reply direct-delivery runs outside any node run,
so bridge lookups fell to the process default (pdd_chat) and 飞鸽 replies
resolved their chat tab through the PDD bundle -> "live-chat tab target not
found", nothing sent (customer run 99t, 2026-10-05). Delivery now runs under the
platform the task's own skill declares (hookBundles) -- read by the live-chat
layer from skill data; the general-purpose browser node is not involved."""

import asyncio
import json
import threading
from types import SimpleNamespace

import pytest

from agent.ec_skills import live_chat_dispatch as lcd
from agent.ec_tasks import runner as rn

FEIGE, PDD = object(), object()


def _skill(bundle, wrapped=True):
    """A front-desk skill as loaded: diagram = whole skill JSON or just workFlow."""
    node = {"id": "browser_automation_0t5L6", "type": "browser-automation",
            "data": {"inputsValues": {"hookBundles": {"type": "template", "content": json.dumps(
                [{"path": bundle, "config": {"cooldown_ms": 1500}}], ensure_ascii=False)}}}}
    loop = {"id": "loop_1", "type": "loop", "blocks": [node]}
    wf = {"nodes": [{"id": "start", "type": "start"}, loop], "edges": []}
    return SimpleNamespace(diagram={"skillName": "x", "workFlow": wf} if wrapped else wf)


@pytest.fixture
def two_bridges(monkeypatch):
    monkeypatch.setattr(lcd, "_BRIDGES", {"feige_chat": FEIGE, "pdd_chat": PDD})
    monkeypatch.setenv("ECAN_LIVE_CHAT_SITE", "pdd_chat")


def test_site_is_read_from_the_skills_own_diagram(two_bridges):
    assert lcd.site_for_skill(_skill("feige_chat")) == "feige_chat"
    assert lcd.site_for_skill(_skill("pdd_chat", wrapped=False)) == "pdd_chat"
    assert lcd.site_for_skill(_skill("some_other_bundle")) is None   # not a live-chat bundle
    assert lcd.site_for_skill(SimpleNamespace(diagram={})) is None


def test_outside_a_node_the_default_is_the_configured_site(two_bridges):
    assert rn._live_chat_bridge() is PDD


def test_delivery_for_a_feige_front_desk_uses_the_feige_bridge(two_bridges):
    tok = rn._enter_task_site(SimpleNamespace(skill=_skill("feige_chat")))
    try:
        assert rn._live_chat_bridge() is FEIGE
    finally:
        rn._leave_task_site(tok)
    assert rn._live_chat_bridge() is PDD   # restored


def test_it_holds_on_the_delivery_worker_loop(two_bridges):
    """The async job runs as a task on another thread's loop (no inherited context)."""
    task = SimpleNamespace(skill=_skill("feige_chat"))
    seen = {}

    async def job():
        tok = rn._enter_task_site(task)
        try:
            await asyncio.sleep(0)
            seen["bridge"] = rn._live_chat_bridge()
        finally:
            rn._leave_task_site(tok)

    t = threading.Thread(target=lambda: asyncio.run(job()))
    t.start(); t.join(5)
    assert seen["bridge"] is FEIGE


def test_a_skill_without_a_live_chat_bundle_keeps_old_behaviour(two_bridges):
    tok = rn._enter_task_site(SimpleNamespace(skill=SimpleNamespace(diagram={})))
    assert tok is None and rn._live_chat_bridge() is PDD


def test_browser_node_does_not_report_platforms():
    import inspect
    from agent.ec_skills.browser_node import runner as bn
    assert "remember_agent_site" not in inspect.getsource(bn)
