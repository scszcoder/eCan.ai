"""``store_id`` — which shop a run serves, carried as a per-task variable.

A store belongs to the TASK, not the agent: an agent is a skill/task holder, one
agent can serve several shops through several tasks, and a shared skill can be
pointed at a different shop by every task that uses it.

So store identity rides the ordinary per-task variable path already in place for
shared skills:

    prompt {{store_id}} → skill.need_inputs → Tasks page 任务变量 field
      → task.metadata["task_vars"]["store_id"] → apply_task_vars
      → state["prompt_refs"]["store_id"]

and ``ec_tasks.runner`` publishes the resolved value on the run scope so
consumers on the dispatch path (per-store 过渡话术 today, per-store billing
attribution next) can read it without threading run state through every call.
"""

from __future__ import annotations

import unittest

# Enter the ec_tasks ↔ prep_skills_run import cycle from the package side,
# matching production import order (see tests/unit/test_task_vars_phase2.py).
import agent.ec_tasks  # noqa: F401
from agent.ec_skills.prompt_variable_providers import (
    STORE_ID_VAR,
    resolve_store_id,
    store_id_from_url,
    get_provider,
)


class StoreIdFromUrlTests(unittest.TestCase):
    def test_host_and_first_segment(self) -> None:
        self.assertEqual(
            store_id_from_url("https://fxg.jinritemai.com/shop/12345/orders"),
            "fxg.jinritemai.com/shop",
        )

    def test_host_only_when_no_path(self) -> None:
        self.assertEqual(store_id_from_url("https://shop.example.com"), "shop.example.com")
        self.assertEqual(store_id_from_url("https://shop.example.com/"), "shop.example.com")

    def test_same_shop_typed_two_ways_lands_on_one_id(self) -> None:
        self.assertEqual(
            store_id_from_url("HTTPS://WWW.Example.com/ShopA"),
            store_id_from_url("https://example.com/ShopA"),
        )

    def test_rejects_non_urls(self) -> None:
        for raw in (None, "", "   ", "not a url", "ftp://x/y", 42, {"a": 1}):
            self.assertEqual(store_id_from_url(raw), "")


class ResolveStoreIdTests(unittest.TestCase):
    def test_explicit_task_var_wins(self) -> None:
        refs = {STORE_ID_VAR: "shop-42", "store_url": "https://example.com/other"}
        self.assertEqual(resolve_store_id(refs), "shop-42")

    def test_falls_back_to_the_deployed_store_url(self) -> None:
        """Fast Deploy seeds store_url for exactly one shop, so it is a better
        default than blank when the operator did not fill the variable in."""
        self.assertEqual(
            resolve_store_id({"store_url": "https://example.com/ShopA"}),
            "example.com/ShopA",
        )

    def test_falls_back_to_first_of_store_urls(self) -> None:
        self.assertEqual(
            resolve_store_id({"store_urls": ["https://example.com/ShopA", "https://b.com"]}),
            "example.com/ShopA",
        )

    def test_unset_means_account_wide_default(self) -> None:
        self.assertEqual(resolve_store_id({}), "")
        self.assertEqual(resolve_store_id({STORE_ID_VAR: "   "}), "")

    def test_accepts_state_or_refs(self) -> None:
        """The runner has task_vars before a state exists; the prompt cascade
        has the state.  One function must answer for both."""
        self.assertEqual(resolve_store_id({"prompt_refs": {STORE_ID_VAR: "S1"}}), "S1")
        self.assertEqual(resolve_store_id({STORE_ID_VAR: "S1"}), "S1")

    def test_tolerates_bad_input(self) -> None:
        for raw in (None, "string", 7, []):
            self.assertEqual(resolve_store_id(raw), "")


