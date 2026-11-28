"""A browser step whose site failed is run again later in the same run (Shopify admin showed a
technical error at 04:15 on 2026-11-26 and the run went on without the day's label)."""
from agent.ec_skills.browser_node.site_retry import RETRIES, retry_wait


def _result(text):
    return {"final": text, "done": True}


def test_a_site_failure_is_retried_twice_with_longer_pauses():
    r = _result('{"labels":[],"all_done":false,"retry_later":true,"reason":"technical error"}')
    waits = [retry_wait(r, n) for n in range(RETRIES + 1)]
    assert waits[0] and waits[1] > waits[0] and waits[-1] is None


def test_other_unfinished_answers_are_kept():
    for text in ('{"labels":[],"all_done":false,"reason":"over the cap"}',
                 '{"labels":[],"all_done":false,"retry_later":"maybe"}', "no json here", ""):
        assert retry_wait(_result(text), 0) is None
    assert retry_wait({"final": {"retry_later": True}}, 0)
    assert retry_wait(None, 0) is None


def test_generated_steps_are_told_when_to_ask_for_a_retry():
    from agent.skill_editor.code_agent import CODE_GENERATION_PROMPT, EDIT_FLOWGRAM_PROMPT
    for prompt in (CODE_GENERATION_PROMPT, EDIT_FLOWGRAM_PROMPT):
        assert '"retry_later": true' in prompt and "Never set retry_later for a refusal" in prompt
