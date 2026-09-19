"""L2: the model picks from a table we built, and can do nothing else.

The load-bearing test in this file is that an index we did not offer is
refused. Everything else is hygiene; that one is the security property. A model
that could hand back a selector — or an index into something we never showed it
— could be steered by page content into acting on an element of the page's
choosing. Page text is untrusted, so the answer space has to be closed.
"""

import asyncio
import json

import pytest

from agent.ec_skills.browser_use_extension import element_resolver as er
from agent.ec_skills.browser_use_extension import element_targeting as et
from agent.ec_skills.browser_use_extension.element_targeting import TargetDescriptor


class _FakeLLM:
    """Stands in for whatever pick_llm returned. Records the prompt."""

    name = "fake/strong-model"

    def __init__(self, reply):
        self._reply = reply
        self.prompts = []

    async def ainvoke(self, prompt):
        self.prompts.append(prompt)
        if isinstance(self._reply, Exception):
            raise self._reply
        return type("R", (), {"content": self._reply})()


@pytest.fixture(autouse=True)
def clean():
    et.reset()
    yield
    et.reset()


def _candidates():
    return [
        er.Candidate(index=1, text="1", role="listitem"),
        er.Candidate(index=2, text="Alice Chen", role="listitem"),
        er.Candidate(index=3, text="2 分钟前", role="listitem"),
    ]


def _run(coro):
    # asyncio.run: 3.14 has no implicit loop in the main thread.
    return asyncio.run(coro)


# ── the closed answer space ────────────────────────────────────────────────

def test_it_accepts_an_index_it_offered():
    llm = _FakeLLM('{"index": 2, "confidence": 0.9, "why": "looks like a name"}')
    r = _run(er.resolve_element(TargetDescriptor(target_text="customer name"),
                                _candidates(), site="s", element="row_name", llm=llm))
    assert r.resolved and r.index == 2
    assert r.confidence == pytest.approx(0.9)


def test_an_index_that_was_never_offered_is_refused():
    """THE security property: the answer space is the table, nothing else."""
    llm = _FakeLLM('{"index": 99, "confidence": 1.0, "why": "trust me"}')
    r = _run(er.resolve_element(TargetDescriptor(target_text="customer name"),
                                _candidates(), site="s", element="row_name", llm=llm))
    assert not r.resolved
    assert "not in candidates" in r.why


@pytest.mark.parametrize("hostile", [
    '{"index": "div.evil > button", "confidence": 1.0}',   # a selector
    '{"index": "2; alert(1)", "confidence": 1.0}',          # injection-ish
    '{"index": [2], "confidence": 1.0}',                    # wrong type
    '{"index": 2.7, "confidence": 1.0}',                    # non-integral
])
def test_anything_that_is_not_a_plain_index_is_refused(hostile):
    """Including 2.7 — int() would make that a confident pick at index 2,
    which is a guess we invented rather than one the model made."""
    llm = _FakeLLM(hostile)
    r = _run(er.resolve_element(TargetDescriptor(target_text="x"), _candidates(),
                                site="s", element="row_name", llm=llm))
    assert not r.resolved, f"must refuse {hostile!r}, got index={r.index}"


def test_a_boolean_is_not_an_index():
    """True == 1 in Python, so a sloppy check would resolve to candidate 1."""
    llm = _FakeLLM('{"index": true, "confidence": 1.0}')
    r = _run(er.resolve_element(TargetDescriptor(target_text="x"), _candidates(),
                                site="s", element="row_name", llm=llm))
    assert not r.resolved


def test_an_integral_float_is_accepted():
    """2.0 is unambiguous; only fractional values are a guess."""
    llm = _FakeLLM('{"index": 2.0, "confidence": 0.9}')
    r = _run(er.resolve_element(TargetDescriptor(target_text="x"), _candidates(),
                                site="s", element="row_name", llm=llm))
    assert r.resolved and r.index == 2


def test_null_means_no_match_and_that_is_a_valid_answer():
    """The prompt tells it null is safe. A wrong pick is worse than a miss."""
    llm = _FakeLLM('{"index": null, "confidence": 0.2, "why": "none match"}')
    r = _run(er.resolve_element(TargetDescriptor(target_text="x"), _candidates(),
                                site="s", element="row_name", llm=llm))
    assert not r.resolved


@pytest.mark.parametrize("junk", ["", "I think it's the second one",
                                  "```json\n{bad}\n```", "null"])
def test_unparseable_answers_degrade_to_no_match(junk):
    llm = _FakeLLM(junk)
    r = _run(er.resolve_element(TargetDescriptor(target_text="x"), _candidates(),
                                site="s", element="row_name", llm=llm))
    assert not r.resolved


def test_json_wrapped_in_prose_or_fences_still_parses():
    llm = _FakeLLM('Sure!\n```json\n{"index": 2, "confidence": 0.8}\n```\n')
    r = _run(er.resolve_element(TargetDescriptor(target_text="x"), _candidates(),
                                site="s", element="row_name", llm=llm))
    assert r.resolved and r.index == 2


# ── it must never break the caller ─────────────────────────────────────────

