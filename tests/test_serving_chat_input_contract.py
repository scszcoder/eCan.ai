"""The visitor's sentence has to reach `state["input"]` as bare text.

A web customer-service turn came back empty with 0 tokens and $0.00 — the model
was never asked, because `state["input"]` was empty while the visitor's text sat
elsewhere in the state as a JSON envelope.

The chain is four links long and nothing guarded it end to end, which is how it
drifted:

    cn_worker_main   WorkerMessage(prompt=...)
    worker_main      in_msg.params.message.parts[0].text = msg.prompt
    prep_skills_run  _extract_chat_message_input_patch -> state["input"]
    build_node       user-turn template defaults to "{{input}}"

Each link is cheap to test on its own; together they are the contract. If any
one of them changes shape, the model silently gets asked the wrong thing — and
an empty reply looks identical whether the model answered nothing or was never
called.
"""

import json
from uuid import uuid4

import pytest

# `prep_skills_run` and `ec_tasks.runner` import each other
# (prep_skills_run -> ec_tasks.resume -> ... -> runner -> prep_skills_run), so
# importing prep_skills_run first hits a partially-initialized module. In
# production the cycle resolves because the agent stack is already loaded by
# the time prep_skills_run is reached. Importing runner first reproduces that
# order. Pre-existing; not introduced by the fix under test.
import agent.ec_tasks.runner  # noqa: F401  (import-order fix, see above)


# ---------------------------------------------------------------------------
# Link 1 — what the serving path puts in WorkerMessage.prompt
# ---------------------------------------------------------------------------

def test_the_visitor_sentence_is_passed_bare_not_as_an_envelope():
    """cn_serve hands over {"text": ..., "conversation_id": ...}.

    Serializing that whole dict asked the model to answer the envelope.
    """
    from agent.cloud_worker.cn_worker_main import _prompt_from_test_inputs

    prompt = _prompt_from_test_inputs(
        {"text": "订单什么时候发货？", "conversation_id": "conv-1"})

    assert prompt == "订单什么时候发货？"
    assert "conversation_id" not in prompt
    assert not prompt.lstrip().startswith('{')


def test_test_inputs_without_text_keep_the_legacy_envelope():
    """A launcher-run skill whose template expects its testInputs as JSON."""
    from agent.cloud_worker.cn_worker_main import _prompt_from_test_inputs

    prompt = _prompt_from_test_inputs({"city": "上海", "sku": "A-1"})

    assert json.loads(prompt) == {"city": "上海", "sku": "A-1"}


@pytest.mark.parametrize("blank", ["", "   ", None, 123])
def test_a_blank_or_non_string_text_falls_back_rather_than_sending_nothing(blank):
    from agent.cloud_worker.cn_worker_main import _prompt_from_test_inputs

    prompt = _prompt_from_test_inputs({"text": blank, "conversation_id": "c"})

    assert json.loads(prompt)["conversation_id"] == "c"


def test_non_dict_test_inputs_do_not_raise():
    from agent.cloud_worker.cn_worker_main import _prompt_from_test_inputs

    assert _prompt_from_test_inputs(None) == "null"
    assert _prompt_from_test_inputs(["a"]) == '["a"]'


# ---------------------------------------------------------------------------
# Links 2 + 3 — prompt -> parts[0].text -> state["input"]
# ---------------------------------------------------------------------------

def _in_msg(prompt: str, chat_id: str = "chat-1") -> dict:
    """The message worker_main._run_skill_once builds from a WorkerMessage.

    Mirrors worker_main.py — if that shape changes, the assertion below about
    where prep_skills_run finds the text is what should fail.
    """
    return {
        "id": str(uuid4()),
        "method": "skill_run",
        "params": {
            "message": {"parts": [{"kind": "text", "text": prompt or ""}]},
            "metadata": {
                "mtype": "skill_run",
                "params": {"chatId": chat_id},
                "async_response": True,
            },
            "sessionId": chat_id,
        },
    }


