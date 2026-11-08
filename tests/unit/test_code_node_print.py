"""A code node's print() reaches the run log (agent/ec_skills/build_node.build_basic_node)."""
from unittest.mock import MagicMock

from agent.ec_skills import build_node


def test_print_in_a_code_node_is_logged(monkeypatch):
    seen = []
    monkeypatch.setattr(build_node.logger, "info", lambda msg, *a, **k: seen.append(str(msg)))
    monkeypatch.setattr(build_node, "node_builder", lambda fn, *a, **k: fn)      # the bare main()
    script = 'def main(state, *, runtime, store):\n    print("[listing-explore]", "尺码表", "recipe saved")\n    return state\n'
    node = build_node.build_basic_node({"script": {"content": script}}, "code_recipe_first", "抖店商品上架", "o", MagicMock())
    node({"attributes": {}}, runtime=None, store=None)
    assert any("[code:抖店商品上架/code_recipe_first] [listing-explore] 尺码表 recipe saved" in m for m in seen), seen[-5:]
