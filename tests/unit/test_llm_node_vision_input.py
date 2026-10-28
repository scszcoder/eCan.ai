"""Per-node "Vision input" switch (2026-10-22): a skill keeps the vision model for
its answering node, while its classifier / small-talk nodes get the customer's
image turn as text only, on their own (cheap) model."""
import json
import types

import pytest

import agent.ec_skills.build_node as bn
from agent.ec_skills.dev_defs import BreakpointManager

IMG = "data:image/png;base64," + "iVBORw0KGgo" * 200
INPUT = json.dumps({
    "customer_id": "c1", "customer_name": "买家甲", "latest_message": "[图片]",
    "latest_message_attachments": [{"kind": "image", "mime": "image/png", "data_uri": IMG}],
}, ensure_ascii=False)


class FakeLLM:
    def __init__(self, seen):
        self.seen = seen

    def bind_tools(self, *a, **k):
        return self

    def invoke(self, messages, *a, **k):
        self.seen["messages"] = messages
        from langchain_core.messages import AIMessage
        return AIMessage(content='{"needs_rag": true, "category": "media"}')

    async def ainvoke(self, messages, *a, **k):
        return self.invoke(messages)


def _run(vision):
    values = {
        "systemPrompt": {"type": "constant", "content": "You classify."},
        "prompt": {"type": "template", "content": "{{input}}"},
        "modelProvider": {"type": "constant", "content": "eCanAI"},
        "modelName": {"type": "constant", "content": "qwen3.8-flash"},
        "apiKey": {"type": "constant", "content": "test"},
        "apiHost": {"type": "constant",
                    "content": "https://example.tcloudbase.com/api/llm-proxy/v1"},
    }
    if vision is not None:
        values["visionInput"] = {"type": "constant", "content": vision}
    seen = {"routed": [], "prepped": 0}

    import agent.ec_skills.llm_utils.media_route as mr
    import agent.ec_skills.llm_utils.llm_utils as lu
    import agent.ec_skills.lambda_proxy_langchain as lp
    real_route, real_prep = mr.media_route, lu.prep_multi_modal_content

    def route(host, model):
        out = real_route(host, model)
        seen["routed"].append(out[1])
        return out

    def prep(*a, **k):
        seen["prepped"] += 1
        return real_prep(*a, **k)

    mp = pytest.MonkeyPatch()
    mp.setattr(mr, "media_route", route)
    mp.setattr(lu, "prep_multi_modal_content", prep)
    mp.setattr(lp, "create_lambda_proxy_langchain", lambda *a, **k: FakeLLM(seen))
    try:
        node = bn.build_llm_node({"inputsValues": values}, "llm_x", "s", "o", BreakpointManager())
        try:
            node({"input": INPUT, "attributes": {}, "messages": ["agent_id"], "history": []},
                 runtime=types.SimpleNamespace(context={}, store=None), store=None)
        except Exception as exc:          # a later step may need the app; the routing is decided before
            seen["error"] = repr(exc)
    finally:
        mp.undo()
    return seen


def _text_of(messages):
    out = []
    for m in messages or []:
        c = getattr(m, "content", m)
        out.append(c if isinstance(c, str) else json.dumps(c, ensure_ascii=False))
    return "\n".join(out)


def test_vision_on_by_default_uses_the_vision_model():
    seen = _run(None)
    assert seen["prepped"] == 1, seen
    assert seen["routed"] == ["qwen3-vl-plus"], seen


def test_vision_off_stays_on_the_node_model_with_text_only():
    seen = _run(False)
    assert seen["prepped"] == 0 and seen["routed"] == [], seen
    if "messages" in seen:                    # what the model got: text, no image bytes
        text = _text_of(seen["messages"])
        assert "base64," not in text and "image" in text
