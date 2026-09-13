"""Unified execution C3 — placement declarations reach the scheduler's inputs.

``residency`` / ``lifetime`` / ``requires[]`` have existed on EC_Skill and
ManagedTask since Path 1.5 Phase 0.3 with nothing reading them. Under unified
execution the scheduler does, which makes the round-trip load-bearing:

  editor -> skill config JSON -> EC_Skill -> ManagedTask -> turn_enqueue

The failure this guards against is specific and has happened here before: a new
field is added to a model, and the value silently never arrives because one of
the several metadata whitelists between the editor and the object does not
mention it. Each hop below is asserted separately for that reason.

The capability vocabulary is duplicated in TypeScript
(gui_v2/src/types/domain/placement.ts) because the two sides are different
runtimes; a test asserts the Python half stays the source that file was written
from.
"""

import json
from pathlib import Path

import pytest

from agent import placement


# ===========================================================================
# Normalisation — what a declaration means when it is malformed
# ===========================================================================

def test_defaults_are_permissive():
    """An old skill that declares nothing must keep running anywhere."""
    p = placement.read_placement({})
    assert p == {"residency": "any", "lifetime": "conversation", "requires": []}
    assert placement.is_default_placement(p)


def test_unknown_values_fall_back_rather_than_raise():
    """A typo must not make a skill unloadable."""
    p = placement.read_placement({"residency": "edge", "lifetime": "forever"})
    assert p["residency"] == "any"
    assert p["lifetime"] == "conversation"


def test_requires_accepts_a_string_list():
    """The editor sends an array; hand-edited JSON and env vars send a string."""
    assert placement.normalize_requires("browser_local, gpu;cn_llm") == [
        "browser_local", "gpu", "cn_llm",
    ]


def test_requires_is_deduplicated_and_bounded():
    assert placement.normalize_requires(["gpu", "gpu", " gpu "]) == ["gpu"]
    assert len(placement.normalize_requires([f"cap{i}" for i in range(50)])) == placement.MAX_REQUIRES


def test_unknown_capabilities_are_kept_not_dropped():
    """Dropping an unrecognised requirement silently WIDENS placement.

    `dedicated:<agent-id>` is legitimate and no static list can contain it, and
    a pod may advertise something this build has not heard of. Dropping is the
    dangerous direction: work runs somewhere it said it could not.
    """
    reqs = placement.normalize_requires(["dedicated:agent_7", "some_new_thing"])
    assert reqs == ["dedicated:agent_7", "some_new_thing"]


def test_dedicated_capability_shape():
    assert placement.dedicated_capability("agent_7") == "dedicated:agent_7"
    assert placement.is_dedicated_capability("dedicated:agent_7")
    assert not placement.is_dedicated_capability("gpu")
    with pytest.raises(ValueError):
        placement.dedicated_capability("")


def test_first_source_wins():
    """File top-level beats the config copy — an edit on disk is not shadowed."""
    p = placement.read_placement(
        {"residency": "cloud"},                       # what the editor just wrote
        {"residency": "local", "lifetime": "turn"},   # the stored config
    )
    assert p["residency"] == "cloud"
    assert p["lifetime"] == "turn"                    # not named above, so inherited


def test_a_source_that_omits_a_field_does_not_veto_the_next():
    p = placement.read_placement({}, {"requires": ["gpu"]})
    assert p["requires"] == ["gpu"]


# ===========================================================================
# The vocabulary is shared with the front end
# ===========================================================================

def test_capability_vocabulary_matches_the_typescript_twin():
    """A skill can only require what a pod can advertise.

    The lists live in two runtimes; if they drift, the editor offers a
    requirement no vehicle form can satisfy and that turn queues forever.
    """
    ts = Path(__file__).resolve().parents[1] / "gui_v2/src/types/domain/placement.ts"
    text = ts.read_text(encoding="utf-8")
    block = text.split("export const CAPABILITIES = [", 1)[1].split("]", 1)[0]
    ts_caps = [line.strip().strip("',\"") for line in block.splitlines() if "'" in line]
    assert ts_caps == list(placement.CAPABILITIES)

    assert placement.DEDICATED_PREFIX in text


