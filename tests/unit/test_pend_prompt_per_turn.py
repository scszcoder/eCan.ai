"""A requirements-collecting chat skill (LLM -> pend_event whose prompt is the
LLM's next question) showed the 1st question, then raw LLM JSON, and never
showed later questions:

- the pend node's "already sent" guard was keyed on (skill, node, chat) for the
  life of the process, so every later question in that chat was suppressed;
- on the interrupt the runner also sent the run's result, i.e. the same
  question again as raw JSON.
"""
import json
from types import SimpleNamespace

from agent.ec_tasks.runner import _interrupt_prompt_is_from_result, _interrupt_prompts


def _step(prompt, delivered=True):
    v = {"i_tag": "pend", "prompt_to_human": prompt}
    if delivered:
        v["prompt_delivered"] = True   # set by build_node's pend node once it posted the question
    return {"__interrupt__": (SimpleNamespace(value=v),)}


Q = "Please share the folder path, and tell me the \"target\" marketplace."


def test_prompt_from_result_dict():
    values = {"result": {"all_done": True, "question": Q, "work_done": True}}
    assert _interrupt_prompt_is_from_result(_step(Q), values)


def test_prompt_from_result_json_string():
    values = {"result": json.dumps({"all_done": True, "question": Q})}
    assert _interrupt_prompt_is_from_result(_step(Q), values)


def test_static_prompt_still_gets_the_llm_reply():
    values = {"result": {"llm_result": {"casual_chat_response": "Sure, here it is."}}}
    assert not _interrupt_prompt_is_from_result(_step("请输入您的回复"), values)


def test_no_prompt_keeps_old_behaviour():
    values = {"result": {"question": Q}}
    assert not _interrupt_prompt_is_from_result(_step(""), values)


def test_interrupt_prompts_gates_auto_resume():
    # A pend that asked the user something must wait for the reply (no
    # auto-resume with the message that started the run); one that asked
    # nothing is the "wait for the first message" case auto-resume feeds.
    assert _interrupt_prompts(_step(Q)) == [Q]
    assert _interrupt_prompts(_step("")) == []
    assert _interrupt_prompts({}) == []


def test_code_built_interrupt_keeps_old_behaviour():
    # common_nodes.pend_for_human_input_node (self-tester chat) puts the LLM's
    # reply in prompt_to_human but never posts it: the runner's result send is
    # how the user sees it, and auto-resume must stay as it was.
    values = {"result": {"llm_result": {"casual_chat_response": Q}}}
    assert not _interrupt_prompt_is_from_result(_step(Q, delivered=False), values)
    assert _interrupt_prompts(_step(Q, delivered=False)) == []
