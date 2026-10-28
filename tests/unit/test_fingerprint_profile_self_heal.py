"""A corrupt fingerprint profile must self-heal instead of failing the front desk.

Field case (2026-10-14): chrome.exe was force-killed repeatedly during an install
fight; the Douyin profile then crashed Chromium on every open (flash-and-die, exit
0x80000003, or "ready" then dead within a second). The launcher now escalates:
retry as-is → clear caches (keep login) → fail, leaving the profile untouched.
It never resets a profile on its own: on KEN 2026-10-29 an automatic reset
logged a 抖店 store out.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent.ec_skills.browser_use_extension.fingerprint import fingerprint_browser as fb


class RepairHelperTests(unittest.TestCase):
    def test_clear_cache_keeps_the_login(self):
        with TemporaryDirectory() as d:
            udd = Path(d)
            (udd / "Default" / "GPUCache").mkdir(parents=True)
            (udd / "Default" / "GPUCache" / "x").write_bytes(b"junk")
            (udd / "GrShaderCache").mkdir()
            (udd / "SingletonLock").write_text("lock")
            # the login-bearing files that must survive
            (udd / "Default" / "Network").mkdir(parents=True)
            cookies = udd / "Default" / "Network" / "Cookies"
            cookies.write_bytes(b"session")

            note = fb._clear_profile_cache(udd)

            self.assertFalse((udd / "Default" / "GPUCache").exists())
            self.assertFalse((udd / "GrShaderCache").exists())
            self.assertFalse((udd / "SingletonLock").exists())
            self.assertTrue(cookies.exists(), "cache clear must not touch the login")
            self.assertIn("login kept", note)

    def test_cache_clear_keeps_session_data(self):
        with TemporaryDirectory() as d:
            udd = Path(d)
            (udd / "Default" / "Session Storage").mkdir(parents=True)
            (udd / "Default" / "Session Storage" / "000003.log").write_bytes(b"token")
            fb._clear_profile_cache(udd)
            self.assertTrue((udd / "Default" / "Session Storage" / "000003.log").exists())

    def test_a_profile_in_use_is_not_touched(self):
        with TemporaryDirectory() as d:
            udd = Path(d)
            (udd / "GrShaderCache").mkdir()
            (udd / "SingletonLock").write_text("lock")
            orig = fb._profile_processes
            fb._profile_processes = lambda _udd: ["chrome.exe"]
            try:
                note = fb._clear_profile_cache(udd)
            finally:
                fb._profile_processes = orig
            self.assertTrue((udd / "SingletonLock").exists() and (udd / "GrShaderCache").exists())
            self.assertIn("left alone", note)


class SelfHealLadderTests(unittest.TestCase):
    def _patch(self, spawn_behaviors):
        """Patch _spawn_once to consume one behavior per call; spy on repairs."""
        self.calls = []
        it = iter(spawn_behaviors)

        def fake_spawn(*a, **k):
            self.calls.append("spawn")
            outcome = next(it)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        self.orig = {
            "_spawn_once": fb._spawn_once,
            "_clear_profile_cache": fb._clear_profile_cache,
            "resolve_browser_path": fb.resolve_browser_path,
            "_wait_profile_released": fb._wait_profile_released,
        }
        fb._wait_profile_released = lambda udd: self.calls.append("wait") or True
        fb._spawn_once = fake_spawn
        fb._clear_profile_cache = lambda udd: self.calls.append("clear") or "cleared"
        fb.resolve_browser_path = lambda profile: "chrome.exe"

    def tearDown(self):
        for name, val in getattr(self, "orig", {}).items():
            setattr(fb, name, val)

    def _run(self):
        return fb._launch_with_self_heal(
            {}, "p", Path("."), 0, False, "about:blank", False, "about:blank", 1.0)

    def test_first_try_succeeds_no_repair(self):
        self._patch(["browser"])
        self.assertEqual(self._run(), "browser")
        self.assertEqual(self.calls, ["spawn"])

    def test_cache_clear_then_success_keeps_login(self):
        self._patch([fb._ProfileUnstable("died"), "browser"])
        self.assertEqual(self._run(), "browser")
        self.assertEqual(self.calls, ["spawn", "clear", "spawn"])

    def test_still_crashing_fails_and_never_resets(self):
        self._patch([fb._ProfileUnstable("a"), fb._ProfileUnstable("b")])
        with self.assertRaises(RuntimeError) as ctx:
            self._run()
        self.assertNotIsInstance(ctx.exception, fb._ProfileUnstable)
        self.assertIn("left untouched", str(ctx.exception))
        self.assertEqual(self.calls, ["spawn", "clear", "spawn"])
        self.assertFalse(hasattr(fb, "_reset_profile_dir"), "no automatic reset exists")

    def test_non_crash_fault_never_repairs(self):
        # A port clash / "someone else owns this port" is a plain RuntimeError and
        # must propagate on the first attempt without wiping anything.
        self._patch([RuntimeError("port served by a different browser")])
        with self.assertRaises(RuntimeError):
            self._run()
        self.assertEqual(self.calls, ["spawn"], "no repair on a non-crash fault")

    def test_a_busy_profile_is_waited_for_never_repaired(self):
        # KEN 2026-10-29: Chromium handed the launch to the old instance (exit 0);
        # read as a crash, the "repair" deleted the 抖店 login.
        self._patch([fb._ProfileBusy("handed over"), "browser"])
        self.assertEqual(self._run(), "browser")
        self.assertEqual(self.calls, ["spawn", "wait", "spawn"])

    def test_a_profile_that_stays_busy_fails_without_touching_it(self):
        self._patch([fb._ProfileBusy("a"), fb._ProfileBusy("b"), fb._ProfileBusy("c")])
        with self.assertRaises(RuntimeError) as ctx:
            self._run()
        self.assertIn("nothing in the profile was changed", str(ctx.exception))
        self.assertNotIn("clear", self.calls)
        self.assertNotIn("reset", self.calls)


if __name__ == "__main__":
    unittest.main()