# ===========================================================================
# Hop 1: skill config JSON -> EC_Skill
# ===========================================================================

def test_apply_placement_sets_the_three_fields():
    class _Target:
        residency = "any"
        lifetime = "conversation"
        requires: list = []

    target = _Target()
    placement.apply_placement(target, {"residency": "cloud", "requires": ["gpu"]})
    assert target.residency == "cloud"
    assert target.lifetime == "conversation"
    assert target.requires == ["gpu"]


def test_ec_skill_round_trips_placement_through_to_dict():
    """to_dict is an allowlist — a field missing from it is silently dropped."""
    from agent.ec_skill import EC_Skill

    skill = EC_Skill(name="placement_probe")
    skill.residency = "cloud"
    skill.lifetime = "long_running"
    skill.requires = ["browser_local"]

    data = skill.to_dict()
    assert data["residency"] == "cloud"
    assert data["lifetime"] == "long_running"
    assert data["requires"] == ["browser_local"]


def test_skill_built_from_db_config_carries_placement():
    """The DB path stores placement inside config; the loader must read it."""
    from agent.ec_skill import EC_Skill

    skill = EC_Skill(name="db_probe")
    skill.config = {
        "run_in_cloud": True,
        "residency": "cloud",
        "lifetime": "turn",
        "requires": ["cn_llm"],
    }
    placement.apply_placement(skill, skill.config)

    assert skill.residency == "cloud"
    assert skill.lifetime == "turn"
    assert skill.requires == ["cn_llm"]


# ===========================================================================
# Hop 2: the IPC save path folds placement into config
# ===========================================================================

def test_save_folds_placement_into_config(monkeypatch):
    """Placement has no GraphQL column, so it must land inside config or be lost."""
    from gui.ipc.w2p_handlers import skill_handler

    skill_info = {
        "name": "probe",
        "residency": "cloud",
        "lifetime": "turn",
        "requires": ["gpu", "gpu"],
        "config": {"run_in_cloud": True},
    }
    prepared = skill_handler._prepare_skill_data(skill_info, "owner@example.com")
    config = prepared["config"]
    assert config["residency"] == "cloud"
    assert config["lifetime"] == "turn"
    assert config["requires"] == ["gpu"]


def test_save_keeps_a_stored_placement_when_the_editor_sends_none():
    """Saving from a surface that does not edit placement must not erase it."""
    from gui.ipc.w2p_handlers import skill_handler

    skill_info = {
        "name": "probe",
        "config": {"residency": "cloud", "lifetime": "turn", "requires": ["gpu"]},
    }
    prepared = skill_handler._prepare_skill_data(skill_info, "owner@example.com")
    assert prepared["config"]["residency"] == "cloud"
    assert prepared["config"]["requires"] == ["gpu"]


# ===========================================================================
# Hop 3: ManagedTask inherits the skill's placement
# ===========================================================================

def _task(**overrides):
    from a2a.types import TaskState, TaskStatus
    from agent.ec_tasks.models import ManagedTask

    fields = dict(
        id="task_1", context_id="task_1", name="t",
        status=TaskStatus(state=TaskState.submitted),
    )
    fields.update(overrides)
    return ManagedTask(**fields)


def _skill(**overrides):
    from agent.ec_skill import EC_Skill

    skill = EC_Skill(name=overrides.pop("name", "probe"))
    for key, value in overrides.items():
        setattr(skill, key, value)
    return skill


def test_task_inherits_its_skill_placement():
    """A scheduler reading only the task must still see where work can run."""
    from agent.agent_converter import _inherit_skill_placement

    task = _task()
    _inherit_skill_placement(task, _skill(
        residency="cloud", lifetime="turn", requires=["browser_local"]))

    assert task.residency == "cloud"
    assert task.lifetime == "turn"
    assert task.requires == ["browser_local"]


