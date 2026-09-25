"""Phase D — profile descriptors sync, profile contents never do.

Remote deployment can provision everything except one thing: a machine cannot
sign in as the seller. So the model is that the cloud learns a profile *should*
exist on machine M and what state it is in, while the session itself — cookies,
localStorage, the proxy password, the directory holding them — stays put.
Copying a profile between machines would also give one seller account two
device fingerprints and two egress IPs, which is exactly what platform
risk-control looks for.

The design said that in prose. These tests make it mechanical: the descriptor
is an allowlist, so a field added to a profile record later is private until
someone opts it in, and the leak test fails on the VALUES as well as the keys.

Login state exists for the same reason. ``profile_status`` answers "is the
browser up", which says nothing about whether the session inside it still
works — and for eight stores across three machines, "store 6 has been silently
offline since Tuesday" is the failure that actually costs money.
"""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from agent.ec_skills.browser_use_extension.fingerprint import profile_registry as reg


class _TempRegistry:
    """Point the registry at a scratch file for the duration of a test.

    The registry writes real state, so a test that used the ambient path would
    edit the developer's actual profiles.
    """

    def __enter__(self):
        self.tmp = tempfile.mkdtemp()
        path = os.path.join(self.tmp, "browser_profiles.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"profiles": []}, fh)
        self._patch = patch.object(reg, "_registry_path", lambda: __import__(
            "pathlib").Path(path))
        self._patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()
        return False


def _profile(**over):
    p = reg.make_profile(
        profile_id=over.pop("profile_id", "store_a"),
        label=over.pop("label", "陆地飞鱼"),
        store_id=over.pop("store_id", "lands_flying_fish"),
        machine_id=over.pop("machine_id", "7fd4a55d-4aad-4238-9c11-0e6c3a8b9412"),
        browser_path=over.pop("browser_path", r"C:\Chromium\chrome.exe"),
        browser_version=over.pop("browser_version", "126.0.6478.127"),
        proxy=over.pop("proxy", None),
    )
    p.update(over)
    return p


class MakeProfileTests(unittest.TestCase):
    def test_carries_store_and_machine(self):
        p = _profile()
        self.assertEqual(p["store_id"], "lands_flying_fish")
        self.assertEqual(p["machine_id"], "7fd4a55d-4aad-4238-9c11-0e6c3a8b9412")

    def test_a_new_profile_has_never_been_signed_in(self):
        # Saying so explicitly is what lets provisioning hand the operator a
        # precise "log in to these" list instead of failing at the first
        # customer message.
        self.assertEqual(_profile()["login_state"], reg.LOGIN_NEEDED)

    def test_store_and_machine_are_optional(self):
        p = reg.make_profile(profile_id="x")
        self.assertEqual(p["store_id"], "")
        self.assertEqual(p["machine_id"], "")


class DescriptorLeakTests(unittest.TestCase):
    """What must never appear in something that may leave the machine."""

    FORBIDDEN_KEYS = (
        "user_data_dir",   # where the session lives, and the machine's layout
        "install_salt",
        "imported_from",
        "proxy",           # only "is there one" may travel, never which
        "browser_path",
    )

    def test_descriptor_omits_every_forbidden_key(self):
        d = reg.descriptor(_profile(proxy={"scheme": "socks5", "host": "1.2.3.4",
                                           "port": 1080, "username": "u"}))
        for key in self.FORBIDDEN_KEYS:
            self.assertNotIn(key, d, f"{key} must not be in a syncable descriptor")

    def test_descriptor_omits_forbidden_VALUES_too(self):
        # A key rename must not turn into a leak: check the serialized form for
        # the sensitive values themselves.
        p = _profile(proxy={"scheme": "socks5", "host": "10.9.8.7",
                            "port": 1080, "username": "seller_u",
                            "password_ref": "keyring://x"})
        blob = json.dumps(reg.descriptor(p), ensure_ascii=False)
        for secret in (p["user_data_dir"], p["install_salt"], "10.9.8.7",
                       "seller_u", "keyring://x", r"C:\Chromium\chrome.exe"):
            self.assertNotIn(str(secret), blob, f"{secret!r} leaked into the descriptor")

    def test_descriptor_keeps_what_the_cloud_legitimately_needs(self):
        d = reg.descriptor(_profile())
        self.assertEqual(d["id"], "store_a")
        self.assertEqual(d["store_id"], "lands_flying_fish")
        self.assertEqual(d["machine_id"], "7fd4a55d-4aad-4238-9c11-0e6c3a8b9412")
        # Which Chromium wrote it matters: a profile written by one build is
        # not always safe to open with another.
        self.assertEqual(d["browser"]["version"], "126.0.6478.127")

    def test_proxy_reduces_to_a_boolean(self):
        with_proxy = reg.descriptor(_profile(proxy={"host": "1.2.3.4", "port": 1080}))
        without = reg.descriptor(_profile(proxy=None))
        self.assertIs(with_proxy["has_proxy"], True)
        self.assertIs(without["has_proxy"], False)

    def test_a_new_private_field_is_excluded_by_default(self):
        # The allowlist is the point: this is what stops a future "sync
        # everything" change from being a silent security decision.
        p = _profile()
        p["some_future_secret"] = "cookie-jar-contents"
        d = reg.descriptor(p)
        self.assertNotIn("some_future_secret", d)
        self.assertNotIn("cookie-jar-contents", json.dumps(d))


class LoginStateTests(unittest.TestCase):
    def test_round_trips_through_the_registry(self):
        with _TempRegistry():
            reg.save_profile(_profile())
            self.assertTrue(reg.set_login_state("store_a", reg.LOGIN_OK, "run reached the site"))
            got = reg.login_state("store_a")
        self.assertEqual(got["state"], reg.LOGIN_OK)
        self.assertEqual(got["detail"], "run reached the site")
        self.assertGreater(got["checked_at"], 0)

    def test_unknown_profile_is_refused_not_invented(self):
        with _TempRegistry():
            self.assertFalse(reg.set_login_state("nope", reg.LOGIN_OK))
            self.assertEqual(reg.login_state("nope")["state"], reg.LOGIN_UNKNOWN)

    def test_unknown_state_is_refused(self):
        with _TempRegistry():
            reg.save_profile(_profile())
            self.assertFalse(reg.set_login_state("store_a", "probably_fine"))
            # And the stored state is untouched.
            self.assertEqual(reg.login_state("store_a")["state"], reg.LOGIN_NEEDED)

    def test_setting_state_preserves_the_rest_of_the_record(self):
        # The session lives at user_data_dir; losing it would lose the login.
        with _TempRegistry():
            original = _profile()
            reg.save_profile(original)
            reg.set_login_state("store_a", reg.LOGIN_OK)
            after = reg.get_profile("store_a")
        self.assertEqual(after["user_data_dir"], original["user_data_dir"])
        self.assertEqual(after["install_salt"], original["install_salt"])
        self.assertEqual(after["store_id"], original["store_id"])

    def test_detail_is_bounded(self):
        with _TempRegistry():
            reg.save_profile(_profile())
            reg.set_login_state("store_a", reg.LOGIN_NEEDED, "x" * 5000)
            self.assertLessEqual(len(reg.login_state("store_a")["detail"]), 500)


class ProvisioningTodoListTests(unittest.TestCase):
    def test_lists_only_what_needs_a_human(self):
        with _TempRegistry():
            reg.save_profile(_profile(profile_id="store_a", store_id="a"))
            reg.save_profile(_profile(profile_id="store_b", store_id="b"))
            reg.save_profile(_profile(profile_id="store_c", store_id="c"))
            reg.set_login_state("store_b", reg.LOGIN_OK)
            pending = reg.profiles_needing_login()
        self.assertEqual({p["id"] for p in pending}, {"store_a", "store_c"})

    def test_entries_name_the_store_and_machine(self):
        # "Profile 7 needs login" is useless across eight stores.
        with _TempRegistry():
            reg.save_profile(_profile())
            pending = reg.profiles_needing_login()
        self.assertEqual(pending[0]["store_id"], "lands_flying_fish")
        self.assertEqual(pending[0]["machine_id"], "7fd4a55d-4aad-4238-9c11-0e6c3a8b9412")

    def test_empty_when_everything_is_signed_in(self):
        with _TempRegistry():
            reg.save_profile(_profile())
            reg.set_login_state("store_a", reg.LOGIN_OK)
            self.assertEqual(reg.profiles_needing_login(), [])


class MachineIdentityTests(unittest.TestCase):
    """Identity must not be borrowed from the network."""

    def test_machine_id_is_stable_across_calls(self):
        from agent.a2a.discovery.machine_id import get_machine_id
        with tempfile.TemporaryDirectory() as home:
            first = get_machine_id(home)
            second = get_machine_id(home)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 36)

    def test_machine_id_is_not_derived_from_host_or_ip(self):
        # The DHCP incident: an agent endpoint frozen at its creation-time LAN
        # IP stopped resolving when the router handed out a new lease.
        import socket
        from agent.a2a.discovery.machine_id import get_machine_id
        with tempfile.TemporaryDirectory() as home:
            mid = get_machine_id(home)
        self.assertNotIn(socket.gethostname().lower(), mid.lower())
        self.assertNotRegex(mid, r"\d+\.\d+\.\d+\.\d+")


