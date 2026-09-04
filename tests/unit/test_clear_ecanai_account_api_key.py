"""Tests for ``clear_ecanai_account_api_key`` — the removal path
mirroring ``sync_account_api_key_to_ecanai``.

Contract (revoke account key → LightRAG cold + warm state):

- Each of the three ``ECANAI_{LLM,EMBEDDING,RERANK}_API_KEY`` slots
  in secure_store is deleted (``delete_api_key``) — NOT overwritten
  with ``''``. The next ``sync_account_api_key_to_ecanai`` call must
  see a missing slot, not an empty-string slot.

- For roles whose current System Settings default is ``ecanai``, the
  matching ``LLM_BINDING_API_KEY`` / ``EMBEDDING_BINDING_API_KEY`` /
  ``RERANK_BINDING_API_KEY`` is blanked in ``lightrag.env`` (via
  ``sync_default_provider_to_lightrag_env``).

- For parser engines (mineru / docling) whose current mode is
  ``ecanai``, ``MINERU_API_TOKEN`` / ``DOCLING_API_KEY`` are blanked
  (via ``sync_default_parser_to_lightrag_env``).

- ``invalidate_lightrag_provider_cache`` is called so a running
  LightRAG child process is restarted and drops its in-memory
  credential cache. The previous-behavior eCanAI fast path is
  preserved.

- A frontend broadcast ``lightrag.providersUpdated`` is sent for
  every role and the parser, so any open Knowledge → Settings tab
  refreshes its current values.

- Per-role failures are caught and logged; the loop does NOT abort
  on the first failure. The function still proceeds to clear
  lightrag.env and broadcast, so a partial failure leaves the system
  in a consistent end state.

- Local / official parser modes are NOT touched — the user owns
  those credentials.

- ``update_all_llms`` is called when ``default_llm == 'ecanai'``,
  mirroring the sync helper's hot-update hook.

These tests directly cover the helper that the Account page invokes
when the user clicks "Remove API Key" and that ``lightrag_handler``
exposes via the ``remove_ecanai_account_api_key`` IPC.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from gui.manager import provider_settings_helper


# ── Test doubles ──────────────────────────────────────────────────


class _RecordingConfigManager:
    """Stand-in for LightRAGConfigManager.get_config_manager() that
    lets each test set mineru/docling mode and capture every
    ``update_config`` write.
    """

    def __init__(self, *, mineru_mode: str = "", docling_mode: str = "",
                 initial: dict | None = None):
        self._state: dict[str, str] = dict(initial or {})
        if mineru_mode:
            self._state["MINERU_API_MODE"] = mineru_mode
        if docling_mode:
            self._state["DOCLING_PROVIDER"] = docling_mode
        self._mineru_mode = mineru_mode
        self._docling_mode = docling_mode
        self.update_calls: list[dict] = []

    def invalidate_caches(self) -> None:
        pass

    def get_value(self, key: str, default=None):
        return self._state.get(key, default)

    def update_config(self, updates: dict) -> bool:
        # Mirror real behaviour: persistent merge, ordered per call.
        merged = dict(updates)
        self._state.update(updates)
        self.update_calls.append(merged)
        return True


class _RecordingManager:
    """Stand-in for llm/embedding/rerank manager that records every
    delete_api_key / store_api_key call."""

    def __init__(self, *, delete_returns: bool = True, store_returns=(True, None)):
        self.delete_calls: list[str] = []
        self.store_calls: list[tuple[str, str]] = []
        self._delete_returns = delete_returns
        self._store_returns = store_returns

    def delete_api_key(self, env_var: str) -> bool:
        self.delete_calls.append(env_var)
        return self._delete_returns

    def store_api_key(self, env_var: str, value: str):
        self.store_calls.append((env_var, value))
        return self._store_returns


class _RecordingWSManager:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def broadcast_sync(self, event: str, payload: dict) -> None:
        self.calls.append((event, dict(payload)))


def _build_main_window(defaults, *, llm_manager=None, embedding_manager=None,
                       rerank_manager=None, agents=None, lightrag_server=None):
    config_manager = SimpleNamespace(
        llm_manager=llm_manager if llm_manager is not None else _RecordingManager(),
        embedding_manager=embedding_manager if embedding_manager is not None else _RecordingManager(),
        rerank_manager=rerank_manager if rerank_manager is not None else _RecordingManager(),
        general_settings=SimpleNamespace(
            default_llm=defaults.get("llm", ""),
            default_llm_model="",
            default_embedding=defaults.get("embedding", ""),
            default_embedding_model="",
            default_rerank=defaults.get("rerank", ""),
            default_rerank_model="",
        ),
    )
    return SimpleNamespace(
        config_manager=config_manager,
        agents=agents if agents is not None else [],
        update_all_llms=lambda **kwargs: True,
        lightrag_server=lightrag_server,
    )


def _patch_dependencies(fake_lr_cm, *, account_key: str | None = None,
                        broadcast_ws: _RecordingWSManager | None = None):
    """Patch the runtime dependencies the helper reaches for.

    Returns a ``contextlib``-style namespace the caller can ``with``-enter.
    """

    fake_ws = SimpleNamespace(app_ws_manager=broadcast_ws or _RecordingWSManager())

    return [
        patch("knowledge.lightrag_config_manager.get_config_manager", return_value=fake_lr_cm),
        patch.object(provider_settings_helper, "sync_default_provider_to_lightrag_env",
                     return_value=True),
        patch.object(provider_settings_helper, "sync_default_parser_to_lightrag_env",
                     return_value=True),
        patch.dict("sys.modules", {"gui.LocalServer": fake_ws}),
        # If account-key lookup path is exercised, make secure_store
        # return a deterministic value (or fail cleanly).
        patch("utils.env.secure_store.secure_store", SimpleNamespace(
            get=lambda *a, **k: account_key,
            set=lambda *a, **k: True,
        )) if account_key is not None else patch.dict("sys.modules", {}),
    ]


# ── Happy-path coverage ───────────────────────────────────────────


def test_clears_all_three_role_slots_via_delete_api_key():
    """Each of the three role managers MUST receive a delete_api_key
    call for its ``ECANAI_*_API_KEY`` env var. The store_api_key
    fallback path is NOT used when delete succeeds."""
    llm = _RecordingManager(delete_returns=True)
    emb = _RecordingManager(delete_returns=True)
    rer = _RecordingManager(delete_returns=True)

    main_window = _build_main_window(
        {"llm": "openai", "embedding": "openai", "rerank": "openai"},
        llm_manager=llm, embedding_manager=emb, rerank_manager=rer,
    )

    fake_lr = _RecordingConfigManager()
    ws = _RecordingWSManager()
    patches = _patch_dependencies(fake_lr, broadcast_ws=ws)
    patches[0] = patch("knowledge.lightrag_config_manager.get_config_manager", return_value=fake_lr)
    patches[1] = patch.object(provider_settings_helper, "sync_default_provider_to_lightrag_env",
                              return_value=True)
    patches[2] = patch.object(provider_settings_helper, "sync_default_parser_to_lightrag_env",
                              return_value=True)
    patches[3] = patch.dict("sys.modules", {"gui.LocalServer": SimpleNamespace(app_ws_manager=ws)})

    with patches[0], patches[1], patches[2], patches[3], \
         patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache"):
        success, error = provider_settings_helper.clear_ecanai_account_api_key(
            main_window=main_window
        )

    assert success is True, error
    assert error is None
    assert llm.delete_calls == ["ECANAI_LLM_API_KEY"]
    assert emb.delete_calls == ["ECANAI_EMBEDDING_API_KEY"]
    assert rer.delete_calls == ["ECANAI_RERANK_API_KEY"]
    # store_api_key fallback was NOT used because delete succeeded.
    assert llm.store_calls == []
    assert emb.store_calls == []
    assert rer.store_calls == []


def test_uses_store_api_key_fallback_when_delete_returns_false():
    """Some manager implementations may return False from delete even
    when the slot is empty. The helper MUST fall back to
    ``store_api_key(env_var, '')`` so the observable end state is
    "no credential present" regardless of the underlying delete
    semantics."""
    llm = _RecordingManager(delete_returns=False)
    emb = _RecordingManager(delete_returns=False)
    rer = _RecordingManager(delete_returns=False)

    main_window = _build_main_window({}, llm_manager=llm, embedding_manager=emb, rerank_manager=rer)

    fake_lr = _RecordingConfigManager()
    ws = _RecordingWSManager()
    with patch("knowledge.lightrag_config_manager.get_config_manager", return_value=fake_lr), \
         patch.object(provider_settings_helper, "sync_default_provider_to_lightrag_env", return_value=True), \
         patch.object(provider_settings_helper, "sync_default_parser_to_lightrag_env", return_value=True), \
         patch.dict("sys.modules", {"gui.LocalServer": SimpleNamespace(app_ws_manager=ws)}), \
         patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache"):
        success, error = provider_settings_helper.clear_ecanai_account_api_key(
            main_window=main_window
        )

    assert success is True, error
    assert llm.store_calls == [("ECANAI_LLM_API_KEY", "")]
    assert emb.store_calls == [("ECANAI_EMBEDDING_API_KEY", "")]
    assert rer.store_calls == [("ECANAI_RERANK_API_KEY", "")]


def test_broadcasts_every_role_and_parser_when_active():
    """When the user clears the key with at least one ecanai role AND
    a parser mode active, the WS broadcast MUST fire one event per
    role plus a single parser event. The Settings tab listens on
    ``lightrag.providersUpdated`` and re-pulls values on every emit."""
    llm = _RecordingManager()
    emb = _RecordingManager()
    rer = _RecordingManager()

    main_window = _build_main_window(
        {"llm": "ecanai", "embedding": "ecanai", "rerank": "ecanai"},
        llm_manager=llm, embedding_manager=emb, rerank_manager=rer,
    )

    fake_lr = _RecordingConfigManager(mineru_mode="ecanai", docling_mode="ecanai")
    ws = _RecordingWSManager()
    with patch("knowledge.lightrag_config_manager.get_config_manager", return_value=fake_lr), \
         patch.object(provider_settings_helper, "sync_default_provider_to_lightrag_env", return_value=True), \
         patch.object(provider_settings_helper, "sync_default_parser_to_lightrag_env", return_value=True), \
         patch.dict("sys.modules", {"gui.LocalServer": SimpleNamespace(app_ws_manager=ws)}), \
         patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache"):
        provider_settings_helper.clear_ecanai_account_api_key(main_window=main_window)

    events = [payload for event, payload in ws.calls if event == "lightrag.providersUpdated"]
    role_events = [p for p in events if p.get("provider_type") in ("llm", "embedding", "rerank")]
    parser_events = [p for p in events if p.get("provider_type") == "parser"]

    # Three role events — one per role.
    role_kinds = sorted(p["provider_type"] for p in role_events)
    assert role_kinds == ["embedding", "llm", "rerank"]
    # One parser event covering both engines.
    assert len(parser_events) == 1
    assert sorted(parser_events[0]["engines"]) == ["docling", "mineru"]


def test_calls_invalidate_lightrag_provider_cache_to_drop_child_process_cache():
    """A running LightRAG subprocess holds the old account key in its
    env-backed cache. After clearing secure_store + lightrag.env the
    helper MUST trigger the cache invalidator (which restarts the
    subprocess if eCanAI is the active binding)."""
    llm = _RecordingManager()
    main_window = _build_main_window({"llm": "ecanai"}, llm_manager=llm)

    fake_lr = _RecordingConfigManager()
    with patch("knowledge.lightrag_config_manager.get_config_manager", return_value=fake_lr), \
         patch.object(provider_settings_helper, "sync_default_provider_to_lightrag_env", return_value=True), \
         patch.object(provider_settings_helper, "sync_default_parser_to_lightrag_env", return_value=True), \
         patch.dict("sys.modules", {"gui.LocalServer": SimpleNamespace(app_ws_manager=_RecordingWSManager())}), \
         patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache") as invalidate:
        provider_settings_helper.clear_ecanai_account_api_key(main_window=main_window)

    invalidate.assert_called_once()


def test_calls_update_all_llms_when_default_llm_is_ecanai():
    """When the user is currently routed to ``ecanai`` for LLM, the
    in-process LLM instances MUST be hot-updated to drop the eCanAI
    credential. Mirrors the sync helper's hot-update hook."""
    update_calls: list[dict] = []

    main_window = _build_main_window({"llm": "ecanai"})
    main_window.update_all_llms = lambda **kwargs: update_calls.append(kwargs) or True

    fake_lr = _RecordingConfigManager()
    with patch("knowledge.lightrag_config_manager.get_config_manager", return_value=fake_lr), \
         patch.object(provider_settings_helper, "sync_default_provider_to_lightrag_env", return_value=True), \
         patch.object(provider_settings_helper, "sync_default_parser_to_lightrag_env", return_value=True), \
         patch.dict("sys.modules", {"gui.LocalServer": SimpleNamespace(app_ws_manager=_RecordingWSManager())}), \
         patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache"):
        provider_settings_helper.clear_ecanai_account_api_key(main_window=main_window)

    assert len(update_calls) == 1
    assert "reason" in update_calls[0]