def test_task_placement_overrides_the_skill():
    """Same skill, two tasks: one pinned local, one wherever."""
    from agent.agent_converter import _inherit_skill_placement

    task = _task(residency="local")
    _inherit_skill_placement(task, _skill(residency="cloud", requires=["gpu"]))

    assert task.residency == "local"      # the task's own word stands
    assert task.requires == ["gpu"]       # but it said nothing about these


def test_task_declaring_nothing_gets_defaults():
    task = _task()
    assert task.residency == "any"
    assert task.lifetime == "conversation"
    assert task.requires == []


def test_inheritance_is_non_fatal():
    """Placement must never be the reason an agent fails to load."""
    from agent.agent_converter import _inherit_skill_placement

    class _Hostile:
        @property
        def residency(self):
            raise RuntimeError("boom")

    _inherit_skill_placement(_Hostile(), _skill())   # no raise


# ===========================================================================
# C1 — pod columns and what a pod costs
# ===========================================================================

def test_pod_migration_adds_the_columns_it_promises(tmp_path):
    """The migration is the only thing standing between the form and a crash."""
    from sqlalchemy import create_engine, text

    from agent.db.migrations.versions.migration_314_to_315 import Migration_314_to_315

    engine = create_engine(f"sqlite:///{tmp_path / 'probe.db'}")
    with engine.begin() as conn:
        # The pre-migration shape: enough of agent_vehicles to be realistic.
        conn.execute(text(
            "CREATE TABLE agent_vehicles ("
            " id VARCHAR(64) PRIMARY KEY, name VARCHAR(128), owner VARCHAR(128),"
            " vehicle_type VARCHAR(64), cpu_cores INTEGER, memory_gb FLOAT,"
            " capabilities TEXT, max_concurrent_tasks INTEGER)"
        ))

    migration = Migration_314_to_315(engine)
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        assert migration.validate_preconditions(session)
        assert migration.upgrade(session)
        assert migration.validate_postconditions(session)

        # Idempotent: a half-applied migration must be safe to re-run.
        assert migration.upgrade(session)


def test_pod_cost_matches_the_figure_the_fleet_design_quotes():
    """2 vCPU / 4 GiB always-on ≈ ¥321/month.

    The rates are only trustworthy because they reproduce that number; if
    someone edits them, this is what says so.
    """
    from agent.pod_sizing import monthly_cost_cny

    assert round(monthly_cost_cny(2, 4)) == 321


def test_on_demand_monthly_is_reported_as_a_ceiling():
    """An on-demand pod has no predictable monthly figure — that is the point."""
    from agent.pod_sizing import estimate_pod_cost

    always_on = estimate_pod_cost(2, 4, lifecycle="always_on")
    on_demand = estimate_pod_cost(2, 4, lifecycle="on_demand")

    assert always_on["monthly_is_ceiling"] is False
    assert on_demand["monthly_is_ceiling"] is True
    assert on_demand["monthly_cny"] == always_on["monthly_cny"]   # the ceiling IS the always-on cost


def test_replicas_multiply_the_bill():
    from agent.pod_sizing import estimate_pod_cost

    one = estimate_pod_cost(2, 4, replicas=1)
    three = estimate_pod_cost(2, 4, replicas=3)
    assert round(three["monthly_cny"]) == round(one["monthly_cny"] * 3)


def test_pod_sizes_match_the_typescript_twin():
    """The form offers sizes from the TS copy; the handler prices the Python one."""
    from agent.pod_sizing import POD_SIZES

    ts = Path(__file__).resolve().parents[1] / "gui_v2/src/types/domain/pod.ts"
    text = ts.read_text(encoding="utf-8")
    for size in POD_SIZES:
        assert f"id: '{size['id']}'" in text, f"{size['id']} missing from pod.ts"
        assert f"cpu: {size['cpu']}" in text
