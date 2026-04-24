"""
BypassActionsHook — generalised HOT-PATH executor.

Replicates the trigger+template+tool-sequence logic that currently lives
inline in ``agent/ec_skills/build_node.py`` (the ``hotPathActions`` block
labelled "HOT-PATH-B" in the logs) as a standalone Tier-0 hook.

Scope of THIS hook (and only this hook):
  * read a list of *rules* from config,
  * match each rule's ``trigger`` against the current event payload,
  * on first match, resolve ``{{placeholder}}`` references in each rule's
    ``actions`` args against the payload,
  * return ``HookResult.bypass(actions=[...])`` so the dispatcher short-
    circuits the LLM and the HookedAgent executes the resolved actions
    deterministically.

Out of scope (owned by sibling hooks, added in later PRs):
  * active-session verification (``VerifyActiveSessionHook`` — pre-action)
  * typing lock acquire/release (``TypingLockHook`` — pre/post-action)
  * recent-send dedup / cooldown (``RecentSendDedupHook`` — pre-action)
  * tab focus enforcement (``EnsureTabFocusedHook`` — pre-step)

This hook is PURE: it reads payload + config, emits a decision.  It does
not touch global state, timers, module dicts, or the browser.  All
side-effect-y bits live in the sibling hooks so they can be composed,
reordered, and disabled individually.

Config schema (passed via ``ctx.config``, typically sourced from the node
editor's ``hotPathActions`` field)::

    {
      "rules": [
        {
          "trigger": {
            "event_type": "chat_message",
            "has_fields": ["response_text", "customer_name"]
          },
          "actions": [
            {"tool": "feige_open_session",
             "args": {"customer_name": "{{customer_name}}"}},
            {"tool": "feige_send_message",
             "args": {"text": "{{response_text}}"}}
          ],
          "reason": "auto-reply via Feige"     # optional — goes into trace
        }
      ]
    }

Legacy flat shape — the top-level is a list of rules — is ALSO accepted
so existing ``hotPathActions`` JSON blobs plug in without reshaping::

    [
      {"trigger": {...}, "actions": [...]},
      ...
    ]

Placeholder syntax matches ``build_node._resolve_template``:
  * ``{{field}}``                    → payload["field"]
  * ``{{field1 || field2 || ...}}``  → first non-empty value among candidates
  * any non-``{{…}}`` string is returned verbatim

Non-string action-arg values (numbers, booleans, lists, dicts) are passed
through unchanged; only string values are scanned for placeholders.
"""

from __future__ import annotations

from typing import Any, Iterable

from ...hook_api import (
    BypassAction,
    HookContext,
    HookResult,
    Stage,
)
from .base import BuiltinHook


# ---------------------------------------------------------------------------
# Template resolver — a copy of build_node._resolve_template, deliberately
# kept here so this hook module has no dependency back on build_node.py.
# Behaviourally identical: ``{{a || b}}`` picks first non-empty payload value.
# ---------------------------------------------------------------------------
def _resolve_template(template: Any, payload: dict) -> Any:
    """Resolve ``{{field}}`` or ``{{field1 || field2}}`` placeholders.

    Non-string inputs are returned as-is so dicts/ints/lists pass through.
    Strings without ``{{…}}`` are returned verbatim.  Strings of the form
    ``{{a || b || c}}`` are resolved to the first non-empty value from
    ``payload``, stringified.  If no candidate resolves, an empty string is
    returned — matching the legacy helper's behaviour.
    """
    if not isinstance(template, str):
        return template
    if not (template.startswith("{{") and template.endswith("}}")):
        return template
    inner = template[2:-2].strip()
    candidates = [c.strip() for c in inner.split("||")]
    for field_name in candidates:
        val = payload.get(field_name)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _resolve_args(args: dict, payload: dict) -> dict:
    """Recursively resolve ``{{…}}`` placeholders inside an action's args.

    Only string leaves are resolved.  Dicts and lists are walked so nested
    structures (``{"opts": ["{{mode}}", "verbose"]}``) work as users expect.
    """
    if not isinstance(args, dict):
        return args

    def _walk(v: Any) -> Any:
        if isinstance(v, str):
            return _resolve_template(v, payload)
        if isinstance(v, dict):
            return {k: _walk(vv) for k, vv in v.items()}
        if isinstance(v, (list, tuple)):
            return [_walk(vv) for vv in v]
        return v

    return {k: _walk(vv) for k, vv in args.items()}