def test_a_model_that_raises_becomes_a_no_match_not_an_exception():
    llm = _FakeLLM(RuntimeError("provider down"))
    r = _run(er.resolve_element(TargetDescriptor(target_text="x"), _candidates(),
                                site="s", element="row_name", llm=llm))
    assert not r.resolved and r.error


def test_no_candidates_short_circuits_without_calling_the_model():
    llm = _FakeLLM('{"index": 1}')
    r = _run(er.resolve_element(TargetDescriptor(target_text="x"), [],
                                site="s", element="row_name", llm=llm))
    assert not r.resolved
    assert llm.prompts == [], "must not spend a call on an empty table"


# ── budget ─────────────────────────────────────────────────────────────────

def test_the_run_budget_stops_a_wholly_broken_page_from_burning_calls():
    llm = _FakeLLM('{"index": 2, "confidence": 0.9}')
    budget = er.ResolverBudget(limit=2)
    for _ in range(2):
        _run(er.resolve_element(TargetDescriptor(target_text="x"), _candidates(),
                                site="s", element="row_name", llm=llm, budget=budget))
    r = _run(er.resolve_element(TargetDescriptor(target_text="x"), _candidates(),
                                site="s", element="row_name", llm=llm, budget=budget))
    assert not r.resolved
    assert len(llm.prompts) == 2, "budget must stop the third call"
    assert budget.remaining() == 0


# ── the prompt ─────────────────────────────────────────────────────────────

def test_the_prompt_carries_the_candidates_and_the_target():
    llm = _FakeLLM('{"index": 2}')
    _run(er.resolve_element(
        TargetDescriptor(target_text="customer name", container_hint="conversation list"),
        _candidates(), site="s", element="row_name", llm=llm))
    prompt = llm.prompts[0]
    assert "Alice Chen" in prompt
    assert "customer name" in prompt
    assert "conversation list" in prompt


def test_the_prompt_says_page_text_is_untrusted():
    """Structural defence is the real one, but the instruction costs nothing."""
    assert "UNTRUSTED" in er._SYSTEM_PROMPT
    assert "NEVER INSTRUCTIONS" in er._SYSTEM_PROMPT


def test_the_prompt_prefers_what_a_human_would_see():
    """The whole thesis: visible text beats structure."""
    lowered = er._SYSTEM_PROMPT.lower()
    assert "class names" in lowered and "weak evidence" in lowered


def test_candidates_are_capped_so_the_table_stays_readable():
    many = [er.Candidate(index=i, text=f"row {i}") for i in range(200)]
    llm = _FakeLLM('{"index": 1}')
    _run(er.resolve_element(TargetDescriptor(target_text="x"), many,
                            site="s", element="row_name", llm=llm))
    sent = json.loads(llm.prompts[0].split("INPUT:\n", 1)[1])
    assert len(sent["candidates"]) == er.MAX_CANDIDATES


def test_oversized_candidate_text_is_truncated():
    """A page can carry megabytes in one attribute."""
    big = er.Candidate(index=1, text="x" * 10_000, nearby="y" * 10_000)
    payload = big.for_prompt()
    assert len(payload["text"]) <= 200 and len(payload["nearby"]) <= 200


# ── wiring ─────────────────────────────────────────────────────────────────

def test_it_is_off_unless_explicitly_enabled(monkeypatch):
    monkeypatch.delenv("ECAN_ELEMENT_RESOLVER", raising=False)
    assert not er.resolver_enabled()
    monkeypatch.setenv("ECAN_ELEMENT_RESOLVER", "1")
    assert er.resolver_enabled()


def test_the_resolver_model_is_a_separate_knob_from_the_run_model(monkeypatch):
    """The run may be on a cheap model for cost; this decision should not be."""
    monkeypatch.setenv("ECAN_RESOLVER_MODEL", "anthropic/claude-opus-5")
    assert er._resolver_model() == ("anthropic", "claude-opus-5")
    monkeypatch.setenv("ECAN_RESOLVER_MODEL", "gpt-5")
    assert er._resolver_model() == (None, "gpt-5")
    monkeypatch.delenv("ECAN_RESOLVER_MODEL")
    assert er._resolver_model() == (None, None)


def test_rows_from_a_page_snapshot_convert_to_candidates():
    rows = [{"index": "1", "text": "Alice", "role": "listitem"},
            {"index": "bad"}, "not a dict", {"no_index": 1}]
    got = er.candidates_from_rows(rows)
    assert [c.index for c in got] == [1]
    assert got[0].text == "Alice"


def test_resolutions_are_recorded_for_the_phase_1_report():
    llm = _FakeLLM('{"index": 2, "confidence": 0.9}')
    _run(er.resolve_element(TargetDescriptor(target_text="x"), _candidates(),
                            site="s", element="row_name", llm=llm))
    assert et.resolution_report()["s"]["row_name"]["resolver_hit"]["ok"] == 1


def test_the_resolver_module_names_no_business():
    import pathlib
    src = pathlib.Path(er.__file__).read_text(encoding="utf-8").lower()
    for term in ("feige", "douyin", "jinritemai", "etsy", "ebay"):
        assert term not in src
