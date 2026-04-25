"""Context dataclasses passed to browser-automation hooks.

Lifted from ``agent.ec_skills.build_node`` in Phase 6.5 (2026-04-24)
to break the ``runner`` → ``build_node`` import cycle.

Original (full_local) shapes
----------------------------

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

Hybrid-cloud tiered shapes (Step 2a, 2026-04-25)
------------------------------------------------

To support running the same skill in ``hybrid_cloud`` mode (where the
LLM, skill graph, and most hook decision logic execute cloud-side while
DOM access stays local), three additional context shapes correspond to
the four ``execution_tier`` values declared in each hook's manifest:

* :class:`CloudHookContext` — tier ``cloud_only``.  No DOM access, no
  live browser session; instead carries narrow proxies for agent
  orchestration (registry, send_chat, dispatch state).  Default tier
  for new hooks.

* :class:`LocalReactiveContext` — tier ``local_reactive``.  Bundle
  ships signed + encrypted to client; runs inside a sandbox with
  bounded primitives (eval_js / type / click / read_dom) plus a
  per-session KV.  Used for latency-critical template typers and
  guards that must read live DOM.

* :class:`LocalExtractContext` — tier ``local_extract``.  Pure
  DOM-to-dict functions, no state, no decisions.  Output is sent up
  to a cloud-side hook for downstream logic.  Bundles ship
  unencrypted (low IP value).

The legacy :class:`BrowserUseHookContext` continues to serve tier
``local_only`` (full_local skills, no cloud counterpart).  The four
contexts together cover the full matrix:

    tier            | context                 | DOM | decisions | protection
    ----------------|-------------------------|-----|-----------|-----------
    cloud_only      | CloudHookContext        | no  | yes       | n/a (cloud)
    local_extract   | LocalExtractContext     | yes | no        | plain
    local_reactive  | LocalReactiveContext    | yes | yes       | signed+enc
    local_only      | BrowserUseHookContext   | yes | yes       | none

See ``HYBRID_HOOK_AUDIT.md`` for the per-hook tier classification of
the ``feige_chat`` reference bundle that drove this design.

``build_node.py`` re-exports the legacy shapes for back-compat so
external hook bundles (e.g.
``browser_use_extension/hooks/external/feige_chat``) can continue to
import them from their historical location.  New tiered contexts are
imported directly from this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable


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
    # Per-node run-mode flag sourced from the flowgram JSON
    # (``inputs["runEnvironment"]["content"]``).  One of
    # ``"full_local"`` (default), ``"passive_local"``,
    # ``"hybrid_cloud"``, ``"full_cloud"``.  The v2 wire-up in
    # :mod:`browser_node.hooks` reads this to choose between
    # :class:`tier_aware_runner.RunMode.FULL_LOCAL` and
    # ``RunMode.HYBRID_CLOUD``; legacy v1 hooks ignore it.  It is a
    # *per-skill / per-node* property, NOT an environment variable.
    run_environment: str = "full_local"


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


# ============================================================================
# Hybrid-cloud tiered context shapes (Step 2a, 2026-04-25)
# ============================================================================
#
# The Protocol classes below define the narrow capability surfaces that the
# tiered contexts expose to hooks.  Each has two implementations:
#
# * an in-process backend used in ``full_local`` mode (wraps the existing
#   build_node closures / mainwin / browser_session — installed by
#   ``BrowserRunSession`` when it constructs the context)
# * a wire-protocol-backed proxy used in ``hybrid_cloud`` mode (sends
#   commands over AppSync to the local executor — see step 3)
#
# Both implementations satisfy the same Protocol so hook code is identical
# regardless of where it runs.


@runtime_checkable
class SessionKV(Protocol):
    """Per-session key-value store available to hook code.

    Scoped to a single skill-run session; values do not survive past
    session end.  Implementations:

    * full_local: backed by an in-memory dict on the run session.
    * hybrid_cloud (cloud-side hook): backed by a cloud KV (DDB / Redis)
      keyed by ``(agent_id, session_id, hook_namespace)``.
    * hybrid_cloud (local-side hook): backed by a local in-memory dict
      identical to full_local; cloud → local sync (if needed) is opt-in
      via the hook manifest's ``state_dependencies`` declaration.

    Methods are intentionally synchronous because all current callers
    (`feige_quick_reply` cooldown KV, `dispatch_state` dedup) are
    synchronous.  An ``aget`` / ``aset`` async variant can be added
    later if a cloud-only hook needs to read from a slow store.
    """
    def get(self, key: str, default: Any = None) -> Any: ...
    def set(self, key: str, value: Any) -> None: ...
    def delete(self, key: str) -> None: ...
    def keys(self) -> list[str]: ...


@runtime_checkable
class BrowserPrimitives(Protocol):
    """Bounded set of DOM-touching capabilities exposed to local hooks.

    This is the *only* path through which a local hook may interact
    with the browser.  Direct ``browser_session`` access is intentionally
    not exposed — primitives map cleanly to wire-protocol commands so
    the same hook code runs in the cloud-orchestrated case (where each
    primitive call becomes a round-trip).

    All methods are async because in ``hybrid_cloud`` mode they involve
    I/O (AppSync → local executor → result).  In ``full_local`` mode
    they wrap the local browser_session's already-async API.

    Privacy filtering (``RegexMaskFilter``) is applied to ``read_dom``
    and ``eval_js`` results before they reach the hook — local-side
    hooks see filtered DOM identical to what cloud-side hooks would see.
    """
    async def eval_js(self, snippet: str, *, timeout_ms: int = 3000) -> Any:
        """Run a JavaScript snippet and return its parsed result.

        Filtered through privacy mask before return.  Caller is
        responsible for the snippet being side-effect-free when used
        from ``LocalExtractContext`` (no enforcement; tier audit
        catches violations).
        """
        ...

    async def read_dom(self, selector: str, *, depth: int = 2) -> dict:
        """Return privacy-filtered DOM tree rooted at ``selector``.

        Tree shape: ``{tag, attrs, text, children: [...]}``.  Empty
        dict if the selector matches nothing.
        """
        ...

    async def click(self, selector: str, *, timeout_ms: int = 3000) -> bool:
        """Click the element matching ``selector``.  Returns True on
        success, False if not found / not clickable within timeout."""
        ...

    async def type(
        self,
        selector: str,
        text: str,
        *,
        clear_first: bool = True,
        submit: bool = False,
    ) -> bool:
        """Type ``text`` into the element matching ``selector``.

        ``clear_first`` clears existing input before typing.  ``submit``
        triggers an Enter keystroke after typing.  Returns True on
        success.
        """
        ...

    async def wait_for(
        self,
        selector: str,
        *,
        condition: str = "present",
        timeout_ms: int = 5000,
    ) -> bool:
        """Wait for ``selector`` to satisfy ``condition`` (one of
        ``present`` / ``visible`` / ``stable``).  Returns True if
        satisfied within timeout, False otherwise."""
        ...


@runtime_checkable
class TypingLock(Protocol):
    """Process-local lock preventing typing-action races.

    Mirrors ``feige_chat.typing_lock`` semantics: TTL-based self-heal,
    empty-customer bypass, single-process scope.  Lives behind a
    Protocol so a hook bundle can request a lock without depending on
    the Feige-specific implementation; alternative skills can install
    their own backend.
    """
    def try_acquire(self, customer_key: str, *, ttl_s: float | None = None) -> bool: ...
    def release(self, customer_key: str) -> None: ...
    def holder(self) -> str: ...


@runtime_checkable
class AgentRegistry(Protocol):
    """Cloud-side agent orchestration surface.

    Replaces ``hook_ctx.mainwin.agents`` access with a narrow
    capability — hooks see only what they need (enumerate workers,
    check load) without reach into mainwin internals.
    """
    def list_workers(self, *, exclude: str = "") -> list[dict]:
        """Return active worker agents as ``[{id, name, role, status}, ...]``.

        Excludes the agent whose id matches ``exclude`` (typically the
        front-desk / calling agent itself).
        """
        ...

    def get_load(self, agent_id: str) -> int:
        """Return the number of non-done tasks queued for ``agent_id``."""
        ...


@runtime_checkable
class SendChatProxy(Protocol):
    """Send a chat message from one cloud-side agent to another.

    In ``hybrid_cloud`` mode both sender and recipient live on the
    cloud, so this is an in-process call (no round-trip).  In
    ``full_local`` it routes through the local mainwin.channel_bridge
    as today.
    """
    async def send_chat(
        self,
        target_agent_id: str,
        message: str,
        *,
        metadata: dict | None = None,
    ) -> dict:
        """Returns ``{success: bool, error: str, task_id: str}``."""
        ...


@runtime_checkable
class DispatchState(Protocol):
    """Cross-customer dispatch dedup + affinity state.

    Cloud-side equivalent of ``feige_chat.dispatch_state`` + the
    inflight-lock trio in ``BrowserUseHookContext``.  Backed by a
    cloud KV in hybrid mode; backed by module-level dicts in
    full_local.
    """
    def is_inflight(self, identity_key: str) -> float:
        """Returns timestamp when the in-flight record was set, or 0.0
        if no record / record older than TTL."""
        ...

    def mark_inflight(self, identity_key: str) -> None: ...
    def clear_inflight(self, identity_key: str) -> None: ...

    def get_last_dispatched_msg_id(self, customer_key: str) -> str: ...
    def set_last_dispatched_msg_id(self, customer_key: str, msg_id: str) -> None: ...

    @property
    def inflight_ttl_s(self) -> float: ...


# ─────────────────────────────────────────────────────────────────────────────
# Tier dataclasses
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CloudHookContext:
    """Tier ``cloud_only`` — runs cloud-side; no DOM, no browser session.

    Receives inputs derived from local-side EventMonitor or
    LocalExtractContext output, carries narrow proxies for cloud-side
    orchestration capabilities.

    Maps to legacy ``BrowserUseHookContext`` fields as follows:

    * ``mainwin`` → split into :attr:`agent_registry` + :attr:`send_chat`
      (no kitchen-sink mainwin reference)
    * ``cached_browser_sessions``, ``get_or_create_browser_session`` → not exposed
      (cloud has no browsers)
    * inflight-lock trio → :attr:`dispatch_state`
    * pure helpers (``safe_format_dict``, ``normalize_dispatch_identity_key``,
      ``resolve_template``, ``parse_json_input``) → kept; they're stateless

    Hooks classified as ``cloud_only`` in HYBRID_HOOK_AUDIT.md:

    * ``actionable_items.before_prompt_build_hook`` (full)
    * ``front_desk.before_run_hook`` (cloud-side dispatch half post-split)
    """
    # Identifiers.
    node_name: str
    calling_agent_id: str

    # Cloud-side orchestration.
    agent_registry: AgentRegistry
    send_chat: SendChatProxy
    dispatch_state: DispatchState

    # Per-session KV.  Survives across all hook invocations within one
    # skill-run session; cleared on session end.
    state: SessionKV

    # Pure helpers (stateless; safe to share across tiers).
    parse_json_input: Callable[[dict, str], Any]
    normalize_dispatch_identity_key: Callable[[str], str]
    resolve_template: Callable[[str, dict], str]
    safe_format_dict: type
    send_log: Callable[[str, str], None]


@dataclass
class LocalReactiveContext:
    """Tier ``local_reactive`` — runs local; bounded DOM primitives + KV.

    Hooks shipped in this tier are signed + encrypted; the bundle is
    delivered per-session and decrypted in memory only.  Surface area
    is intentionally minimal so the sandbox boundary is small.

    Hooks classified as ``local_reactive`` in HYBRID_HOOK_AUDIT.md:

    * ``FeigeQuickReplyHook`` (template typer)
    * ``FeigeCrosstalkGuardHook`` (DOM-eval guard)
    * ``front_desk.before_session_setup_hook`` (HOT-PATH-B; monolithic)

    Note on ``dispatch_state``
    --------------------------

    Step 2e port of HOT-PATH-B surfaced one cross-boundary state field:
    the per-customer dispatch-inflight lock.  HOT-PATH-B clears the lock
    after a successful (or failed) typed reply so the next genuine
    customer turn isn't blocked by a stale inflight record.  In
    full_local mode the lock state is process-local; in hybrid_cloud
    mode the cloud side owns the authoritative copy and the local
    proxy RPCs cloud on every call.  Both backends satisfy
    :class:`DispatchState` (same Protocol as ``CloudHookContext``), so
    hook code is identical regardless of deployment.
    """
    # Identifiers.
    node_name: str
    calling_agent_id: str

    # DOM access — the ONLY path to the browser from a hook.
    primitives: BrowserPrimitives

    # Process-local typing lock (prevents racing typed replies).
    typing_lock: TypingLock

    # Per-session KV (local-resident; ephemeral).
    state: SessionKV

    # Cross-boundary dispatch-inflight clearing.  See class docstring
    # for the rationale on why this lives on the local context too.
    dispatch_state: DispatchState

    # Pure helpers (stateless).
    safe_format_dict: type
    resolve_template: Callable[[str, dict], str]
    normalize_dispatch_identity_key: Callable[[str], str]
    send_log: Callable[[str, str], None]


@dataclass
class LocalExtractContext:
    """Tier ``local_extract`` — runs local; pure DOM-to-dict scrapers.

    No state, no decisions.  Hook reads DOM via :attr:`primitives` and
    returns a serializable dict that gets sent up to a cloud-side
    follow-up hook (typically a ``cloud_only`` hook running in the same
    skill-run session).

    Bundles in this tier ship unencrypted (low IP value — selectors
    and DOM-walking logic are easy to recreate by inspecting the page).

    Hooks classified as ``local_extract`` in HYBRID_HOOK_AUDIT.md:

    * ``front_desk.before_run_hook`` (DOM-walk half post-split — the
      sidebar enumeration + per-row scrape that today is intertwined
      with dispatch logic)
    """
    # Identifiers.
    node_name: str
    calling_agent_id: str

    # DOM access (read-favoured; tier audit flags side-effects).
    primitives: BrowserPrimitives

    # Pure helpers (stateless).
    send_log: Callable[[str, str], None]
    # Note: no ``state``, no decision helpers.  Extract hooks return
    # data; downstream cloud_only hooks decide.
