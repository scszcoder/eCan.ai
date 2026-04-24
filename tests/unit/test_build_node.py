"""Unit tests for build_node.py core functions via flowgram2langgraph module.

Tests cover:
  - apply_operator: comparison/boolean operators
  - extract_value: state value extraction
  - evaluate_condition_legacy: condition evaluation
  - KeySafeDict / _Missing: safe dict access
"""

import pytest

pytestmark = pytest.mark.unit


# ============================================================================
# apply_operator
# ============================================================================

class TestApplyOperator:
    """Tests for the apply_operator function."""

    def test_equal_operator_true(self):
        from agent.ec_skills.flowgram2langgraph import apply_operator

        assert apply_operator(42, 42, "Equal") is True
        assert apply_operator("hello", "hello", "Equal") is True
        assert apply_operator(True, True, "Equal") is True

    def test_equal_operator_false(self):
        from agent.ec_skills.flowgram2langgraph import apply_operator

        assert apply_operator(42, 43, "Equal") is False
        assert apply_operator("hello", "world", "Equal") is False

    def test_not_equal_operator(self):
        from agent.ec_skills.flowgram2langgraph import apply_operator

        assert apply_operator(42, 43, "Not Equal") is True
        assert apply_operator("a", "b", "Not Equal") is True
        assert apply_operator(42, 42, "Not Equal") is False

    def test_larger_than_operator(self):
        from agent.ec_skills.flowgram2langgraph import apply_operator

        assert apply_operator(10, 5, "Larger Than") is True
        assert apply_operator(5, 10, "Larger Than") is False
        assert apply_operator(5, 5, "Larger Than") is False

    def test_smaller_than_operator(self):
        from agent.ec_skills.flowgram2langgraph import apply_operator

        assert apply_operator(3, 7, "Smaller Than") is True
        assert apply_operator(7, 3, "Smaller Than") is False
        assert apply_operator(5, 5, "Smaller Than") is False

    def test_larger_or_equal_than_operator(self):
        from agent.ec_skills.flowgram2langgraph import apply_operator

        assert apply_operator(10, 10, "Larger Or Equal Than") is True
        assert apply_operator(10, 5, "Larger Or Equal Than") is True
        assert apply_operator(5, 10, "Larger Or Equal Than") is False

    def test_smaller_or_equal_than_operator(self):
        from agent.ec_skills.flowgram2langgraph import apply_operator

        assert apply_operator(10, 10, "Smaller Or Equal Than") is True
        assert apply_operator(5, 10, "Smaller Or Equal Than") is True
        assert apply_operator(10, 5, "Smaller Or Equal Than") is False

    def test_in_operator(self):
        from agent.ec_skills.flowgram2langgraph import apply_operator

        assert apply_operator("a", ["a", "b", "c"], "In") is True
        assert apply_operator("z", ["a", "b", "c"], "In") is False

    def test_not_in_operator(self):
        from agent.ec_skills.flowgram2langgraph import apply_operator

        assert apply_operator("z", ["a", "b", "c"], "Not In") is True
        assert apply_operator("a", ["a", "b", "c"], "Not In") is False

    def test_is_empty_operator(self):
        from agent.ec_skills.flowgram2langgraph import apply_operator

        assert apply_operator("", None, "Is Empty") is True
        assert apply_operator([], None, "Is Empty") is True
        assert apply_operator(None, None, "Is Empty") is True
        assert apply_operator("hello", None, "Is Empty") is False
        assert apply_operator([1], None, "Is Empty") is False

    def test_is_not_empty_operator(self):
        from agent.ec_skills.flowgram2langgraph import apply_operator

        assert apply_operator("hello", None, "Is Not Empty") is True
        assert apply_operator([1], None, "Is Not Empty") is True
        assert apply_operator("", None, "Is Not Empty") is False
        assert apply_operator(None, None, "Is Not Empty") is False

    def test_is_true_operator(self):
        from agent.ec_skills.flowgram2langgraph import apply_operator

        assert apply_operator(True, None, "Is True") is True
        assert apply_operator(1, None, "Is True") is True
        assert apply_operator(False, None, "Is True") is False
        assert apply_operator(0, None, "Is True") is False

    def test_is_false_operator(self):
        from agent.ec_skills.flowgram2langgraph import apply_operator

        assert apply_operator(False, None, "Is False") is True
        assert apply_operator(0, None, "Is False") is True
        assert apply_operator(True, None, "Is False") is False

    def test_unknown_operator_returns_false(self):
        from agent.ec_skills.flowgram2langgraph import apply_operator

        assert apply_operator(1, 2, "UnknownOperator") is False
        assert apply_operator(1, 2, "") is False


# ============================================================================
# extract_value
# Note: content is a LIST of keys for nested access, not a single string.
# ============================================================================

