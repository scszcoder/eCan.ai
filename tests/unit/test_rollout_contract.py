"""Server ↔ client contract for rollout.json.

``set_rollout.py`` (the GitHub-Actions control plane) writes
``{env}/channels/{channel}/rollout.json``; ``ota/core/rollout.py`` reads
it on every update check. These tests exercise the full round trip:
``execute(apply=True)`` → stored bytes → ``json.loads`` → ``is_eligible()``.

A failure here means an operator's action would NOT be enforced the way
the fleet actually behaves — the class of bug no single-side test can
catch (each side tests against its own hand-written dict).

Covered:
  * promote (default 100 / percent=0 / cohort whitelist) mirrored through
    the client decision table
  * pause gates every version; resume reopens
  * ramp monotonicity and reduce shrinkage via stable buckets
  * ``v``-prefix normalization parity
  * corrupt/missing record = open on both sides
  * guard failures write nothing (client keeps seeing the old state)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "build_system" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import set_rollout  # noqa: E402
from ota.core.rollout import bucket_for, is_eligible  # noqa: E402
from test_set_rollout import FakeStore as _SharedFakeStore  # noqa: E402

pytestmark = pytest.mark.unit

ROLLOUT_KEY = "channels/stable/rollout.json"
CLIENT_KEYS = ("version", "percent", "paused", "cohort_include_prefix")


def _store():
    """Shared in-memory store, with this file's default release set."""
    return _SharedFakeStore(releases=("1.0.0", "2.0.0", "2.1.0"))


def _apply(store, action, **kw):
    """Run an action with apply=True; fail loudly if the guard blocked it."""
    res = set_rollout.execute(
        store, "intl", "production", "stable", action=action, apply=True, **kw
    )
    assert not res["guard_errors"], res["guard_errors"]
    assert res["written"] is True, "guard passed but nothing was written"
    return res


def _stored(store):
    raw = store.get(ROLLOUT_KEY)
    assert raw, "rollout.json was not written"
    doc = json.loads(raw.decode("utf-8"))
    for key in CLIENT_KEYS:
        assert key in doc, f"client-required key {key!r} missing from {doc!r}"
    return doc


# ---------------------------------------------------------------------------
# promote
# ---------------------------------------------------------------------------

def test_promote_default_is_fully_open_on_both_sides():
    store = _store()
    _apply(store, "promote", version="2.1.0")
    doc = _stored(store)
    assert doc["percent"] == 100
    assert doc["paused"] is False
    assert doc["version"] == "2.1.0"
    # Client: every install passes the governed candidate.
    assert is_eligible(doc, "2.1.0", "install-a")
    assert is_eligible(doc, "2.1.0", "install-b")


def test_missing_record_is_open_on_both_sides():
    store = _store()
    st = set_rollout.collect_status(store, "intl", "production", "stable")
    assert st["rollout_exists"] is False
    # Server's normalized view and the client's None both mean "open".
    assert st["rollout"]["percent"] == set_rollout.DEFAULT_PERCENT
    assert st["rollout"]["paused"] is False
    assert is_eligible(None, "2.1.0", "install-a")
    assert is_eligible(st["rollout"], "2.1.0", "install-a")


def test_promote_zero_percent_blocks_except_whitelist_and_other_versions():
    store = _store()
    _apply(store, "promote", version="2.1.0", percent=0, cohort="Alice, bob")
    doc = _stored(store)
    assert doc["percent"] == 0
    assert doc["cohort_include_prefix"] == ["alice", "bob"]

    # Percentage gate: nobody outside the whitelist.
    assert not is_eligible(doc, "2.1.0", "install-a")
    # Whitelist beats percent=0.
    assert is_eligible(doc, "2.1.0", "install-a", user_prefix="alice")
    assert is_eligible(doc, "2.1.0", "install-a", user_prefix="bob")
    assert not is_eligible(doc, "2.1.0", "install-a", user_prefix="eve")
    # The gate only governs the version it names.
    assert is_eligible(doc, "2.0.0", "install-a")


def test_cohort_accepts_phone_and_openid_identities():
    """cohort entries are opaque identity strings — phone-login and
    WeChat-login accounts whitelist exactly like email accounts."""
    store = _store()
    _apply(
        store, "promote", version="2.1.0", percent=0,
        cohort="13800138000, AABE7F97",
    )
    doc = _stored(store)
    assert doc["cohort_include_prefix"] == ["13800138000", "aabe7f97"]

    assert is_eligible(doc, "2.1.0", "install-a", user_prefix="13800138000")
    assert is_eligible(doc, "2.1.0", "install-a", user_prefix="AABE7F97")
    assert not is_eligible(doc, "2.1.0", "install-a", user_prefix="139")
    assert not is_eligible(doc, "2.1.0", "install-a")  # logged out


# ---------------------------------------------------------------------------
# pause / resume
# ---------------------------------------------------------------------------