def test_the_prompt_lands_in_state_input():
    from agent.ec_skills.prep_skills_run import _extract_chat_message_input_patch

    patch = _extract_chat_message_input_patch(_in_msg("有货吗？"), {}, {})

    assert patch.get("input") == "有货吗？"


def test_an_envelope_prompt_would_reach_the_model_as_json():
    """Why link 1 matters: nothing downstream unwraps it.

    This is the bug as it was — the text arrived, so the turn did not fail, and
    the model was simply asked the wrong question.
    """
    from agent.ec_skills.prep_skills_run import _extract_chat_message_input_patch

    envelope = json.dumps({"text": "有货吗？", "conversation_id": ""}, ensure_ascii=False)
    patch = _extract_chat_message_input_patch(_in_msg(envelope), {}, {})

    assert patch.get("input") == envelope, "no link in the chain unwraps JSON"


def test_an_empty_prompt_leaves_input_unset():
    """The observed failure: nothing to ask, so the node renders {{input}} empty."""
    from agent.ec_skills.prep_skills_run import _extract_chat_message_input_patch

    patch = _extract_chat_message_input_patch(_in_msg(""), {}, {})

    assert not patch.get("input")


def test_the_serving_path_end_to_end_gives_the_model_the_sentence():
    """Link 1 into links 2+3, the way a real turn runs."""
    from agent.cloud_worker.cn_worker_main import _prompt_from_test_inputs
    from agent.ec_skills.prep_skills_run import _extract_chat_message_input_patch

    # What cn_serve puts in options["testInputs"] for a web chat turn.
    test_inputs = {"text": "你们周末发货吗？", "conversation_id": "conv-9"}

    prompt = _prompt_from_test_inputs(test_inputs)
    patch = _extract_chat_message_input_patch(_in_msg(prompt), {}, {})

    assert patch.get("input") == "你们周末发货吗？"


# ---------------------------------------------------------------------------
# Link 4 — the node renders state["input"]
# ---------------------------------------------------------------------------

def test_the_user_turn_template_defaults_to_the_input_variable():
    """If this default changes, state["input"] stops being what the model sees."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1]
           / 'agent/ec_skills/build_node.py').read_text(encoding='utf-8')

    assert 'inline_user_prompt = ((inputs.get("prompt") or {}).get("content") or "{{input}}")' in src


# ---------------------------------------------------------------------------
# The helper underneath links 2+3
# ---------------------------------------------------------------------------

def test_safe_get_indexes_lists():
    """`parts.0.text` is the A2A message shape; it used to always yield None.

    Both callers of a numeric path (prep_skills_run's primary chat accessor and
    resume.py's a2a_result) were silently getting nothing.
    """
    from agent.ec_tasks.resume import _safe_get

    msg = {"params": {"message": {"parts": [{"kind": "text", "text": "hi"},
                                            {"kind": "text", "text": "second"}]}}}

    assert _safe_get(msg, "params.message.parts.0.text") == "hi"
    assert _safe_get(msg, "params.message.parts.1.text") == "second"
    assert _safe_get(msg, "params.message.parts.-1.text") == "second"


def test_safe_get_returns_the_default_for_an_out_of_range_index():
    from agent.ec_tasks.resume import _safe_get

    assert _safe_get({"a": [1]}, "a.5", "fallback") == "fallback"
    assert _safe_get({"a": []}, "a.0") is None


def test_a_dict_key_that_looks_like_an_index_still_wins():
    """Dicts are checked first, so a literal "0" key is not shadowed."""
    from agent.ec_tasks.resume import _safe_get

    assert _safe_get({"a": {"0": "dict-wins"}}, "a.0") == "dict-wins"


def test_safe_get_still_ignores_a_numeric_segment_on_a_scalar():
    from agent.ec_tasks.resume import _safe_get

    assert _safe_get({"a": "text"}, "a.0") is None
