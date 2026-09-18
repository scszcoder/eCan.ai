"""Which fingerprint profile a run uses belongs to the TASK, not the skill.

A skill can be published, shared or rented. A browser profile is a live
logged-in seller session plus the proxy credentials it egresses through, so it
must never be stored on the skill -- otherwise renting out a skill hands over
the store. The skill says "use the fingerprint browser"; the task says which
identity to be.

That makes the precedence load-bearing rather than cosmetic:

    task.metadata["browser_identity"]["browser_profile_id"]   wins over
    the node's `browserProfileId`                             which is only a
                                                              single-user
                                                              convenience

Observed 2026-09-18: a node set to the fingerprint browser with no profile id
fell through to an empty default profile and browsed Etsy logged-out from the
user's own IP -- which is also why acquisition now fails closed.
"""

import pytest

from agent.ec_skills.browser_node.build_helpers import resolve_state_browser_identity


class _Task:
    def __init__(self, metadata=None, name="t"):
        self.metadata = metadata or {}
        self.name = name


def _apply(task, state):
    from agent.ec_skills.prep_skills_run import apply_task_vars
    apply_task_vars(task, state)
    return state


# ── the task carries the identity ──────────────────────────────────────────

def test_a_task_can_name_the_fingerprint_profile():
    state = _apply(
        _Task({"browser_identity": {"browser_profile_id": "etsy"}}), {})
    assert resolve_state_browser_identity(state)["browser_profile_id"] == "etsy"


@pytest.mark.parametrize("alias", ["browser_profile_id",
                                   "fingerprint_profile_id",
                                   "profile_id"])
def test_the_spellings_a_task_may_use_all_land_in_one_place(alias):
    state = _apply(_Task({"browser_identity": {alias: "etsy"}}), {})
    assert resolve_state_browser_identity(state)["browser_profile_id"] == "etsy"


def test_two_tasks_on_one_shared_skill_get_different_identities():
    """The entire point: one rented skill, two stores, no crosstalk."""
    a = _apply(_Task({"browser_identity": {"browser_profile_id": "etsy_main"}}), {})
    b = _apply(_Task({"browser_identity": {"browser_profile_id": "etsy_alt"}}), {})

    assert resolve_state_browser_identity(a)["browser_profile_id"] == "etsy_main"
    assert resolve_state_browser_identity(b)["browser_profile_id"] == "etsy_alt"


def test_profile_id_is_distinct_from_the_browser_use_profile():
    """`profile` (a browser-use preset) and `profile_id` (an identity) are
    different things that have collided in the UI before."""
    state = _apply(_Task({"browser_identity": {
        "profile": "some_browser_use_preset",
        "browser_profile_id": "etsy",
    }}), {})
    resolved = resolve_state_browser_identity(state)
    assert resolved["browser_profile"] == "some_browser_use_preset"
    assert resolved["browser_profile_id"] == "etsy"


def test_a_task_without_an_identity_resolves_nothing():
    """So the node's own value is used, and nothing is invented."""
    assert "browser_profile_id" not in resolve_state_browser_identity(_apply(_Task(), {}))
    assert "browser_profile_id" not in resolve_state_browser_identity({})


# ── precedence: task over skill ────────────────────────────────────────────

def _effective(run_identity, node_setting):
    """The expression used at both acquire_browser call sites."""
    return run_identity.get("browser_profile_id") or node_setting or None


def test_the_task_wins_over_a_profile_left_on_the_skill():
    assert _effective({"browser_profile_id": "etsy"}, "stale_from_skill") == "etsy"


def test_the_node_value_is_the_fallback_for_a_private_skill():
    assert _effective({}, "etsy") == "etsy"


def test_neither_resolves_to_none_so_the_caller_fails_closed():
    assert _effective({}, "") is None


# ── the two call sites must not drift apart ────────────────────────────────

def test_both_acquire_sites_prefer_the_task_identity():
    """build_helpers and session.py duplicate this wiring and have drifted
    before (the monitor-param round-trip incident)."""
    import inspect
    from agent.ec_skills.browser_node import build_helpers, session

    bh = inspect.getsource(build_helpers)
    assert 'get("browser_profile_id")' in bh, (
        "build_helpers no longer prefers the task's identity")

    sm = inspect.getsource(session)
    assert "state_profile_id or self.cfg.browser_profile_id" in sm, (
        "session.py no longer prefers the task's identity")


def test_the_fingerprint_browser_fails_closed_at_both_sites():
    """Falling back to an unprotected browser leaks the real IP."""
    import inspect
    from agent.ec_skills.browser_node import build_helpers, session

    for mod in (build_helpers, session):
        src = inspect.getsource(mod)
        # Match on text that survives line wrapping in the f-string.
        assert "BrowserType.FINGERPRINT" in src and "unprotected browser" in src, (
            "{} no longer refuses to degrade a fingerprint run to an "
            "unprotected browser".format(mod.__name__)
        )
