"""Build-time configuration for the browser-automation node.

``NodeConfig`` is a frozen dataclass capturing every knob extracted
from ``config_metadata["inputsValues"]`` plus a few derived values
(downloads_path, timeout floor enforcement).

``parse_node_config`` is the single place that knows the shape of
``inputsValues``.  It is pure: takes ``config_metadata`` + identity
fields, returns a ``NodeConfig``.

Keeping this in its own module means:
  * the config surface is self-documenting (read the dataclass)
  * adding a new node-editor input is a one-line addition here
  * downstream code (session, runner, auto) consumes typed fields
    instead of digging through a dict-of-dicts
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from utils.logger_helper import logger_helper as logger


# Minimum timeout floor: browser automation involves multiple LLM calls
# + page navigations, so timeouts below 300s typically cause premature
# failures.  Public so callers can reference the same constant.
BROWSER_MIN_TIMEOUT_SEC: int = 300

# Maximum number of cached BrowserSessions per build_browser_automation_node
# instance.  Above this, oldest non-chat scopes are evicted on insertion.
# Can be overridden via ECAN_MAX_BROWSER_CACHE_SIZE env var.
MAX_BROWSER_CACHE_SIZE: int = int(os.environ.get("ECAN_MAX_BROWSER_CACHE_SIZE", "3"))

# Maximum number of cached ``chat:<customer>`` scopes (browser session +
# browser-use Agent) that may be retained simultaneously.  Each entry
# costs ~860 MB (Agent) + browser-session/event-bus overhead, so without
# a cap a long-running front-desk grows by one entry per unique customer
# and quickly exhausts memory (observed RSS 0.3 GB → 9.5 GB in ~12 min
# in customer logs from 2026-04-26).  Eviction order is FIFO based on
# the dict's insertion order; the *current* scope is always preserved.
# Can be overridden via ECAN_MAX_CHAT_SCOPE_CACHE_SIZE env var.
MAX_CHAT_SCOPE_CACHE_SIZE: int = int(os.environ.get("ECAN_MAX_CHAT_SCOPE_CACHE_SIZE", "4"))

# Seconds to wait after creating a fallback blank tab.
NEW_TAB_WAIT_SEC: float = 2.0


# ─────────────────────────────────────────────────────────────────────
# Helpers for normalising inputsValues content
# ─────────────────────────────────────────────────────────────────────

def _content(inputs: dict, key: str) -> Any:
    """Read ``inputs[key]["content"]`` defensively.

    Returns ``None`` if either the key is missing, the entry is not a
    dict, or the entry has no ``content`` field.
    """
    raw = inputs.get(key)
    if isinstance(raw, dict):
        return raw.get("content")
    return None


def _str_content(inputs: dict, key: str, default: str = "") -> str:
    val = _content(inputs, key)
    if val is None:
        return default
    s = str(val).strip()
    return s if s else default


def _bool_content(inputs: dict, key: str, default: bool = False) -> bool:
    val = _content(inputs, key)
    if val is None:
        return default
    return str(val).lower() in ("true", "1", "yes", "on")


def _int_content(inputs: dict, key: str, default: int | None = None) -> int | None:
    val = _content(inputs, key)
    if val in (None, ""):
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _float_content(inputs: dict, key: str, default: float | None = None) -> float | None:
    val = _content(inputs, key)
    if val in (None, ""):
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


# ─────────────────────────────────────────────────────────────────────
# NodeConfig dataclass
# ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class NodeConfig:
    """All build-time configuration for one ``browser_automation`` node.

    Frozen so accidental runtime mutation is caught.  Fields are
    grouped by concern; see ``parse_node_config`` for parsing logic.
    """

    # ── Identity ──────────────────────────────────────────────────
    node_name: str
    skill_name: str
    owner: str

    # ── Provider + legacy task fields ────────────────────────────
    provider: str = "browser-use"
    action: str = "open_page"
    params: dict = field(default_factory=dict)
    task_text_raw: str = ""
    wait_for_done: bool = False

    # ── Browser session settings ──────────────────────────────────
    browser_type: str = "new chromium"          # new chromium | existing chrome | ads power | ...
    browser_driver: str = "native"              # native | cdp
    cdp_port: str = ""                          # "auto" | "0" | numeric str | ""
    headless: bool = False
    profile: str = ""
    keep_browser_alive: bool = False

    # ── Run environment + privacy ────────────────────────────────
    run_environment: str = "full_local"         # full_local | hybrid_cloud | full_cloud
    privacy_strategy: str = "none"
    enable_judge: bool = False
    enable_stealth: bool = False
    user_data_dir: str = ""

    # ── LLM settings ──────────────────────────────────────────────
    llm_provider: str | None = None
    llm_model_name: str | None = None
    use_thinking: bool = False
    use_vision: bool = False

    # ── Performance + step budget ────────────────────────────────
    flash_mode: bool = False
    max_steps: int | None = None
    max_actions_per_step: int | None = None

    # ── Timeouts ──────────────────────────────────────────────────
    enable_guardrail_timer: bool = False
    browser_timeout_seconds: float = 300.0
    hard_timeout: bool = False
    node_timeout_seconds: float | None = None

    # ── DOM reduction ─────────────────────────────────────────────
    dom_focus_selector: str = ""
    dom_limit: int | None = None

    # ── Loop / event semantics ───────────────────────────────────
    loop_history_mode: str = "clear"            # clear | trim:N | accumulate
    actionable_field: str = ""
    event_monitor_done_policy: str = "keep"     # keep | stop

    # ── Shop + downloads path ────────────────────────────────────
    shop_name: str = ""
    downloads_path: str | None = None

    # ── Prompt selection ─────────────────────────────────────────
    prompt_selection: str = "inline"
    system_prompt_id: str | None = None
    user_prompt_id: str | None = None
    inline_system_prompt: str = ""
    inline_user_prompt: str = ""

    # Tools-to-use raw content from inputsValues (resolved later in
    # build_time prompt resolution).
    tools_to_use_raw: str = ""

    # Preserved for hook context / event-monitor parsing.  We keep the
    # raw inputsValues dict so downstream callers don't have to re-parse.
    raw_inputs: dict = field(default_factory=dict)

    # Event-monitor configs are parsed by a sibling module (events.py
    # or session.py) because they need ``parse_monitor_configs`` from
    # event_monitor.py.  Stored as a list of EventMonitorConfig
    # objects (opaque here to avoid an import cycle).
    event_monitor_configs: list = field(default_factory=list)

    # ── Human behavior simulation ────────────────────────────────
    enable_human_behavior: bool = False          # Enable human-like mouse/typing/scroll behavior
    enable_platform_profile: bool = False         # Auto-select profile based on target domain
    use_pc_chrome: bool = False                 # Use PC's existing Chrome with cookies

    # ── Convenience derived properties ────────────────────────────

    @property
    def is_browser_use(self) -> bool:
        return self.provider == "browser-use"

    @property
    def isolate_per_chat(self) -> bool:
        """True when each chat gets its own browser session scope.

        Currently mirrors the old ``isolate_scope`` heuristic
        (browser_scope_key starting with ``chat:``); this is decided
        at runtime, not build time, so we only expose the policy hint.
        """
        return True  # legacy default — runtime resolves the key


# ─────────────────────────────────────────────────────────────────────
# parse_node_config
# ─────────────────────────────────────────────────────────────────────

def parse_node_config(
    config_metadata: dict | None,
    *,
    node_name: str,
    skill_name: str,
    owner: str,
) -> NodeConfig:
    """Parse a ``config_metadata`` payload into a typed ``NodeConfig``.

    Pure function: never raises, never logs at warning level for
    individual missing keys (each has a sensible default).  The only
    log emitted is the timeout-floor enforcement.
    """
    cfg = config_metadata or {}
    inputs = cfg.get("inputsValues") or {}

    # Provider: GUI stores it under inputsValues.tool.content; legacy
    # config_metadata.provider still honored.
    provider = (cfg.get("provider") or "browser-use").lower()
    tool_sel = _str_content(inputs, "tool").lower()
    if tool_sel in ("browser-use", "crawl4ai", "browsebase"):
        provider = tool_sel

    # Browser settings
    browser_type = _str_content(inputs, "browser", "new chromium").lower()
    browser_driver = _str_content(inputs, "browserDriver", "native").lower()
    cdp_port = _str_content(inputs, "cdpPort", "")
    if _bool_content(inputs, "cdpPortAuto"):
        cdp_port = "auto"
    keep_browser_alive = _bool_content(inputs, "keepBrowserAlive")

    # Run env + privacy
    run_environment = _str_content(inputs, "runEnvironment", "full_local").lower()
    privacy_strategy = _str_content(inputs, "privacyStrategy", "none").lower()
    enable_stealth = _bool_content(inputs, "enableStealth")
    user_data_dir = _str_content(inputs, "userDataDir")

    # Timeouts
    browser_timeout_seconds = (
        _float_content(inputs, "timeout_seconds")
        or float(cfg.get("timeout_seconds") or 0)
        or 300.0
    )
    hard_timeout = (
        _bool_content(inputs, "hard_timeout")
        or bool(cfg.get("hard_timeout"))
    )
    enable_guardrail_timer = (
        _bool_content(inputs, "enable_guardrail_timer")
        or bool(cfg.get("enable_guardrail_timer"))
    )
    node_timeout_seconds = (
        _float_content(inputs, "nodeTimeoutSeconds")
        or _float_content(inputs, "timeoutSeconds")
    )
    if node_timeout_seconds is not None and node_timeout_seconds < BROWSER_MIN_TIMEOUT_SEC:
        logger.warning(
            f"[BrowserAutomation] node_timeout_seconds={node_timeout_seconds}s is below "
            f"minimum {BROWSER_MIN_TIMEOUT_SEC}s for browser automation. "
            f"Bumping to {BROWSER_MIN_TIMEOUT_SEC}s to prevent premature timeout."
        )
        node_timeout_seconds = float(BROWSER_MIN_TIMEOUT_SEC)

    # Loop history mode normalisation
    loop_history_raw = _str_content(inputs, "loopHistoryMode", "clear").lower() or "clear"
    if loop_history_raw == "trim":
        loop_history_raw = "trim:10"

    # Event monitor done policy
    em_policy = _str_content(inputs, "eventMonitorDonePolicy", "keep").lower() or "keep"
    if em_policy == "teardown":
        em_policy = "stop"

    # Shop name + downloads path
    shop_sel = _str_content(inputs, "shopName")
    custom_shop = _str_content(inputs, "customShopName")
    shop_name = custom_shop if shop_sel == "custom" else shop_sel
    downloads_path = _resolve_downloads_path(shop_name)

    # Prompt selection
    prompt_selection = _str_content(inputs, "promptSelection", "inline") or "inline"

    inline_system_prompt = _str_content(inputs, "systemPrompt")
    inline_user_prompt = _str_content(inputs, "prompt")
    if prompt_selection and prompt_selection not in ("", "inline"):
        # Saved prompt selected → blank inline so it can't override.
        inline_system_prompt = ""
        inline_user_prompt = ""

    # Tools-to-use raw content (resolved into the system prompt later)
    tools_raw_obj = inputs.get("tools_to_use") or {}
    tools_to_use_raw = (
        tools_raw_obj.get("content", "")
        if isinstance(tools_raw_obj, dict)
        else str(tools_raw_obj or "")
    )

    # Event monitors — parse here so consumers don't have to.
    event_monitor_configs = _parse_event_monitor_configs(inputs)

    # Human behavior simulation
    enable_human_behavior = _bool_content(inputs, "enableHumanBehavior", False)

    # Platform-aware profile selection
    enable_platform_profile = _bool_content(inputs, "enablePlatformProfile", False)
    use_pc_chrome = _bool_content(inputs, "usePcChrome", False)

    # task_text comes from config_metadata directly (legacy path)
    task_text_raw = cfg.get("task") or ""
    if not task_text_raw:
        action = cfg.get("action") or "open_page"
        params = cfg.get("params") or {}
        task_text_raw = f"{action} {params}".strip()

    return NodeConfig(
        node_name=node_name,
        skill_name=skill_name,
        owner=owner or "",
        provider=provider,
        action=cfg.get("action") or "open_page",
        params=dict(cfg.get("params") or {}),
        task_text_raw=task_text_raw,
        wait_for_done=bool(cfg.get("wait_for_done", False)),
        browser_type=browser_type,
        browser_driver=browser_driver,
        cdp_port=cdp_port,
        headless=_bool_content(inputs, "headless"),
        profile=_str_content(inputs, "profile"),
        keep_browser_alive=keep_browser_alive,
        run_environment=run_environment,
        privacy_strategy=privacy_strategy,
        enable_judge=_bool_content(inputs, "enableJudge"),
        enable_stealth=enable_stealth,
        user_data_dir=user_data_dir,
        llm_provider=(
            _str_content(inputs, "modelProvider")
            or _str_content(inputs, "provider")
            or None
        ),
        llm_model_name=(
            _str_content(inputs, "modelName")
            or _str_content(inputs, "model")
            or None
        ),
        use_thinking=_bool_content(inputs, "useThinking"),
        use_vision=_bool_content(inputs, "useVision"),
        flash_mode=_bool_content(inputs, "flashMode"),
        max_steps=_int_content(inputs, "maxSteps"),
        max_actions_per_step=_int_content(inputs, "maxActionsPerStep"),
        enable_guardrail_timer=enable_guardrail_timer,
        browser_timeout_seconds=browser_timeout_seconds,
        hard_timeout=hard_timeout,
        node_timeout_seconds=node_timeout_seconds,
        dom_focus_selector=_str_content(inputs, "domFocusSelector"),
        dom_limit=_int_content(inputs, "domLimit"),
        loop_history_mode=loop_history_raw,
        actionable_field=_str_content(inputs, "actionableField"),
        event_monitor_done_policy=em_policy,
        shop_name=shop_name,
        downloads_path=downloads_path,
        prompt_selection=prompt_selection,
        system_prompt_id=_str_content(inputs, "systemPromptId") or None,
        user_prompt_id=_str_content(inputs, "promptId") or None,
        inline_system_prompt=inline_system_prompt,
        inline_user_prompt=inline_user_prompt,
        tools_to_use_raw=tools_to_use_raw,
        raw_inputs=inputs,
        event_monitor_configs=event_monitor_configs,
        enable_human_behavior=enable_human_behavior,
        enable_platform_profile=enable_platform_profile,
        use_pc_chrome=use_pc_chrome,
    )


def _resolve_downloads_path(shop_name: str) -> str | None:
    """Compute ``<appdata>/daily_work/D<YYYYMMDD>/<shop>/`` if shop_name set."""
    if not shop_name:
        return None
    try:
        from config.app_info import app_info
        appdata = Path(app_info.appdata_path)
        date_str = datetime.now().strftime("%Y%m%d")
        return str(appdata / "daily_work" / f"D{date_str}" / shop_name)
    except Exception:
        return None


def _parse_event_monitor_configs(inputs: dict) -> list:
    """Best-effort parse of event-monitor configs from inputsValues.

    Returns ``[]`` on import failure so a missing event_monitor module
    doesn't poison build-time.  Logs once at info level when configs
    were parsed (mirrors the old behaviour).
    """
    try:
        from agent.ec_skills.browser_use_extension.event_monitor import parse_monitor_configs

        configs = parse_monitor_configs(inputs) or []
        if configs:
            logger.info(
                f"[BrowserAutomation] Parsed {len(configs)} event monitor config(s): "
                f"{[c.label for c in configs]}"
            )
        return configs
    except Exception as exc:
        logger.warning(f"[BrowserAutomation] Failed to parse event monitor configs: {exc}")
        return []
