"""Unit tests for Mustache variable resolution in build_node.py.

Tests cover:
  - Simple variable replacement: {{var}}
  - Dot-path variable resolution: {{result.xxx}}, {{tool_result.xxx}}
  - State fallback when fmt_ctx doesn't have the value
  - Empty/unknown variable handling with logging
"""

import pytest
import logging

pytestmark = pytest.mark.unit


class TestMustacheVariableResolution:
    """Tests for Mustache variable resolution in _resolve_mustache_variables."""

    def test_simple_variable_replacement(self):
        """Test basic {{variable}} replacement."""
        from agent.ec_skills.build_node import _resolve_mustache_variables

        template = "Hello {{name}}, welcome!"
        state = {"name": "Alice"}
        fmt_ctx = {"name": "Alice"}

        result = _resolve_mustache_variables(template, fmt_ctx, state, mainwin=None)
        assert result == "Hello Alice, welcome!"

    def test_dot_path_tool_result(self):
        """Test {{tool_result.node_id.field}} resolution via state fallback."""
        from agent.ec_skills.build_node import _resolve_mustache_variables

        template = "Product: {{tool_result.collector.product_name}}"
        state = {
            "tool_result": {
                "collector": {
                    "product_name": "iPhone 17 Pro Max",
                    "brand": "Apple"
                }
            }
        }
        fmt_ctx = {}  # Not in fmt_ctx, should fall back to state

        result = _resolve_mustache_variables(template, fmt_ctx, state, mainwin=None)
        assert result == "Product: iPhone 17 Pro Max"

    def test_dot_path_result(self):
        """Test {{result.node_id.field}} resolution."""
        from agent.ec_skills.build_node import _resolve_mustache_variables

        template = "Brand: {{result.collector.brand}}"
        state = {
            "result": {
                "collector": {
                    "product_name": "iPhone 17 Pro Max",
                    "brand": "Apple"
                }
            }
        }
        fmt_ctx = {}  # Not in fmt_ctx, should fall back to state

        result = _resolve_mustache_variables(template, fmt_ctx, state, mainwin=None)
        assert result == "Brand: Apple"

    def test_dot_path_with_json_string_in_fmt_ctx(self):
        """Test that JSON strings in fmt_ctx are parsed correctly."""
        from agent.ec_skills.build_node import _resolve_mustache_variables
        import json

        template = "Name: {{result.product_name}}"
        state = {
            "result": {
                "product_name": "Should not see this"
            }
        }
        # fmt_ctx has a JSON string that should be parsed
        fmt_ctx = {
            "result": json.dumps({"product_name": "Parsed Product"})
        }

        result = _resolve_mustache_variables(template, fmt_ctx, state, mainwin=None)
        assert result == "Name: Parsed Product"

    def test_unknown_variable_logs_warning(self, caplog):
        """Test that unknown variables trigger a warning log."""
        from agent.ec_skills.build_node import _resolve_mustache_variables

        template = "Value: {{unknown_var}}"
        state = {}
        fmt_ctx = {}

        with caplog.at_level(logging.WARNING):
            result = _resolve_mustache_variables(template, fmt_ctx, state, mainwin=None)

        assert "unknown_var" in caplog.text or "not found" in caplog.text.lower()
        assert "Value: " in result  # Should be empty string

    def test_nested_dot_path_not_found_logs_warning(self, caplog):
        """Test that nested paths not found in state trigger a warning."""
        from agent.ec_skills.build_node import _resolve_mustache_variables

        template = "Value: {{tool_result.nonexistent.field}}"
        state = {
            "tool_result": {
                "collector": {"product_name": "iPhone"}
            }
        }
        fmt_ctx = {}

        with caplog.at_level(logging.WARNING):
            result = _resolve_mustache_variables(template, fmt_ctx, state, mainwin=None)

        # Should have a warning about not finding the path
        assert "nonexistent" in caplog.text or "not found" in caplog.text.lower()

    def test_tool_result_entire_dict(self):
        """Test {{tool_result}} without dot-path returns full dict as JSON."""
        from agent.ec_skills.build_node import _resolve_mustache_variables

        template = "Full result: {{tool_result}}"
        state = {
            "tool_result": {
                "collector": {"product_name": "iPhone"},
                "validator": {"valid": True}
            }
        }
        fmt_ctx = {}

        result = _resolve_mustache_variables(template, fmt_ctx, state, mainwin=None)
        assert "collector" in result
        assert "product_name" in result
        assert "iPhone" in result


class TestPromptVariableProviders:
    """Tests for prompt_variable_providers.py cascading resolution."""

    def test_simple_variable_resolution(self):
        """Test basic variable resolution via cascading providers."""
        from agent.ec_skills.prompt_variable_providers import resolve_prompt_variables

        state = {
            "input": "Test input",
            "product_keyword": "iphone"
        }

        result = resolve_prompt_variables(
            variable_names=["input", "product_keyword"],
            state=state,
            mainwin=None
        )

        assert result.get("input") == "Test input"
        assert result.get("product_keyword") == "iphone"

    def test_previous_node_output_provider(self):
        """Test previous_node_output provider returns latest node output."""
        from agent.ec_skills.prompt_variable_providers import resolve_prompt_variables

        state = {
            "input": "Test",
            "tool_result": {
                "node1": {"data": "first"},
                "node2": {"data": "second"}
            }
        }

        result = resolve_prompt_variables(
            variable_names=["previous_node_output"],
            state=state,
            mainwin=None
        )

        # Should return the most recent node output
        assert result.get("previous_node_output") is not None
        # The result should be one of the node outputs
        prev_output = result.get("previous_node_output")
        assert prev_output in [{"data": "first"}, {"data": "second"}]

    def test_explicit_prompt_refs_takes_priority(self):
        """Test that state['prompt_refs'] takes highest priority."""
        from agent.ec_skills.prompt_variable_providers import resolve_prompt_variables

        state = {
                "input": "original input",
                "prompt_refs": {
                    "input": "explicit ref value"
                }
            }

        result = resolve_prompt_variables(
            variable_names=["input"],
            state=state,
            mainwin=None
        )

        assert result.get("input") == "explicit ref value"
