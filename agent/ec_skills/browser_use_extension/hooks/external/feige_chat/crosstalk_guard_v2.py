"""Tier-aware port of FeigeCrosstalkGuardHook (Step 2d, 2026-04-25).

Third hook port in the hybrid-cloud migration.  Targets the
``local_reactive`` tier and runs against :class:`LocalReactiveContext`.

What changes vs. v1
-------------------

* Inheritance is gone — v1 subclassed
  :class:`VerifyActiveSessionHook` (a Tier-0 builtin coupled to the
  legacy ``HookContext``).  v2 is a flat class so it doesn't inherit
  the ``ctx.browser_session`` access pattern the parent used.
* ``ctx.browser_session`` + ``_eval_js_on_session`` →
  ``await ctx.primitives.eval_js(script)``.
* ``ctx.site_adapter`` (passed via legacy HookContext) → carried in
  ``self._site_adapter`` from the bundle config.  The site-adapter is
  per-hook-bundle config, not per-skill-run state, so it belongs in the
  hook instance, not the context.
* The pure helpers
  (:func:`_extract_expected_customer`, :func:`_parse_js_result`,
  :func:`build_active_session_js`, :func:`normalize_site_adapter`,
  :func:`verify_active_session_match`) are reused verbatim from the
  builtin module — they don't touch the browser, so they don't need
  porting.

What stays identical
--------------------

* The 2-of-3 verdict semantics (sidebar vs header vs strategy)
* Fail-open behaviour: payload-not-dict / action-not-guarded / no
  expected name in args / no primitives → cont; eval error → cont
  with ``verify:eval_error`` reason
* Drop-on-mismatch semantics

Hook instance ownership of ``site_adapter``
-------------------------------------------

In v1, ``site_adapter`` was carried on ``ctx.site_adapter`` because the
HookedAgent injected it from a per-node config slot.  In the cloud
world, each hook bundle declares its own site adapter (Feige selectors
are the bundle's IP), so v2 takes it as ``__init__(config={'site_adapter': {...}})``.

Default site_adapter is the one ``normalize_site_adapter({})`` returns
for the Feige preset, so passing no config matches v1 behaviour for
the Feige bundle.
"""

from __future__ import annotations

import logging
from typing import Any

from agent.ec_skills.browser_node.contexts import LocalReactiveContext

# Reuse pure helpers from the Tier-0 builtin — they don't touch the
# browser, so no porting needed.
from agent.ec_skills.browser_use_extension.hook_api import HookResult
from agent.ec_skills.browser_use_extension.hooks.builtin.verify_active_session import (
    _extract_expected_customer,
    _parse_js_result,
)
from agent.ec_skills.browser_use_extension.hooks.builtin.site_adapter import (
    build_active_session_js,
    normalize_site_adapter,
    verify_active_session_match,
)

logger = logging.getLogger("ecan.hooks.feige_chat.v2")

__all__ = ["FeigeCrosstalkGuardHookV2"]


# Defaults mirror v1's FeigeCrosstalkGuardHook.
DEFAULT_GUARDED_ACTIONS = ("feige_send_message", "feige_send_draft")
DEFAULT_EXPECTED_CUSTOMER_KEYS = (
    "customer_name",
    "expected_customer",
    "customer_id",
    "recipient",
    "chat_target",
)


def _extract_action_args(payload: dict, action_name: str) -> dict:
    """Pull the args dict for ``action_name`` out of the on_pre_action payload.

    Mirrors the legacy parent's extraction logic: payload may carry a
    ``model_dump``-able ActionModel under ``action`` (browser-use
    convention) or a plain dict.
    """
    action_obj = payload.get("action")
    if action_obj is None:
        return {}
    if hasattr(action_obj, "model_dump"):
        try:
            dumped = action_obj.model_dump(exclude_unset=True) or {}
        except Exception:
            return {}
        if isinstance(dumped, dict):
            tool_args = dumped.get(action_name)
            if isinstance(tool_args, dict):
                return tool_args
        return {}
    if isinstance(action_obj, dict):
        if isinstance(action_obj.get(action_name), dict):
            return action_obj[action_name]
        return action_obj
    return {}


class FeigeCrosstalkGuardHookV2:
    """Tier ``local_reactive`` port of FeigeCrosstalkGuardHook.

    Verifies the active sidebar customer matches the action's intended
    target before allowing a write-path tool call.  Reads the live DOM
    via :meth:`LocalReactiveContext.primitives.eval_js` exactly once per
    pre-action invocation.

    Identical decision logic to v1; only the DOM access path changes.
    """

    EXECUTION_TIER = "local_reactive"

    def __init__(self, config: dict | None = None):
        cfg = dict(config or {})
        self._guarded: list[str] = list(
            cfg.get("guarded_actions") or DEFAULT_GUARDED_ACTIONS
        )
        self._expected_keys: list[str] = list(
            cfg.get("expected_customer_keys") or DEFAULT_EXPECTED_CUSTOMER_KEYS
        )
        # Site adapter — bundle-specific DOM selectors / JS scaffolding.
        # ``normalize_site_adapter`` fills in Feige-preset defaults when
        # the supplied dict is empty.
        self._site_adapter: dict = normalize_site_adapter(
            cfg.get("site_adapter") or {}
        )
        self.config = cfg
        logger.info(
            f"[feige_crosstalk_guard_v2] guarded_actions={self._guarded} "
            f"expected_customer_keys={self._expected_keys}"
        )

    async def run(
        self,
        ctx: LocalReactiveContext,
        payload: Any,
    ) -> HookResult:
        if not isinstance(payload, dict):
            return HookResult.cont(reason="verify_v2:payload_not_dict")

        action_name = str(payload.get("action_name") or "").strip()
        if action_name not in self._guarded:
            return HookResult.cont(
                reason=f"verify_v2:action_not_guarded:{action_name}"
            )

        args = _extract_action_args(payload, action_name)
        expected = _extract_expected_customer(args, self._expected_keys)
        if not expected:
            # Can't verify without an expected name — fail-open.
            return HookResult.cont(reason="verify_v2:no_expected_in_args")

        # Live DOM read — the only place this hook reaches the browser.
        if ctx.primitives is None:
            return HookResult.cont(reason="verify_v2:no_primitives")

        script = build_active_session_js(self._site_adapter)
        try:
            raw = await ctx.primitives.eval_js(script)
        except Exception as err:
            # Transient DOM issue; fail-open per Tier-0 policy.
            logger.warning(
                f"[feige_crosstalk_guard_v2] eval_js failed ({err!r}); "
                f"allowing send (fail-open)"
            )
            return HookResult.cont(
                reason=f"verify_v2:eval_error:{type(err).__name__}"
            )

        result = _parse_js_result(raw)
        ok, reason = verify_active_session_match(
            self._site_adapter, result, expected
        )

        if ok:
            logger.info(
                f"[feige_crosstalk_guard_v2] OK expected={expected!r} "
                f"active={result.get('active')!r} "
                f"header={result.get('header')!r} "
                f"strategy={result.get('strategy')!r} ({reason})"
            )
            return HookResult.cont(reason=reason)

        logger.warning(
            f"[feige_crosstalk_guard_v2] BLOCK expected={expected!r} "
            f"active={result.get('active')!r} "
            f"header={result.get('header')!r} "
            f"strategy={result.get('strategy')!r} "
            f"diag={result.get('diagnostics')!r} ({reason})"
        )
        return HookResult.drop(reason=reason)
