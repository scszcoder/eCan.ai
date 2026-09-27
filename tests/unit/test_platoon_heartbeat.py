"""A Platoon heartbeats to the cloud every minute (it died silently on its first pass in 99b)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

MainGUI = pytest.importorskip("gui.MainGUI")
MainWindow = MainGUI.MainWindow


def _platoon(**over):
    me = SimpleNamespace(
        vehicles=[], machine_name="DESKTOP-LNOV1-S", os_short="win", user="u@x.com", working_state="running_idle",
        functions="", processor="x86_64", platform="Windows", ip="10.0.0.7", host_role="Platoon",
        showMsg=lambda *a, **k: None, saveVehiclesJsonFile=lambda: None)
    me.getAgentIdsOnThisVehicle = lambda: "[]"
    me.__dict__.update(over)
    return me


def test_a_platoon_builds_its_own_report():
    report = MainWindow.prepVehicleReportData(_platoon(), None)
    assert report and report[0]["vname"] == "DESKTOP-LNOV1-S:win"
    assert "agent_ids" in report[0] and "bids" not in report[0]


def test_one_failing_pass_does_not_stop_the_heartbeat():
    beats = []
    me = _platoon()
    me.prepVehicleReportData = lambda v: MainWindow.prepVehicleReportData(me, v)

    async def heartbeat(report):
        beats.append(report)
        if len(beats) == 1:
            raise RuntimeError("cloud hiccup")     # the first pass fails...
        if len(beats) == 2:
            raise asyncio.CancelledError()        # ...the second still happens

    me._cloud_heartbeat_and_placement = heartbeat
    real_sleep = asyncio.sleep

    async def fast_sleep(_s):
        await real_sleep(0)

    async def run():
        with patch.object(MainGUI, "_local_vehicle_report_fields", return_value={}), \
             patch("asyncio.sleep", fast_sleep):
            with pytest.raises(asyncio.CancelledError):
                await MainWindow.runAgentsMonitor(me, asyncio.Queue())
    asyncio.run(run())
    assert len(beats) == 2, "the loop survived the failed pass and heartbeated again"