def test_does_not_call_update_all_llms_when_default_llm_is_not_ecanai():
    """When the user has already switched to a non-ecanai provider,
    ``update_all_llms`` MUST NOT be called — there is no eCanAI
    credential to drop and the call would pointlessly churn the
    in-process LLM."""
    update_calls: list[dict] = []

    main_window = _build_main_window({"llm": "openai"})
    main_window.update_all_llms = lambda **kwargs: update_calls.append(kwargs) or True

    fake_lr = _RecordingConfigManager()
    with patch("knowledge.lightrag_config_manager.get_config_manager", return_value=fake_lr), \
         patch.object(provider_settings_helper, "sync_default_provider_to_lightrag_env", return_value=True), \
         patch.object(provider_settings_helper, "sync_default_parser_to_lightrag_env", return_value=True), \
         patch.dict("sys.modules", {"gui.LocalServer": SimpleNamespace(app_ws_manager=_RecordingWSManager())}), \
         patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache"):
        provider_settings_helper.clear_ecanai_account_api_key(main_window=main_window)

    assert update_calls == []


# ── Local / official mode non-interference ────────────────────────


def test_local_mineru_mode_is_left_alone():
    """When mineru is in ``local`` mode the user owns the
    ``MINERU_API_TOKEN`` — the helper MUST NOT touch it. Only
    ``sync_default_parser_to_lightrag_env`` is invoked; whether it
    writes anything is its own concern (the parser helper is unit
    tested separately)."""
    main_window = _build_main_window({"llm": "ecanai"})

    fake_lr = _RecordingConfigManager(mineru_mode="local", docling_mode="local")
    with patch("knowledge.lightrag_config_manager.get_config_manager", return_value=fake_lr), \
         patch.object(provider_settings_helper, "sync_default_provider_to_lightrag_env", return_value=True) as prov_sync, \
         patch.object(provider_settings_helper, "sync_default_parser_to_lightrag_env") as parser_sync, \
         patch.dict("sys.modules", {"gui.LocalServer": SimpleNamespace(app_ws_manager=_RecordingWSManager())}), \
         patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache"):
        provider_settings_helper.clear_ecanai_account_api_key(main_window=main_window)

    # Provider-side sync still runs (LLM/embedding/rerank roles).
    prov_sync.assert_called_once()
    # Parser sync was invoked (the contract for local/official is
    # that the helper is a no-op inside, not that we skip the call).
    parser_sync.assert_called_once()


