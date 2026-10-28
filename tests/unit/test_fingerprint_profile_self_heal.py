"""A corrupt fingerprint profile must self-heal instead of failing the front desk.

Field case (2026-10-14): chrome.exe was force-killed repeatedly during an install
fight; the Douyin profile then crashed Chromium on every open (flash-and-die, exit
0x80000003, or "ready" then dead within a second). The launcher now escalates:
retry as-is → clear cache (keep login) → reset (login lost, old copy kept).
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

    def test_reset_moves_corrupt_aside_and_starts_fresh(self):
        with TemporaryDirectory() as d:
            udd = Path(d) / "profile"
            (udd / "Default").mkdir(parents=True)
            (udd / "Default" / "Cookies").write_bytes(b"old")

            note = fb._reset_profile_dir(udd)

            self.assertTrue(udd.exists(), "a fresh empty profile dir is recreated")
            self.assertEqual(list(udd.iterdir()), [], "fresh profile starts empty")
            backups = list(udd.parent.glob("profile.corrupt-*"))
            self.assertEqual(len(backups), 1, "the corrupt copy is kept, not deleted")
            self.assertTrue((backups[0] / "Default" / "Cookies").exists())
            self.assertIn("re-login is needed", note)


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
            "_reset_profile_dir": fb._reset_profile_dir,
            "resolve_browser_path": fb.resolve_browser_path,
            "_wait_profile_released": fb._wait_profile_released,
        }
        fb._wait_profile_released = lambda udd: self.calls.append("wait") or True
        fb._spawn_once = fake_spawn
        fb._clear_profile_cache = lambda udd: self.calls.append("clear") or "cleared"
        fb._reset_profile_dir = lambda udd: self.calls.append("reset") or "reset"
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
        self.assertNotIn("reset", self.calls, "must not reset when a cache clear fixed it")

    def test_reset_is_last_resort(self):
        self._patch([fb._ProfileUnstable("a"), fb._ProfileUnstable("b"), "browser"])
        self.assertEqual(self._run(), "browser")
        self.assertEqual(self.calls, ["spawn", "clear", "spawn", "reset", "spawn"])

    def test_gives_up_after_reset_still_crashes(self):
        self._patch([fb._ProfileUnstable("a"), fb._ProfileUnstable("b"), fb._ProfileUnstable("c")])
        with self.assertRaises(RuntimeError) as ctx:
            self._run()
        self.assertNotIsInstance(ctx.exception, fb._ProfileUnstable)
        self.assertIn("antivirus", str(ctx.exception).lower())
        self.assertEqual(self.calls, ["spawn", "clear", "spawn", "reset", "spawn"])

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


class ResetNeverDeletesTests(unittest.TestCase):
    def test_a_profile_that_will_not_move_is_left_untouched(self):
        with TemporaryDirectory() as d:
            udd = Path(d) / "profile"
            (udd / "Default").mkdir(parents=True)
            cookies = udd / "Default" / "Cookies"
            cookies.write_bytes(b"session")
            orig = Path.rename

            def locked(self, target):
                raise PermissionError("in use by another process")
            Path.rename = locked
            try:
                note = fb._reset_profile_dir(udd)
            finally:
                Path.rename = orig
            self.assertTrue(cookies.exists(), "the login must survive a reset that cannot move the folder")
            self.assertIn("left it untouched", note)


if __name__ == "__main__":
    unittest.main()
