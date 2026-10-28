"""A run names the page it must start on (prompt_refs.start_url): a reused
agent otherwise begins on whatever tab the last run left open -- a 拼多多
listing run woke on the previous run's 提交成功 page and reported that old
product as its own (KEN 2026-10-28)."""
from agent.ec_skills.browser_node.runner import extract_run_start_url


def test_start_url_from_prompt_refs():
    st = {"prompt_refs": {"start_url": "https://mms.pinduoduo.com/goods/category"}}
    assert extract_run_start_url(st) == "https://mms.pinduoduo.com/goods/category"


def test_no_or_bad_start_url_means_no_pre_navigation():
    assert extract_run_start_url(None) is None
    assert extract_run_start_url({}) is None
    assert extract_run_start_url({"prompt_refs": {"start_url": ""}}) is None
    assert extract_run_start_url({"prompt_refs": {"start_url": "javascript:alert(1)"}}) is None
