import unittest
import json
from agent.ec_skills.flowgram2langgraph import flowgram2langgraph


class Flowgram2LangGraphTests(unittest.TestCase):
    def test_single_sheet_entry_and_edges(self):
        flow = {
            "skillName": "demo",
            "owner": "me",
            "workFlow": {
                "nodes": [
                    {"id": "start", "type": "start"},
                    {"id": "a", "type": "code", "data": {"script": {"content": "def main(state):\n    return state\n"}}},
                    {"id": "b", "type": "code", "data": {"script": {"content": "def main(state):\n    return state\n"}}},
                    {"id": "end", "type": "end"},
                ],
                "edges": [
                    {"sourceNodeID": "start", "targetNodeID": "a"},
                    {"sourceNodeID": "a", "targetNodeID": "b"},
                    {"sourceNodeID": "b", "targetNodeID": "end"},
                ],
            },
        }
        wf, bps = flowgram2langgraph(flow)
        self.assertTrue(wf is not None)

    def test_multi_sheet_entry(self):
        bundle = {
            "sheets": [
                {
                    "name": "main",
                    "document": {
                        "nodes": [
                            {"id": "start", "type": "start"},
                            {"id": "x", "type": "code", "data": {"script": {"content": "def main(state):\n    return state\n"}}},
                        ],
                        "edges": [
                            {"sourceNodeID": "start", "targetNodeID": "x"}
                        ],
                    },
                },
                {
                    "name": "sub",
                    "document": {
                        "nodes": [
                            {"id": "start", "type": "start"},
                            {"id": "y", "type": "code", "data": {"script": {"content": "def main(state):\n    return state\n"}}},
                        ],
                        "edges": [
                            {"sourceNodeID": "start", "targetNodeID": "y"}
                        ],
                    },
                },
            ]
        }
        flow = {"skillName": "demo", "owner": "me", "bundle": bundle}
        wf, bps = flowgram2langgraph(flow)
        self.assertTrue(wf is not None)

    def test_sheet_call_jump(self):
        bundle = {
            "sheets": [
                {
                    "name": "main",
                    "document": {
                        "nodes": [
                            {"id": "start", "type": "start"},
                            {"id": "call", "type": "sheet-call", "data": {"target_sheet": "sub"}},
                        ],
                        "edges": [
                            {"sourceNodeID": "start", "targetNodeID": "call"}
                        ],
                    },
                },
                {
                    "name": "sub",
                    "document": {
                        "nodes": [
                            {"id": "start", "type": "start"},
                            {"id": "z", "type": "code", "data": {"script": {"content": "def main(state):\n    return state\n"}}},
                        ],
                        "edges": [
                            {"sourceNodeID": "start", "targetNodeID": "z"}
                        ],
                    },
                },
            ]
        }
        flow = {"skillName": "demo", "owner": "me", "bundle": bundle}
        wf, bps = flowgram2langgraph(flow)
        self.assertTrue(wf is not None)

    def test_variable_node_assigns(self):
        flow = {
            "skillName": "demo",
            "owner": "me",
            "workFlow": {
                "nodes": [
                    {"id": "start", "type": "start"},
                    {"id": "v", "type": "variable", "data": {"assignments": [
                        {"target": "attributes.foo", "value": 1},
                        {"target": "metadata.bar", "value": "x"}
                    ]}},
                ],
                "edges": [
                    {"sourceNodeID": "start", "targetNodeID": "v"}
                ],
            },
        }
        wf, bps = flowgram2langgraph(flow)
        self.assertTrue(wf is not None)

    def test_condition_node_with_ports(self):
        flow = {
            "skillName": "demo",
            "owner": "me",
            "workFlow": {
                "nodes": [
                    {"id": "start", "type": "start"},
                    {"id": "cond1", "type": "condition", "data": {
                        "conditions": [
                            {"key": "if_0", "value": {"mode": "state.condition"}},
                            {"key": "elif_1", "value": {"mode": "custom", "expr": "attributes.get('flag') == True"}},
                            {"key": "else_2", "value": {}}
                        ]
                    }},
                    {"id": "a", "type": "code", "data": {"script": {"content": "def main(state):\n    return state\n"}}},
                    {"id": "b", "type": "code", "data": {"script": {"content": "def main(state):\n    return state\n"}}},
                    {"id": "c", "type": "code", "data": {"script": {"content": "def main(state):\n    return state\n"}}},
                    {"id": "end", "type": "end"},
                ],
                "edges": [
                    {"sourceNodeID": "start", "targetNodeID": "cond1"},
                    {"sourceNodeID": "cond1", "targetNodeID": "a", "sourcePortID": "if_0"},
                    {"sourceNodeID": "cond1", "targetNodeID": "b", "sourcePortID": "elif_1"},
                    {"sourceNodeID": "cond1", "targetNodeID": "c", "sourcePortID": "else_2"},
                    {"sourceNodeID": "a", "targetNodeID": "end"},
                    {"sourceNodeID": "b", "targetNodeID": "end"},
                    {"sourceNodeID": "c", "targetNodeID": "end"},
                ],
            },
        }
        wf, bps = flowgram2langgraph(flow)
        self.assertTrue(wf is not None)

    def test_loop_node_with_internal_blocks(self):
        # Loop node provides blocks and edges; ensure process_blocks integrates them
        flow = {
            "skillName": "demo",
            "owner": "me",
            "workFlow": {
                "nodes": [
                    {"id": "start", "type": "start"},
                    {"id": "loop1", "type": "loop", "data": {"iter": 3}, "blocks": [
                        {"id": "n1", "type": "code", "data": {"script": {"content": "def main(state):\n    return state\n"}}},
                        {"id": "n2", "type": "code", "data": {"script": {"content": "def main(state):\n    return state\n"}}},
                    ], "edges": [
                        {"sourceNodeID": "n1", "targetNodeID": "n2"}
                    ]},
                    {"id": "after", "type": "code", "data": {"script": {"content": "def main(state):\n    return state\n"}}},
                    {"id": "end", "type": "end"},
                ],
                "edges": [
                    {"sourceNodeID": "start", "targetNodeID": "loop1"},
                    {"sourceNodeID": "loop1", "targetNodeID": "after"},
                    {"sourceNodeID": "after", "targetNodeID": "end"},
                ],
            },
        }
        wf, bps = flowgram2langgraph(flow)
        self.assertTrue(wf is not None)

    def test_comment_node_noop(self):
        flow = {
            "skillName": "demo",
            "owner": "me",
            "workFlow": {
                "nodes": [
                    {"id": "start", "type": "start"},
                    {"id": "note", "type": "comment", "data": {"text": "just a note"}},
                    {"id": "x", "type": "code", "data": {"script": {"content": "def main(state):\n    return state\n"}}},
                    {"id": "end", "type": "end"},
                ],
                "edges": [
                    {"sourceNodeID": "start", "targetNodeID": "note"},
                    {"sourceNodeID": "note", "targetNodeID": "x"},
                    {"sourceNodeID": "x", "targetNodeID": "end"},
                ],
            },
        }
        wf, bps = flowgram2langgraph(flow)
        self.assertTrue(wf is not None)

    def test_multi_sheet_with_condition_in_sub_sheet(self):
        bundle = {
            "sheets": [
                {
                    "name": "main",
                    "document": {
                        "nodes": [
                            {"id": "start", "type": "start"},
                            {"id": "goto", "type": "sheet-call", "data": {"target_sheet": "sub"}},
                        ],
                        "edges": [
                            {"sourceNodeID": "start", "targetNodeID": "goto"}
                        ],
                    },
                },
                {
                    "name": "sub",
                    "document": {
                        "nodes": [
                            {"id": "start", "type": "start"},
                            {"id": "condS", "type": "condition", "data": {
                                "conditions": [
                                    {"key": "if_0", "value": {"mode": "custom", "expr": "attributes.get('x', 0) > 0"}},
                                    {"key": "else_1", "value": {}}
                                ]
                            }},
                            {"id": "p", "type": "code", "data": {"script": {"content": "def main(state):\n    return state\n"}}},
                            {"id": "q", "type": "code", "data": {"script": {"content": "def main(state):\n    return state\n"}}},
                        ],
                        "edges": [
                            {"sourceNodeID": "start", "targetNodeID": "condS"},
                            {"sourceNodeID": "condS", "targetNodeID": "p", "sourcePortID": "if_0"},
                            {"sourceNodeID": "condS", "targetNodeID": "q", "sourcePortID": "else_1"}
                        ],
                    },
                },
            ]
        }
        flow = {"skillName": "demo", "owner": "me", "bundle": bundle}
        wf, bps = flowgram2langgraph(flow)
        self.assertTrue(wf is not None)


if __name__ == "__main__":
    unittest.main()