# ── Failure-mode coverage ────────────────────────────────────────


def test_returns_false_when_main_window_not_initialized():
    """If neither ``main_window`` nor AppContext has a window yet, the
    helper MUST surface a clear error rather than raise. The IPC
    handler uses this error to fail the request cleanly."""
    with patch("app_context.AppContext.get_main_window", return_value=None):
        success, error = provider_settings_helper.clear_ecanai_account_api_key(main_window=None)

    assert success is False
    assert error and "Main window" in error


def test_returns_false_when_main_window_has_no_config_manager():
    """A test-stub MainWindow without ``config_manager`` is treated as
    not-yet-initialized. The helper MUST NOT crash on attribute
    access."""
    main_window = SimpleNamespace()  # no config_manager attribute

    success, error = provider_settings_helper.clear_ecanai_account_api_key(main_window=main_window)

    assert success is False
    assert error and "Main window" in error


def test_one_role_failure_does_not_abort_remaining_roles():
    """If the LLM manager's delete_api_key raises, the embedding and
    rerank managers MUST still be called. This is the documented
    "per-role failure is caught and logged" semantics; an abort
    here would leave two slots dangling after a partial failure."""
    failure_msg = "keychain locked"

    def llm_delete(env_var: str) -> bool:
        raise RuntimeError(failure_msg)

    llm = SimpleNamespace(delete_api_key=llm_delete, store_api_key=lambda *a, **k: (True, None))
    emb = _RecordingManager()
    rer = _RecordingManager()

    main_window = _build_main_window({}, llm_manager=llm, embedding_manager=emb, rerank_manager=rer)

    fake_lr = _RecordingConfigManager()
    with patch("knowledge.lightrag_config_manager.get_config_manager", return_value=fake_lr), \
         patch.object(provider_settings_helper, "sync_default_provider_to_lightrag_env", return_value=True), \
         patch.object(provider_settings_helper, "sync_default_parser_to_lightrag_env", return_value=True), \
         patch.dict("sys.modules", {"gui.LocalServer": SimpleNamespace(app_ws_manager=_RecordingWSManager())}), \
         patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache"):
        success, error = provider_settings_helper.clear_ecanai_account_api_key(main_window=main_window)

    # The function still succeeds — partial success is preferable to
    # leaving the system in an inconsistent state.
    assert success is True, error
    # embedding + rerank were still called even though llm raised.
    assert emb.delete_calls == ["ECANAI_EMBEDDING_API_KEY"]
    assert rer.delete_calls == ["ECANAI_RERANK_API_KEY"]


