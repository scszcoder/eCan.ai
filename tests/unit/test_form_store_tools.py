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


_FAKE_REACT16_PAGE = r"""
// A React 16 page (fiber under __reactInternalInstance$) with an antd 3 form:
// string names, getFieldsValue() takes no `true`, setFieldsValue takes nested values.
const data = { sku: { price: 10 }, basic: { goods_name: 'x' } };
const get = (o, path) => path.split('.').reduce((a, k) => a == null ? a : a[k], o);
const merge = (t, s) => { for (const [k, v] of Object.entries(s)) { if (v && typeof v === 'object' && !Array.isArray(v) && t[k] && typeof t[k] === 'object') merge(t[k], v); else t[k] = v; } };
const form = {
  getFieldsValue: (names) => { if (names !== undefined) throw new Error('antd3 wants an array of names'); return data; },
  getFieldValue: (name) => { if (typeof name !== 'string') throw new Error('antd3 wants a string name'); return get(data, name); },
  setFieldsValue: (v) => merge(data, v),
};
const input = { tagName: 'INPUT', children: [], innerText: '', placeholder: '价格' };
input['__reactInternalInstance$abc'] = { memoizedProps: {}, return: { memoizedProps: { form }, return: null } };
global.window = global;
global.document = { querySelectorAll: () => [input] };
global.Element = function () {};
"""


def _run_in_node(js):
    import shutil
    import subprocess
    import pytest
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    out = subprocess.run([node, "-e", _FAKE_REACT16_PAGE + "(" + js + ").then(r => console.log(r))"],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def test_react16_pages_with_an_antd3_form_are_reachable():
    # 拼多多 goods_add (KEN 2026-10-31): probe found no store anywhere, because
    # the fiber was under __reactInternalInstance$ and the form was antd 3.
    import json
    probe = json.loads(_run_in_node(t._probe_js("价格")))
    assert probe["stores"] and probe["stores"][0]["kind"] == "named fields"
    assert "sku" in probe["stores"][0]["keys"]
    assert json.loads(_run_in_node(t._read_js("sku.price")))["value"] == 10
    wrote = json.loads(_run_in_node(t._write_js("sku.price", 25)))
    assert wrote["same_as_written"] is True


def test_the_store_scan_does_not_stop_at_a_side_widget():
    # 抖店 run 61: the first input belonged to a discount box; the recipe's field
    # was in the main form, further down the page, and was never found.
    import json
    page = _FAKE_REACT16_PAGE.replace("global.document = { querySelectorAll: () => [input] };", """
const side = { tagName: 'INPUT', children: [], innerText: '', placeholder: '' };
const sideForm = { getFieldsValue: () => ({ discount: 1 }), getFieldValue: (n) => n === 'discount' ? 1 : undefined, setFieldsValue: () => {} };
side['__reactInternalInstance$x'] = { memoizedProps: { form: sideForm }, return: null };
global.document = { querySelectorAll: () => [side, input] };""")
    import shutil, subprocess, pytest
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    out = subprocess.run([node, "-e", page + "(" + t._read_js("sku.price") + ").then(r => console.log(r))"],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip())["value"] == 10


def test_try_recipe_replays_the_publish_script_and_restores():
    import json
    out = json.loads(_run_in_node(t._try_recipe_js("sku.price", "return DATA.p", {"p": 33})))
    assert out["restored"] is True
    assert json.loads(out["replay"])["same_as_written"] is True
