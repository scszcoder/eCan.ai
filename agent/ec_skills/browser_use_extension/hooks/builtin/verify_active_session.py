"""
VerifyActiveSessionHook — crosstalk guard at ``on_pre_action``.

Blocks a type/send action when the browser's currently-focused chat does
not match the customer the action intends to reply to.  This is the
zero-risk guard rail that prevents reply-to-wrong-customer bugs during
multi-customer dispatch races.

Behaviour:
  * Matches on configurable ``action_name`` — default: ``feige_send_message``.
  * Reads ``site_adapter`` from ``ctx.site_adapter`` (data) and uses
    ``build_active_session_js(cfg)`` to produce a DOM-reading JS snippet.
  * Evaluates the JS via ``_evaluate_js(ctx.browser_session, script)`` from
    ``extension_tools_service``.  If eval fails or ctx.browser_session is
    None (test context), returns ``Continue`` so the action proceeds —
    fail-open is preferable to fail-closed because a false negative here
    means stalling a customer reply, which is also bad.
  * Compares the JS result against the expected customer name extracted
    from the action args; returns ``Drop`` on mismatch with a structured
    reason string, ``Continue`` on affirmation.

The expected-customer extractor understands the common arg shapes:
  * ``{"text": "<reply>", "customer_name": "客户A"}``    (our canonical shape)
  * ``{"customer_name": "客户A"}``                        (open_session)
  * ``{"text": "...", "expected_customer": "客户A"}``    (legacy)

Callers that want a different arg key should set
``manifest.matches["expected_customer_arg"]`` in the config passed to the
constructor.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ...hook_api import HookContext, HookResult, Stage
from .base import BuiltinHook
from .site_adapter import (
    build_active_session_js,
    normalize_site_adapter,
    verify_active_session_match,
)


# ---------------------------------------------------------------------------
# Expected-customer extractor.  Pure function, easy to test.
# ---------------------------------------------------------------------------
def _extract_expected_customer(args: dict, lookup_keys: list[str]) -> str:
    """Return the first non-empty string among *lookup_keys* in *args*."""
    if not isinstance(args, dict):
        return ""
    for k in lookup_keys:
        v = args.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


# ---------------------------------------------------------------------------
# Lazy import of _evaluate_js so this module can be imported without
# browser-use being installed (tests, analysis tools, etc.).
# ---------------------------------------------------------------------------
async def _eval_js_on_session(browser_session: Any, script: str) -> Any:
    from agent.ec_skills.browser_use_extension.extension_tools_service import (  # type: ignore
        _evaluate_js,
    )
    return await _evaluate_js(browser_session, script)


def _parse_js_result(raw: Any) -> dict:
    """Accept either a JSON string or a dict and return a dict."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


