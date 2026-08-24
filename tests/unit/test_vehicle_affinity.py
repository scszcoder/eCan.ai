"""Phase 1.5 tests: vehicle (host) affinity for agent startup.

Covers docs/SHARED_SKILL_MULTI_TASK_PLAN.md Phase 1.5: agents assigned to a
vehicle only start on the matching host; unassigned agents keep today's
start-everywhere behaviour; every failure path fails open.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agent.ec_agents import vehicle_affinity as va


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.delenv("ECAN_DISABLE_VEHICLE_AFFINITY", raising=False)
    va._reset_for_tests()
    yield
    va._reset_for_tests()


def _agent(vehicle_id=None, vehicle=None, mainwin=None):
    return SimpleNamespace(vehicle_id=vehicle_id, vehicle=vehicle, mainwin=mainwin)


class TestAgentLaunchAllowed:
    def test_no_affinity_starts_everywhere(self):
        allowed, reason = va.agent_launch_allowed(_agent())
        assert allowed and reason == "no-affinity"

    def test_matching_vehicle_allowed(self):
        va._local_vehicle_id = "veh-1"
        allowed, reason = va.agent_launch_allowed(_agent(vehicle_id="veh-1"))
        assert allowed and reason == "local"

    def test_mismatched_vehicle_skipped(self):
        va._local_vehicle_id = "veh-1"
        allowed, reason = va.agent_launch_allowed(_agent(vehicle_id="veh-2"))
        assert not allowed
        assert "veh-2" in reason

    def test_vehicle_attr_fallback(self):
        """EC_Agent's constructor stores the assignment under `vehicle`."""
        va._local_vehicle_id = "veh-1"
        allowed, _ = va.agent_launch_allowed(_agent(vehicle="veh-2"))
        assert not allowed

    def test_unresolvable_local_vehicle_fails_open(self):
        allowed, reason = va.agent_launch_allowed(_agent(vehicle_id="veh-2"))
        assert allowed and reason == "local-vehicle-unresolved"

    def test_kill_switch_disables_gate(self, monkeypatch):
        monkeypatch.setenv("ECAN_DISABLE_VEHICLE_AFFINITY", "1")
        va._local_vehicle_id = "veh-1"
        allowed, reason = va.agent_launch_allowed(_agent(vehicle_id="veh-2"))
        assert allowed and reason == "affinity-disabled"

    def _mainwin_with_row(self, row):
        service = MagicMock()
        service.get_vehicle_by_id.return_value = {"success": True, "data": row}
        return SimpleNamespace(ec_db_mgr=SimpleNamespace(vehicle_service=service))

    def test_legacy_gui_row_for_this_host_allowed(self, monkeypatch):
        """An assignment made via the GUI dropdown (legacy row with
        name '<hostname>:<os>') still counts as local."""
        va._local_vehicle_id = "machine-id-1"
        monkeypatch.setattr(va.socket, "gethostname", lambda: "MyPC")
        mainwin = self._mainwin_with_row({"id": "legacy-7", "name": "mypc:win", "hostname": ""})
        allowed, reason = va.agent_launch_allowed(_agent(vehicle_id="legacy-7", mainwin=mainwin))
        assert allowed and reason == "local-legacy-row"

    def test_legacy_row_for_other_host_skipped(self, monkeypatch):
        va._local_vehicle_id = "machine-id-1"
        monkeypatch.setattr(va.socket, "gethostname", lambda: "MyPC")
        mainwin = self._mainwin_with_row({"id": "legacy-9", "name": "otherpc:win", "hostname": "otherpc"})
        allowed, _ = va.agent_launch_allowed(_agent(vehicle_id="legacy-9", mainwin=mainwin))
        assert not allowed

    def test_unverifiable_assignment_stays_skipped(self, monkeypatch):
        """A mismatching id whose row can't be looked up must NOT fail open —
        the user deliberately assigned somewhere."""
        va._local_vehicle_id = "machine-id-1"
        monkeypatch.setattr(va.socket, "gethostname", lambda: "MyPC")
        service = MagicMock()
        service.get_vehicle_by_id.side_effect = RuntimeError("db down")
        mainwin = SimpleNamespace(ec_db_mgr=SimpleNamespace(vehicle_service=service))
        allowed, _ = va.agent_launch_allowed(_agent(vehicle_id="veh-x", mainwin=mainwin))
        assert not allowed


class TestResolveLocalVehicleId:
    def test_resolves_and_persists_machine_id(self, tmp_path):
        mainwin = SimpleNamespace(my_ecb_data_homepath=str(tmp_path))
        first = va.resolve_local_vehicle_id(mainwin)
        assert first and len(first) == 36  # uuid format

        va._reset_for_tests()
        assert va.resolve_local_vehicle_id(mainwin) == first  # file-persisted

    def test_no_mainwin_no_username_returns_empty(self):
        assert va.resolve_local_vehicle_id() == ""

    def test_cached_after_first_resolution(self, tmp_path):
        mainwin = SimpleNamespace(my_ecb_data_homepath=str(tmp_path))
        first = va.resolve_local_vehicle_id(mainwin)
        # Second call ignores a different mainwin — process-cached
        assert va.resolve_local_vehicle_id(SimpleNamespace(my_ecb_data_homepath="")) == first


class TestRegisterLocalVehicle:
    def _mainwin(self, tmp_path, service):
        return SimpleNamespace(
            my_ecb_data_homepath=str(tmp_path),
            ec_db_mgr=SimpleNamespace(vehicle_service=service),
            user="tester@example.com",
        )

    def test_registers_new_vehicle_row(self, tmp_path):
        service = MagicMock()
        service.get_vehicle_by_id.return_value = {"success": False, "data": None}
        mainwin = self._mainwin(tmp_path, service)

        va.register_local_vehicle(mainwin)

        data = service.add_vehicle.call_args[0][0]
        assert data["id"] == va.resolve_local_vehicle_id(mainwin)
        assert data["status"] == "online"

    def test_updates_existing_row(self, tmp_path):
        service = MagicMock()
        service.get_vehicle_by_id.return_value = {"success": True, "data": {"id": "x"}}
        mainwin = self._mainwin(tmp_path, service)

        va.register_local_vehicle(mainwin)

        service.add_vehicle.assert_not_called()
        assert service.update_vehicle.call_args[0][1]["status"] == "online"

    def test_idempotent_per_process(self, tmp_path):
        service = MagicMock()
        service.get_vehicle_by_id.return_value = {"success": False, "data": None}
        mainwin = self._mainwin(tmp_path, service)

        va.register_local_vehicle(mainwin)
        va.register_local_vehicle(mainwin)

        assert service.add_vehicle.call_count == 1

    def test_missing_service_is_nonfatal(self, tmp_path):
        mainwin = SimpleNamespace(my_ecb_data_homepath=str(tmp_path), ec_db_mgr=None)
        va.register_local_vehicle(mainwin)  # must not raise
