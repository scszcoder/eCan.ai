"""Phase E — the runner bridge becomes a registry keyed by site.

``_RUNNER_BRIDGE`` was one process-global, last-write-wins. Load two live-chat
bundles and the later import won: the other platform's dispatch ran through the
wrong bridge — wrong DOM driver, wrong selectors, wrong send path — silently.
That is what pinned the deployment model at one platform per process.

Changing the ~100 call sites was never an option, so what changed is what
``runner_bridge()`` resolves against. The property these tests exist to protect
is that **a single-bundle process behaves exactly as the old global did**, in
every path, including the ones that do not look like the happy path: that is
what makes this shippable before a second bundle exists.

The second property is that ambiguity fails loudly. A missing bridge already
has a defined meaning at every call site (fall back to generic behaviour), so
returning ``None`` is safe; driving 淘宝 with 飞鸽's selectors is not.
"""

import threading
import unittest

from agent.ec_skills import live_chat_dispatch as lcd


class _Bridge:
    def __init__(self, site):
        self.site_plugin_name = site

    def __repr__(self):
        return f"<Bridge {self.site_plugin_name}>"


class _Registry:
    """Install a known set of bridges, and always restore what was there."""

    def __init__(self, *sites):
        self.sites = sites

    def __enter__(self):
        self.saved = dict(lcd._BRIDGES)
        lcd._BRIDGES.clear()
        self.bridges = {}
        for s in self.sites:
            b = _Bridge(s)
            self.bridges[s] = b
            lcd.register_runner_bridge(b)
        return self.bridges

    def __exit__(self, *exc):
        lcd._BRIDGES.clear()
        lcd._BRIDGES.update(self.saved)
        return False


class _ActiveSite:
    def __init__(self, site):
        self.site = site

    def __enter__(self):
        self.token = lcd.set_active_site(self.site)

    def __exit__(self, *exc):
        lcd.reset_active_site(self.token)
        return False


class SingleBundleIsUnchangedTests(unittest.TestCase):
    """Every path must return the one bridge, as the old global did."""

    def test_no_active_site(self):
        with _Registry("feige_chat") as b:
            with _ActiveSite(None):
                self.assertIs(lcd.runner_bridge(), b["feige_chat"])

    def test_matching_active_site(self):
        with _Registry("feige_chat") as b:
            with _ActiveSite("feige_chat"):
                self.assertIs(lcd.runner_bridge(), b["feige_chat"])

    def test_active_site_naming_a_bundle_with_no_bridge(self):
        # A node can declare an ordinary hook bundle that registers no runner
        # bridge. There is still exactly one possible answer, and the old
        # global returned it -- so this must too, or the change is a
        # regression for nodes that mix bundles.
        with _Registry("feige_chat") as b:
            with _ActiveSite("some_other_bundle"):
                self.assertIs(lcd.runner_bridge(), b["feige_chat"])

    def test_from_a_raw_thread_where_contextvars_do_not_reach(self):
        # The placeholder sweeper and the dedicated CDP loop run off-loop and
        # see no ContextVar. The sole-bridge fallback is what keeps them
        # working, and is why it stays until a second bundle ships.
        with _Registry("feige_chat") as b:
            seen = []
            with _ActiveSite("feige_chat"):
                t = threading.Thread(target=lambda: seen.append(lcd.runner_bridge()))
                t.start()
                t.join()
            self.assertIs(seen[0], b["feige_chat"])


class NoBundleTests(unittest.TestCase):
    def test_empty_registry_resolves_to_none(self):
        with _Registry():
            self.assertIsNone(lcd.runner_bridge())

    def test_empty_registry_with_an_active_site(self):
        with _Registry():
            with _ActiveSite("feige_chat"):
                self.assertIsNone(lcd.runner_bridge())


class MultiBundleTests(unittest.TestCase):
    """The case the registry exists for."""

    def test_active_site_selects_its_own_bridge(self):
        with _Registry("feige_chat", "tmall_chat") as b:
            with _ActiveSite("tmall_chat"):
                self.assertIs(lcd.runner_bridge(), b["tmall_chat"])
            with _ActiveSite("feige_chat"):
                self.assertIs(lcd.runner_bridge(), b["feige_chat"])

    def test_no_active_site_refuses_to_guess(self):
        # The old behaviour was "whichever imported last", which is how one
        # platform silently drove another.
        with _Registry("feige_chat", "tmall_chat"):
            with _ActiveSite(None):
                self.assertIsNone(lcd.runner_bridge())

    def test_unknown_active_site_refuses_to_guess(self):
        with _Registry("feige_chat", "tmall_chat"):
            with _ActiveSite("shopee_chat"):
                self.assertIsNone(lcd.runner_bridge())


