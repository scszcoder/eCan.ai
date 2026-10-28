"""select_option picks a REAL option of a custom dropdown (KEN 2026-10-25: the
agent typed values that were not options, e.g. 无, and nothing got selected)."""
from agent.ec_skills.browser_use_extension.extension_tools_service import pick_option


def test_exact_match_wins_over_partial():
    assert pick_option(["圆领T恤领", "圆领", "V领"], "圆领") == 1


def test_option_containing_the_text():
    assert pick_option(["A类（婴幼儿用品）", "B类（直接接触皮肤）", "C类"], "B类") == 1


def test_text_containing_the_option_and_spaces_ignored():
    assert pick_option(["其他", "宽松型"], "宽松 型 版型") == 1


def test_no_match_returns_none():
    assert pick_option(["高", "中", "低"], "无") is None
    assert pick_option([], "无") is None
    assert pick_option(["高"], "  ") is None
