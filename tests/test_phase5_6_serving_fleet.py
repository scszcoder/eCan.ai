"""Phase 5 + 6 of Path 1.5 — serving-mode pod and fleet membership.

Phase 5 turns the CN worker from one-shot (load task, run, exit) into something
that stays up and takes work item after work item. The execution core is
unchanged; the loop is new, and it has to hold three properties:

  * a serving pod refuses to start on an in-memory checkpointer, because it
    cannot survive the restart it exists to survive;
  * it installs a headless service locator, since there is no MainWindow;
  * one bad work item must not take the pod down.

Phase 6 lets a pod join the fleet. A desktop install IS its machine, so its
vehicle id comes from a machine fingerprint; a pod is cattle, and the scheduler
says which vehicle it is. Both the fail-open behaviour and the
ECAN_DISABLE_VEHICLE_AFFINITY kill switch must survive that.
"""

import asyncio

import pytest

from agent.cloud_worker import cn_serve
from agent.ec_agents import vehicle_affinity as va


# ===========================================================================
# Phase 5 — serving mode
# ===========================================================================

async def _alist(items):
    for it in items:
        yield it


def _run(coro):
    return asyncio.run(coro)


# --- preconditions ---------------------------------------------------------

def test_serving_refuses_an_ephemeral_checkpointer(monkeypatch):
    """A pod that cannot survive a restart should not pretend to serve."""
    monkeypatch.delenv("ECAN_CHECKPOINTER", raising=False)
    monkeypatch.delenv("ECAN_SERVE_ALLOW_EPHEMERAL", raising=False)
    with pytest.raises(cn_serve.ServePreconditionFailed) as exc:
        cn_serve.require_durable_checkpointer()
    assert "ECAN_CHECKPOINTER" in str(exc.value)


def test_ephemeral_allowed_explicitly_for_dev(monkeypatch):
    monkeypatch.delenv("ECAN_CHECKPOINTER", raising=False)
    monkeypatch.setenv("ECAN_SERVE_ALLOW_EPHEMERAL", "1")
    cn_serve.require_durable_checkpointer()          # no raise


def test_durable_checkpointer_satisfies_the_precondition(monkeypatch):
    monkeypatch.setenv("ECAN_CHECKPOINTER", "postgres")
    monkeypatch.delenv("ECAN_SERVE_ALLOW_EPHEMERAL", raising=False)
    cn_serve.require_durable_checkpointer()          # no raise (not built, just selected)


# --- the loop --------------------------------------------------------------

def test_serves_items_in_order(monkeypatch):
    monkeypatch.setenv("ECAN_SERVE_ALLOW_EPHEMERAL", "1")
    seen = []

    async def handler(item):
        seen.append(item)

    stats = _run(cn_serve.serve(
        _alist(['{"task_id": "t1"}', '{"task_id": "t2"}']),
        handler=handler, install_context=False))

    assert seen == ['{"task_id": "t1"}', '{"task_id": "t2"}']
    assert (stats.accepted, stats.completed, stats.failed) == (2, 2, 0)


def test_one_bad_item_does_not_kill_the_pod(monkeypatch):
    """Per-item isolation — the whole point of a serving loop."""
    monkeypatch.setenv("ECAN_SERVE_ALLOW_EPHEMERAL", "1")
    seen = []

    async def handler(item):
        seen.append(item)
        if "boom" in item:
            raise RuntimeError("skill blew up")

    stats = _run(cn_serve.serve(
        _alist(['{"task_id":"ok1"}', '{"task_id":"boom"}', '{"task_id":"ok2"}']),
        handler=handler, install_context=False))

    assert len(seen) == 3, "loop must continue past the failure"
    assert (stats.accepted, stats.completed, stats.failed) == (3, 2, 1)


