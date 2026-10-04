"""Loop update nodes count iterations per loop (state["attributes"]["loop_iterations"])
and reset the loops nested in them, so an inner loop counts from 0 every time it is
entered -- what an "at most N attempts" inner loop needs."""

import unittest

from agent.ec_skills.flowgram2langgraph_v2 import _v2_convert_loops


def _flow():
    inner = {"id": "loop_in", "type": "loop", "data": {"loopMode": "loopWhile", "loopWhileExpr": "True"},
             "blocks": [{"id": "bs2", "type": "block-start"}, {"id": "work", "type": "code"},
                        {"id": "be2", "type": "block-end"}],
             "edges": [{"sourceNodeID": "bs2", "targetNodeID": "work"},
                       {"sourceNodeID": "work", "targetNodeID": "be2"}]}
    outer = {"id": "loop_out", "type": "loop", "data": {"loopMode": "loopWhile", "loopWhileExpr": "True"},
             "blocks": [{"id": "bs1", "type": "block-start"}, {"id": "plan", "type": "code"}, inner,
                        {"id": "be1", "type": "block-end"}],
             "edges": [{"sourceNodeID": "bs1", "targetNodeID": "plan"},
                       {"sourceNodeID": "plan", "targetNodeID": "loop_in"},
                       {"sourceNodeID": "loop_in", "targetNodeID": "be1"}]}
    return {"nodes": [{"id": "start", "type": "start"}, outer, {"id": "end", "type": "end"}],
            "edges": [{"sourceNodeID": "start", "targetNodeID": "loop_out"},
                      {"sourceNodeID": "loop_out", "targetNodeID": "end"}]}


def _updates():
    wf = _flow()
    while any(n.get("type") == "loop" for n in wf["nodes"]):
        wf = _v2_convert_loops(wf)
    fns = {}
    for n in wf["nodes"]:
        if n["id"].startswith("update_"):
            scope = {}
            exec(n["data"]["script"]["content"], scope)
            fns[n["id"]] = scope["main"]
    return fns


class LoopIterationCounterTests(unittest.TestCase):
    def test_counts_and_resets_nested_loop(self):
        fns = _updates()
        outer, inner = fns["update_loop_out_condition"], fns["update_loop_in_condition"]
        state = {}
        it = lambda: state["attributes"]["loop_iterations"]
        outer(state, runtime=None, store=None)            # enter outer
        inner(state, runtime=None, store=None)            # enter inner
        self.assertEqual((it()["loop_out"], it()["loop_in"]), (0, 0))
        inner(state, runtime=None, store=None)            # inner repeats twice
        inner(state, runtime=None, store=None)
        self.assertEqual(it()["loop_in"], 2)
        outer(state, runtime=None, store=None)            # next outer pass
        self.assertEqual((it()["loop_out"], it()["loop_in"]), (1, -1))
        inner(state, runtime=None, store=None)            # inner entered again: counts from 0
        self.assertEqual(it()["loop_in"], 0)

    def test_counter_survives_a_replaced_result(self):
        fns = _updates()
        state = {}
        fns["update_loop_out_condition"](state, runtime=None, store=None)
        state["result"] = {"llm_result": {"pass": False}}   # what an LLM node does
        fns["update_loop_out_condition"](state, runtime=None, store=None)
        self.assertEqual(state["attributes"]["loop_iterations"]["loop_out"], 1)


class NestedLoopEntryTests(unittest.TestCase):
    def test_nested_loop_skill_enters_at_outer_loop(self):
        # A stray unwired node used to become the entry: the nested-loop pass
        # deleted start -> outer loop after sheet flattening had dropped 'start'.
        from agent.ec_skills.flowgram2langgraph_v2 import flowgram2langgraph_v2
        flow = _flow()
        flow["nodes"].append({"id": "stray", "type": "code"})
        wf, _ = flowgram2langgraph_v2({"workFlow": flow}, bundle_json=None, enable_subgraph=False)
        graph = wf.compile().get_graph()
        self.assertEqual([e.target for e in graph.edges if e.source == "__start__"],
                         ["update_loop_out_condition"])

    def test_loop_entry_follows_block_start_when_a_back_edge_returns_to_it(self):
        # plan -> tools -> route; route[if_tool] -> plan (back edge), route[else] -> block-end.
        loop = {"id": "loop_a", "type": "loop", "data": {"loopMode": "loopWhile", "loopWhileExpr": "True"},
                "blocks": [{"id": "bs", "type": "block-start"}, {"id": "plan", "type": "code"},
                           {"id": "tools", "type": "code"},
                           {"id": "route", "type": "condition", "data": {"conditions": [
                               {"key": "if_tool", "value": {"mode": "custom", "expr": "False"}},
                               {"key": "else_done", "value": {}}]}},
                           {"id": "be", "type": "block-end"}],
                "edges": [{"sourceNodeID": "bs", "targetNodeID": "plan"},
                          {"sourceNodeID": "plan", "targetNodeID": "tools"},
                          {"sourceNodeID": "tools", "targetNodeID": "route"},
                          {"sourceNodeID": "route", "targetNodeID": "plan", "sourcePortID": "if_tool"},
                          {"sourceNodeID": "route", "targetNodeID": "be", "sourcePortID": "else_done"}]}
        wf = _v2_convert_loops({"nodes": [{"id": "start", "type": "start"}, loop, {"id": "end", "type": "end"}],
                                "edges": [{"sourceNodeID": "start", "targetNodeID": "loop_a"},
                                          {"sourceNodeID": "loop_a", "targetNodeID": "end"}]})
        edges = {(e["sourceNodeID"], e["targetNodeID"], e.get("sourcePortID")) for e in wf["edges"]}
        self.assertIn(("check_loop_a_condition", "plan", "if_out"), edges)
        self.assertIn(("route", "update_loop_a_condition", "else_done"), edges)
        self.assertFalse({e for e in edges if e[0] == "check_loop_a_condition" and e[1] in ("tools", "route")})


if __name__ == "__main__":
    unittest.main()