class StoreIdProviderTests(unittest.TestCase):
    def test_registered_as_a_builtin(self) -> None:
        self.assertIsNotNone(get_provider(STORE_ID_VAR))

    def test_provider_derives_from_store_url(self) -> None:
        provider = get_provider(STORE_ID_VAR)
        state = {"prompt_refs": {"store_url": "https://example.com/ShopA"}}
        self.assertEqual(provider(state, None), "example.com/ShopA")

    def test_task_var_reaches_the_prompt_cascade(self) -> None:
        """End of the declared path: a task variable resolves {{store_id}}."""
        from types import SimpleNamespace
        from agent.ec_skills.prep_skills_run import apply_task_vars
        from agent.ec_skills.prompt_variable_providers import resolve_prompt_variables

        state: dict = {}
        task = SimpleNamespace(metadata={"task_vars": {STORE_ID_VAR: "shop-42"}})
        apply_task_vars(task, state)
        self.assertEqual(state["prompt_refs"][STORE_ID_VAR], "shop-42")
        resolved = resolve_prompt_variables([STORE_ID_VAR], state, mainwin=None)
        self.assertEqual(resolved[STORE_ID_VAR], "shop-42")


class RunnerScopeStampTests(unittest.TestCase):
    """The runner must publish store_id on the run scope — that is the only
    reason the dispatch path can read it without run state in hand."""

    def test_runner_publishes_store_id_on_the_scope(self) -> None:
        from pathlib import Path
        src = Path("agent/ec_tasks/runner.py").read_text(encoding="utf-8")
        idx = src.find("with _log_scope(")
        self.assertGreater(idx, -1)
        block = src[idx:idx + 900]
        self.assertIn("store_id=_store_id,", block)
        self.assertIn("resolve_store_id", src)

    def test_scope_key_matches_what_the_consumer_reads(self) -> None:
        from pathlib import Path
        consumer = Path(
            "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/"
            "placeholder_config.py"
        ).read_text(encoding="utf-8")
        self.assertIn('_scope().get("store_id")', consumer)
        # Regression guard for the correction that produced this file: the
        # agent id must never stand in for a store.
        self.assertNotIn('sc.get("agent_id")', consumer)


class UrlDerivationCannotSeparateFeigeStoresTests(unittest.TestCase):
    """The URL fallback is a trap on 飞鸽 and must stay visibly so.

    Every seller works out of the same workstation page, so store identity
    lives in the logged-in session, not the path. These tests pin that fact:
    if someone later "fixes" store_id_from_url to look like it distinguishes
    stores, or drops the explicit-var precedence, this fails loudly instead of
    two stores quietly sharing one placeholder config and one metering bucket.
    """

    FEIGE = "https://im.jinritemai.com/pc_seller_v2/main/workspace"

    def test_two_different_feige_stores_derive_the_same_id(self) -> None:
        from agent.ec_skills.prompt_variable_providers import resolve_store_id
        store_a = {"store_url": self.FEIGE, "store_urls": self.FEIGE}
        store_b = {"store_url": self.FEIGE, "store_urls": self.FEIGE}
        self.assertEqual(resolve_store_id(store_a), resolve_store_id(store_b))
        self.assertTrue(resolve_store_id(store_a))  # non-empty, which is the trap

    def test_an_explicit_store_id_separates_them(self) -> None:
        from agent.ec_skills.prompt_variable_providers import resolve_store_id
        store_a = {"store_url": self.FEIGE, "store_id": "lands_flying_fish"}
        store_b = {"store_url": self.FEIGE, "store_id": "second_shop"}
        self.assertEqual(resolve_store_id(store_a), "lands_flying_fish")
        self.assertEqual(resolve_store_id(store_b), "second_shop")
        self.assertNotEqual(resolve_store_id(store_a), resolve_store_id(store_b))

    def test_fast_deploy_writes_an_explicit_store_id_into_task_vars(self) -> None:
        from pathlib import Path
        src = Path("cli/deploy/commands.py").read_text(encoding="utf-8")
        self.assertIn('store_id = str(cfg.get("store_id") or "").strip()', src)
        self.assertIn('task_vars["store_id"] = store_id', src)
        # And warns when it is absent, rather than silently merging stores.
        self.assertIn("WARNING: no store_id given", src)

    def test_the_panel_collects_it(self) -> None:
        from pathlib import Path
        panel = Path(
            "gui_v2/src/components/FastDeploy/FastDeployPanel.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn("store_id: (config.storeId", panel)
        schema = Path(
            "gui_v2/src/components/FastDeploy/scenarios.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn("storeId: true", schema)


if __name__ == "__main__":
    unittest.main()