class MachineCapabilityTests(unittest.TestCase):
    """The input a placement decision needs: what can this host run?

    A front desk owns a real browser — CDP, typing lock, tab pool — so it needs
    a desktop session. Q&A agents work over A2A and never touch the DOM, so a
    display-less Linux box is a fine Q&A host and a useless front-desk one.
    Guessing from ``platform`` alone gets exactly that case wrong.
    """

    def _caps(self, system, env=None):
        from agent.ec_agents import vehicle_affinity as va
        clean = {k: None for k in ("DISPLAY", "WAYLAND_DISPLAY", "ECAN_HEADLESS")}
        clean.update(env or {})
        keep = {k: v for k, v in clean.items() if v is not None}
        drop = [k for k, v in clean.items() if v is None]
        saved = {k: os.environ.pop(k, None) for k in drop}
        try:
            with patch.object(va._platform, "system", lambda: system), patch.dict(
                os.environ, keep, clear=False
            ):
                return va.machine_capabilities()
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    def test_every_machine_can_run_qa(self):
        from agent.ec_agents.vehicle_affinity import CAP_QA
        for system in ("Windows", "Darwin", "Linux"):
            self.assertIn(CAP_QA, self._caps(system), system)

    def test_desktop_os_can_host_a_front_desk(self):
        from agent.ec_agents.vehicle_affinity import CAP_FRONT_DESK
        self.assertIn(CAP_FRONT_DESK, self._caps("Windows"))
        self.assertIn(CAP_FRONT_DESK, self._caps("Darwin"))

    def test_headless_linux_cannot_host_a_front_desk(self):
        # The case the whole check exists for.
        from agent.ec_agents.vehicle_affinity import CAP_FRONT_DESK, CAP_QA
        caps = self._caps("Linux")
        self.assertNotIn(CAP_FRONT_DESK, caps)
        self.assertIn(CAP_QA, caps)

    def test_linux_with_a_display_can(self):
        from agent.ec_agents.vehicle_affinity import CAP_FRONT_DESK
        self.assertIn(CAP_FRONT_DESK, self._caps("Linux", {"DISPLAY": ":0"}))
        self.assertIn(CAP_FRONT_DESK, self._caps("Linux", {"WAYLAND_DISPLAY": "wayland-0"}))

    def test_explicit_headless_overrides_a_desktop_os(self):
        from agent.ec_agents.vehicle_affinity import CAP_FRONT_DESK
        self.assertNotIn(CAP_FRONT_DESK, self._caps("Windows", {"ECAN_HEADLESS": "1"}))

    def test_registration_reports_capabilities(self):
        # The vehicle row already had a capabilities slot; nothing filled it,
        # so a scheduler had only `platform` to guess from.
        from pathlib import Path
        src = Path("agent/ec_agents/vehicle_affinity.py").read_text(encoding="utf-8")
        self.assertIn('"capabilities": caps', src)
        # Refreshed on an existing row too: a machine can lose its session.
        self.assertEqual(src.count('"capabilities": caps'), 2)


class DtoTests(unittest.TestCase):
    def test_login_state_reaches_the_front_end(self):
        from gui.ipc.w2p_handlers.browser_profile_handler import _to_dto
        p = _profile()
        p["login_state"] = reg.LOGIN_NEEDED
        dto = _to_dto(p, status={"running": True})
        self.assertEqual(dto["login"]["state"], reg.LOGIN_NEEDED)
        self.assertEqual(dto["store_id"], "lands_flying_fish")
        # Browser up and session valid are different questions.
        self.assertTrue(dto["status"]["running"])

    def test_dto_still_hides_the_password(self):
        from gui.ipc.w2p_handlers.browser_profile_handler import _to_dto
        p = _profile(proxy={"host": "1.2.3.4", "port": 1080, "password_ref": "k"})
        blob = json.dumps(_to_dto(p), ensure_ascii=False)
        self.assertNotIn("password_ref", blob)


if __name__ == "__main__":
    unittest.main()
