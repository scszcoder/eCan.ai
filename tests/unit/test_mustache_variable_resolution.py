"""
Tests for Mustache template resolution and the prompt-variable cascade.

Rewritten 2026-10-23. The previous version of this file imported
`_resolve_mustache_variables` from `agent.ec_skills.build_node` — a
symbol that has never existed in this repo's history (verified with
`git log --all -S`). It was committed broken in be99cdc49 (2026-05-19)
and all 9 tests have failed ever since.

The real entry point is `_resolve_mustache_template(template, state,
mainwin=None)`, which resolves variables through the cascading provider
in `prompt_variable_providers.resolve_prompt_variables`. These tests
now exercise that path as it actually behaves:

* variables resolve from `state` through the cascade, in the documented
  priority order (prompt_refs → direct state key → dotted path → implicit
  node output → prompt/skill declarations → empty string);
* `state["result"]` is always a dict in production (`llm_hooks` /
  `build_node` both assign dicts), so the dot-path tests use dicts. The
  JSON-string form that the old test asserted is not a production shape —
  see `test_result_as_json_string_does_not_resolve`, which pins that gap
  deliberately rather than pretending it works;
* an unresolved variable renders as an empty string AND logs a warning,
  because a silently-blank prompt is exactly the failure this needs to
  make visible.
"""
from __future__ import annotations

import json
import logging
from contextlib import contextmanager

import pytest


@contextmanager
def _capture_eCan(caplog):
    """Capture warnings from the eCan logger.

    It sets `propagate = False` and writes through an async
    QueueHandler, so caplog's root handler never sees a record —
    `caplog.text` is empty no matter what level is set. The only way to
    observe these warnings is to attach caplog's handler to the logger.
    """
    ecan_logger = logging.getLogger("eCan")
    ecan_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.WARNING, logger="eCan"):
            yield
    finally:
        ecan_logger.removeHandler(caplog.handler)


# ============================================================================
# Template resolution against the real entry point
# ============================================================================