# ---------------------------------------------------------------------------
# Trigger matcher.  Separate helper so tests can exercise edge cases directly.
# ---------------------------------------------------------------------------
def _trigger_matches(trigger: dict, event_type: str, payload: dict) -> bool:
    """Return True when *trigger* matches the current event payload.

    Semantics mirror the inline HOT-PATH-B block:
      * ``event_type`` must equal the payload's event_type (when specified);
      * every field listed in ``has_fields`` must be present with a truthy
        string value in the payload.

    A missing trigger (empty dict / None) matches anything.
    """
    if not trigger:
        return True
    want_et = trigger.get("event_type")
    if want_et and want_et != event_type:
        return False
    required: Iterable[str] = trigger.get("has_fields") or ()
    for field in required:
        val = payload.get(field)
        if val is None:
            return False
        if isinstance(val, str) and not val.strip():
            return False
    return True


# ---------------------------------------------------------------------------
# Config normalisation — accept both the legacy flat-list shape and the new
# {"rules": [...]} shape so existing hotPathActions JSON plugs in unchanged.
# ---------------------------------------------------------------------------
def _extract_rules(config: dict | list | None) -> list[dict]:
    if not config:
        return []
    # Legacy: top-level is already a list of rule dicts.
    if isinstance(config, list):
        return [r for r in config if isinstance(r, dict)]
    # Modern: object with a "rules" key.
    rules = config.get("rules")
    if isinstance(rules, list):
        return [r for r in rules if isinstance(r, dict)]
    # Also accept {"hotPathActions": [...]} nesting, since that's what the
    # node editor blob currently looks like when passed verbatim.
    hpa = config.get("hotPathActions")
    if isinstance(hpa, list):
        return [r for r in hpa if isinstance(r, dict)]
    if isinstance(hpa, dict) and isinstance(hpa.get("rules"), list):
        return [r for r in hpa["rules"] if isinstance(r, dict)]
    return []


