"""The form-data browser actions build page scripts the prompt renderer leaves
alone and that carry their parameters as JSON (no quoting for the model to fumble)."""
from agent.ec_skills.browser_use_extension import form_store_tools as t


def test_scripts_carry_their_parameters_as_json():
    for js in (t._probe_js('身高 "cm"'), t._read_js("size_chart_form/configTable"),
               t._write_js("a/b", {"x": [1, "二"]}), t._revert_js("a/b")):
        assert "{{" not in js and "}}" not in js
    import json
    assert json.dumps('身高 "cm"') in t._probe_js('身高 "cm"')
    assert json.dumps({"x": [1, "二"]}, ensure_ascii=False) in t._write_js("a/b", {"x": [1, "二"]})


def test_the_four_actions_are_registered():
    from agent.ec_skills.browser_use_extension.extension_tools_service import custom_controller
    names = set(custom_controller.registry.registry.actions)
    assert {"probe_page_data", "read_form_field", "write_form_field", "revert_form_field"} <= names


def test_the_value_is_json_not_a_json_string():
    rows = [{"size": "110/48", "specMap": {"身高(cm)": "100-110"}}]
    assert t._as_value(rows) == rows
    assert t._as_value('[{"size": "110/48"}]') == [{"size": "110/48"}]
    # Opus's over-escaped attempt (KEN 2026-10-30)
    assert t._as_value(r'[{\"size\": \"120/50\"}]') == [{"size": "120/50"}]
    assert t._as_value("plain text") == "plain text"