def test_stop_sentinel_drains(monkeypatch):
    monkeypatch.setenv("ECAN_SERVE_ALLOW_EPHEMERAL", "1")
    seen = []

    async def handler(item):
        seen.append(item)

    stats = _run(cn_serve.serve(
        _alist(['{"task_id":"a"}', cn_serve.STOP, '{"task_id":"never"}']),
        handler=handler, install_context=False))

    assert seen == ['{"task_id":"a"}']
    assert stats.completed == 1


def test_max_items_stops_the_loop(monkeypatch):
    monkeypatch.setenv("ECAN_SERVE_ALLOW_EPHEMERAL", "1")

    async def handler(item):
        pass

    stats = _run(cn_serve.serve(
        _alist(['{"task_id":"%d"}' % i for i in range(10)]),
        handler=handler, install_context=False, max_items=3))
    assert stats.accepted == 3


def test_dict_items_are_serialised_for_the_handler(monkeypatch):
    monkeypatch.setenv("ECAN_SERVE_ALLOW_EPHEMERAL", "1")
    seen = []

    async def handler(item):
        seen.append(item)

    _run(cn_serve.serve(_alist([{"task_id": "t1"}]), handler=handler,
                        install_context=False))
    assert isinstance(seen[0], str) and "t1" in seen[0]


def test_headless_context_is_installed_and_removed(monkeypatch):
    """A pod has no MainWindow; the locator must be up while serving."""
    monkeypatch.setenv("ECAN_SERVE_ALLOW_EPHEMERAL", "1")
    import app_context as ac

    during = {}

    async def handler(item):
        during["main_window"] = ac.AppContext.get_main_window()
        during["headless"] = ac.headless_enabled()

    _run(cn_serve.serve(_alist(['{"task_id":"t"}']), handler=handler,
                        install_context=True))

    assert during["main_window"] is not None
    assert during["headless"] is True
    # and torn down afterwards
    assert ac.AppContext.get_main_window() is None
    assert ac.headless_enabled() is False


def test_stats_report_uptime(monkeypatch):
    monkeypatch.setenv("ECAN_SERVE_ALLOW_EPHEMERAL", "1")

    async def handler(item):
        pass

    stats = _run(cn_serve.serve(_alist([]), handler=handler, install_context=False))
    assert set(stats.as_dict()) == {"accepted", "completed", "failed", "uptime_s"}


def test_worker_exposes_serve_mode():
    from pathlib import Path
    src = Path("agent/cloud_worker/cn_worker_main.py").read_text(encoding="utf-8")
    assert '"single", "serve"' in src
    assert "_serve_cn" in src


# ===========================================================================
# Phase 6 — fleet membership
# ===========================================================================

@pytest.fixture(autouse=True)
def _reset_vehicle(monkeypatch):
    monkeypatch.delenv(va.ENV_ASSIGNED_VEHICLE_ID, raising=False)
    va._reset_for_tests()
    yield
    va._reset_for_tests()


class _FakeVehicleService:
    """Mirrors the real DBVehicleService surface used by vehicle_affinity.

    Existence is checked via query_vehicles(id=...) -> {"success", "data"} —
    there is no get_vehicle_by_id (that AttributeError was a v0.9.95t bug).
    """

    def __init__(self, existing=None):
        self.rows = dict(existing or {})
        self.added = []
        self.updated = []

    def query_vehicles(self, **kw):
        vid = kw.get("id")
        row = self.rows.get(vid)
        return {"success": True, "data": [row] if row else []}

    def add_vehicle(self, payload):
        self.added.append(payload)
        self.rows[payload["id"]] = payload

    def update_vehicle(self, vid, patch):
        self.updated.append((vid, patch))
        self.rows.setdefault(vid, {}).update(patch)


# --- scheduler-assigned id -------------------------------------------------

def test_assigned_id_wins_over_machine_fingerprint():
    va.set_assigned_vehicle_id("pod-abc123")
    assert va.resolve_local_vehicle_id() == "pod-abc123"