class TestMustacheVariableResolution:
    """`_resolve_mustache_template` — the function skills actually call."""

    @staticmethod
    def _resolve(template: str, state: dict) -> str:
        from agent.ec_skills.build_node import _resolve_mustache_template

        return _resolve_mustache_template(template, state)

    def test_template_without_variables_is_returned_verbatim(self):
        assert self._resolve("just plain text", {"anything": 1}) == "just plain text"

    def test_empty_template(self):
        assert self._resolve("", {"name": "Alice"}) == ""

    def test_simple_variable_replacement(self):
        assert self._resolve(
            "Hello {{name}}, welcome!", {"name": "Alice"}
        ) == "Hello Alice, welcome!"

    def test_dot_path_tool_result(self):
        """{{tool_result.<node>.<field>}} reads a named node's output."""
        assert self._resolve(
            "Product: {{tool_result.collector.product_name}}",
            {"tool_result": {"collector": {"product_name": "iPhone 17 Pro Max"}}},
        ) == "Product: iPhone 17 Pro Max"

    def test_dot_path_result(self):
        """{{result.<field>}} reads the LLM node's output dict."""
        assert self._resolve(
            "Brand: {{result.brand}}",
            {"result": {"brand": "Apple"}},
        ) == "Brand: Apple"

    def test_deeply_nested_dot_path(self):
        assert self._resolve(
            "{{result.llm_result.tool_input.query}}",
            {"result": {"llm_result": {"tool_input": {"query": "cheap earbuds"}}}},
        ) == "cheap earbuds"

    def test_tool_result_whole_node_output_serialises_as_json(self):
        """A dict value is JSON-encoded so an MCP tool gets valid JSON."""
        out = self._resolve(
            "{{tool_result.collector}}",
            {"tool_result": {"collector": {"product_name": "iPhone"}}},
        )
        assert json.loads(out) == {"product_name": "iPhone"}

    def test_simple_var_dict_value_is_json_encoded(self):
        out = self._resolve("{{tool_result}}", {"tool_result": {"a": 1}})
        assert json.loads(out) == {"a": 1}

    def test_falsy_values_are_preserved_and_do_not_warn(self, caplog):
        """0 / False / [] are answers, not misses.

        The miss check distinguishes "resolved to a falsy value" from
        "not found" — `resolve_prompt_variables` returns "" for the
        latter. An earlier version of this fix tested `if not val`,
        which rendered `{{count}}` as empty instead of `0` and warned
        about a correct answer. That silently changed prompt text for
        every skill that interpolates a falsy value.
        """
        for template, state, expected in (
            ("N={{count}}", {"count": 0}, "N=0"),
            ("F={{flag}}", {"flag": False}, "F=False"),
            ("L={{items}}", {"items": []}, "L=[]"),
            ("H={{name}}", {"name": "Alice"}, "H=Alice"),
        ):
            with _capture_eCan(caplog):
                result = self._resolve(template, state)
            assert result == expected, (
                f"{template!r} with {state!r} rendered {result!r}, "
                f"expected {expected!r}"
            )
            assert caplog.text == "", (
                f"{template!r} with {state!r} resolved correctly but logged "
                f"a warning: {caplog.text!r}"
            )

    def test_unknown_variable_renders_empty_and_warns(self, caplog):
        """An unresolved variable must be loud, not silently blank.

        A blank prompt is the failure mode this guards: the model gets
        "Value: " with no idea a variable was missing.
        """
        # The eCan logger sets propagate=False and routes through an
        # async QueueHandler, so caplog's root-level handler never sees
        # it — attach caplog's handler to the logger directly.
        ecan_logger = logging.getLogger("eCan")
        ecan_logger.addHandler(caplog.handler)
        try:
            with caplog.at_level(logging.WARNING, logger="eCan"):
                result = self._resolve("Value: {{unknown_var}}", {})
        finally:
            ecan_logger.removeHandler(caplog.handler)
        assert result == "Value: "
        assert "unknown_var" in caplog.text

    def test_nested_dot_path_not_found_renders_empty(self):
        assert self._resolve(
            "Value: {{tool_result.nonexistent.field}}",
            {"tool_result": {"collector": {"product_name": "iPhone"}}},
        ) == "Value: "

    def test_result_as_json_string_does_not_resolve(self, caplog):
        """Pins a real gap: `state["result"]` is only read when it is a dict.

        `resolve_prompt_variables` special-cases `{{result}}` with
        `isinstance(_direct_result, dict)`. A JSON *string* in
        state["result"] is ignored, so `{{result.field}}` renders empty.
        This is not a production shape today — both writers
        (`llm_hooks.standard_post_llm_hook` and `build_node`) assign
        dicts — so it is documented rather than fixed. If a node ever
        stores a serialised result, this test is the tripwire.
        """
        with _capture_eCan(caplog):
            result = self._resolve(
                "Name: {{result.product_name}}",
                {"result": json.dumps({"product_name": "Parsed Product"})},
            )
        assert result == "Name: "

    def test_oversized_template_is_skipped(self):
        """A >1MB template is passed through untouched, not regex-bombed."""
        big = "x" * 1_000_001 + " {{name}}"
        assert self._resolve(big, {"name": "Alice"}) == big

    def test_escaped_newline_normalisation(self):
        """JSON stores `\\n` literally; the resolver normalises before matching."""
        assert self._resolve(
            "line1 {{name}}\\nline2", {"name": "Alice"}
        ) == "line1 Alice\nline2"

    def test_section_block_does_not_double_substitute(self):
        """Vars inside {{#section}} belong to the section, not the top level."""
        out = self._resolve(
            "{{#items}}[{{name}}]{{/items}}",
            {"name": "TOP", "items": [{"name": "A"}, {"name": "B"}]},
        )
        assert "[A]" in out and "[B]" in out
        assert "TOP" not in out