class ExplicitSiteTests(unittest.TestCase):
    def test_explicit_wins_over_the_active_site(self):
        with _Registry("feige_chat", "tmall_chat") as b:
            with _ActiveSite("feige_chat"):
                self.assertIs(lcd.runner_bridge("tmall_chat"), b["tmall_chat"])

    def test_explicit_unknown_site_is_not_substituted(self):
        # A caller naming a site means it knows which one it wants; handing it
        # a different platform's bridge is worse than handing it nothing --
        # even when there is only one to hand over.
        with _Registry("feige_chat"):
            self.assertIsNone(lcd.runner_bridge("tmall_chat"))


class RegistrationTests(unittest.TestCase):
    def test_a_bridge_names_itself_from_site_plugin_name(self):
        # The bundle already publishes this, so no call site changes.
        with _Registry("feige_chat"):
            self.assertEqual(lcd.bridge_sites(), ["feige_chat"])

    def test_an_explicit_site_overrides_the_declared_one(self):
        with _Registry():
            lcd.register_runner_bridge(_Bridge("feige_chat"), site="custom")
            self.assertEqual(lcd.bridge_sites(), ["custom"])

    def test_an_unnamed_bridge_still_registers(self):
        # One bundle is the norm; an unnamed one must not break, it just
        # cannot be told apart from another unnamed one.
        class _Anon:
            pass

        with _Registry():
            lcd.register_runner_bridge(_Anon())
            self.assertIsNotNone(lcd.runner_bridge())

    def test_re_registering_a_site_replaces_it(self):
        with _Registry():
            first, second = _Bridge("feige_chat"), _Bridge("feige_chat")
            lcd.register_runner_bridge(first)
            lcd.register_runner_bridge(second)
            self.assertIs(lcd.runner_bridge(), second)
            self.assertEqual(len(lcd.bridge_sites()), 1)

    def test_clear_one_site_leaves_the_others(self):
        with _Registry("feige_chat", "tmall_chat") as b:
            lcd.clear_runner_bridge("tmall_chat")
            self.assertEqual(lcd.bridge_sites(), ["feige_chat"])
            self.assertIs(lcd.runner_bridge(), b["feige_chat"])

    def test_clear_all(self):
        with _Registry("feige_chat", "tmall_chat"):
            lcd.clear_runner_bridge()
            self.assertEqual(lcd.bridge_sites(), [])


class ActiveSiteScopeTests(unittest.TestCase):
    def test_reset_restores_the_previous_site(self):
        with _Registry("feige_chat", "tmall_chat") as b:
            with _ActiveSite("feige_chat"):
                with _ActiveSite("tmall_chat"):
                    self.assertIs(lcd.runner_bridge(), b["tmall_chat"])
                self.assertIs(lcd.runner_bridge(), b["feige_chat"])

    def test_blank_site_reads_as_none(self):
        with _ActiveSite("   "):
            self.assertIsNone(lcd.active_site())


class NodeEntryWiringTests(unittest.TestCase):
    """The node must publish its site, or the registry has nothing to key on."""

    def _src(self):
        from pathlib import Path
        return Path("agent/ec_skills/browser_node/runner.py").read_text(encoding="utf-8")

    def test_node_entry_sets_the_active_site(self):
        src = self._src()
        self.assertIn("from agent.ec_skills.live_chat_dispatch import set_active_site", src)
        self.assertIn("set_active_site(_site)", src)

    def test_site_is_taken_from_the_bundle_spec_path(self):
        # A bundle's name is the `path` of its hookBundles entry, which is the
        # same string it publishes as site_plugin_name.
        src = self._src()
        self.assertIn('_spec.get("path")', src)

    def test_platform_files_name_no_site(self):
        self.assertNotIn("feige", self._src().lower())
        from pathlib import Path
        lcd_src = Path("agent/ec_skills/live_chat_dispatch.py").read_text(encoding="utf-8")
        self.assertNotIn("feige", lcd_src.lower())


if __name__ == "__main__":
    unittest.main()
