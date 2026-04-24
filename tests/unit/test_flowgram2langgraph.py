"""Unit tests for flowgram2langgraph conversion."""

import pytest

pytestmark = pytest.mark.unit


class TestFlowgram2LangGraph:
    """Tests for the Flowgram → LangGraph conversion logic."""

    def test_single_sheet_entry_and_edges(self):
        """Simple linear flow: start → code → code → end."""
        from agent.ec_skills.flowgram2langgraph import flowgram2langgraph

        flow = {
            "skillName": "demo",
            "owner": "me",
            "workFlow": {
                "nodes": [
                    {"id": "start", "type": "start"},
                    {
                        "id": "a",
                        "type": "code",
                        "data": {"script": {"content": "def main(state):\n    return state\n"}},
                    },
                    {
                        "id": "b",
                        "type": "code",
                        "data": {"script": {"content": "def main(state):\n    return state\n"}},
                    },
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
        assert wf is not None
        # Returns a StateGraph object from langgraph, with breakpoints as list
        assert hasattr(wf, "nodes")  # StateGraph has a nodes attribute
        assert isinstance(bps, list)

    def test_multi_sheet_entry(self):
        """Multi-sheet workflow: main sheet with a sub-sheet reference."""
        from agent.ec_skills.flowgram2langgraph import flowgram2langgraph

        bundle = {
            "sheets": [
                {
                    "name": "main",
                    "document": {
                        "nodes": [
                            {"id": "start", "type": "start"},
                            {
                                "id": "x",
                                "type": "code",
                                "data": {"script": {"content": "def main(state):\n    return state\n"}},
                            },
                        ],
                        "edges": [
                            {"sourceNodeID": "start", "targetNodeID": "x"},
                            {"sourceNodeID": "x", "targetNodeID": "end"},
                        ],
                    },
                },
                {
                    "name": "sub",
                    "document": {
                        "nodes": [
                            {"id": "start", "type": "start"},
                            {
                                "id": "y",
                                "type": "code",
                                "data": {"script": {"content": "def main(state):\n    return state\n"}},
                            },
                        ],
                        "edges": [
                            {"sourceNodeID": "start", "targetNodeID": "y"},
                            {"sourceNodeID": "y", "targetNodeID": "end"},
                        ],
                    },
                },
            ],
        }
        wf, bps = flowgram2langgraph(bundle)
        assert wf is not None

    def test_multi_sheet_with_condition_in_sub_sheet(self):
        """Sub-sheet with conditional branch: if/else path."""
        from agent.ec_skills.flowgram2langgraph import flowgram2langgraph

        bundle = {
            "sheets": [
                {
                    "name": "main",
                    "document": {
                        "nodes": [
                            {"id": "start", "type": "start"},
                            {
                                "id": "x",
                                "type": "code",
                                "data": {"script": {"content": "def main(state):\n    return state\n"}},
                            },
                            {"id": "end", "type": "end"},
                        ],
                        "edges": [
                            {"sourceNodeID": "start", "targetNodeID": "x"},
                            {"sourceNodeID": "x", "targetNodeID": "end"},
                        ],
                    },
                },
                {
                    "name": "sub",
                    "document": {
                        "nodes": [
                            {"id": "start", "type": "start"},
                            {
                                "id": "cond",
                                "type": "condition",
                                "data": {
                                    "expression": "state.get('value', 0) > 5",
                                },
                            },
                            {
                                "id": "true_path",
                                "type": "code",
                                "data": {"script": {"content": "def main(state):\n    return state\n"}},
                            },
                            {
                                "id": "false_path",
                                "type": "code",
                                "data": {"script": {"content": "def main(state):\n    return state\n"}},
                            },
                            {"id": "end", "type": "end"},
                        ],
                        "edges": [
                            {"sourceNodeID": "start", "targetNodeID": "cond"},
                            {"sourceNodeID": "cond", "targetNodeID": "true_path", "condition": "true"},
                            {"sourceNodeID": "cond", "targetNodeID": "false_path", "condition": "false"},
                            {"sourceNodeID": "true_path", "targetNodeID": "end"},
                            {"sourceNodeID": "false_path", "targetNodeID": "end"},
                        ],
                    },
                },
            ],
        }
        wf, bps = flowgram2langgraph(bundle)
        assert wf is not None
