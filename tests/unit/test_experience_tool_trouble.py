"""A tool that fails on many different fields is flagged as the tool's problem
(ours), not explored as page parts (抖店 select_option, KEN 11-01)."""
from agent.ec_skills.experience import tool_trouble, tool_trouble_text
from agent.ec_skills.explorer.loop import _log_tool_issues


def _fail(tool, text, err="box shows ''"):
    return {"failed": [{"action": tool, "args": {"index": 1, "text": text}, "error": err}]}


def test_many_fields_flag_the_tool():
    trace = [_fail("select_option", f) for f in ("棉", "通用", "运动风", "B类", "春秋")]
    issues = tool_trouble(trace)
    assert issues[0]["tool"] == "select_option" and issues[0]["fields"] == 5
    assert "select_option" in tool_trouble_text(issues)


def test_one_field_retried_is_not_the_tool():
    # the same field failing again and again is that field's (page) problem
    trace = [_fail("select_option", "通用") for _ in range(8)] + [_fail("input", "标题")]
    assert tool_trouble(trace) == []


def test_explorer_tool_issues_are_read_from_its_answer():
    done = '{"part": "属性", "script": "", "tool_issues": [{"tool": "select_option", "claimed": "box empty", "actual": "安全等级=B类"}]}'
    assert [i["tool"] for i in _log_tool_issues(done)] == ["select_option"]
    assert _log_tool_issues('{"part": "x"}') == [] and _log_tool_issues("not json") == []