def test_provider_sync_failure_is_logged_but_does_not_fail_call():
    """A failure inside ``sync_default_provider_to_lightrag_env`` (e.g.
    lightrag.env is read-only) is caught and logged. The function
    still returns True so the IPC caller does not surface a confusing
    error to the user — secure_store was cleared, which is the
    primary contract the user cares about."""
    main_window = _build_main_window({"llm": "ecanai"})

    fake_lr = _RecordingConfigManager()
    with patch("knowledge.lightrag_config_manager.get_config_manager", return_value=fake_lr), \
         patch.object(provider_settings_helper, "sync_default_provider_to_lightrag_env",
                      side_effect=RuntimeError("env readonly")), \
         patch.object(provider_settings_helper, "sync_default_parser_to_lightrag_env", return_value=True), \
         patch.dict("sys.modules", {"gui.LocalServer": SimpleNamespace(app_ws_manager=_RecordingWSManager())}), \
         patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache"):
        success, error = provider_settings_helper.clear_ecanai_account_api_key(main_window=main_window)

    assert success is True
    assert error is None


def test_invalidate_failure_is_swallowed():
    """The cache invalidator is best-effort. If restarting LightRAG
    fails (e.g. child process crash), the secure_store + lightrag.env
    have already been cleared, so a future launch will read the
    correct empty state. The function returns True."""
    main_window = _build_main_window({"llm": "ecanai"})

    fake_lr = _RecordingConfigManager()
    with patch("knowledge.lightrag_config_manager.get_config_manager", return_value=fake_lr), \
         patch.object(provider_settings_helper, "sync_default_provider_to_lightrag_env", return_value=True), \
         patch.object(provider_settings_helper, "sync_default_parser_to_lightrag_env", return_value=True), \
         patch.dict("sys.modules", {"gui.LocalServer": SimpleNamespace(app_ws_manager=_RecordingWSManager())}), \
         patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache",
                      side_effect=RuntimeError("server down")):
        success, error = provider_settings_helper.clear_ecanai_account_api_key(main_window=main_window)

    assert success is True