# ---------------------------------------------------------------------------
# The hook.
# ---------------------------------------------------------------------------
class VerifyActiveSessionHook(BuiltinHook):
    """Pre-action crosstalk guard.

    Registered by the HookedAgent when a ``site_adapter`` is configured.
    Runs at ``on_pre_action`` with high priority (low number) so it
    evaluates BEFORE any other pre-action hook that might modify state.
    """

    NAME = "verify_active_session"
    STAGE = Stage.ON_PRE_ACTION
    VERSION = "1.0.0"
    # Run very early — before TypingLockHook so we can short-circuit
    # entirely on a verified mismatch without ever touching the lock.
    PRIORITY = 5

    DEFAULT_GUARDED_ACTIONS: tuple[str, ...] = ("feige_send_message",)
    DEFAULT_EXPECTED_CUSTOMER_KEYS: tuple[str, ...] = (
        "customer_name",
        "expected_customer",
        "customer_id",
    )

    def __init__(
        self,
        *,
        guarded_actions: Optional[list[str]] = None,
        expected_customer_keys: Optional[list[str]] = None,
    ) -> None:
        self._guarded = tuple(guarded_actions or self.DEFAULT_GUARDED_ACTIONS)
        self._expected_keys = list(
            expected_customer_keys or self.DEFAULT_EXPECTED_CUSTOMER_KEYS
        )
        self.manifest = self._make_manifest(
            matches={"action_name": list(self._guarded)},
            permissions={"tools": []},  # no tool calls — DOM eval direct
            # Verify JS needs a browser round-trip; give it generous budget.
            budget={"timeout_ms": 1500, "rate_per_minute": 600},
        )
        super().__init__()
        self._logger.info(
            f"[hook:{self.manifest.name}] guarded_actions={list(self._guarded)} "
            f"expected_customer_keys={self._expected_keys}"
        )

    # ------------------------------------------------------------- run
    async def run(self, ctx: HookContext, payload: Any) -> HookResult:
        if not isinstance(payload, dict):
            return HookResult.cont(reason="verify:payload_not_dict")

        action_name = str(payload.get("action_name") or "").strip()
        if action_name not in self._guarded:
            # Dispatcher's matcher should have filtered already, but be
            # defensive — matcher ignores unknown match keys so callers
            # can add new match criteria without touching this code.
            return HookResult.cont(reason=f"verify:action_not_guarded:{action_name}")

        # Extract args from the ActionModel wrapper (payload["action"]).
        action_obj = payload.get("action")
        args: dict = {}
        if action_obj is not None:
            if hasattr(action_obj, "model_dump"):
                try:
                    dumped = action_obj.model_dump(exclude_unset=True) or {}
                    # The dump is {tool_name: {args}}; extract the args dict.
                    if isinstance(dumped, dict):
                        tool_args = dumped.get(action_name)
                        if isinstance(tool_args, dict):
                            args = tool_args
                except Exception:
                    args = {}
            elif isinstance(action_obj, dict):
                if isinstance(action_obj.get(action_name), dict):
                    args = action_obj[action_name]
                else:
                    args = action_obj

        expected = _extract_expected_customer(args, self._expected_keys)
        if not expected:
            # No expected name available — we can't verify.  Return Continue
            # so the send proceeds; the Tier-0 nature of this hook is
            # "block when we know it's wrong", not "block when we can't tell".
            return HookResult.cont(reason="verify:no_expected_in_args")

        if ctx.browser_session is None:
            # Test or non-browser context.  Fail-open.
            return HookResult.cont(reason="verify:no_browser_session")

        cfg = normalize_site_adapter(ctx.site_adapter)
        script = build_active_session_js(cfg)

        try:
            raw = await _eval_js_on_session(ctx.browser_session, script)
        except Exception as err:
            # Browser eval failed (network glitch, page navigated, CDP
            # detached).  Fail-open — better to risk a single mis-send
            # than to stall the customer reply on a transient DOM issue.
            self._logger.warning(
                f"[hook:{self.manifest.name}] JS eval failed ({err!r}); "
                f"allowing send (fail-open)"
            )
            return HookResult.cont(reason=f"verify:eval_error:{type(err).__name__}")

        result = _parse_js_result(raw)
        ok, reason = verify_active_session_match(cfg, result, expected)

        if ok:
            self._logger.info(
                f"[hook:{self.manifest.name}] OK expected={expected!r} "
                f"active={result.get('active')!r} header={result.get('header')!r} "
                f"strategy={result.get('strategy')!r} ({reason})"
            )
            return HookResult.cont(reason=reason)

        self._logger.warning(
            f"[hook:{self.manifest.name}] BLOCK expected={expected!r} "
            f"active={result.get('active')!r} header={result.get('header')!r} "
            f"strategy={result.get('strategy')!r} diag={result.get('diagnostics')!r} "
            f"({reason})"
        )
        return HookResult.drop(reason=reason)


__all__ = [
    "VerifyActiveSessionHook",
    "_extract_expected_customer",
    "_parse_js_result",
]
