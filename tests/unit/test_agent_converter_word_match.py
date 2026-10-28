"""A task with no bound skill is matched by shared words only when one skill wins."""
from types import SimpleNamespace

from agent.agent_converter import _find_matching_skill_for_task


def _skill(name):
    return SimpleNamespace(name=name, id=f"id_{name}", runnable=object())


def test_generic_words_shared_by_several_skills_do_not_pick_one():
    task = SimpleNamespace(name="ebay_after_sales_daily", skill=None)
    pool = [_skill(n) for n in ("amazon_after_sales", "shopify_after_sales", "tiktok_after_sales", "demo0")]
    matched, _ = _find_matching_skill_for_task(task, pool, [])
    assert matched is None


def test_single_best_word_match_still_attaches():
    task = SimpleNamespace(name="chat:product listing chatter task", skill=None)
    pool = [_skill(n) for n in ("product_listing_orchestrator", "shopify_after_sales")]
    matched, _ = _find_matching_skill_for_task(task, pool, [])
    assert matched.name == "product_listing_orchestrator"