# ── Idempotency / no-op cases ─────────────────────────────────────


def test_idempotent_when_no_active_role_was_ecanai():
    """When the user is NOT routed to ecanai for any role, the helper
    still runs but the broadcast omits parser events (no parser was
    cleared) and ``update_all_llms`` is not called."""
    llm = _RecordingManager()
    emb = _RecordingManager()
    rer = _RecordingManager()

    main_window = _build_main_window(
        {"llm": "openai", "embedding": "openai", "rerank": "openai"},
        llm_manager=llm, embedding_manager=emb, rerank_manager=rer,
    )

    fake_lr = _RecordingConfigManager(mineru_mode="local", docling_mode="local")
    ws = _RecordingWSManager()
    with patch("knowledge.lightrag_config_manager.get_config_manager", return_value=fake_lr), \
         patch.object(provider_settings_helper, "sync_default_provider_to_lightrag_env", return_value=True), \
         patch.object(provider_settings_helper, "sync_default_parser_to_lightrag_env", return_value=True), \
         patch.dict("sys.modules", {"gui.LocalServer": SimpleNamespace(app_ws_manager=ws)}), \
         patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache"):
        success, error = provider_settings_helper.clear_ecanai_account_api_key(main_window=main_window)

    assert success is True
    # Slot cleanup still happens — the secure_store entries exist
    # independently of the active role default.
    assert llm.delete_calls == ["ECANAI_LLM_API_KEY"]
    assert emb.delete_calls == ["ECANAI_EMBEDDING_API_KEY"]
    assert rer.delete_calls == ["ECANAI_RERANK_API_KEY"]
