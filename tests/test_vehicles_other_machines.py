"""Vehicles page refresh lists this account's other machines: cloud desktops, running pods, LAN."""

import time
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

from gui.ipc.w2p_handlers import vehicle_handler as vh


def _utc(seconds_ago):
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat().replace("+00:00", "Z")


def _desk(id_, name, ago=30, status="online"):
    return {"id": id_, "name": name, "vehicle_type": None, "status": status,
            "last_heartbeat": _utc(ago), "ip_address": "1.2.3.4", "platform": "windows"}


class CloudRowTests(unittest.TestCase):
    def test_a_heartbeating_desktop_is_online_and_a_silent_one_offline(self):
        self.assertEqual(vh._machine_entry(_desk("m1", "PC-1", ago=30))["status"], "active")
        self.assertEqual(vh._machine_entry(_desk("m2", "PC-2", ago=900))["status"], "offline")

    def test_pre_fix_duplicates_without_a_stamp_are_skipped(self):
        self.assertIsNone(vh._machine_entry({"id": "SCHOME:win", "name": "SCHOME:win",
                                             "status": "running_idle", "last_heartbeat": None}))

    def test_running_pods_show_by_status_despite_the_prc_stamp(self):
        # The server stamps pods in PRC time: read as UTC it is 8h in the FUTURE.
        future = (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat()
        pod = {"id": "pod-7", "name": "ecan-pod-7", "vehicle_type": "cloud", "status": "online",
               "last_heartbeat": future}
        e = vh._machine_entry(pod)
        self.assertEqual((e["type"], e["status"]), ("cloud", "active"))

    def test_pod_tombstones_and_pod_definitions_stay_in_the_pods_panel(self):
        self.assertIsNone(vh._machine_entry({"id": "old", "vehicle_type": "cloud", "status": "offline"}))
        with mock.patch.object(vh, "_is_customer_pod", return_value=True):
            self.assertIsNone(vh._machine_entry({"id": "def", "vehicle_type": "cloud", "status": "online"}))


class MergeTests(unittest.TestCase):
    def _lan(self, mid, name, ago=10, host="192.168.1.9"):
        return SimpleNamespace(machine_id=mid, machine_name=name, lan_host=host, os="win", arch="x64",
                               lan_last_seen=time.time() - ago)

    def _run(self, cloud_rows, lan_nodes, exclude=()):
        directory = SimpleNamespace(list_nodes=lambda: lan_nodes)
        with mock.patch.object(vh, "_cloud_ctx", return_value={"session": None, "token": "t", "endpoint": "e"}), \
             mock.patch.object(vh, "_query_pod_rows", return_value=cloud_rows), \
             mock.patch("agent.a2a.discovery.directory.get_directory", return_value=directory):
            return {e["id"]: e for e in vh._cloud_machines(set(exclude))}

    def test_the_same_machine_seen_both_ways_is_one_entry(self):
        out = self._run([_desk("m1", "PC-1")], [self._lan("m1", "PC-1", host="192.168.1.20")])
        self.assertEqual(len(out), 1)
        self.assertEqual((out["m1"]["source"], out["m1"]["ip"]), ("cloud+lan", "192.168.1.20"))

    def test_lan_only_and_cloud_only_machines_both_show(self):
        out = self._run([_desk("far", "Office-PC")], [self._lan("near", "Next-desk")])
        self.assertEqual((out["far"]["source"], out["near"]["source"]), ("cloud", "lan"))

    def test_this_machine_is_not_listed_twice(self):
        out = self._run([_desk("me", "Me")], [self._lan("me", "Me")], exclude=["me"])
        self.assertEqual(out, {})

    def test_signed_out_still_shows_the_lan(self):
        directory = SimpleNamespace(list_nodes=lambda: [self._lan("near", "Next-desk")])
        with mock.patch.object(vh, "_cloud_ctx", return_value=None), \
             mock.patch("agent.a2a.discovery.directory.get_directory", return_value=directory):
            self.assertEqual([e["id"] for e in vh._cloud_machines(set())], ["near"])


if __name__ == "__main__":
    unittest.main()
