"""Unit tests for the client-side rollout gate (``ota/core/rollout.py``)
and its wiring in ``OTAUpdater.check_for_updates``.

Three layers, all hermetic (no network, no real bucket):

  1. ``is_eligible`` — the pure decision table. Must mirror the
     server-side guards in ``build_system/scripts/set_rollout.py``:
     fail-open, pause first, version-scoped, whitelist over percent,
     then the sha256 bucket.
  2. ``bucket_for`` — deterministic, monotone in percent, roughly
     uniform across the install base.
  3. ``fetch_rollout`` — TTL cache + stale-while-error + fail-open.
  4. ``OTAUpdater`` — the gate actually suppresses offers end-to-end.
"""

from __future__ import annotations

import importlib
import json
import threading
from types import SimpleNamespace

import pytest
import requests

import ota.core.rollout as rollout
from ota.core.rollout import bucket_for, fetch_rollout, get_install_id, is_eligible

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _sync_rollout_module():
    """Re-bind every ``ota.core.rollout`` name before each test.

    ``test_local_ota_routing._fresh_config`` evicts ``ota.*`` from
    ``sys.modules``, after which ``OTAUpdater``'s runtime
    ``from ota.core.rollout import ...`` resolves a FRESH module object
    while this file's import-time bindings still point at the orphaned
    one — monkeypatching the old object would silently miss (and the
    stateful functions would read the old module's globals instead of
    the patched ones). Pure functions tolerate either identity, but
    ``fetch_rollout`` / ``get_install_id`` must be the live objects.
    """
    global rollout, bucket_for, fetch_rollout, get_install_id, is_eligible
    rollout = importlib.import_module("ota.core.rollout")
    bucket_for = rollout.bucket_for
    fetch_rollout = rollout.fetch_rollout
    get_install_id = rollout.get_install_id
    is_eligible = rollout.is_eligible
    # Drop any memoized no-app_info fallback id so tests can't leak
    # bucket slots into each other.
    rollout._fallback_install_id = None