class TestExtractValue:
    """Tests for extract_value function."""

    def test_extract_constant(self):
        from agent.ec_skills.flowgram2langgraph import extract_value

        assert extract_value(None, {"type": "constant", "content": 42}) == 42
        assert extract_value(None, {"type": "constant", "content": "hello"}) == "hello"
        assert extract_value(None, {"type": "constant", "content": True}) is True

    def test_extract_ref_single_key(self):
        """ref.content is a list of keys for nested access."""
        from agent.ec_skills.flowgram2langgraph import extract_value

        state = {"name": "Alice", "age": 30}
        assert extract_value(state, {"type": "ref", "content": ["name"]}) == "Alice"
        assert extract_value(state, {"type": "ref", "content": ["age"]}) == 30

    def test_extract_ref_nested(self):
        """Nested access via list of keys."""
        from agent.ec_skills.flowgram2langgraph import extract_value

        state = {"user": {"profile": {"city": "NYC"}}}
        result = extract_value(state, {"type": "ref", "content": ["user", "profile", "city"]})
        assert result == "NYC"

    def test_extract_ref_missing_key(self):
        """Missing keys return None."""
        from agent.ec_skills.flowgram2langgraph import extract_value

        state = {"name": "Alice"}
        assert extract_value(state, {"type": "ref", "content": ["missing_key"]}) is None

    def test_extract_unknown_type(self):
        """Unknown operand types return None."""
        from agent.ec_skills.flowgram2langgraph import extract_value

        assert extract_value(None, {"type": "unknown", "content": "value"}) is None


# ============================================================================
# KeySafeDict / _Missing
# ============================================================================

class TestKeySafeDict:
    """Tests for KeySafeDict and _Missing sentinel."""

    def test_get_existing_key(self):
        from agent.ec_skills.flowgram2langgraph import KeySafeDict

        d = KeySafeDict({"name": "Alice", "age": 30})
        assert d["name"] == "Alice"
        assert d["age"] == 30

    def test_get_missing_key_returns_sentinel(self):
        """Missing keys return _Missing sentinel (not a dict)."""
        from agent.ec_skills.flowgram2langgraph import KeySafeDict, _Missing

        d = KeySafeDict({"name": "Alice"})
        result = d["missing"]
        assert isinstance(result, _Missing)
        assert bool(result) is False

    def test_nested_wrap(self):
        from agent.ec_skills.flowgram2langgraph import KeySafeDict

        d = KeySafeDict({"user": {"city": "NYC"}})
        inner = d["user"]
        assert inner["city"] == "NYC"


class TestMissingSentinel:
    """Tests for _Missing singleton sentinel."""

    def test_missing_is_falsy(self):
        from agent.ec_skills.flowgram2langgraph import _Missing

        m = _Missing()
        assert bool(m) is False

    def test_missing_getitem_returns_self(self):
        from agent.ec_skills.flowgram2langgraph import _Missing

        m = _Missing()
        assert m["any_key"] is m

    def test_missing_get_with_default(self):
        """_Missing.get returns the default value when provided."""
        from agent.ec_skills.flowgram2langgraph import _Missing

        m = _Missing()
        assert m.get("key", "default") == "default"


# ============================================================================
# evaluate_condition_legacy
# Note: conditions is a flat list of { "value": { "left", "right", "operator" } }
# No "logic" key - all conditions are AND-ed.
# ============================================================================

class TestEvaluateConditionLegacy:
    """Tests for evaluate_condition_legacy function."""

    def test_single_equal_condition_true(self):
        from agent.ec_skills.flowgram2langgraph import evaluate_condition_legacy

        state = {"status": "active"}
        conditions = [
            {
                "value": {
                    "left": {"type": "ref", "content": ["status"]},
                    "operator": "Equal",
                    "right": {"type": "constant", "content": "active"},
                }
            }
        ]
        assert evaluate_condition_legacy(state, conditions) is True

    def test_single_equal_condition_false(self):
        from agent.ec_skills.flowgram2langgraph import evaluate_condition_legacy

        state = {"status": "inactive"}
        conditions = [
            {
                "value": {
                    "left": {"type": "ref", "content": ["status"]},
                    "operator": "Equal",
                    "right": {"type": "constant", "content": "active"},
                }
            }
        ]
        assert evaluate_condition_legacy(state, conditions) is False

    def test_multiple_conditions_all_true(self):
        """Multiple conditions - all must pass (AND logic)."""
        from agent.ec_skills.flowgram2langgraph import evaluate_condition_legacy

        state = {"a": 5, "b": 10}
        conditions = [
            {
                "value": {
                    "left": {"type": "ref", "content": ["a"]},
                    "operator": "Equal",
                    "right": {"type": "constant", "content": 5},
                }
            },
            {
                "value": {
                    "left": {"type": "ref", "content": ["b"]},
                    "operator": "Equal",
                    "right": {"type": "constant", "content": 10},
                }
            },
        ]
        assert evaluate_condition_legacy(state, conditions) is True

    def test_multiple_conditions_one_false(self):
        """If any condition fails, evaluate_condition_legacy returns False."""
        from agent.ec_skills.flowgram2langgraph import evaluate_condition_legacy

        state = {"a": 5, "b": 20}
        conditions = [
            {
                "value": {
                    "left": {"type": "ref", "content": ["a"]},
                    "operator": "Equal",
                    "right": {"type": "constant", "content": 5},
                }
            },
            {
                "value": {
                    "left": {"type": "ref", "content": ["b"]},
                    "operator": "Equal",
                    "right": {"type": "constant", "content": 10},
                }
            },
        ]
        assert evaluate_condition_legacy(state, conditions) is False
