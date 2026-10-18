"""An agent-to-agent message in the A2A SDK shape carries its sender at
params.metadata.params.senderId. The baseline must find it, or a skill with no
pend_event replies into a non-existent chat and the caller never hears back
(2026-10-18: 做图经理小李 -> 做图专家小王, image made, result lost)."""
from types import SimpleNamespace

import agent.ec_tasks.runner  # noqa: F401  -- the app loads this first (prep_skills_run import cycle)
from agent.ec_skills.prep_skills_run import _node_state_baseline

LI, WANG = "agent_39b3bed06e884620", "agent_9ab5224dc8364b4a"


def _msg():   # trimmed from the log
    return {
        "id": "ec25e809",
        "params": {
            "id": "ec25e809", "sessionId": "83c7dde1",
            "message": {"kind": "message", "messageId": "9c02", "metadata": {"mtype": "send_chat"},
                        "parts": [{"kind": "text", "text": "请按需求文件制作图片。\n需求文件：C:\\tmp\\requirements.json"}]},
            "metadata": {
                "params": {"chatId": "chat-14697d84", "senderId": LI, "receiverId": WANG,
                           "senderName": "做图经理小李", "role": "agent", "human": False,
                           "transport": "a2a", "senderType": "agent"},
                "async_response": True,
            },
        },
        "__trigger_source__": "message",
    }


def test_sender_is_found_in_the_nested_sdk_shape():
    agent = SimpleNamespace(card=SimpleNamespace(id=WANG, name="做图专家小王"))
    st = _node_state_baseline(agent, "task_x", _msg())
    attrs = st["attributes"]
    assert attrs["inbound_sender_id"] == LI
    assert attrs["inbound_sender_type"] == "agent"
    assert attrs["inbound_transport"] == "a2a"