# ============================================================================
# The variable-resolution cascade
# ============================================================================


class TestPromptVariableProviders:
    """`resolve_prompt_variables` — the cascade behind template rendering."""

    @staticmethod
    def _resolve(names: list[str], state: dict) -> dict:
        from agent.ec_skills.prompt_variable_providers import resolve_prompt_variables

        return resolve_prompt_variables(variable_names=names, state=state, mainwin=None)

    def test_input_reads_state_input(self):
        result = self._resolve(["input"], {"input": "Test input"})
        assert result.get("input") == "Test input"

    def test_input_falls_back_to_empty_not_the_last_message(self):
        """`{{input}}` must not be polluted by upstream node output.

        Regression guard: an earlier bug let condition-node output
        ({"all_done": false}) land in {{input}}, which silently swallowed
        the real customer message.
        """
        result = self._resolve(
            ["input"],
            {"tool_result": {"cond": {"all_done": False, "work_done": False}}},
        )
        assert result.get("input") == ""

    def test_prompt_refs_take_priority_over_state(self):
        """`state["prompt_refs"]` (written from the node's inputsValues) wins."""
        result = self._resolve(
            ["input"],
            {
                "input": "original input",
                "prompt_refs": {"input": "explicit ref value"},
            },
        )
        assert result.get("input") == "explicit ref value"

    def test_dotted_path_reads_state_directly(self):
        result = self._resolve(
            ["result.llm_result.all_done"],
            {"result": {"llm_result": {"all_done": True}}},
        )
        assert result.get("result.llm_result.all_done") == "True"

    def test_result_serialises_dict_to_json(self):
        """`{{result}}` is handed to prompts as pretty-printed JSON."""
        result = self._resolve(["result"], {"result": {"a": 1}})
        assert json.loads(result.get("result")) == {"a": 1}

    def test_implicit_variable_from_previous_node_output(self):
        """Zero-config: a business field from the latest node output.

        `{{product_keyword}}` with no declaration resolves from
        state["tool_result"], which is what makes skills work without
        wiring every variable.
        """
        result = self._resolve(
            ["product_keyword"],
            {"tool_result": {"collector": {"product_keyword": "iphone"}}},
        )
        assert result.get("product_keyword") == "iphone"

    def test_unknown_variable_is_empty_string_never_none(self):
        """Callers concatenate the result, so None would raise downstream."""
        result = self._resolve(["totally_unknown_xyz"], {})
        assert result.get("totally_unknown_xyz") == ""

    def test_upstream_outputs_exposes_all_node_ids(self):
        result = self._resolve(
            ["upstream_outputs"],
            {"tool_result": {"node1": {"x": 1}, "node2": {"y": 2}}},
        )
        parsed = json.loads(result.get("upstream_outputs"))
        assert set(parsed) == {"node1", "node2"}


# ============================================================================
# Import-surface guard
# ============================================================================


class TestMustacheModuleSurface:
    """The old test file's central claim, kept as an explicit assertion."""

    def test_removed_symbol_does_not_reappear(self):
        """`_resolve_mustache_variables` was never a real symbol.

        The 5-month failure of this file traced to importing a name that
        does not exist. If someone re-adds an alias, this fails and asks
        whether both entry points are meant to exist.
        """
        from agent.ec_skills import build_node

        assert not hasattr(build_node, "_resolve_mustache_variables")

    def test_template_entry_point_exists(self):
        from agent.ec_skills.build_node import _resolve_mustache_template

        assert callable(_resolve_mustache_template)

    @pytest.mark.parametrize(
        "module",
        ["agent.ec_skills.build_node", "agent.ec_skills.browser_node.runner"],
    )
    def test_both_callers_import_the_same_function(self, module):
        """One resolver, two callers — they must not drift apart."""
        import importlib

        importlib.import_module(module)

        from agent.ec_skills.build_node import _resolve_mustache_template

        assert _resolve_mustache_template is not None