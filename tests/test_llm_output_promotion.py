"""An LLM node's parsed output is published under its node id in tool_result (and
state["result"]) on every run path, so a later node can take one LLM's field by name
-- a planner's gen_prompt in a media-gen node -- and a loop condition can tell two
LLM nodes' verdicts apart."""

import unittest

from agent.ec_skills.build_node import _promote_llm_output


class PromoteLlmOutputTests(unittest.TestCase):
    def test_publishes_under_node_id(self):
        state = {"result": {"llm_result": {"gen_prompt": "p", "all_done": False}}}
        _promote_llm_output(state, "llm_plan")
        self.assertEqual(state["tool_result"]["llm_plan"], {"gen_prompt": "p", "all_done": False})
        self.assertEqual(state["result"]["llm_plan"]["gen_prompt"], "p")
        self.assertEqual(state["result"]["gen_prompt"], "p")

    def test_two_llm_nodes_keep_separate_entries(self):
        state = {"result": {"llm_result": {"all_done": False}}}
        _promote_llm_output(state, "llm_plan")
        state["result"] = {"llm_result": {"pass": True}}       # next LLM node replaces result
        _promote_llm_output(state, "llm_review")
        self.assertEqual(state["tool_result"]["llm_plan"], {"all_done": False})
        self.assertEqual(state["tool_result"]["llm_review"], {"pass": True})

    def test_later_stamp_on_llm_result_does_not_rewrite_published_output(self):
        state = {"result": {"llm_result": {"all_done": False, "gen_prompt": "p"}}}
        _promote_llm_output(state, "llm_plan")
        state["result"]["llm_result"]["all_done"] = True     # MCP auto-select, no tool picked
        self.assertFalse(state["tool_result"]["llm_plan"]["all_done"])

    def test_double_wrapped_and_unparsed(self):
        state = {"result": {"llm_result": {"llm_result": {"x": 1}}}}
        _promote_llm_output(state, "n")
        self.assertEqual(state["tool_result"]["n"], {"x": 1})
        state = {"result": {"llm_result": "not json"}}
        _promote_llm_output(state, "n")
        self.assertNotIn("tool_result", state)


if __name__ == "__main__":
    unittest.main()