def test_assigned_id_can_come_from_env(monkeypatch):
    monkeypatch.setenv(va.ENV_ASSIGNED_VEHICLE_ID, "pod-from-env")
    va._reset_for_tests()
    monkeypatch.setenv(va.ENV_ASSIGNED_VEHICLE_ID, "pod-from-env")
    assert va.resolve_local_vehicle_id() == "pod-from-env"


def test_no_assignment_leaves_desktop_resolution_alone():
    """Desktop keeps deriving its id from the machine."""
    assert va.assigned_vehicle_id() == ""
    vid = va.resolve_local_vehicle_id()
    assert vid and not vid.startswith("pod-")


def test_setting_an_assignment_drops_a_cached_local_id():
    first = va.resolve_local_vehicle_id()
    assert first
    va.set_assigned_vehicle_id("pod-late")
    assert va.resolve_local_vehicle_id() == "pod-late"


# --- cloud registration ----------------------------------------------------

def test_cloud_registration_records_type_capacity_and_capabilities():
    svc = _FakeVehicleService()
    vid = va.register_cloud_vehicle(
        svc, owner="o@e.com", capacity=8,
        capabilities=["browser_local"], vehicle_id="pod-1", hostname="pod-1.local")

    assert vid == "pod-1"
    row = svc.added[0]
    assert row["vehicle_type"] == "cloud"
    assert row["max_concurrent_tasks"] == 8
    assert row["capabilities"] == ["browser_local"]
    assert row["status"] == "online"
    assert row["last_heartbeat"] is not None


def test_re_registration_updates_rather_than_duplicates():
    svc = _FakeVehicleService(existing={"pod-1": {"id": "pod-1"}})
    va.register_cloud_vehicle(svc, owner="o@e.com", vehicle_id="pod-1")
    assert svc.added == []
    assert svc.updated and svc.updated[0][0] == "pod-1"


def test_capacity_is_at_least_one():
    svc = _FakeVehicleService()
    va.register_cloud_vehicle(svc, owner="o", capacity=0, vehicle_id="pod-1")
    assert svc.added[0]["max_concurrent_tasks"] == 1


def test_registration_fails_open():
    """A fleet that cannot register should degrade, not refuse to serve."""
    assert va.register_cloud_vehicle(None, owner="o", vehicle_id="pod-1") == ""

    class _Broken:
        def query_vehicles(self, **kw): raise RuntimeError("db down")
        def add_vehicle(self, p): raise RuntimeError("db down")
        def update_vehicle(self, v, p): raise RuntimeError("db down")

    assert va.register_cloud_vehicle(_Broken(), owner="o", vehicle_id="pod-1") == ""


# --- heartbeat -------------------------------------------------------------

def test_heartbeat_refreshes_status_and_timestamp():
    svc = _FakeVehicleService(existing={"pod-1": {"id": "pod-1"}})
    assert va.heartbeat_vehicle(svc, "pod-1") is True
    vid, patch = svc.updated[-1]
    assert vid == "pod-1"
    assert patch["status"] == "online"
    assert patch["last_heartbeat"] is not None


def test_heartbeat_can_mark_draining():
    svc = _FakeVehicleService(existing={"pod-1": {"id": "pod-1"}})
    va.heartbeat_vehicle(svc, "pod-1", status="maintenance")
    assert svc.updated[-1][1]["status"] == "maintenance"


def test_heartbeat_fails_open():
    assert va.heartbeat_vehicle(None, "pod-1") is False


# --- invariants the handoff said to preserve -------------------------------

def test_kill_switch_still_present(monkeypatch):
    monkeypatch.setenv("ECAN_DISABLE_VEHICLE_AFFINITY", "1")
    assert va._affinity_disabled() is True
    monkeypatch.setenv("ECAN_DISABLE_VEHICLE_AFFINITY", "0")
    assert va._affinity_disabled() is False


def test_desktop_registration_path_untouched():
    from pathlib import Path
    src = Path("agent/ec_agents/vehicle_affinity.py").read_text(encoding="utf-8")
    assert "def register_local_vehicle(mainwin)" in src
    assert '"vehicle_type": "desktop"' in src
