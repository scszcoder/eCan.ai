"""Context dataclasses passed to browser-automation hooks.

Lifted from ``agent.ec_skills.build_node`` in Phase 6.5 (2026-04-24)
to break the ``runner`` → ``build_node`` import cycle.

Four dataclasses live here:

* :class:`BrowserUseHookContext` — passed to
  ``before_browser_session_setup`` and ``before_browser_use_run`` hooks.
  Carries identifiers, build-scope helper closures, and shared
  build-node state (caches, dispatch-inflight trio).

* :class:`PromptBuildContext` — passed to ``before_prompt_build`` hooks.
  Snapshot of DOM event + compacted items at task-prompt assembly time.

* :class:`PromptBuildResult` — return value from ``before_prompt_build``
  hooks.  Describes how to mutate task text / override block, or
  short-circuit the node.

* :class:`_AssignmentContext` — internal bundle of cross-phase
  assignment-scope state used by ``BrowserRunSession``.

``build_node.py`` re-exports these for back-compat so external hook
bundles (e.g. ``browser_use_extension/hooks/external/feige_chat``) can
continue to import them from their historical location.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable


@dataclass
class BrowserUseHookContext:
    """Data + helpers passed to ``before_browser_use_run`` hooks.

    Site-specific state (e.g. Feige's dispatch dicts) lives in the
    hook module itself, not here.  This context carries only the
    generic helpers / shared state that ``build_node`` owns and that
    hook implementations (+ their delegated helpers) need.
    """
    # Identifiers.
    node_name: str
    calling_agent_id: str
    mainwin: Any
    # Closure-scoped helpers from ``_run_browser_use`` (can't be
    # module-level because they capture per-invocation locals).
    resolve_scope_key: Callable[[dict], str]
    extract_runtime_invocation_input: Callable[[dict | None], str]
    # Module-level helpers (safe to call anywhere).
    parse_json_input: Callable[[dict, str], Any]
    send_log: Callable[[str, str], None]
    normalize_dispatch_identity_key: Callable[[str], str]
    safe_format_dict: type
    # Generic shared state owned by ``build_node`` module scope.
    cached_browser_sessions: dict
    dispatch_state_by_agent: dict
    # Inflight-lock trio (prevents double-dispatch of the same item
    # across scopes).  Keyed by dispatch-identity-key (see
    # ``normalize_dispatch_identity_key``).
    is_dispatch_inflight: Callable[[str], float]
    mark_dispatch_inflight: Callable[[str], None]
    clear_dispatch_inflight: Callable[[str], None]
    inflight_ttl_s: float
    # Template renderer for placeholder substitution in action args.
    # Resolves ``{{field}}`` / ``{{a || b}}`` against a payload dict.
    resolve_template: Callable[[str, dict], str]
    # Closure that creates / retrieves the cached browser session for
    # this node invocation.  Exposed so early-phase hooks (which run
    # before the browser-use agent is constructed) can still acquire
    # a live session.  Signature: ``(mainwin, state=..., calling_agent_id=...)``.
    get_or_create_browser_session: Callable[..., Awaitable[Any]]


@dataclass
class PromptBuildContext:
    """Data passed to ``before_prompt_build`` hooks.

    Snapshot of the DOM event + compacted items available at the
    time the task prompt is being assembled.  Hooks read from this
    and return a :class:`PromptBuildResult` describing how to mutate
    the task text / override block, or short-circuit the node.
    """
    # DOM snapshot with heavy fields (avatars, URLs) stripped.
    compact_items: list
    # Subset of ``compact_items`` whose ``actionable_field`` is non-empty.
    # Empty list when ``actionable_field`` is "" / unset.
    actionable_raw: list
    # The node-config field name used for actionable filtering (may be "").
    actionable_field: str
    # Triggering event type / label (e.g. "browser_event" / "" or
    # "chat_message" / "...").
    event_type: str
    event_label: str


@dataclass
class _AssignmentContext:
    """Bundled cross-phase assignment-scope state for ``BrowserRunSession``.

    Output of :meth:`BrowserRunSession._extract_assignment_and_scope`.
    Groups together the 8 cross-phase variables that flow from the
    assignment-scope phase into downstream phases (browser session
    acquisition, focus preflight, agent construction, finalize).
    """
    asg_cfg: dict | None
    session_id: str
    tab_id: str
    chat_url: str
    customer_name: str
    browser_scope_key: str
    cached_browser_session: Any
    last_known_focus_target_id: Any


@dataclass
class PromptBuildResult:
    """Return value from a ``before_prompt_build`` hook.

    Any of the three effects can be requested in a single return:

    * ``short_circuit_state`` — if set, node returns this dict instead
      of running the LLM.  When set, the text mutations are ignored.
    * ``task_hint_append`` — text appended to ``_new_msg_hint`` (which
      becomes part of the task prompt).
    * ``override_prepend`` — text prepended to the protocol override
      block (which is glued onto the front of the task).
    """
    short_circuit_state: dict | None = None
    task_hint_append: str = ""
    override_prepend: str = ""
