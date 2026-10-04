"""Unit tests for ``build_system/scripts/set_rollout.py``.

The script is the only writer of the rollout control plane
(``{env}/channels/{channel}/rollout.json``) and the guard that stands
between an operator typo and a broken fleet-wide rollout. Everything
here runs against an in-memory ``FakeStore`` — no bucket, no network.

Covered:
  * pure helpers: ``normalize_version`` / ``normalize_cohort`` /
    ``normalize_rollout``
  * ``plan``: every action's guard rules (promote version+sha256
    checks, ramp/reduce direction guards, pause/resume idempotence
    warnings, rollback version requirement, param-ignored warnings)
  * ``execute``: apply vs dry-run vs guard-blocked writes
  * ``collect_status``: rollout/latest/available reporting incl.
    user-prefix exclusion from the universal release list
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "build_system" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import set_rollout  # noqa: E402
from set_rollout import (  # noqa: E402
    DEFAULT_PERCENT,
    collect_status,
    execute,
    normalize_cohort,
    normalize_rollout,
    normalize_version,
    plan,
    write_summary,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fake storage
# ---------------------------------------------------------------------------

class FakeStore:
    """In-memory stand-in for ``set_rollout.BucketStore``.

    Keys are relative to the env prefix (the real store prefixes with
    ``{base}/{env}`` internally; status keys like
    ``channels/stable/rollout.json`` stay relative either way).
    """

    def __init__(
        self,
        *,
        releases=("1.0.0",),
        rollout_json=None,
        latest_json=None,
        sha256_dirs=None,
        prefix="production",
    ):
        self.prefix = prefix
        self._objects: dict[str, bytes] = {}
        self._releases = list(releases)
        self._sha256_dirs = set(
            sha256_dirs if sha256_dirs is not None else releases
        )
        self.puts: list[tuple[str, bytes]] = []
        if rollout_json is not None:
            self._objects["channels/stable/rollout.json"] = json.dumps(
                rollout_json
            ).encode("utf-8")
        if latest_json is not None:
            self._objects["latest.json"] = json.dumps(latest_json).encode(
                "utf-8"
            )

    def get(self, rel: str):
        return self._objects.get(rel)

    def put(self, rel: str, body: bytes, content_type: str) -> None:
        self._objects[rel] = body
        self.puts.append((rel, body))

    def list_release_dirs(self):
        return list(self._releases)

    def release_has_sha256(self, release_dir: str) -> bool:
        return release_dir in self._sha256_dirs

    @staticmethod
    def parse_version(version: str):
        parts = [int(p) for p in re.findall(r"\d+", version)]
        return tuple(parts) if parts else (0,)


def _rollout(**over):
    base = {
        "schema": 1,
        "version": "1.0.0",
        "percent": 50,
        "paused": False,
        "cohort_include_prefix": [],
        "updated_at": "2026-10-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _status(store: FakeStore, channel: str = "stable"):
    return collect_status(store, "cn", "production", channel)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

class TestNormalizeVersion:
    def test_bare_version_passthrough(self):
        assert normalize_version("0.8.0") == "0.8.0"

    def test_v_prefix_stripped(self):
        assert normalize_version("v0.8.0") == "0.8.0"

    def test_user_prefixed_dir_reduces_to_core(self):
        assert normalize_version("alice_v1.2.3") == "1.2.3"

    def test_empty_inputs(self):
        assert normalize_version(None) == ""
        assert normalize_version("   ") == ""


class TestNormalizeCohort:
    def test_case_dedupe_and_spaces(self):
        assert normalize_cohort("Alice, bob ,alice") == ["alice", "bob"]

    def test_empty(self):
        assert normalize_cohort(None) == []
        assert normalize_cohort("") == []


class TestNormalizeRollout:
    def test_none_gives_fully_open_defaults(self):
        out = normalize_rollout(None)
        assert out["percent"] == DEFAULT_PERCENT == 100
        assert out["paused"] is False
        assert out["version"] == ""
        assert out["cohort_include_prefix"] == []

    def test_percent_clamped(self):
        assert normalize_rollout({"percent": 150})["percent"] == 100
        assert normalize_rollout({"percent": -5})["percent"] == 0

    def test_garbage_percent_defaults_open(self):
        assert normalize_rollout({"percent": "not-a-number"})["percent"] == 100

    def test_cohort_normalized(self):
        out = normalize_rollout({"cohort_include_prefix": [" Alice ", "", "BOB"]})
        assert out["cohort_include_prefix"] == ["alice", "bob"]

    def test_non_dict_is_open(self):
        assert normalize_rollout("junk")["percent"] == 100


# ---------------------------------------------------------------------------
# plan — promote
# ---------------------------------------------------------------------------

class TestPlanPromote:
    def test_no_version_and_no_releases_errors(self):
        store = FakeStore(releases=[])
        pl = plan("promote", None, None, None, _status(store), store=store)
        assert any("no --version given" in e for e in pl["errors"])

    def test_auto_picks_newest_available(self):
        store = FakeStore(releases=["1.0.0", "1.2.0", "1.1.0"])
        pl = plan("promote", None, None, None, _status(store), store=store)
        assert not pl["errors"]
        assert pl["resolved"]["target_version"] == "1.2.0"
        assert pl["result_rollout"]["version"] == "1.2.0"

    def test_explicit_version_must_exist(self):
        store = FakeStore(releases=["1.0.0"])
        pl = plan("promote", 100, "9.9.9", None, _status(store), store=store)
        assert any("9.9.9" in e and "not a universal release" in e
                   for e in pl["errors"])

    def test_version_without_sha256_is_guarded(self):
        store = FakeStore(releases=["1.0.0"], sha256_dirs=set())
        pl = plan("promote", 100, "1.0.0", None, _status(store), store=store)
        assert any(".sha256" in e for e in pl["errors"])

    def test_promote_writes_fully_open_by_default(self):
        store = FakeStore(releases=["1.0.0"])
        pl = plan("promote", None, None, None, _status(store), store=store)
        assert not pl["errors"]
        got = pl["result_rollout"]
        assert got["percent"] == 100
        assert got["paused"] is False
        assert got["cohort_include_prefix"] == []
        assert pl["resolved"]["publish"] is True
        assert pl["resolved"]["smoke"] is True

    def test_promote_percent_zero_without_cohort_warns(self):
        store = FakeStore(releases=["1.0.0"])
        pl = plan("promote", 0, None, None, _status(store), store=store)
        assert any("nobody will be offered" in w for w in pl["warnings"])

    def test_promote_percent_100_with_cohort_warns(self):
        store = FakeStore(releases=["1.0.0"])
        pl = plan("promote", 100, None, "alice", _status(store), store=store)
        assert any("cohort has no effect" in w for w in pl["warnings"])
        assert pl["result_rollout"]["cohort_include_prefix"] == ["alice"]

    def test_promote_already_published_warns_idempotent(self):
        store = FakeStore(
            releases=["1.0.0"], latest_json={"version": "1.0.0"}
        )
        pl = plan("promote", 100, None, None, _status(store), store=store)
        assert any("already the published version" in w for w in pl["warnings"])

    def test_promote_clamps_out_of_range_percent(self):
        store = FakeStore(releases=["1.0.0"])
        pl = plan("promote", 150, None, None, _status(store), store=store)
        assert pl["result_rollout"]["percent"] == 100
        pl = plan("promote", -5, None, None, _status(store), store=store)
        assert pl["result_rollout"]["percent"] == 0

    def test_promote_while_paused_warns_that_it_resumes(self):
        store = FakeStore(
            releases=["1.0.0"],
            rollout_json=_rollout(version="0.9.0", paused=True),
        )
        pl = plan("promote", 100, None, None, _status(store), store=store)
        assert any("paused" in w and "resume" in w for w in pl["warnings"])
        assert pl["result_rollout"]["paused"] is False

    def test_promote_passes_manual_exclude_through(self):
        store = FakeStore(releases=["1.0.0"])
        pl = plan(
            "promote", 100, None, None, _status(store),
            store=store, exclude="v0.9.0, 0.9.0",
        )
        # manual list normalized to bare cores and deduped
        assert pl["resolved"]["exclude"] == "0.9.0"


# ---------------------------------------------------------------------------
# plan — ramp / reduce
# ---------------------------------------------------------------------------

class TestPlanRampReduce:
    def test_ramp_requires_existing_rollout(self):
        store = FakeStore(releases=["1.0.0"])
        pl = plan("ramp", 20, None, None, _status(store), store=store)
        assert any("no rollout.json" in e or "run action=promote first" in e
                   for e in pl["errors"])

    def test_ramp_cannot_move_down(self):
        store = FakeStore(releases=["1.0.0"], rollout_json=_rollout(percent=50))
        pl = plan("ramp", 20, None, None, _status(store), store=store)
        assert any("ramp only moves upward" in e for e in pl["errors"])
        # Guard blocked => result keeps current percent.
        assert pl["result_rollout"]["percent"] == 50

    def test_reduce_cannot_move_up(self):
        store = FakeStore(releases=["1.0.0"], rollout_json=_rollout(percent=20))
        pl = plan("reduce", 50, None, None, _status(store), store=store)
        assert any("reduce only moves downward" in e for e in pl["errors"])

    def test_ramp_moves_up(self):
        store = FakeStore(releases=["1.0.0"], rollout_json=_rollout(percent=20))
        pl = plan("ramp", 50, None, None, _status(store), store=store)
        assert not pl["errors"]
        assert pl["result_rollout"]["percent"] == 50
        assert pl["resolved"]["publish"] is False

    def test_reduce_moves_down(self):
        store = FakeStore(releases=["1.0.0"], rollout_json=_rollout(percent=50))
        pl = plan("reduce", 10, None, None, _status(store), store=store)
        assert not pl["errors"]
        assert pl["result_rollout"]["percent"] == 10

    def test_percent_only_actions_warn_on_version_and_cohort(self):
        store = FakeStore(releases=["1.0.0"], rollout_json=_rollout(percent=20))
        pl = plan("ramp", 50, "1.0.0", "alice", _status(store), store=store)
        assert any("ignore --version" in w for w in pl["warnings"])
        assert any("ignore --cohort" in w for w in pl["warnings"])

    def test_missing_percent_is_an_error(self):
        store = FakeStore(releases=["1.0.0"], rollout_json=_rollout(percent=20))
        pl = plan("ramp", None, None, None, _status(store), store=store)
        assert any("requires --percent" in e for e in pl["errors"])


# ---------------------------------------------------------------------------
# plan — pause / resume
# ---------------------------------------------------------------------------

class TestPlanPauseResume:
    def test_pause_sets_flag(self):
        store = FakeStore(releases=["1.0.0"], rollout_json=_rollout(percent=50))
        pl = plan("pause", None, None, None, _status(store), store=store)
        assert not pl["errors"]
        assert pl["result_rollout"]["paused"] is True
        # percent preserved — pause is a switch, not a reset.
        assert pl["result_rollout"]["percent"] == 50

    def test_pause_twice_warns(self):
        store = FakeStore(
            releases=["1.0.0"], rollout_json=_rollout(paused=True)
        )
        pl = plan("pause", None, None, None, _status(store), store=store)
        assert any("already paused" in w for w in pl["warnings"])

    def test_pause_without_record_gates_every_version(self):
        store = FakeStore(releases=["1.0.0"])
        pl = plan("pause", None, None, None, _status(store), store=store)
        assert not pl["errors"]
        got = pl["result_rollout"]
        assert got["paused"] is True
        # version cleared so the kill switch covers every candidate.
        assert got["version"] == ""

    def test_resume_clears_flag(self):
        store = FakeStore(
            releases=["1.0.0"], rollout_json=_rollout(paused=True)
        )
        pl = plan("resume", None, None, None, _status(store), store=store)
        assert not pl["errors"]
        assert pl["result_rollout"]["paused"] is False

    def test_pause_ignores_percent_version_cohort_with_warnings(self):
        store = FakeStore(releases=["1.0.0"], rollout_json=_rollout())
        pl = plan("pause", 80, "1.0.0", "alice", _status(store), store=store)
        assert any("ignores --percent" in w for w in pl["warnings"])
        assert any("ignores --version" in w for w in pl["warnings"])
        assert any("ignores --cohort" in w for w in pl["warnings"])


# ---------------------------------------------------------------------------
# plan — rollback
# ---------------------------------------------------------------------------

class TestPlanRollback:
    def test_rollback_requires_version(self):
        store = FakeStore(releases=["1.0.0"], rollout_json=_rollout())
        pl = plan("rollback", None, None, None, _status(store), store=store)
        assert any("requires --version" in e for e in pl["errors"])

    def test_rollback_version_must_exist(self):
        store = FakeStore(releases=["1.0.0"], rollout_json=_rollout())
        pl = plan("rollback", None, "9.9.9", None, _status(store), store=store)
        assert any("not a universal release" in e for e in pl["errors"])

    def test_rollback_repoints_version_and_publishes(self):
        store = FakeStore(releases=["1.0.0", "1.1.0"],
                          rollout_json=_rollout(version="1.1.0", percent=60))
        pl = plan("rollback", None, "1.0.0", None, _status(store), store=store)
        assert not pl["errors"]
        got = pl["result_rollout"]
        assert got["version"] == "1.0.0"
        # percent/paused/cohort survive a rollback (only the target moves).
        assert got["percent"] == 60
        assert pl["resolved"]["publish"] is True
        assert pl["resolved"]["smoke"] is True

    def test_rollback_ignores_percent_and_cohort_with_warnings(self):
        store = FakeStore(releases=["1.0.0"], rollout_json=_rollout())
        pl = plan("rollback", 10, None, "alice", _status(store), store=store)
        assert any("percent is ignored for rollback" in w for w in pl["warnings"])
        assert any("cohort is ignored for rollback" in w for w in pl["warnings"])

    def test_rollback_requires_sha256_like_promote(self):
        store = FakeStore(releases=["1.0.0"], sha256_dirs=set(),
                          rollout_json=_rollout())
        pl = plan("rollback", None, "1.0.0", None, _status(store), store=store)
        assert any(".sha256" in e for e in pl["errors"])

    def test_rollback_auto_excludes_bad_version(self):
        # The bad version is what latest.json advertises AND what the
        # current rollout governs — both point at it before rollback.
        store = FakeStore(
            releases=["1.0.0", "1.1.0"],
            rollout_json=_rollout(version="1.1.0", percent=100),
            latest_json={"version": "1.1.0"},
        )
        pl = plan("rollback", None, "1.0.0", None, _status(store), store=store)
        assert not pl["errors"]
        assert pl["resolved"]["exclude"] == "1.1.0"
        assert pl["resolved"]["target_version"] == "1.0.0"

    def test_rollback_derives_from_latest_and_rollout_union(self):
        # Partial prior run: latest.json already moved but the rollout
        # still names the bad version — exclude both.
        store = FakeStore(
            releases=["1.0.0", "1.1.0", "1.2.0"],
            rollout_json=_rollout(version="1.2.0", percent=100),
            latest_json={"version": "1.1.0"},
        )
        pl = plan("rollback", None, "1.0.0", None, _status(store), store=store)
        assert pl["resolved"]["exclude"] == "1.1.0,1.2.0"

    def test_rollback_merges_manual_exclude(self):
        store = FakeStore(
            releases=["1.0.0", "1.1.0"],
            rollout_json=_rollout(version="1.1.0", percent=100),
            latest_json={"version": "1.1.0"},
        )
        pl = plan(
            "rollback", None, "1.0.0", None, _status(store),
            store=store, exclude="v0.9.0-rc.1, 0.9.0-rc.1",
        )
        assert pl["resolved"]["exclude"] == "1.1.0,0.9.0-rc.1"

    def test_rollback_never_excludes_the_target(self):
        # Idempotent rerun: latest.json + rollout already at target.
        store = FakeStore(
            releases=["1.0.0", "1.1.0"],
            rollout_json=_rollout(version="1.0.0", percent=100),
            latest_json={"version": "1.0.0"},
        )
        pl = plan("rollback", None, "1.0.0", None, _status(store), store=store)
        assert pl["resolved"]["exclude"] == ""
        assert any("no versions to exclude" in w for w in pl["warnings"])

    def test_rollback_kept_low_percent_warns(self):
        store = FakeStore(
            releases=["1.0.0", "1.1.0"],
            rollout_json=_rollout(version="1.1.0", percent=20),
        )
        pl = plan("rollback", None, "1.0.0", None, _status(store), store=store)
        assert any("keeps percent=20" in w for w in pl["warnings"])
        assert any("ramp" in w for w in pl["warnings"])

    def test_rollback_kept_paused_warns(self):
        store = FakeStore(
            releases=["1.0.0", "1.1.0"],
            rollout_json=_rollout(version="1.1.0", percent=100, paused=True),
        )
        pl = plan("rollback", None, "1.0.0", None, _status(store), store=store)
        assert any("paused" in w and "resume" in w for w in pl["warnings"])

    def test_exclude_ignored_for_percent_only_actions(self):
        store = FakeStore(releases=["1.0.0"], rollout_json=_rollout())
        pl = plan(
            "ramp", 60, None, None, _status(store),
            store=store, exclude="9.9.9",
        )
        assert not pl["errors"]
        assert any("exclude is ignored" in w for w in pl["warnings"])
        assert pl["resolved"]["exclude"] == ""


class TestPlanMisc:
    def test_unknown_action_errors(self):
        store = FakeStore(releases=["1.0.0"])
        pl = plan("explode", None, None, None, _status(store), store=store)
        assert any("unknown action" in e for e in pl["errors"])


# ---------------------------------------------------------------------------
# collect_status
# ---------------------------------------------------------------------------

class TestCollectStatus:
    def test_missing_rollout_reports_open_default(self):
        store = FakeStore(releases=["1.0.0"])
        st = _status(store)
        assert st["rollout_exists"] is False
        assert st["rollout"]["percent"] == 100
        assert st["rollout_key"] == "channels/stable/rollout.json"

    def test_rollout_and_latest_read_back(self):
        store = FakeStore(
            releases=["1.0.0"],
            rollout_json=_rollout(version="1.0.0", percent=20),
            latest_json={"version": "1.0.0"},
        )
        st = _status(store)
        assert st["rollout_exists"] is True
        assert st["rollout"]["percent"] == 20
        assert st["published_version"] == "1.0.0"

    def test_user_prefixed_releases_excluded_from_available(self):
        store = FakeStore(releases=["v1.0.0", "alice_v2.0.0", "v1.1.0"])
        st = _status(store)
        versions = [a["version"] for a in st["available"]]
        assert versions == ["1.1.0", "1.0.0"]  # newest first, no alice_*

    def test_unreadable_rollout_treated_as_open(self):
        store = FakeStore(releases=["1.0.0"])
        store._objects["channels/stable/rollout.json"] = b"not json {"
        st = _status(store)
        assert st["rollout_exists"] is True
        assert st["rollout"]["percent"] == 100  # normalize fallback


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------

class TestExecute:
    def test_status_only_mode_never_writes(self):
        store = FakeStore(releases=["1.0.0"], rollout_json=_rollout())
        result = execute(store, "cn", "production", "stable", action=None)
        assert "written" not in result
        assert store.puts == []

    def test_dry_run_does_not_write(self):
        store = FakeStore(releases=["1.0.0"])
        result = execute(
            store, "cn", "production", "stable",
            action="promote", percent=100, apply=False,
        )
        assert result["written"] is False
        assert store.puts == []
        assert not result["guard_errors"]

    def test_apply_writes_rollout_json(self):
        store = FakeStore(releases=["1.0.0"])
        result = execute(
            store, "cn", "production", "stable",
            action="promote", percent=20, apply=True,
        )
        assert result["written"] is True
        assert len(store.puts) == 1
        key, body = store.puts[0]
        assert key == "channels/stable/rollout.json"
        written = json.loads(body.decode("utf-8"))
        assert written["version"] == "1.0.0"
        assert written["percent"] == 20
        assert written["paused"] is False

    def test_guard_violation_blocks_write(self):
        store = FakeStore(releases=["1.0.0"], rollout_json=_rollout(percent=50))
        result = execute(
            store, "cn", "production", "stable",
            action="ramp", percent=10, apply=True,  # downward ramp
        )
        assert result["guard_errors"]
        assert result["written"] is False
        assert store.puts == []

    def test_apply_without_write_flag_for_status_fields(self):
        # pause via execute: paused flag lands in the store.
        store = FakeStore(releases=["1.0.0"], rollout_json=_rollout(percent=30))
        result = execute(
            store, "cn", "production", "stable",
            action="pause", apply=True,
        )
        assert result["written"] is True
        written = json.loads(store._objects["channels/stable/rollout.json"])
        assert written["paused"] is True
        assert written["percent"] == 30

    def test_execute_carries_exclude_into_resolved(self):
        store = FakeStore(
            releases=["1.0.0", "1.1.0"],
            rollout_json=_rollout(version="1.1.0", percent=100),
            latest_json={"version": "1.1.0"},
        )
        result = execute(
            store, "cn", "production", "stable",
            action="rollback", version="1.0.0", exclude="0.8.0",
            apply=False,
        )
        assert not result["guard_errors"]
        assert result["resolved"]["exclude"] == "1.1.0,0.8.0"
        assert result["requested"]["exclude"] == ["0.8.0"]


# ---------------------------------------------------------------------------
# write_summary
# ---------------------------------------------------------------------------

class TestWriteSummary:
    def test_appends_markdown_for_status(self, tmp_path):
        store = FakeStore(
            releases=["1.0.0"],
            rollout_json=_rollout(version="1.0.0", percent=20),
            latest_json={"version": "1.0.0"},
        )
        result = execute(store, "cn", "production", "stable", action=None)
        summary = tmp_path / "summary.md"
        write_summary(str(summary), result)
        text = summary.read_text(encoding="utf-8")
        assert "OTA rollout" in text
        assert "percent=`20`" in text
        assert "1.0.0" in text

    def test_summary_never_raises_on_garbage(self, tmp_path):
        summary = tmp_path / "summary.md"
        write_summary(str(summary), {"app": "cn"})  # minimal/odd shape
        assert summary.exists()

    def test_guard_errors_rendered(self, tmp_path):
        store = FakeStore(releases=["1.0.0"], rollout_json=_rollout(percent=50))
        result = execute(
            store, "cn", "production", "stable",
            action="ramp", percent=10, apply=False,
        )
        summary = tmp_path / "summary.md"
        write_summary(str(summary), result)
        text = summary.read_text(encoding="utf-8")
        assert "blocked" in text
        assert "Guard errors:" in text


# ---------------------------------------------------------------------------
# CLI exit-code contract (main with a stubbed store)
# ---------------------------------------------------------------------------

class TestMainExitCodes:
    def test_guard_violation_returns_3(self, monkeypatch, tmp_path):
        store = FakeStore(releases=["1.0.0"], rollout_json=_rollout(percent=50))
        monkeypatch.setattr(set_rollout, "build_store", lambda *a, **k: store)
        rc = set_rollout.main([
            "--env", "production", "--channel", "stable",
            "--action", "ramp", "--percent", "10",
        ])
        assert rc == 3

    def test_status_returns_0(self, monkeypatch):
        store = FakeStore(releases=["1.0.0"])
        monkeypatch.setattr(set_rollout, "build_store", lambda *a, **k: store)
        rc = set_rollout.main([
            "--env", "production", "--channel", "stable", "--status",
        ])
        assert rc == 0

    def test_apply_ok_returns_0(self, monkeypatch):
        store = FakeStore(releases=["1.0.0"])
        monkeypatch.setattr(set_rollout, "build_store", lambda *a, **k: store)
        rc = set_rollout.main([
            "--env", "production", "--channel", "stable",
            "--action", "promote", "--percent", "100", "--version", "1.0.0",
            "--apply",
        ])
        assert rc == 0
        assert store.puts  # actually wrote

    def test_percent_out_of_range_is_usage_error(self, monkeypatch):
        store = FakeStore(releases=["1.0.0"])
        monkeypatch.setattr(set_rollout, "build_store", lambda *a, **k: store)
        with pytest.raises(SystemExit) as exc:
            set_rollout.main([
                "--env", "production", "--action", "promote",
                "--percent", "150",
            ])
        assert exc.value.code == 2

    def test_exclude_flag_lands_in_resolved_output(
        self, monkeypatch, capsys
    ):
        store = FakeStore(
            releases=["1.0.0", "1.1.0"],
            rollout_json=_rollout(version="1.1.0", percent=100),
            latest_json={"version": "1.1.0"},
        )
        monkeypatch.setattr(set_rollout, "build_store", lambda *a, **k: store)
        rc = set_rollout.main([
            "--env", "production", "--channel", "stable",
            "--action", "rollback", "--version", "1.0.0",
            "--exclude", "0.9.0",
        ])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["resolved"]["exclude"] == "1.1.0,0.9.0"
