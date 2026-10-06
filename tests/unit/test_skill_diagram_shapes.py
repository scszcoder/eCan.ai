"""A skill's diagram in every stored shape yields its workflow, so event routing
and the live-chat site are found.

0.9.99yc 千牛 alpha (2026-10-07): the 天猫 front desk was compiled from its DB
copy, whose diagram is a double-encoded JSON string; the runner read it as "no
diagram", registered ZERO routing rules, and every 千牛 event hit "No target
task found for browser_event (sub_type=qianniu_chat)".
"""
import json
from types import SimpleNamespace

from agent.ec_skills import live_chat_dispatch
from agent.ec_skills.skill_diagram import as_workflow
from agent.ec_tasks.runner import TaskRunner

PEND = {"id": "pend", "type": "pend_event_node", "data": {"inputsValues": {
    "eventType": {"content": "chat_message"},
    "pendingSources": {"content": [{"type": "browser_event", "browserEventLabel": "qianniu_chat"}]},
    "agentIds": {"content": ""}, "matchFields": {"content": []}}}}
PREP = {"id": "prep", "type": "code", "data": {"inputsValues": {
    "hookBundles": {"type": "constant", "content": json.dumps([{"path": "qianniu_chat"}])}}}}
WF = {"nodes": [{"id": "loop", "type": "loop", "blocks": [PEND, PREP]}], "edges": []}

SHAPES = {
    "db object": WF,
    "db string": json.dumps(WF),
    "db double-encoded string": json.dumps(json.dumps(WF)),
    "file": {"skillName": "淘宝客服前台01", "workFlow": WF},
    "editor bundle": {"mainSheetId": "main", "sheets": [{"id": "main", "document": WF}]},
}


def test_every_stored_shape_yields_the_workflow():
    for name, shape in SHAPES.items():
        assert as_workflow(shape) == WF, name
    assert as_workflow(None) is None and as_workflow("not json") is None and as_workflow({}) is None


def test_routing_rules_are_found_in_every_shape():
    for name, shape in SHAPES.items():
        entries = TaskRunner._extract_event_types_from_skill(
            SimpleNamespace(), SimpleNamespace(name="淘宝客服前台01", diagram=shape),
            SimpleNamespace(name="天猫客服前台001", metadata={}))
        labels = {(e["event_type"], e.get("browser_event_label")) for e in entries}
        assert ("browser_event", "qianniu_chat") in labels, (name, labels)
        assert any(e["event_type"] == "chat_message" for e in entries), name


def test_the_live_chat_site_is_found_in_every_shape():
    live_chat_dispatch.register_runner_bridge(SimpleNamespace(site_plugin_name="qianniu_chat"), "qianniu_chat")
    try:
        for name, shape in SHAPES.items():
            assert live_chat_dispatch.site_for_skill(SimpleNamespace(diagram=shape)) == "qianniu_chat", name
    finally:
        live_chat_dispatch.clear_runner_bridge("qianniu_chat")
