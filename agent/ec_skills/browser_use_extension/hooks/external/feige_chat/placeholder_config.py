"""过渡话术 (placeholder) settings — per-store, GUI-editable.

Background
----------
``placeholder_timer`` types a short stand-by line ("人工服务正在回复中...")
when a customer's real reply is late, so Feige's 未回复 red-flag clock
resets.  The text has been operator-tunable since mt048A, but only by
hand-editing ``<user_data_home>/ecan/placeholder_texts.json`` — a file our
integration partner cannot reasonably talk a 店主 through.

This module adds the GUI tiers behind the bundle's own config panel
(Plugins page → feige_chat → Config → ``gui/config.html``), keeping the
legacy file working for already-deployed installs.

Precedence (each field resolved independently)
----------------------------------------------
1. **Per-store override** — ``plugin_storage['feige_chat']['placeholder:<store>']``
2. **Account default** — ``plugin_config['feige_chat']``, user overrides ONLY.
   Deliberately not ``plugin_config.merged()``: a manifest default is not a
   user choice and must not outrank the operator's env var.
3. **Env** — ``ECAN_FEIGE_PLACEHOLDER_*`` (Fast Deploy seeds the timeout).
4. **Legacy file** — texts only; still resolved inside ``placeholder_timer``
   so its mt048A loader and tests stay exactly as they were.
5. **Built-in default**.

The GUI deliberately outranks env (decision 2026-09-21): once a 店主 can type
the phrase into a panel, a support-set env var that silently wins makes Save
look broken.  The panel surfaces the env value when one is set, so support can
still see why a number looks the way it does.

Store identity
--------------
``current_store_key()`` is the shared notion of "which store is this run
serving".  Today that resolves to the agent id, because Fast Deploy creates one
agent per store; the resolver checks a ``store_key``/``store_id`` scope field
first so a future platform stamp (derived from ``prompt_refs.store_url`` in
``browser_node/runner.extract_store_url``) upgrades every caller at once.
Billing's per-store dimension is meant to call THIS function — if store
identity ever forks in two, the config panel and the bill start disagreeing
about how many stores the customer has.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Optional

from utils.logger_helper import logger_helper as logger

BUNDLE = "feige_chat"

# Field names — identical in the per-store blob, the account config and the
# panel's form, so a reader only has to learn them once.
K_ENABLED = "placeholder_enabled"
K_TIMEOUT = "placeholder_timeout_s"
K_TEXTS = "placeholder_texts"

# plugin_storage keys.
STORE_KEY_PREFIX = "placeholder:"
STORE_REGISTRY_KEY = "stores"

# Cap mirrors placeholder_timer._PLACEHOLDER_MAX_TEXTS — the dedup cache needs
# headroom, and a 店主 with 6 phrases silently losing one is a support ticket.
MAX_TEXTS = 5

# When the switch is turned on in the GUI but no deadline was ever set, use the
# value every worked example in the docs uses.
DEFAULT_ENABLED_TIMEOUT_S = 20.0

# Re-read the two small JSON files at most this often.  Bounded staleness is
# what kills the "saved in the GUI, still need to restart the app" trap; 1 s is
# far below the placeholder deadline, so a save lands on the next turn.
_CACHE_TTL_S = 1.0

_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, dict]] = {}

# The registry is written from arm(), i.e. the dispatch path, so it is written
# ONCE PER STORE PER PROCESS rather than on a timer: plugin_storage.set is a
# synchronous read-modify-write, and this codebase has paid for putting
# synchronous work on the dispatch/CDP loop more than once (ws087 deflate,
# ws175 dispatch-lock).  One small write per store per app run is enough — the
# picker only needs the store to exist and a last_seen to order by.
_store_noted: set[str] = set()


# ---------------------------------------------------------------------------
# Store identity
# ---------------------------------------------------------------------------
def _scope() -> dict:
    try:
        from utils.log_scope import get_scope
        return get_scope() or {}
    except Exception:
        return {}


def current_store_key() -> str:
    """Which store the current run serves ("" = no run context → account default).

    Resolved in the dispatch context, never in the sweeper thread: ContextVars
    do not cross ``threading.Thread``, so callers stamp the resolved key onto
    the timer entry at arm() time instead of re-resolving it when it fires.
    """
    env = (os.getenv("ECAN_FEIGE_STORE_ID") or "").strip()
    if env:
        return env
    sc = _scope()
    for field in ("store_key", "store_id"):
        val = str(sc.get(field) or "").strip()
        if val:
            return val
    return str(sc.get("agent_id") or "").strip()


def current_store_label() -> str:
    """Human label for the store selector — the agent name a 店主 recognises."""
    sc = _scope()
    for field in ("store_name", "agent_name", "task_name"):
        val = str(sc.get(field) or "").strip()
        if val:
            return val
    return ""


def note_active_store() -> None:
    """Record this store in the bundle's KV so the config panel can list it.

    The panel is a global-scope iframe with no run context of its own, so the
    runtime is the only thing that knows which stores actually exist.  Once per
    store per process, and fully best-effort: a failure here must never touch
    the reply path.
    """
    key = current_store_key()
    if not key or key in _store_noted:
        return
    _store_noted.add(key)   # marked before the write: one attempt, never a retry loop
    now = time.time()
    try:
        from agent.ec_skills.browser_use_extension import plugin_storage
        stores = plugin_storage.get(BUNDLE, STORE_REGISTRY_KEY, None)
        if not isinstance(stores, dict):
            stores = {}
        prev = stores.get(key)
        prev = prev if isinstance(prev, dict) else {}
        label = current_store_label()
        stores[key] = {
            "label": label or prev.get("label") or key,
            "last_seen": int(now),
            # The panel is an iframe and can read neither the process env nor
            # the pre-GUI text file, so mirror both here (throttled, once per
            # store per 5 min): support needs to see WHY a deadline is what it
            # is, and a 店主 upgrading from the file needs to see the phrase
            # they already have before deciding to adopt it.
            "env_timeout_s": _env_timeout(),
            "legacy_texts": _legacy_texts(),
        }
        plugin_storage.set(BUNDLE, STORE_REGISTRY_KEY, stores)
    except Exception as exc:
        logger.debug(f"[placeholder_config] store registry note failed: {exc}")


# ---------------------------------------------------------------------------
# Tier readers — each degrades to {} when the plugin system isn't available
# (cloud worker, unit test, bundle loaded by raw path rather than installed).
# ---------------------------------------------------------------------------
def _account_config() -> dict:
    try:
        from agent.ec_skills.browser_use_extension import plugin_config
        data = plugin_config.get(BUNDLE)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.debug(f"[placeholder_config] account config unavailable: {exc}")
        return {}


def _store_config(store_key: str) -> dict:
    if not store_key:
        return {}
    try:
        from agent.ec_skills.browser_use_extension import plugin_storage
        data = plugin_storage.get(BUNDLE, STORE_KEY_PREFIX + store_key, None)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.debug(f"[placeholder_config] store config unavailable: {exc}")
        return {}


# ---------------------------------------------------------------------------
# Validation — mirrors placeholder_timer's mt048A file rules exactly, so the
# panel can never save a list the loader would silently shorten.
# ---------------------------------------------------------------------------
def sanitize_texts(raw: Any) -> Optional[list[str]]:
    """Strip / drop empties / dedupe / cap.  ``None`` when nothing usable."""
    if not isinstance(raw, (list, tuple)):
        return None
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
        if len(cleaned) >= MAX_TEXTS:
            break
    return cleaned or None


def _coerce_timeout(raw: Any) -> Optional[float]:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    return val if val >= 0 else None


def _coerce_enabled(raw: Any) -> Optional[bool]:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    return None


def _env_timeout() -> Optional[float]:
    return _coerce_timeout(os.getenv("ECAN_FEIGE_PLACEHOLDER_TIMEOUT_S"))


# ---------------------------------------------------------------------------
# Legacy-file visibility
# ---------------------------------------------------------------------------
def _legacy_texts() -> Optional[list[str]]:
    """The pre-GUI ``placeholder_texts.json`` list, for DISPLAY only.

    Deliberately never written into the account config behind the operator's
    back: an earlier draft copied it on first read, and a single test run was
    enough for a getter's side effect to rewrite real machine state.  The panel
    instead shows this as the current effective value and lets the 店主 adopt
    it with an explicit Save.
    """
    try:
        from . import placeholder_timer
        return sanitize_texts(placeholder_timer._load_placeholder_texts_from_file())
    except Exception as exc:
        logger.debug(f"[placeholder_config] legacy file unreadable: {exc}")
        return None


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------
def _resolve(store_key: str) -> dict:
    store = _store_config(store_key)
    account = _account_config()

    texts = sanitize_texts(store.get(K_TEXTS))
    texts_source = "store"
    if texts is None:
        texts = sanitize_texts(account.get(K_TEXTS))
        texts_source = "account"
    if texts is None:
        texts_source = ""

    enabled = _coerce_enabled(store.get(K_ENABLED))
    enabled_source = "store"
    if enabled is None:
        enabled = _coerce_enabled(account.get(K_ENABLED))
        enabled_source = "account"
    if enabled is None:
        enabled_source = ""

    timeout = _coerce_timeout(store.get(K_TIMEOUT))
    timeout_source = "store"
    if timeout is None:
        timeout = _coerce_timeout(account.get(K_TIMEOUT))
        timeout_source = "account"
    if timeout is None:
        timeout = _env_timeout()
        timeout_source = "env" if timeout is not None else ""

    return {
        "store_key": store_key,
        "texts": texts,
        "texts_source": texts_source,
        "enabled": enabled,
        "enabled_source": enabled_source,
        "timeout_s": timeout,
        "timeout_source": timeout_source,
        "env_timeout_s": _env_timeout(),
    }


def settings(store_key: Optional[str] = None) -> dict:
    """Resolved GUI tiers for ``store_key`` (defaults to the current run's).

    ``texts`` / ``enabled`` / ``timeout_s`` are ``None`` when no GUI tier set
    them — the caller then keeps whatever it did before this feature existed.
    """
    key = current_store_key() if store_key is None else str(store_key or "")
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and (now - hit[0]) < _CACHE_TTL_S:
            return hit[1]
    resolved = _resolve(key)
    with _cache_lock:
        _cache[key] = (now, resolved)
    return resolved


def invalidate() -> None:
    """Drop the read cache (tests; and any in-process writer)."""
    with _cache_lock:
        _cache.clear()


def texts_override(store_key: Optional[str] = None) -> Optional[list[str]]:
    """GUI-configured placeholder texts, or ``None`` to use the legacy tiers."""
    try:
        return settings(store_key).get("texts")
    except Exception as exc:
        logger.debug(f"[placeholder_config] texts_override failed: {exc}")
        return None


def timeout_override(store_key: Optional[str] = None) -> Optional[float]:
    """Effective placeholder deadline from the GUI tiers, else ``None``.

    Returns ``0.0`` when the GUI switch is explicitly off — that is a real
    answer ("disabled"), not an absence, and it must outrank the env var the
    same way an explicitly typed deadline does.
    """
    try:
        resolved = settings(store_key)
    except Exception as exc:
        logger.debug(f"[placeholder_config] timeout_override failed: {exc}")
        return None
    enabled = resolved.get("enabled")
    timeout = resolved.get("timeout_s")
    if enabled is False:
        return 0.0
    if enabled is True:
        # Switched on with no deadline typed anywhere: fall back to the
        # documented example rather than 0, which would mean "off".
        return timeout if timeout and timeout > 0 else DEFAULT_ENABLED_TIMEOUT_S
    if resolved.get("timeout_source") in ("store", "account"):
        return timeout
    return None


def effective_timeout_s(store_key: Optional[str] = None) -> float:
    """The placeholder deadline every caller should use (0 = disabled).

    GUI tier when one is set, otherwise the pre-existing env/default tunable —
    so an install that never opens the config panel behaves exactly as it did.
    """
    override = timeout_override(store_key)
    if override is not None:
        return override
    try:
        from .tunables import resolve_float, DEFAULT_FEIGE_PLACEHOLDER_TIMEOUT_S
        return resolve_float(
            "FEIGE_PLACEHOLDER_TIMEOUT_S", DEFAULT_FEIGE_PLACEHOLDER_TIMEOUT_S, None
        )
    except Exception as exc:
        logger.debug(f"[placeholder_config] tunable fallback failed: {exc}")
        return 0.0