def _rollout(**over):
    base = {
        "schema": 1,
        "version": "1.2.3",
        "percent": 100,
        "paused": False,
        "cohort_include_prefix": [],
        "updated_at": "2026-10-01T00:00:00+00:00",
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# is_eligible — decision table
# ---------------------------------------------------------------------------

class TestIsEligibleDecisionTable:
    def test_no_rollout_is_open(self):
        assert is_eligible(None, "1.2.3", "id-1") is True
        assert is_eligible("junk", "1.2.3", "id-1") is True

    def test_pause_kills_every_version(self):
        # paused is checked BEFORE version scoping: a kill switch that
        # only paused one version would be useless.
        r = _rollout(paused=True, percent=100, version="1.2.3")
        assert is_eligible(r, "1.2.3", "id-1") is False
        assert is_eligible(r, "0.9.0", "id-1") is False

    def test_gate_only_applies_to_target_version(self):
        r = _rollout(version="1.2.3", percent=0)
        # A different candidate (older/other build) passes untouched...
        assert is_eligible(r, "1.2.0", "id-1") is True
        assert is_eligible(r, "", "id-1") is True

    def test_version_comparison_normalizes_v_prefix_and_case(self):
        r = _rollout(version="V1.2.3", percent=0)
        assert is_eligible(r, "1.2.3", "id-1") is False  # gate applies
        r2 = _rollout(version="v1.2.3", percent=100)
        assert is_eligible(r2, "1.2.3", "id-1") is True   # gate applies

    def test_whitelist_beats_percent_zero(self):
        r = _rollout(percent=0, cohort_include_prefix=["alice"])
        assert is_eligible(r, "1.2.3", "id-1", "alice") is True
        assert is_eligible(r, "1.2.3", "id-1", "ALICE") is True  # case-insens
        assert is_eligible(r, "1.2.3", "id-1", "bob") is False

    def test_percent_100_everyone_passes(self):
        r = _rollout(percent=100)
        for i in range(50):
            assert is_eligible(r, "1.2.3", f"id-{i}") is True

    def test_percent_0_nobody_passes_without_cohort(self):
        r = _rollout(percent=0)
        for i in range(50):
            assert is_eligible(r, "1.2.3", f"id-{i}") is False

    def test_missing_install_id_fails_open_below_100(self):
        r = _rollout(percent=1)
        assert is_eligible(r, "1.2.3", "") is True

    def test_garbage_percent_fails_open(self):
        r = _rollout(percent="lots")
        assert is_eligible(r, "1.2.3", "id-1") is True

    def test_empty_version_in_rollout_gates_all_candidates(self):
        # version='' means the record is not scoped — percent applies
        # to every candidate (this is what action=pause writes when no
        # prior record existed).
        r = _rollout(version="", percent=0)
        assert is_eligible(r, "9.9.9", "id-1") is False

    def test_decision_is_deterministic_across_calls(self):
        r = _rollout(percent=37)
        first = is_eligible(r, "1.2.3", "stable-id")
        for _ in range(20):
            assert is_eligible(r, "1.2.3", "stable-id") is first


# ---------------------------------------------------------------------------
# bucket_for — stability / monotonicity / uniformity
# ---------------------------------------------------------------------------

class TestBucketProperties:
    def test_deterministic(self):
        assert bucket_for("abc", "1.0.0") == bucket_for("abc", "1.0.0")

    def test_in_range(self):
        for i in range(500):
            b = bucket_for(f"id-{i}", "1.0.0")
            assert 0 <= b < 100

    def test_different_versions_get_different_slots(self):
        # Version is part of the hash so a client's slot for 1.0.0 has
        # no correlation with its slot for 1.1.0 (each ramp re-shuffles,
        # but monotonicity holds WITHIN one version's ramp).
        same = sum(
            bucket_for(f"id-{i}", "1.0.0") == bucket_for(f"id-{i}", "1.1.0")
            for i in range(1000)
        )
        assert same < 60  # ~10 expected by chance; allow generous slack

    def test_eligibility_monotone_in_percent(self):
        ids = [f"install-{i}" for i in range(1000)]
        def eligible(pct):
            r = _rollout(version="1.2.3", percent=pct)
            return {i for i in ids if is_eligible(r, "1.2.3", i)}

        e20, e50, e80 = eligible(20), eligible(50), eligible(80)
        assert e20 <= e50 <= e80  # raising percent never drops a client
        assert 150 <= len(e20) <= 260   # ~200 ± generous binomial slack
        assert 430 <= len(e50) <= 570   # ~500
        assert 730 <= len(e80) <= 870   # ~800

    def test_distribution_roughly_uniform(self):
        below_50 = sum(
            bucket_for(f"device-{i}", "1.2.3") < 50 for i in range(20000)
        )
        frac = below_50 / 20000
        assert 0.45 < frac < 0.55


# ---------------------------------------------------------------------------
# get_install_id — env override + persistence
# ---------------------------------------------------------------------------

class TestInstallId:
    def test_env_override_wins(self, monkeypatch):
        monkeypatch.setenv("ECAN_OTA_INSTALL_ID", "PinnedId42")
        assert get_install_id() == "pinnedid42"  # lower-cased

    def test_generated_and_persisted(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ECAN_OTA_INSTALL_ID", raising=False)
        monkeypatch.setattr(rollout, "app_info",
                            SimpleNamespace(appdata_path=str(tmp_path)))

        first = get_install_id()
        assert first
        id_file = tmp_path / "ota_install_id.json"
        assert id_file.exists()
        payload = json.loads(id_file.read_text(encoding="utf-8"))
        assert payload["install_id"] == first

        # Second call reads the persisted id — same bucket slot forever.
        assert get_install_id() == first

    def test_corrupt_file_regenerates(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ECAN_OTA_INSTALL_ID", raising=False)
        monkeypatch.setattr(rollout, "app_info",
                            SimpleNamespace(appdata_path=str(tmp_path)))
        (tmp_path / "ota_install_id.json").write_text("{broken", encoding="utf-8")

        recovered = get_install_id()
        assert recovered
        # ...and the file is healed with the new id.
        payload = json.loads(
            (tmp_path / "ota_install_id.json").read_text(encoding="utf-8")
        )
        assert payload["install_id"] == recovered

    def test_fallback_id_stable_without_app_info(self, monkeypatch):
        # Defensive path (app_info unavailable): the in-memory id must
        # stay stable across calls, otherwise the percent bucket would
        # re-roll on every update check.
        monkeypatch.delenv("ECAN_OTA_INSTALL_ID", raising=False)
        monkeypatch.setattr(rollout, "app_info", None)
        ids = {get_install_id() for _ in range(5)}
        assert len(ids) == 1


# ---------------------------------------------------------------------------
# fetch_rollout — TTL cache / fail-open
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, status_code=200, content=b"{}"):
        self.status_code = status_code
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


@pytest.fixture
def gate_env(monkeypatch):
    """Point rollout at a fake URL + controllable transport, reset cache."""
    monkeypatch.setattr(rollout, "_last_attempt", 0.0)
    monkeypatch.setattr(rollout, "_last_data", None)
    monkeypatch.setattr(
        rollout, "ota_config",
        SimpleNamespace(get_rollout_url=lambda: "https://fake/channels/stable/rollout.json"),
    )
    state = {"calls": 0, "behavior": None}

    def fake_get(url, timeout=None, headers=None):
        state["calls"] += 1
        beh = state["behavior"]
        if beh is None:
            return _FakeResponse()
        if isinstance(beh, Exception):
            raise beh
        return beh

    monkeypatch.setattr(rollout, "requests", SimpleNamespace(get=fake_get))
    return state


class TestFetchRollout:
    def test_success_then_cached(self, gate_env):
        body = json.dumps(_rollout(percent=20)).encode("utf-8")
        gate_env["behavior"] = _FakeResponse(content=body)

        first = fetch_rollout()
        assert first["percent"] == 20
        assert gate_env["calls"] == 1

        second = fetch_rollout()
        assert second["percent"] == 20
        assert gate_env["calls"] == 1  # within TTL: no second request

    def test_force_bypasses_cache(self, gate_env):
        body = json.dumps(_rollout(percent=20)).encode("utf-8")
        gate_env["behavior"] = _FakeResponse(content=body)
        fetch_rollout()
        fetch_rollout(force=True)
        assert gate_env["calls"] == 2

    def test_404_means_open(self, gate_env):
        gate_env["behavior"] = _FakeResponse(status_code=404)
        assert fetch_rollout() is None

    def test_invalid_json_means_open(self, gate_env):
        gate_env["behavior"] = _FakeResponse(content=b"<html>not json")
        assert fetch_rollout() is None

    def test_non_object_body_means_open(self, gate_env):
        gate_env["behavior"] = _FakeResponse(content=b"[1, 2, 3]")
        assert fetch_rollout() is None

    def test_first_failure_means_open(self, gate_env):
        gate_env["behavior"] = requests.ConnectionError("boom")
        assert fetch_rollout() is None

    def test_transport_error_serves_stale_value(self, gate_env):
        # A previously resolved value must keep gating through an
        # outage (pause must not "un-pause" because the bucket hiccuped).
        body = json.dumps(_rollout(percent=20, paused=True)).encode("utf-8")
        gate_env["behavior"] = _FakeResponse(content=body)
        assert fetch_rollout()["paused"] is True

        import time as _time
        monkey_ttl_expired = _time.time() - 9999
        rollout._last_attempt = monkey_ttl_expired  # force a refetch
        gate_env["behavior"] = requests.ConnectionError("outage")

        stale = fetch_rollout()
        assert stale is not None and stale["paused"] is True

    def test_no_url_short_circuits_without_request(self, monkeypatch):
        monkeypatch.setattr(rollout, "_last_attempt", 0.0)
        monkeypatch.setattr(rollout, "_last_data", None)
        monkeypatch.setattr(
            rollout, "ota_config", SimpleNamespace(get_rollout_url=lambda: "")
        )
        state = {"calls": 0}

        def boom(*a, **k):
            state["calls"] += 1
            raise AssertionError("must not fetch without a URL")

        monkeypatch.setattr(rollout, "requests", SimpleNamespace(get=boom))
        assert fetch_rollout() is None
        assert state["calls"] == 0


# ---------------------------------------------------------------------------
# OTAUpdater wiring — gate actually suppresses offers
# ---------------------------------------------------------------------------

def _bare_updater(platform_has_update=True, info=None):
    """Build an OTAUpdater without running __init__ (no threads, no
    platform probing) — only the attributes check_for_updates touches."""
    from ota.core.updater import OTAUpdater

    u = object.__new__(OTAUpdater)
    u._check_lock = threading.Lock()
    u._callback_lock = threading.Lock()
    u.is_checking = False
    u.is_installing = False
    u.update_callback = None
    u.error_callback = None
    u.user_prefix = None
    u.app_version = "1.0.0"
    u.platform = "TestOS"
    u._auto_check_thread = None
    result = (platform_has_update, info)
    u.platform_updater = SimpleNamespace(
        check_for_updates=lambda silent, return_info=True: result
    )
    return u


class TestUpdaterGate:
    def test_open_rollout_offers_update(self, monkeypatch):
        monkeypatch.setattr(rollout, "fetch_rollout", lambda *a, **k: None)
        info = {"latest_version": "1.2.3", "url": "https://x/y"}
        u = _bare_updater(True, info)

        has_update, got = u.check_for_updates(return_info=True)
        assert has_update is True
        assert got is info

    def test_paused_rollout_withholds_update(self, monkeypatch):
        monkeypatch.setattr(
            rollout, "fetch_rollout",
            lambda *a, **k: _rollout(version="1.2.3", paused=True, percent=100),
        )
        monkeypatch.setattr(rollout, "get_install_id", lambda: "id-1")
        info = {"latest_version": "1.2.3"}
        u = _bare_updater(True, info)

        assert u.check_for_updates(return_info=True) == (False, None)
        assert u.check_for_updates() is False  # non-tuple mode too

    def test_percent_zero_withholds_without_whitelist(self, monkeypatch):
        monkeypatch.setattr(
            rollout, "fetch_rollout",
            lambda *a, **k: _rollout(version="1.2.3", percent=0),
        )
        monkeypatch.setattr(rollout, "get_install_id", lambda: "id-1")
        u = _bare_updater(True, {"latest_version": "1.2.3"})
        assert u.check_for_updates(return_info=True) == (False, None)

    def test_whitelisted_prefix_gets_the_offer(self, monkeypatch):
        monkeypatch.setattr(
            rollout, "fetch_rollout",
            lambda *a, **k: _rollout(
                version="1.2.3", percent=0, cohort_include_prefix=["alice"]
            ),
        )
        monkeypatch.setattr(rollout, "get_install_id", lambda: "id-1")
        # check_for_updates re-resolves user_prefix every run; feed it
        # through the documented env-var source.
        monkeypatch.setenv("ECAN_OTA_USER_PREFIX", "alice")
        u = _bare_updater(True, {"latest_version": "1.2.3"})

        has_update, got = u.check_for_updates(return_info=True)
        assert has_update is True
        assert got == {"latest_version": "1.2.3"}

    def test_other_version_not_scoped_by_gate(self, monkeypatch):
        monkeypatch.setattr(
            rollout, "fetch_rollout",
            lambda *a, **k: _rollout(version="9.9.9", percent=0),
        )
        u = _bare_updater(True, {"latest_version": "1.2.3"})
        has_update, _ = u.check_for_updates(return_info=True)
        assert has_update is True  # gate names 9.9.9, not this candidate

    def test_gate_failure_fails_open(self, monkeypatch):
        def explode(*a, **k):
            raise RuntimeError("control plane on fire")

        monkeypatch.setattr(rollout, "fetch_rollout", explode)
        u = _bare_updater(True, {"latest_version": "1.2.3"})
        has_update, got = u.check_for_updates(return_info=True)
        assert has_update is True
        assert got == {"latest_version": "1.2.3"}

    def test_missing_candidate_version_fails_open(self, monkeypatch):
        monkeypatch.setattr(
            rollout, "fetch_rollout",
            lambda *a, **k: _rollout(version="1.2.3", percent=0),
        )
        u = _bare_updater(True, {"url": "https://x/y"})  # no version key
        has_update, _ = u.check_for_updates(return_info=True)
        assert has_update is True

    def test_no_update_flow_unaffected_by_gate(self, monkeypatch):
        def explode(*a, **k):
            raise AssertionError("gate must not run when no update")

        monkeypatch.setattr(rollout, "fetch_rollout", explode)
        u = _bare_updater(False, None)
        assert u.check_for_updates(return_info=True) == (False, None)