def test_pause_gates_every_version_resume_reopens():
    store = _store()
    _apply(store, "promote", version="2.1.0")
    assert is_eligible(_stored(store), "2.1.0", "install-a")
    assert is_eligible(_stored(store), "1.0.0", "install-a")

    _apply(store, "pause")
    doc = _stored(store)
    assert doc["paused"] is True
    assert not is_eligible(doc, "2.1.0", "install-a")
    # Paused beats version scope: even non-governed candidates stop.
    assert not is_eligible(doc, "1.0.0", "install-a")

    _apply(store, "resume")
    doc = _stored(store)
    assert doc["paused"] is False
    assert doc["percent"] == 100  # resume keeps the record's percent
    assert is_eligible(doc, "2.1.0", "install-a")
    assert is_eligible(doc, "1.0.0", "install-a")


def test_pause_without_existing_record_gates_all_versions():
    store = _store()
    _apply(store, "pause")
    doc = _stored(store)
    assert doc["paused"] is True
    assert doc["version"] == ""  # no scope: hold everything
    assert not is_eligible(doc, "2.1.0", "install-a")
    assert not is_eligible(doc, "1.0.0", "install-a")


# ---------------------------------------------------------------------------
# ramp / reduce (stable buckets)
# ---------------------------------------------------------------------------

def test_ramp_monotone_reduce_shrinks_percent_only():
    ids = [f"install-{i}" for i in range(300)]

    store = _store()
    _apply(store, "promote", version="2.1.0", percent=0)
    zero = _stored(store)
    assert not any(is_eligible(zero, "2.1.0", i) for i in ids)

    _apply(store, "ramp", percent=20)
    doc20 = _stored(store)
    eligible20 = {i for i in ids if is_eligible(doc20, "2.1.0", i)}

    _apply(store, "ramp", percent=60)
    doc60 = _stored(store)
    eligible60 = {i for i in ids if is_eligible(doc60, "2.1.0", i)}
    # Same version, same install ids, higher percent ⇒ never shrinks.
    assert eligible20 <= eligible60

    _apply(store, "reduce", percent=10)
    doc10 = _stored(store)
    assert doc10["percent"] == 10
    # reduce changes only the percent; scope/cohort survive.
    assert doc10["version"] == "2.1.0"
    eligible10 = {i for i in ids if is_eligible(doc10, "2.1.0", i)}
    assert eligible10 <= eligible20

    # Full open at the end.
    _apply(store, "ramp", percent=100)
    assert all(is_eligible(_stored(store), "2.1.0", i) for i in ids)


def test_reduce_below_existing_requires_existing_rollout():
    store = _store()  # no rollout.json yet
    res = set_rollout.execute(
        store, "intl", "production", "stable",
        action="reduce", percent=10, apply=True,
    )
    assert res["guard_errors"]
    assert res["written"] is False
    assert store.get(ROLLOUT_KEY) is None


# ---------------------------------------------------------------------------
# version normalization parity
# ---------------------------------------------------------------------------

def test_v_prefix_normalized_on_write_governs_both_spellings_on_read():
    store = _store()
    _apply(store, "promote", version="v2.1.0", percent=0)
    doc = _stored(store)
    assert doc["version"] == "2.1.0"  # server strips the v
    # Client normalizes the candidate too — both spellings are governed.
    assert not is_eligible(doc, "v2.1.0", "install-a")
    assert not is_eligible(doc, "2.1.0", "install-a")
    # A different version stays out of scope.
    assert is_eligible(doc, "v2.0.0", "install-a")


# ---------------------------------------------------------------------------
# failure modes: open on both sides, guard failures write nothing
# ---------------------------------------------------------------------------

def test_corrupt_rollout_is_open_on_both_sides():
    store = _store()
    store.put(ROLLOUT_KEY, b"not-json{{", "application/json")
    st = set_rollout.collect_status(store, "intl", "production", "stable")
    # Server: unreadable record normalizes to the open default.
    assert st["rollout"]["percent"] == 100
    assert st["rollout"]["paused"] is False
    # Client equivalent: fetch fails → rollout=None → open.
    assert is_eligible(None, "2.1.0", "install-a")
    # Server and client therefore agree on the effective decision.
    assert is_eligible(st["rollout"], "2.1.0", "install-a")


def test_non_dict_rollout_json_treated_as_open_by_server():
    store = _store()
    store.put(ROLLOUT_KEY, b'"just a string"', "application/json")
    st = set_rollout.collect_status(store, "intl", "production", "stable")
    assert st["rollout_exists"] is True
    assert st["rollout"]["percent"] == 100
    assert is_eligible(st["rollout"], "2.1.0", "install-a")


def test_guard_failure_writes_nothing_client_keeps_prior_state():
    store = _store()
    _apply(store, "promote", version="2.0.0", percent=50)
    before = _stored(store)

    # Unknown version: guard blocks, prior state untouched.
    res = set_rollout.execute(
        store, "intl", "production", "stable",
        action="promote", version="9.9.9", percent=100, apply=True,
    )
    assert res["guard_errors"]
    assert res["written"] is False
    assert _stored(store) == before
    # Client still governed by the previous record (2.0.0 @ 50%):
    # governed candidate follows the bucket rule, others stay out of scope.
    assert is_eligible(before, "2.0.0", "install-x") == (
        bucket_for("install-x", "2.0.0") < 50
    )
    assert is_eligible(before, "2.1.0", "install-x") is True
