"""Fleet transfers: sealed end to end, LAN when reachable, cloud otherwise."""

import json
import os
import tempfile
import threading
import time
import unittest
import uuid
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from agent.fleet import lan, payloads, seal, transfers


class SealTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _file(self, name, data):
        p = os.path.join(self.tmp, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def _roundtrip(self, data):
        priv, pub = seal.new_keypair()
        src = self._file("plain", data)
        sealed, out = os.path.join(self.tmp, "sealed"), os.path.join(self.tmp, "out")
        seal.seal_file(src, sealed, pub, "t1")
        seal.open_file(sealed, out, priv, "t1")
        with open(out, "rb") as f:
            return f.read(), sealed, priv

    def test_roundtrip_empty_small_and_multi_chunk(self):
        for data in (b"", b"hello", os.urandom(seal.CHUNK * 2 + 17)):
            self.assertEqual(self._roundtrip(data)[0], data)

    def test_only_the_receiver_can_open_it(self):
        _, sealed, _ = self._roundtrip(b"secret")
        other, _ = seal.new_keypair()
        with self.assertRaises(seal.SealError):
            seal.open_file(sealed, os.path.join(self.tmp, "x"), other, "t1")

    def test_bound_to_the_transfer_id(self):
        _, sealed, priv = self._roundtrip(b"secret")
        with self.assertRaises(seal.SealError):
            seal.open_file(sealed, os.path.join(self.tmp, "x"), priv, "another")

    def test_a_cut_short_bundle_does_not_open_as_a_shorter_one(self):
        _, sealed, priv = self._roundtrip(os.urandom(seal.CHUNK + 100))
        with open(sealed, "rb") as f:
            data = f.read()
        cut = self._file("cut", data[: 36 + 4 + seal.CHUNK + 16])   # header + first chunk only
        with self.assertRaises(seal.SealError):
            seal.open_file(cut, os.path.join(self.tmp, "x"), priv, "t1")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "x")))


class LanTests(unittest.TestCase):
    def test_upload_reaches_the_listener_with_the_token_only(self):
        tmp = tempfile.mkdtemp()
        dest = os.path.join(tmp, "in")
        src = os.path.join(tmp, "src")
        with open(src, "wb") as f:
            f.write(b"x" * 5000)
        rcv = lan.Receiver("tid", dest, "tok")
        port = rcv.start()
        try:
            with mock.patch.object(lan, "_lan_address", return_value=True):
                self.assertEqual(lan.send(["127.0.0.1"], port, "wrong", "tid", src), "")
                self.assertFalse(rcv.received.is_set())
                self.assertEqual(lan.send(["127.0.0.1"], port, "tok", "tid", src), "127.0.0.1")
            self.assertTrue(rcv.received.is_set())
            self.assertEqual(os.path.getsize(dest), 5000)
        finally:
            rcv.stop()

    def test_public_addresses_are_never_tried(self):
        with mock.patch("socket.create_connection") as conn:
            self.assertEqual(lan.send(["8.8.8.8"], 80, "tok", "tid", __file__), "")
        conn.assert_not_called()

    def test_private_addresses_only(self):
        self.assertTrue(lan._lan_address("192.168.1.5"))
        self.assertTrue(lan._lan_address("10.0.0.2"))
        self.assertFalse(lan._lan_address("127.0.0.1"))
        self.assertFalse(lan._lan_address("49.235.169.108"))


class FakeCloud:
    """The transfer records, the way the server keeps them (contract §3)."""

    def __init__(self):
        self.rows, self.blobs, self.lock = {}, {}, threading.Lock()

    def create(self, kind, source, receiver, requester, params, receiver_info=None):
        tid = uuid.uuid4().hex
        self.rows[tid] = {"transfer_id": tid, "kind": kind, "status": "requested",
                          "source_vehicle_id": source, "receiver_vehicle_id": receiver,
                          "requester_vehicle_id": requester, "params": params, "receiver": {}}
        return dict(self.rows[tid])

    def list_for(self, vid, include_finished=False):
        return [dict(r) for r in self.rows.values()
                if vid in (r["source_vehicle_id"], r["receiver_vehicle_id"], r["requester_vehicle_id"])
                and (include_finished or r["status"] not in ("done", "failed", "expired"))]

    def update(self, tid, **f):
        with self.lock:
            r = self.rows[tid]
            if r["status"] in ("done", "failed"):
                raise RuntimeError("INVALID_TRANSITION")
            r.update({k: v for k, v in f.items() if v is not None})
            return dict(r)

    def upload_url(self, tid):
        return f"mem://{tid}"

    def download_url(self, tid):
        return f"mem://{tid}"

    def put_blob(self, url, path):
        with open(path, "rb") as f:
            self.blobs[url] = f.read()

    def get_blob(self, url, path):
        with open(path, "wb") as f:
            f.write(self.blobs[url])

    def finish(self, tid, status, error=""):
        with self.lock:
            self.rows[tid].update(status=status, error=error)
            return dict(self.rows[tid])


class LogsFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cloud = FakeCloud()
        self.me = {"id": "A"}
        patches = [
            mock.patch.object(transfers, "_api", return_value=self.cloud),
            mock.patch.object(transfers, "_me", side_effect=lambda mw: self.me["id"]),
            mock.patch.object(transfers, "_work_dir", return_value=Path(self.tmp)),
            mock.patch.object(transfers, "downloads_dir", return_value=Path(self.tmp)),
            mock.patch.object(transfers, "_ensure_fast_loop"),
            mock.patch.object(payloads, "build_logs", side_effect=self._fake_logs),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(transfers._forget_finished, set())

    def _fake_logs(self, dest, hours):
        with zipfile.ZipFile(dest, "w") as zf:
            zf.writestr("runlogs/eCan.log", "log line\n")
        return {"files": 1, "bytes": 9}

    def _as(self, vid):
        self.me["id"] = vid
        transfers.tick(None)

    def _wait(self, tid, status):
        for _ in range(100):
            if self.cloud.rows[tid]["status"] == status and not transfers._busy:
                return
            time.sleep(0.05)
        self.fail(f"status {self.cloud.rows[tid]['status']} != {status}")

    def _run(self, lan_reachable):
        t = transfers.request_logs(None, "B", hours=2)
        tid = t["transfer_id"]
        self.assertEqual(self.cloud.rows[tid]["status"], "ready")
        self.assertTrue(self.cloud.rows[tid]["receiver"]["pubkey"])
        with mock.patch.object(lan, "_lan_address", return_value=lan_reachable):
            if lan_reachable:
                self.cloud.rows[tid]["receiver"]["lan"]["addrs"] = ["127.0.0.1"]
            self._as("B")                         # source packs and sends
            for _ in range(100):
                if not transfers._busy:
                    break
                time.sleep(0.05)
        self._as("A")                             # receiver picks it up
        self._wait(tid, "done")
        return tid

    def test_same_lan_the_bytes_never_touch_the_cloud(self):
        tid = self._run(lan_reachable=True)
        self.assertEqual(self.cloud.blobs, {})
        self.assertEqual(transfers._results[tid]["route"], "lan")
        with zipfile.ZipFile(transfers._results[tid]["path"]) as zf:
            self.assertEqual(zf.read("runlogs/eCan.log"), b"log line\n")

    def test_different_networks_go_through_the_cloud_sealed(self):
        tid = self._run(lan_reachable=False)
        self.assertEqual(transfers._results[tid]["route"], "cloud")
        blob = next(iter(self.cloud.blobs.values()))
        self.assertTrue(blob.startswith(seal.MAGIC))
        self.assertNotIn(b"log line", blob)       # the cloud only ever held ciphertext


class ProfileBundleTests(unittest.TestCase):
    """A login moves whole: record, proxy password, cookies, files -- minus what the OS binds."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        src = self.tmp / "src_profile"
        (src / "Default" / "Local Storage").mkdir(parents=True)
        (src / "Default" / "Local Storage" / "000003.log").write_text("device-id")
        (src / "Default" / "Cookies").write_text("dpapi")
        (src / "Default" / "Cache").mkdir()
        (src / "Default" / "Cache" / "blob").write_text("cache")
        (src / "Local State").write_text("wrapped key")
        (src / "SingletonLock").write_text("")
        self.records = {"shop": {"id": "shop", "user_data_dir": str(src), "install_salt": "s1",
                                 "machine_id": "B1", "store_id": "st",
                                 "proxy": {"host": "1.2.3.4", "port": 1080, "username": "u",
                                           "password_ref": "ecan_browser_proxy/shop"}}}
        self.saved = {}
        reg = SimpleNamespace(
            get_profile=lambda pid: self.records.get(pid),
            get_proxy_password=lambda rec: "pw",
            PRUNABLE_DIRS=("Cache",),
            make_profile=lambda pid: {"user_data_dir": str(self.tmp / f"dest_{pid}"), "install_salt": "s2"},
            save_profile=lambda rec, proxy_password="": self.saved.update(rec=rec, pw=proxy_password),
        )
        browser = SimpleNamespace(profile_status=lambda pid: {"running": False})
        for p in (mock.patch.object(payloads, "_registry", return_value=reg),
                  mock.patch.object(payloads, "_browser", return_value=browser),
                  mock.patch.object(payloads, "_read_cookies_and_close",
                                    return_value=[{"name": "sid", "value": "v", "domain": ".x.com"}])):
            p.start()
            self.addCleanup(p.stop)

    def test_pack_and_install(self):
        bundle = str(self.tmp / "b.zip")
        info = payloads.build_profile("shop", bundle)
        self.assertEqual(info["cookies"], 1)
        with zipfile.ZipFile(bundle) as zf:
            names = zf.namelist()
            manifest = json.loads(zf.read("manifest.json"))
        self.assertIn("files/Default/Local Storage/000003.log", names)
        for gone in ("files/Default/Cookies", "files/Local State", "files/SingletonLock",
                     "files/Default/Cache/blob"):
            self.assertNotIn(gone, names)
        self.assertNotIn("user_data_dir", manifest["profile"])
        self.assertEqual(manifest["proxy_password"], "pw")

        out = payloads.install_profile(bundle, machine_id="B2", store_id="st")
        self.assertEqual(out["profile_id"], "shop")
        dest = self.tmp / "dest_shop"
        self.assertEqual((dest / "Default" / "Local Storage" / "000003.log").read_text(), "device-id")
        pending = json.loads((dest / ".ecan_pending_cookies.json").read_text())
        self.assertEqual(pending[0]["name"], "sid")
        rec = self.saved["rec"]
        self.assertEqual(rec["user_data_dir"], str(dest))
        self.assertEqual(rec["machine_id"], "B2")
        self.assertNotIn("password_ref", rec["proxy"], "the source's keyring entry means nothing here")
        self.assertEqual(self.saved["pw"], "pw", "the password goes into THIS machine's keyring")

    def test_a_hostile_bundle_cannot_write_outside_the_profile(self):
        bundle = str(self.tmp / "evil.zip")
        with zipfile.ZipFile(bundle, "w") as zf:
            zf.writestr("manifest.json", json.dumps({"version": 1, "profile": {"id": "shop"}}))
            zf.writestr("cookies.json", "[]")
            zf.writestr("files/../../escaped.txt", "x")
        payloads.install_profile(bundle)
        self.assertFalse((self.tmp / "escaped.txt").exists())


class MoveRulesTests(unittest.TestCase):
    def test_a_move_needs_confirmation(self):
        with self.assertRaises(transfers.TransferError):
            transfers.request_store_move(None, "st", "B2", confirmed=False)

    def test_the_handler_refuses_without_confirmation(self):
        from gui.ipc.w2p_handlers import fleet_handler
        req = SimpleNamespace(id="1", method="fleet.move_store")
        with mock.patch.object(fleet_handler, "create_error_response",
                               side_effect=lambda r, code, msg: code) as err:
            self.assertEqual(fleet_handler.handle_move_store(req, {"store_id": "st", "vehicle_id": "B2"}),
                             "CONFIRMATION_REQUIRED")

    def test_placement_waits_for_an_incoming_login(self):
        import agent.ec_agents.store_placement as sp
        agent = SimpleNamespace(mainwin=None)
        with mock.patch.object(sp, "store_ids_of_agent", return_value=["st"]), \
             mock.patch("agent.ec_agents.vehicle_affinity.resolve_local_vehicle_id", return_value="B2"), \
             mock.patch.object(transfers, "incoming_login_for", return_value="tid"):
            verdict, why = sp.placement_for_agent(agent)
        self.assertEqual(verdict, sp.SKIP)
        self.assertIn("waiting for its login", why)

    def test_a_moved_away_login_refuses_to_launch(self):
        from agent.ec_skills.browser_use_extension.fingerprint import fingerprint_browser as fb
        with mock.patch.object(fb.registry, "get_profile",
                               return_value={"id": "shop", "moved_to": "B2", "user_data_dir": "x"}):
            with self.assertRaisesRegex(RuntimeError, "moved to machine B2"):
                fb.launch_profile("shop")


if __name__ == "__main__":
    unittest.main()
