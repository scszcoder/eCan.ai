"""The fleet activity feed: what this machine's agents do, for the account's web view."""

import asyncio
import json
import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agent.fleet import activity_feed as af
from utils.logger_helper import logger_helper


@pytest.fixture
def feed():
    f = af.FleetFeed()
    f._mainwin = SimpleNamespace(
        machine_name="PLATOON-1", host_role="Platoon",
        agents=[SimpleNamespace(card=SimpleNamespace(id="a1", name="前台-店A"), _running=True, status="active"),
                SimpleNamespace(card=SimpleNamespace(id="a2", name="客服小A"), _running=False, status="active")])
    with patch("agent.ec_agents.vehicle_affinity.resolve_local_vehicle_id", return_value="veh-p1"):
        yield f
    f._stop_tail("test end")


def _sent_bodies(calls):
    return [json.loads(c["contents"]) for c in calls]


def _capture(ok=True):
    calls = []

    async def fake_send(req, mainwin):
        calls.append(req)
        return {"data": {"sendWanMessage": {"id": "m"}}} if ok else {"errors": [{"message": "Unexpected error."}]}
    return calls, fake_send


def test_events_go_out_in_capped_batches_on_the_feed_channel(feed):
    for i in range(130):
        feed.note("task", task=f"t{i}", status="completed")
    calls, fake = _capture()
    with patch("agent.chats.wan_chat.wanSendMessage8", side_effect=fake):
        while True:
            batch = feed._take_batch()
            if not batch:
                break
            assert asyncio.run(feed._send(batch))
    assert all(c["chatID"] == af.FEED_CHANNEL and c["type"] == "fleet_feed" for c in calls)
    bodies = _sent_bodies(calls)
    assert sum(len(b["events"]) for b in bodies) == 130
    assert all(len(b["events"]) <= af.MAX_EVENTS_PER_SEND for b in bodies)
    assert all(len(c["contents"].encode()) < 32_000 for c in calls)
    assert bodies[0]["machine"] == {"id": "veh-p1", "name": "PLATOON-1", "role": "Platoon"}


def test_a_refused_send_keeps_the_events_and_backs_off(feed):
    feed.note("task", task="t", status="failed")
    calls, fake = _capture(ok=False)

    async def one_tick():
        with patch("agent.chats.wan_chat.wanSendMessage8", side_effect=fake), \
             patch.object(af, "FLUSH_S", 0.01):
            task = asyncio.create_task(feed._flush_loop())
            await asyncio.sleep(0.2)
            task.cancel()
    asyncio.run(one_tick())
    assert calls, "it tried"
    assert feed._events, "nothing lost when the cloud refused"
    assert feed._backoff_until > 0


def test_snapshot_lists_this_machines_agents(feed):
    snap = feed._snapshot()
    assert [(a["name"], a["running"]) for a in snap["agents"]] == [("前台-店A", True), ("客服小A", False)]


def test_commands_for_another_machine_are_ignored(feed):
    cmd = lambda machine, what="log_start": {"type": "fleet_cmd", "contents": json.dumps(
        {"cmd": what, "machine": machine, "ttl_s": 60})}
    feed.handle_command(cmd("veh-other"))
    assert feed._tail is None
    feed.handle_command(cmd("veh-p1"))
    assert feed._tail is not None
    feed.handle_command(cmd("*", "log_stop"))
    assert feed._tail is None


def test_the_log_tail_carries_log_lines_but_never_its_own(feed):
    feed.handle_command({"type": "fleet_cmd", "contents": json.dumps({"cmd": "log_start", "machine": "*"})})
    feed._events.clear()
    logger_helper.logger.info("[DIRECT-DELIVERY] outcome ok=True customer='A'")
    logger_helper.logger.info(f"{af._TAG} something about the feed itself")
    texts = [e["text"] for e in feed._events if e["kind"] == "log"]
    assert any("DIRECT-DELIVERY" in t for t in texts)
    assert not any(af._TAG in t for t in texts)


def test_task_status_and_readiness_reach_the_feed(feed):
    with patch.object(af, "_FEED", feed):
        feed.note_task(SimpleNamespace(id="t1", name="飞鸽客服前台-店A", agent_id="a1",
                                       status=SimpleNamespace(message="boom")), "failed")
        from utils import agent_status
        agent_status.report("a1", chrome="up", monitor="watching")
    kinds = [e["kind"] for e in feed._events]
    assert "task" in kinds and "agent_status" in kinds
    task_ev = next(e for e in feed._events if e["kind"] == "task")
    assert task_ev["status"] == "failed" and task_ev["error"] == "boom"


def test_the_feed_can_be_turned_off(feed, monkeypatch):
    monkeypatch.setenv("ECAN_FLEET_FEED", "0")
    feed.note("task", task="t")
    assert not feed._events