# ---------------------------------------------------------------------------
# The hook itself.
# ---------------------------------------------------------------------------
class BypassActionsHook(BuiltinHook):
    """Tier-0 hook that runs at ``on_event_normalized`` and may short-circuit
    the LLM by emitting a deterministic action sequence.

    Example usage (registered inside PrivacyAgent setup — future PR)::

        from agent.ec_skills.browser_use_extension.hooks.builtin.bypass_actions \
            import BypassActionsHook

        agent.hook_dispatcher.register(
            BypassActionsHook(config=node_inputs.get("hotPathActions")),
            allow_tier0=True,
        )
    """

    NAME = "bypass_actions"
    STAGE = Stage.ON_EVENT_NORMALIZED
    VERSION = "1.0.0"
    # Run EARLY so LLM-bound processing never starts when a deterministic
    # rule matches.  Priority < 50 puts us ahead of most ordinary hooks.
    PRIORITY = 10

    def __init__(
        self,
        *,
        config: dict | list | None = None,
        permitted_tools: Iterable[str] | None = None,
    ) -> None:
        """Construct a ``BypassActionsHook``.

        Parameters
        ----------
        config
            The ``hotPathActions`` blob from the node editor.  Accepts both
            the legacy flat-list shape and the ``{"rules": [...]}`` object
            shape.  May be ``None`` when the hook is registered but no rules
            are configured (the hook then no-ops on every event).
        permitted_tools
            Tool-name globs the emitted BypassActions are allowed to
            invoke.  Defaults to the union of tool names referenced by the
            config's rules plus ``"feige_*"`` for backwards-compat with
            existing skill bundles.  An explicit empty iterable means "no
            tools" — the hook will still match and emit decisions, but
            downstream execution will fail permission checks.
        """
        self._rules: list[dict] = _extract_rules(config)

        if permitted_tools is None:
            # Inspect the rules to infer what tools they reference.
            # Non-dict action entries are silently skipped here; they're
            # warned about in run() when the rule actually matches.
            inferred: set[str] = set()
            for rule in self._rules:
                for act in rule.get("actions", []) or ():
                    if not isinstance(act, dict):
                        continue
                    tool = act.get("tool")
                    if isinstance(tool, str) and tool:
                        inferred.add(tool)
            # Always keep a Feige-friendly fallback glob so un-authored
            # rules can still reach the feige_* family that ships today.
            if not inferred:
                inferred.add("feige_*")
            permitted_tools = sorted(inferred)

        self.manifest = self._make_manifest(
            permissions={"tools": list(permitted_tools)},
        )
        super().__init__()
        self._log_configured()

    # ------------------------------------------------------------ diagnostics
    def _log_configured(self) -> None:
        rule_count = len(self._rules)
        tools = sorted(set(self.manifest.permissions.tools))
        self._logger.info(
            f"[hook:{self.manifest.name}] configured rules={rule_count} "
            f"permitted_tools={tools}"
        )

    @property
    def rules(self) -> list[dict]:
        """Expose parsed rules for tests + diagnostics."""
        return list(self._rules)

    # ----------------------------------------------------------------- run
    async def run(self, ctx: HookContext, payload: Any) -> HookResult:
        """Match payload against rules and emit Bypass on first hit.

        * ``payload`` is the normalised event dict produced by the
          event_monitor / pend_event_node pipeline.  It MUST carry at least
          ``event_type``; other fields are rule-dependent.
        * When the rule list is empty or no rule matches, returns
          ``Continue`` so the agent loop proceeds normally (LLM or any
          later hook can act).
        """
        if not self._rules:
            return HookResult.cont(reason="no rules configured")

        if not isinstance(payload, dict):
            return HookResult.cont(reason="payload not a dict")

        event_type = str(payload.get("event_type") or "").strip()

        for idx, rule in enumerate(self._rules):
            trigger = rule.get("trigger") or {}
            if not _trigger_matches(trigger, event_type, payload):
                continue

            raw_actions = rule.get("actions") or []
            if not raw_actions:
                self._logger.warning(
                    f"[hook:{self.manifest.name}] rule[{idx}] matched but has "
                    f"empty actions list; skipping"
                )
                continue

            bypass: list[BypassAction] = []
            for ai, act in enumerate(raw_actions):
                if not isinstance(act, dict):
                    self._logger.warning(
                        f"[hook:{self.manifest.name}] rule[{idx}].actions[{ai}] "
                        f"is not an object; skipping action"
                    )
                    continue
                tool = act.get("tool")
                if not isinstance(tool, str) or not tool:
                    self._logger.warning(
                        f"[hook:{self.manifest.name}] rule[{idx}].actions[{ai}] "
                        f"missing 'tool' field; skipping action"
                    )
                    continue
                resolved_args = _resolve_args(act.get("args") or {}, payload)
                bypass.append(BypassAction(name=tool, args=resolved_args))

            if not bypass:
                # All actions invalid — degrade to Continue so we don't
                # emit an empty Bypass (which downstream would treat as "no
                # actions required").
                return HookResult.cont(reason=f"rule[{idx}] had no valid actions")

            reason = str(rule.get("reason") or f"hotPathActions[{idx}] matched")
            self._logger.info(
                f"[hook:{self.manifest.name}] rule[{idx}] matched "
                f"(event_type={event_type!r}, actions={len(bypass)}); "
                f"emitting Bypass ({reason})"
            )
            return HookResult.bypass(actions=bypass, reason=reason)

        return HookResult.cont(reason="no rule matched")


__all__ = [
    "BypassActionsHook",
    # exposed for tests
    "_resolve_template",
    "_resolve_args",
    "_trigger_matches",
    "_extract_rules",
]
