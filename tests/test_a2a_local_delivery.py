"""agent/a2a/local_delivery.py: a chat to an agent running in this process
skips HTTP (Phase 5a)."""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from a2a.types import Message, TextPart
from agent.a2a import local_delivery as ld


def _agent(aid="qa1", running=True):
    a = SimpleNamespace(_running=running, runner=MagicMock(), card=SimpleNamespace(id=aid, name=aid, url="http://1.2.3.4:3603"))
    a.get_card = lambda: a.card
    return a


@pytest.fixture
def registry(monkeypatch):
    agents = {}
    monkeypatch.setattr("agent.agent_service.get_agent_by_id", lambda aid: agents.get(aid))
    monkeypatch.delenv("ECAN_A2A_LOCAL_FASTPATH", raising=False)
    return agents


def _msg(text="你好"):
    return Message(role="user", parts=[TextPart(text=text)], metadata={"mtype": "send_chat"}, message_id="m1")


def test_running_local_agent_gets_the_chat_without_http(registry):
    qa = registry["qa1"] = _agent()
    res = ld.deliver_chat(qa, "qa1", "send_chat", _msg(), {"content": "你好"})
    assert res["local_fastpath"] is True
    evt, request = qa.runner.sync_task_wait_in_line.call_args[0]
    assert evt == "chat_message" and qa.runner.sync_task_wait_in_line.call_args[1] == {"async_response": True}
    p = request["params"]
    # same shape the A2A server builds: fresh ids, params + async_response metadata
    assert request["id"] == p["id"] and p["id"] != p["sessionId"]
    assert p["metadata"] == {"params": {"content": "你好"}, "async_response": True}
    assert p["message"]["parts"][0]["text"] == "你好"


def test_dev_chat_event(registry):
    qa = registry["qa1"] = _agent()
    ld.deliver_chat(qa, "qa1", "dev_send_chat", _msg("dev> hi"), {})
    assert qa.runner.sync_task_wait_in_line.call_args[0][0] == "dev_human_chat"


@pytest.mark.parametrize("case", ["not_running", "other_object", "unregistered", "not_chat", "switched_off", "runner_error"])
def test_falls_back_to_http(registry, monkeypatch, case):
    qa = _agent(running=case != "not_running")
    if case == "other_object":
        registry["qa1"] = _agent()        # a different object with the same id
    elif case != "unregistered":
        registry["qa1"] = qa
    if case == "switched_off":
        monkeypatch.setenv("ECAN_A2A_LOCAL_FASTPATH", "0")
    if case == "runner_error":
        qa.runner.sync_task_wait_in_line.side_effect = RuntimeError("boom")
    mtype = "send_task" if case == "not_chat" else "send_chat"
    assert ld.deliver_chat(qa, "qa1", mtype, _msg(), {}) is None


def test_ec_agent_send_skips_http_for_a_local_recipient(registry):
    from agent.ec_agent import EC_Agent
    qa = registry["qa1"] = _agent()
    sender = SimpleNamespace(a2a_client=MagicMock())
    message = {"messages": ["fd1", "chat9", "m1", "trace7", "你好"],
               "attributes": {"params": {"content": "你好", "attachments": []}}}
    res = EC_Agent.a2a_send_chat_message_sync(sender, qa, message)
    assert res["local_fastpath"] is True
    sender.a2a_client.sync_send_task.assert_not_called()

    qa._running = False                      # e.g. its store runs on another machine
    sender.a2a_client.sync_send_task.return_value = {"result": "http"}
    assert EC_Agent.a2a_send_chat_message_sync(sender, qa, message) == {"result": "http"}
