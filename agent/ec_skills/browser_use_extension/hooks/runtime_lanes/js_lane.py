"""
JS-injected runtime lane.

Lets a hook author ship a ``.js`` file whose body runs **inside the page**
via CDP.  No Python→CDP→Python round-trip for each decision; the predicate
evaluates in the browser itself.

Authoring contract
==================

The JS file must define a top-level function named ``hook`` that receives
the payload as its single argument and returns a plain object shaped like:

    {
      "decision": "continue" | "replace" | "bypass" | "drop" |
                  "handoff"  | "escalate",
      "payload":  <any, optional>,            // REPLACE / BYPASS payloads
      "reason":   "<short string, optional>",
      "handoff_agent": "<agent name, optional for handoff>"
    }

Example ``predicate.js``::

    function hook(payload) {
      if (!payload || !payload.text) return {decision: "continue"};
      const ok = !!document.querySelector("[data-qa-id=\\"qa-conversation-chat-item\\"].active");
      return ok
        ? {decision: "continue", reason: "js:active-ok"}
        : {decision: "drop",     reason: "js:no-active-convo"};
    }

Manifest entry (YAML)::

    - name: feige_dom_guard_js
      runtime: js_injected
      entrypoint: "predicate.js"
      stage: on_pre_action
      tier: 1
      priority: 10
      permissions: {tools: []}

Safety
======

* The lane ALWAYS fails open (``Decision.CONTINUE``) when:
    - ``ctx.browser_session`` is None (e.g. unit-test context).
    - JS eval raises.
    - JS returns anything the parser cannot coerce to a HookResult.
  Fail-open is correct here because a JS-lane hook is by definition
  informational; safety-critical decisions belong in Tier-0 Python.
* JS source is read ONCE at load time and embedded in the dispatch
  wrapper.  No eval of user JSON at dispatch time — only JSON.stringify
  of the payload going in, and JSON.parse of the result coming out.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ...hook_api import (
    BypassAction,
    Decision,
    HookContext,
    HookManifest,
    HookResult,
)

logger = logging.getLogger(__name__)


# Map dotted decision strings to enum members; extra keys accepted for
# forward compatibility but unknown values collapse to CONTINUE.
_DECISION_MAP: dict[str, Decision] = {d.value: d for d in Decision}


def _parse_js_decision(raw: Any) -> HookResult:
    """Translate whatever the JS snippet returned into a ``HookResult``.

    Accepts:
      * ``None``               → Continue (JS returned nothing)
      * ``dict``               → normal path
      * JSON string            → decoded then treated as dict

    Unknown shapes are coerced to Continue + ``reason="js:bad_shape"`` so
    a broken JS file never crashes the agent loop.
    """
    if raw is None:
        return HookResult.cont(reason="js:returned_none")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return HookResult.cont(reason="js:bad_json_string")
    if not isinstance(raw, dict):
        return HookResult.cont(reason="js:bad_shape")

    dec_str = str(raw.get("decision") or "continue").lower().strip()
    reason = str(raw.get("reason") or "")
    dec = _DECISION_MAP.get(dec_str)
    if dec is None:
        return HookResult.cont(reason=f"js:unknown_decision:{dec_str}")

    if dec == Decision.REPLACE:
        return HookResult.replace(raw.get("payload"), reason=reason)
    if dec == Decision.BYPASS:
        raw_actions = raw.get("payload") or raw.get("actions") or []
        if not isinstance(raw_actions, list):
            return HookResult.cont(reason="js:bypass_payload_not_list")
        # Normalise into BypassAction objects (pydantic validates shape).
        # Any single malformed entry fails the whole decision — we prefer
        # a visible fall-through to silently dropping actions the author
        # intended to emit.
        acts: list[BypassAction] = []
        for a in raw_actions:
            if not isinstance(a, dict) or "name" not in a:
                return HookResult.cont(reason="js:bypass_action_invalid")
            try:
                acts.append(BypassAction.model_validate(a))
            except Exception:
                return HookResult.cont(reason="js:bypass_action_invalid")
        return HookResult.bypass(acts, reason=reason)
    if dec == Decision.DROP:
        return HookResult.drop(reason=reason)
    if dec == Decision.HANDOFF:
        return HookResult.handoff(
            str(raw.get("handoff_agent") or ""), reason=reason,
        )
    if dec == Decision.ESCALATE:
        return HookResult.escalate(reason=reason)
    # CONTINUE
    return HookResult.cont(reason=reason)


def _build_wrapped_script(user_js: str, payload_json: str) -> str:
    """Return the JS string to evaluate via CDP.

    The wrapping gives us:
      * The user's source declared in a fresh IIFE scope.
      * A top-level ``hook(payload)`` call.
      * ``JSON.stringify`` on the result so Python sees a predictable
        string regardless of the browser-use evaluate_js backend.
    """
    return (
        "(function(){"
        f"{user_js}\n"
        f"var __ecan_payload = {payload_json};"
        "try {"
        "  var __ecan_result = (typeof hook === 'function') ? hook(__ecan_payload) : null;"
        "  return JSON.stringify(__ecan_result);"
        "} catch(e) {"
        "  return JSON.stringify({decision: 'continue', reason: 'js:exception:' + (e && e.message || String(e))});"
        "}"
        "})()"
    )


# ---------------------------------------------------------------------------
# The lane hook.  The loader instantiates ONE of these per manifest entry
# that declares ``runtime: js_injected``.
# ---------------------------------------------------------------------------
class JsInjectedLaneHook:
    """Shim that behaves like a Python Hook but dispatches to a JS snippet."""

    manifest: HookManifest

    def __init__(
        self,
        *,
        js_source: str,
        manifest: HookManifest | None = None,
        config: dict | None = None,
    ):
        if not isinstance(js_source, str) or not js_source.strip():
            raise ValueError("JsInjectedLaneHook requires non-empty js_source")
        self._js = js_source
        self.config = dict(config or {})
        if manifest is not None:
            self.manifest = manifest

    @classmethod
    def from_file(
        cls,
        js_path: Path,
        *,
        manifest: HookManifest | None = None,
        config: dict | None = None,
    ) -> "JsInjectedLaneHook":
        """Convenience — read a ``.js`` file and wrap it."""
        p = Path(js_path)
        if not p.is_file():
            raise FileNotFoundError(f"js entrypoint not found: {p}")
        return cls(
            js_source=p.read_text(encoding="utf-8"),
            manifest=manifest,
            config=config,
        )

    async def run(self, ctx: HookContext, payload: Any) -> HookResult:
        session = getattr(ctx, "browser_session", None)
        if session is None:
            # Test contexts, or stages that fire before a session exists.
            return HookResult.cont(reason="js:no_browser_session")

        try:
            payload_json = json.dumps(payload, default=str, ensure_ascii=False)
        except Exception as e:
            return HookResult.cont(reason=f"js:payload_unserializable:{type(e).__name__}")

        script = _build_wrapped_script(self._js, payload_json)
        try:
            raw = await _eval_js(session, script)
        except Exception as e:
            logger.warning(
                f"[js_lane:{getattr(self.manifest, 'name', '?')}] eval failed: {e!r}"
            )
            return HookResult.cont(reason=f"js:eval_error:{type(e).__name__}")

        return _parse_js_decision(raw)


# ---------------------------------------------------------------------------
# Thin wrapper over extension_tools_service._evaluate_js so the test suite
# can patch a single symbol.
# ---------------------------------------------------------------------------
async def _eval_js(browser_session: Any, script: str) -> Any:
    from agent.ec_skills.browser_use_extension.extension_tools_service import (  # type: ignore
        _evaluate_js,
    )
    return await _evaluate_js(browser_session, script)


__all__ = [
    "JsInjectedLaneHook",
    "_parse_js_decision",
    "_build_wrapped_script",
    "_eval_js",
]
