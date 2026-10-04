"""A planner LLM's per-image prompt reaches the media-gen node through the node's
template fields: {{gen_prompt}} (the latest upstream output carrying the field),
{{tool_result.<node>.<field>}}, and a reviewer's revised prompt winning on retry."""

import json

import types

import pytest

from agent.ec_skills.media import media_gen_node
from tests.unit.test_media_proxy import FakeProxy, _client


@pytest.fixture
def proxy(tmp_path, monkeypatch):
    fp = FakeProxy()
    monkeypatch.setattr(media_gen_node, "_make_client", lambda: _client(fp))
    monkeypatch.setattr(media_gen_node, "generated_medias_root", lambda: str(tmp_path / "gm"))
    return fp


def _node(prompt, **fields):
    cfg = {"title": "MediaGen_1", "inputsValues": {
        "mediaType": {"type": "constant", "content": "image"},
        "modelName": {"type": "constant", "content": "seedream-4.0"},
        "prompt": {"type": "template", "content": prompt},
        **{k: {"type": "template", "content": v} for k, v in fields.items()}}}
    return media_gen_node.build_media_gen_node(cfg, "media-gen_x", "sk", "owner", None)


_RT = types.SimpleNamespace(context={"task_id": "t", "run_id": "r"})


def _sent(proxy):
    _, _, _, body = proxy.calls("POST", "/v1/images/generations")[-1]
    return json.loads(body)


def _sent_prompt(proxy):
    return _sent(proxy)["prompt"]


def _planned(**extra):
    out = {"all_done": False, "image_id": "pi001-main",
           "gen_prompt": "single LED strip coiled on pure white, seven colours glowing, 1:1"}
    out.update(extra)
    return out


def test_planner_field_by_name(proxy):
    state = {"messages": [], "attributes": {}, "result": {}, "tool_result": {"llm_plan": _planned()}}
    _node("{{gen_prompt}}")(state, runtime=_RT, store=None)
    assert _sent_prompt(proxy) == _planned()["gen_prompt"]


def test_planner_field_by_tool_result_path(proxy):
    state = {"messages": [], "attributes": {}, "result": {}, "tool_result": {"llm_plan": _planned()}}
    _node("{{tool_result.llm_plan.gen_prompt}}")(state, runtime=_RT, store=None)
    assert _sent_prompt(proxy) == _planned()["gen_prompt"]


def test_reviewers_revision_wins_on_retry(proxy):
    timings = [{"node": "llm_plan", "status": "completed"}, {"node": "llm_review", "status": "completed"}]
    state = {"messages": [], "result": {}, "attributes": {"__node_timings__": timings},
             "tool_result": {"llm_plan": _planned(),
                             "llm_review": {"pass": False, "gen_prompt": "same strip, add a 1:1 white margin"}}}
    _node("{{gen_prompt}}")(state, runtime=_RT, store=None)
    assert _sent_prompt(proxy) == "same strip, add a 1:1 white margin"


def test_negative_template_that_renders_empty_is_not_sent_raw(proxy):
    state = {"messages": [], "attributes": {}, "result": {}, "tool_result": {"llm_plan": _planned()}}
    _node("{{gen_prompt}}", negativePrompt="{{negative_prompt}}")(state, runtime=_RT, store=None)
    assert "{{" not in str(_sent(proxy).get("negative_prompt") or "")


def test_negative_template_renders_planner_value(proxy):
    state = {"messages": [], "attributes": {}, "result": {},
             "tool_result": {"llm_plan": _planned(negative_prompt="text, watermark")}}
    _node("{{gen_prompt}}", negativePrompt="{{negative_prompt}}")(state, runtime=_RT, store=None)
    assert _sent(proxy)["negative_prompt"] == "text, watermark"


def test_rendered_list_splits_into_paths():
    from agent.ec_skills.media.media_inputs import split_media_list
    assert split_media_list("['C:/a.png', 'C:/b.png']") == ["C:/a.png", "C:/b.png"]
    assert split_media_list('["https://x/a.png"]') == ["https://x/a.png"]
    assert split_media_list("[]") == []
    assert split_media_list("C:/a.png, C:/b.png") == ["C:/a.png", "C:/b.png"]
