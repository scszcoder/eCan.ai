"""Phase 1.5 tests: vehicle (host) affinity for agent startup.

Covers docs/SHARED_SKILL_MULTI_TASK_PLAN.md Phase 1.5: agents assigned to a
vehicle only start on the matching host; unassigned agents keep today's
start-everywhere behaviour; every failure path fails open.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agent.ec_agents import vehicle_affinity as va
from agent.ec_agents import machine_fingerprint as mf


class TestMachineFingerprint:
    """OS-native machine id → deterministic UUID5, per docs/
    VEHICLE_AFFINITY_MACHINE_ID.md §4."""

    def test_windows_reads_machine_guid(self):
        with patch.object(mf.platform, "system", return_value="Windows"), \
             patch.object(mf, "_read_windows_machine_guid", return_value="WINGUID-123"):
            v1 = mf.get_os_vehicle_id()
            v2 = mf.get_os_vehicle_id()
        assert v1 == v2 and len(v1) == 36  # deterministic uuid5

    def test_macos_reads_platform_uuid(self):
        with patch.object(mf.platform, "system", return_value="Darwin"), \
             patch.object(mf, "_read_macos_platform_uuid", return_value="MAC-UUID-9"):
            assert len(mf.get_os_vehicle_id()) == 36

    def test_linux_reads_machine_id(self):
        with patch.object(mf.platform, "system", return_value="Linux"), \
             patch.object(mf, "_read_linux_machine_id", return_value="deadbeef"):
            assert len(mf.get_os_vehicle_id()) == 36

    def test_distinct_os_ids_give_distinct_uuids(self):
        with patch.object(mf.platform, "system", return_value="Linux"):
            with patch.object(mf, "_read_linux_machine_id", return_value="aaaa"):
                a = mf.get_os_vehicle_id()
            with patch.object(mf, "_read_linux_machine_id", return_value="bbbb"):
                b = mf.get_os_vehicle_id()
        assert a != b

    def test_none_when_os_id_unavailable(self):
        with patch.object(mf, "read_os_machine_id", return_value=""):
            assert mf.get_os_vehicle_id() is None


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

    def test_unresolvable_local_vehicle_fails_open(self, monkeypatch):
        # Force both id sources to fail (no OS id, no data-home) so the local
        # vehicle is genuinely unresolvable.
        from agent.ec_agents import machine_fingerprint as mf
        monkeypatch.setattr(mf, "get_os_vehicle_id", lambda: None)
        allowed, reason = va.agent_launch_allowed(_agent(vehicle_id="veh-2"))
        assert allowed and reason == "local-vehicle-unresolved"

    def test_kill_switch_disables_gate(self, monkeypatch):
        monkeypatch.setenv("ECAN_DISABLE_VEHICLE_AFFINITY", "1")
        va._local_vehicle_id = "veh-1"
        allowed, reason = va.agent_launch_allowed(_agent(vehicle_id="veh-2"))
        assert allowed and reason == "affinity-disabled"

    def _mainwin_with_row(self, row):
        service = MagicMock()
        service.query_vehicles.return_value = {"success": True, "data": [row]}
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
        service.query_vehicles.side_effect = RuntimeError("db down")
        mainwin = SimpleNamespace(ec_db_mgr=SimpleNamespace(vehicle_service=service))
        allowed, _ = va.agent_launch_allowed(_agent(vehicle_id="veh-x", mainwin=mainwin))
        assert not allowed


class TestResolveLocalVehicleId:
    def test_os_fingerprint_is_primary(self, monkeypatch):
        """Primary source is the OS machine fingerprint — same id in any
        process regardless of data-home path (the 2026-09-03 fix)."""
        from agent.ec_agents import machine_fingerprint as mf
        monkeypatch.setattr(mf, "get_os_vehicle_id", lambda: "os-uuid-xyz")
        # data-home doesn't matter when the OS id resolves
        assert va.resolve_local_vehicle_id(
            SimpleNamespace(my_ecb_data_homepath="/whatever")) == "os-uuid-xyz"

    def test_app_and_cli_paths_agree_via_os_id(self, monkeypatch):
        """The core invariant: app (mainwin) and CLI (username) resolve the
        SAME id, even with divergent data-homes, because the OS id is
        path-independent."""
        from agent.ec_agents import machine_fingerprint as mf
        monkeypatch.setattr(mf, "get_os_vehicle_id", lambda: "os-uuid-same")
        app_id = va.resolve_local_vehicle_id(SimpleNamespace(my_ecb_data_homepath="/app/home"))
        va._reset_for_tests()
        cli_id = va.resolve_local_vehicle_id(username="user@example.com")
        assert app_id == cli_id == "os-uuid-same"

    def test_falls_back_to_persisted_uuid_without_os_id(self, tmp_path, monkeypatch):
        from agent.ec_agents import machine_fingerprint as mf
        monkeypatch.setattr(mf, "get_os_vehicle_id", lambda: None)
        mainwin = SimpleNamespace(my_ecb_data_homepath=str(tmp_path))
        first = va.resolve_local_vehicle_id(mainwin)
        assert first and len(first) == 36  # uuid format from machine_id.py
        va._reset_for_tests()
        assert va.resolve_local_vehicle_id(mainwin) == first  # file-persisted

    def test_no_mainwin_no_username_returns_empty(self, monkeypatch):
        from agent.ec_agents import machine_fingerprint as mf
        monkeypatch.setattr(mf, "get_os_vehicle_id", lambda: None)
        assert va.resolve_local_vehicle_id() == ""

    def test_cached_after_first_resolution(self, tmp_path, monkeypatch):
        from agent.ec_agents import machine_fingerprint as mf
        monkeypatch.setattr(mf, "get_os_vehicle_id", lambda: None)
        mainwin = SimpleNamespace(my_ecb_data_homepath=str(tmp_path))
        first = va.resolve_local_vehicle_id(mainwin)
        # Second call ignores a different mainwin — process-cached
        assert va.resolve_local_vehicle_id(SimpleNamespace(my_ecb_data_homepath="")) == first


class TestGateSelfHealAndTransition:
    def _mainwin(self, row_for_id=None):
        service = MagicMock()
        if row_for_id is None:
            service.query_vehicles.return_value = {"success": True, "data": []}
        else:
            service.query_vehicles.return_value = {"success": True, "data": [row_for_id]}
        return SimpleNamespace(ec_db_mgr=SimpleNamespace(vehicle_service=service))

    def test_orphan_pin_is_adopted(self):
        """A pin to an id that is no known vehicle (e.g. minted by the old
        data-home-dependent scheme) is adopted, not stranded."""
        va._local_vehicle_id = "os-new"
        va._legacy_vehicle_id = "legacy-old"
        mainwin = self._mainwin(row_for_id=None)  # no row for the pin → orphan
        allowed, reason = va.agent_launch_allowed(
            _agent(vehicle_id="2417627c-stale", mainwin=mainwin))
        assert allowed and reason == "stale-pin-adopt"

    def test_real_other_host_still_skipped(self):
        """A pin that IS a known vehicle row (a genuine other host) is still
        skipped — self-heal must not weaken the multi-host case."""
        va._local_vehicle_id = "os-new"
        va._legacy_vehicle_id = "legacy-old"
        mainwin = self._mainwin(row_for_id={"id": "other-host", "name": "otherpc", "hostname": "otherpc"})
        allowed, _ = va.agent_launch_allowed(
            _agent(vehicle_id="other-host", mainwin=mainwin))
        assert not allowed

    def test_legacy_id_accepted_in_transition(self):
        """During the id transition, a pin matching the persisted-UUID id
        still counts as local."""
        va._local_vehicle_id = "os-new"
        va._legacy_vehicle_id = "legacy-old"
        allowed, reason = va.agent_launch_allowed(
            _agent(vehicle_id="legacy-old", mainwin=SimpleNamespace()))
        assert allowed and reason == "local-legacy-id"


class TestRegisterLocalVehicle:
    def _mainwin(self, tmp_path, service):
        return SimpleNamespace(
            my_ecb_data_homepath=str(tmp_path),
            ec_db_mgr=SimpleNamespace(vehicle_service=service),
            user="tester@example.com",
        )

    def test_registers_new_vehicle_row(self, tmp_path):
        service = MagicMock()
        service.query_vehicles.return_value = {"success": False, "data": None}
        mainwin = self._mainwin(tmp_path, service)

        va.register_local_vehicle(mainwin)

        data = service.add_vehicle.call_args[0][0]
        assert data["id"] == va.resolve_local_vehicle_id(mainwin)
        assert data["status"] == "online"

    def test_updates_existing_row(self, tmp_path):
        service = MagicMock()
        service.query_vehicles.return_value = {"success": True, "data": [{"id": "x"}]}
        mainwin = self._mainwin(tmp_path, service)

        va.register_local_vehicle(mainwin)

        service.add_vehicle.assert_not_called()
        assert service.update_vehicle.call_args[0][1]["status"] == "online"

    def test_idempotent_per_process(self, tmp_path):
        service = MagicMock()
        service.query_vehicles.return_value = {"success": False, "data": None}
        mainwin = self._mainwin(tmp_path, service)

        va.register_local_vehicle(mainwin)
        va.register_local_vehicle(mainwin)

        assert service.add_vehicle.call_count == 1

    def test_missing_service_is_nonfatal(self, tmp_path):
        mainwin = SimpleNamespace(my_ecb_data_homepath=str(tmp_path), ec_db_mgr=None)
        va.register_local_vehicle(mainwin)  # must not raise
