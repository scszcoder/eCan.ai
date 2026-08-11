"""Tests for the Tmall/Qianniu (千牛) external hook bundle (Phase 1 scaffold).

Covers:
  * manifest-driven hook loading (hook.yaml → TmallQuickReplyHook / guard)
  * the runner-bridge surface (identity strings, partial-surface contract)
  * dom.py URL-marker tab resolution
  * typing_lock acquire/release/TTL-steal semantics
  * tunables resolution precedence
  * system_message_filter markers
  * the active-site gating in BOTH site bundles' __init__ (source scan —
    registration itself is process-global, validated by the smoke script)
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.ec_skills.browser_use_extension.hook_api import Decision, Stage
from agent.ec_skills.browser_use_extension.hook_loader import (
    HookBundleSpec,
    load_bundle,
)

_BUNDLE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "agent", "ec_skills", "browser_use_extension", "hooks", "external", "tmall_chat",
)
_FEIGE_INIT = os.path.join(os.path.dirname(_BUNDLE_DIR), "feige_chat", "__init__.py")


# ---------------------------------------------------------------------------
# Manifest bundle load
# ---------------------------------------------------------------------------
class TestTmallBundleLoad(unittest.TestCase):
    def test_bundle_loads_via_relative_name(self):
        hooks = load_bundle(HookBundleSpec(path="tmall_chat"))
        names = [h.manifest.name for h in hooks]
        self.assertIn("tmall_quick_reply", names)
        self.assertIn("tmall_crosstalk_guard_ext", names)

    def test_manifest_declares_correct_stages(self):
        hooks = load_bundle(HookBundleSpec(path="tmall_chat"))
        by_name = {h.manifest.name: h for h in hooks}
        self.assertEqual(
            by_name["tmall_quick_reply"].manifest.stage,
            Stage.ON_EVENT_NORMALIZED,
        )
        self.assertEqual(
            by_name["tmall_crosstalk_guard_ext"].manifest.stage,
            Stage.ON_PRE_ACTION,
        )

    def test_all_tiers_are_external(self):
        hooks = load_bundle(HookBundleSpec(path="tmall_chat"))
        for h in hooks:
            self.assertGreaterEqual(h.manifest.tier, 1)

    def test_quick_reply_permissions_declare_send_tool(self):
        hooks = load_bundle(HookBundleSpec(path="tmall_chat"))
        quick = next(h for h in hooks if h.manifest.name == "tmall_quick_reply")
        self.assertIn("tmall_send_message", quick.manifest.permissions.tools)

    def test_guard_covers_tmall_send(self):
        hooks = load_bundle(HookBundleSpec(path="tmall_chat"))
        guard = next(
            h for h in hooks if h.manifest.name == "tmall_crosstalk_guard_ext"
        )
        self.assertIn("tmall_send_message", guard._guarded)


class TestTmallQuickReplyRun(unittest.IsolatedAsyncioTestCase):
    def _make_ctx(self):
        store: dict = {}
        state = SimpleNamespace(
            get=lambda k, default=None: store.get(k, default),
            set=lambda k, v: store.__setitem__(k, v),
            delete=lambda k: store.pop(k, None),
            keys=lambda: list(store.keys()),
        )
        return SimpleNamespace(
            manifest=None, trace_id="t", span_id="s", step=0,
            site_adapter={}, tools=None, state=state, logger=None,
            config={}, browser_session=None, emit_span=lambda *a, **k: None,
        )

    async def test_exact_match_emits_bypass_with_tmall_send(self):
        hooks = load_bundle(HookBundleSpec(path="tmall_chat"))
        hook = next(h for h in hooks if h.manifest.name == "tmall_quick_reply")
        result = await hook.run(self._make_ctx(), {
            "text": "你好",
            "customer_name": "买家A",
        })
        self.assertEqual(result.decision, Decision.BYPASS)
        action = result.payload[0]
        self.assertEqual(action["name"], "tmall_send_message")
        self.assertEqual(action["args"]["customer_name"], "买家A")
        self.assertTrue(action["args"]["text"].startswith("亲"))

    async def test_unknown_trigger_continues(self):
        hooks = load_bundle(HookBundleSpec(path="tmall_chat"))
        hook = next(h for h in hooks if h.manifest.name == "tmall_quick_reply")
        result = await hook.run(self._make_ctx(), {
            "text": "这款有货吗",
            "customer_name": "买家A",
        })
        self.assertEqual(result.decision, Decision.CONTINUE)


# ---------------------------------------------------------------------------
# Runner bridge surface
# ---------------------------------------------------------------------------
class TestTmallRunnerBridge(unittest.TestCase):
    def _bridge(self):
        from agent.ec_skills.browser_use_extension.hooks.external.tmall_chat.runner_bridge import (
            TmallRunnerBridge,
        )
        return TmallRunnerBridge()

    def test_identity_strings(self):
        b = self._bridge()
        self.assertEqual(b.site_plugin_name, "tmall_chat")
        self.assertEqual(b.tool_name_glob, "tmall_*")
        self.assertEqual(b.trace_label_prefix, "tmall_")
        self.assertEqual(b.open_session_tool_name, "tmall_open_session")
        self.assertEqual(b.send_message_tool_name, "tmall_send_message")
        self.assertEqual(b.list_sessions_tool_name, "tmall_list_sessions")

    def test_site_adapter_preset(self):
        b = self._bridge()
        preset = b.site_adapter_preset
        self.assertEqual(preset["name"], "tmall")
        self.assertIn("sidebar", preset)
        self.assertIn("verify_policy", preset)

    def test_retryable_send_reasons(self):
        b = self._bridge()
        self.assertIn("tool_failed:tmall_send_message", b.retryable_send_reasons)

    def test_classify_send_error(self):
        b = self._bridge()
        self.assertEqual(
            b.classify_send_error("tmall_send_message: tmall_send_failed:input_not_found"),
            "send_failed_input_not_found",
        )
        self.assertIsNone(b.classify_send_error("some other error"))

    def test_partial_surface_missing_attributes_raise(self):
        """Guard-semantics contract: unported capabilities must raise
        AttributeError so platform guards take their no-bundle fallback."""
        b = self._bridge()
        for missing in ("dispatch_state", "placeholder_timer", "hot_path",
                        "ws_session", "pre_dispatch_enrich", "front_desk"):
            with self.assertRaises(AttributeError):
                getattr(b, missing)

    def test_typed_tunables_defaults(self):
        b = self._bridge()
        self.assertEqual(b.typing_concurrency(), 1)
        self.assertAlmostEqual(b.tab_resolve_timeout_s(), 5.0)


# ---------------------------------------------------------------------------
# dom.py — URL markers + tab resolution
# ---------------------------------------------------------------------------
class TestTmallDom(unittest.TestCase):
    def setUp(self):
        os.environ.pop("ECAN_TMALL_IM_URL_MARKERS", None)

    def tearDown(self):
        os.environ.pop("ECAN_TMALL_IM_URL_MARKERS", None)

    def test_default_markers(self):
        from agent.ec_skills.browser_use_extension.hooks.external.tmall_chat import dom
        self.assertTrue(dom.is_tmall_im_url("https://work.taobao.com/im/index"))
        self.assertTrue(dom.is_tmall_im_url("https://myseller.taobao.com/home"))
        self.assertFalse(dom.is_tmall_im_url("https://im.jinritemai.com/pc_seller_v2"))
        self.assertFalse(dom.is_tmall_im_url(""))

    def test_env_override_markers(self):
        from agent.ec_skills.browser_use_extension.hooks.external.tmall_chat import dom
        os.environ["ECAN_TMALL_IM_URL_MARKERS"] = "example.com/im, foo.cn"
        self.assertTrue(dom.is_tmall_im_url("https://example.com/im/chat"))
        self.assertFalse(dom.is_tmall_im_url("https://work.taobao.com/im/index"))

    def test_resolve_picks_shallowest_matching_tab(self):
        from agent.ec_skills.browser_use_extension.hooks.external.tmall_chat import dom

        targets = {
            "t1": SimpleNamespace(target_type="page", url="https://work.taobao.com/im/chat/deep/page"),
            "t2": SimpleNamespace(target_type="page", url="https://work.taobao.com/im"),
            "t3": SimpleNamespace(target_type="page", url="https://example.com/other"),
            "t4": SimpleNamespace(target_type="worker", url="https://work.taobao.com/im"),
        }
        session = SimpleNamespace(
            session_manager=SimpleNamespace(get_all_targets=lambda: targets)
        )
        tid = asyncio.run(dom.resolve_tmall_tab_target_id(session))
        self.assertEqual(tid, "t2")

    def test_resolve_no_match_returns_empty(self):
        from agent.ec_skills.browser_use_extension.hooks.external.tmall_chat import dom
        session = SimpleNamespace(
            session_manager=SimpleNamespace(get_all_targets=lambda: {
                "t1": SimpleNamespace(target_type="page", url="https://example.com"),
            })
        )
        self.assertEqual(asyncio.run(dom.resolve_tmall_tab_target_id(session)), "")


# ---------------------------------------------------------------------------
# typing_lock
# ---------------------------------------------------------------------------
class TestTmallTypingLock(unittest.IsolatedAsyncioTestCase):
    async def test_acquire_release_roundtrip(self):
        from agent.ec_skills.browser_use_extension.hooks.external.tmall_chat import typing_lock
        got = await typing_lock.acquire("owner_a", timeout_s=1.0)
        self.assertTrue(got)
        self.assertEqual(typing_lock.holder(), "owner_a")
        typing_lock.release("owner_a")
        self.assertEqual(typing_lock.holder(), "")

    async def test_second_acquire_times_out_within_ttl(self):
        from agent.ec_skills.browser_use_extension.hooks.external.tmall_chat import typing_lock
        self.assertTrue(await typing_lock.acquire("owner_a", timeout_s=0.5))
        try:
            got = await typing_lock.acquire("owner_b", timeout_s=0.2)
            self.assertFalse(got)
        finally:
            typing_lock.release("owner_a")

    async def test_release_by_non_owner_is_noop(self):
        from agent.ec_skills.browser_use_extension.hooks.external.tmall_chat import typing_lock
        self.assertTrue(await typing_lock.acquire("owner_a", timeout_s=0.5))
        typing_lock.release("owner_b")
        self.assertEqual(typing_lock.holder(), "owner_a")
        typing_lock.release("owner_a")


# ---------------------------------------------------------------------------
# tunables
# ---------------------------------------------------------------------------
class TestTmallTunables(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("ECAN_TMALL_TEST_KNOB", None)

    def test_precedence_node_over_env_over_default(self):
        from agent.ec_skills.browser_use_extension.hooks.external.tmall_chat import tunables
        # default
        self.assertEqual(tunables.resolve_int("TMALL_TEST_KNOB", 7), 7)
        # env wins over default
        os.environ["ECAN_TMALL_TEST_KNOB"] = "8"
        self.assertEqual(tunables.resolve_int("TMALL_TEST_KNOB", 7), 8)
        # node override wins over env
        state = {"metadata": {"browser_auto_overrides": {"TMALL_TEST_KNOB": 9}}}
        self.assertEqual(tunables.resolve_int("TMALL_TEST_KNOB", 7, state), 9)

    def test_resolve_bool_spellings(self):
        from agent.ec_skills.browser_use_extension.hooks.external.tmall_chat import tunables
        os.environ["ECAN_TMALL_TEST_KNOB"] = "true"
        self.assertTrue(tunables.resolve_bool("TMALL_TEST_KNOB", False))
        os.environ["ECAN_TMALL_TEST_KNOB"] = "0"
        self.assertFalse(tunables.resolve_bool("TMALL_TEST_KNOB", True))


# ---------------------------------------------------------------------------
# system_message_filter
# ---------------------------------------------------------------------------
class TestTmallSystemMessageFilter(unittest.TestCase):
    def test_system_rows_filtered(self):
        from agent.ec_skills.browser_use_extension.hooks.external.tmall_chat import (
            system_message_filter as smf,
        )
        self.assertTrue(smf.is_system_message("会话已结束，感谢您的咨询"))
        self.assertTrue(smf.is_system_message("【系统消息】您有新的活动"))
        self.assertTrue(smf.is_system_message("店小蜜为您服务"))

    def test_buyer_messages_pass(self):
        from agent.ec_skills.browser_use_extension.hooks.external.tmall_chat import (
            system_message_filter as smf,
        )
        self.assertFalse(smf.is_system_message("这款有货吗"))
        self.assertFalse(smf.is_system_message("能便宜点吗"))
        self.assertFalse(smf.is_system_message(""))


# ---------------------------------------------------------------------------
# Active-site gating — source scan of BOTH bundles' __init__.
# (Actual registration is process-global state; the two-process smoke
# script validates it live.  Here we pin the gating structure so a future
# edit can't silently drop a guard.)
# ---------------------------------------------------------------------------
class TestActiveSiteGating(unittest.TestCase):
    def test_tmall_init_gates_all_registrations(self):
        with open(os.path.join(_BUNDLE_DIR, "__init__.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn('== "tmall_chat"', src)
        # Every registration block must consult the gate.
        self.assertEqual(src.count("if _SITE_ACTIVE and not "), 2)

    def test_feige_init_gates_all_registrations(self):
        with open(_FEIGE_INIT, encoding="utf-8") as f:
            src = f.read()
        self.assertIn('== "feige_chat"', src)
        # 6 gated blocks: front_desk, actionable_items, direct_delivery,
        # a2a_local, runner_bridge, site_tools — plus the durability scan.
        self.assertEqual(src.count("if _SITE_ACTIVE and not "), 7)

    def test_default_site_is_feige(self):
        with open(_FEIGE_INIT, encoding="utf-8") as f:
            feige_src = f.read()
        self.assertIn('or "feige_chat"', feige_src)
        with open(os.path.join(_BUNDLE_DIR, "__init__.py"), encoding="utf-8") as f:
            tmall_src = f.read()
        self.assertIn('or "feige_chat"', tmall_src)


if __name__ == "__main__":
    unittest.main()
