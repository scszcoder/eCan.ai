"""Tests for the eCanAI parser sync path inside ``sync_account_api_key_to_ecanai``.

Contract (account key rotation → LightRAG parser path):

- When the account key changes, every eCanAI-mode parser (mineru / docling)
  must have its env file ``MINERU_API_TOKEN`` / ``DOCLING_API_KEY`` updated
  to the new account key. Without this, the running LightRAG child process
  keeps using the previous (now stale) credential.
- Local / official modes own their own user-typed credentials and MUST NOT
  be touched on account-key rotation.
- The LightRAG cache invalidator (and therefore the restart hook) must
  trigger when ANY eCanAI consumer is active — LLM / embedding / rerank
  defaults OR parser modes (mineru / docling).
- A frontend broadcast for ``parser`` is sent so an open Settings tab
  re-pulls the parser engine current values.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from gui.manager import provider_settings_helper


def _build_main_window(defaults, *, lightrag_server=None):
    """Build a minimal main_window stand-in with the given default-* roles."""

    def manager():
        return SimpleNamespace(store_api_key=lambda env_var, value: (True, None))

    config_manager = SimpleNamespace(
        llm_manager=manager(),
        embedding_manager=manager(),
        rerank_manager=manager(),
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
        agents=[],
        update_all_llms=lambda **_k: True,
        lightrag_server=lightrag_server,
    )


class _FakeConfigManager:
    """Minimal stand-in for LightRAGConfigManager.get_config_manager() that
    lets the test set mineru/docling mode + capture update_config calls."""

    def __init__(self, *, mineru_mode: str = "", docling_mode: str = ""):
        self._mineru_mode = mineru_mode
        self._docling_mode = docling_mode
        self.update_calls: list[dict] = []

    def invalidate_caches(self) -> None:
        pass

    def get_value(self, key: str, default=None):
        if key == "MINERU_API_MODE":
            return self._mineru_mode
        if key == "DOCLING_PROVIDER":
            return self._docling_mode
        return default

    def update_config(self, updates: dict) -> bool:
        self.update_calls.append(dict(updates))
        return True


def test_mineru_ecanai_writes_account_key_to_lightrag_env():
    """When mineru is in ecanai mode, MINERU_API_TOKEN must be written to
    lightrag.env with the latest account key."""
    fake_cm = _FakeConfigManager(mineru_mode="ecanai", docling_mode="")

    main_window = _build_main_window({"llm": "openai"})

    with patch("knowledge.lightrag_config_manager.get_config_manager", return_value=fake_cm), \
         patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache") as invalidate:
        success, error = provider_settings_helper.sync_account_api_key_to_ecanai(
            "rotated-account-key-9876543210",
            main_window=main_window,
        )

    assert success and error is None
    assert len(fake_cm.update_calls) == 1
    assert fake_cm.update_calls[0] == {"MINERU_API_TOKEN": "rotated-account-key-9876543210"}
    # DOCLING_API_KEY must NOT appear when docling is not in ecanai mode.
    assert "DOCLING_API_KEY" not in fake_cm.update_calls[0]
    # The restart hook must be triggered because the mineru parser is active.
    invalidate.assert_called_once_with("llm", "ecanai")


def test_docling_ecanai_writes_account_key_to_lightrag_env():
    """When docling is in ecanai mode, DOCLING_API_KEY must be written."""
    fake_cm = _FakeConfigManager(mineru_mode="", docling_mode="ecanai")

    main_window = _build_main_window({"llm": "openai"})

    with patch("knowledge.lightrag_config_manager.get_config_manager", return_value=fake_cm), \
         patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache") as invalidate:
        success, _error = provider_settings_helper.sync_account_api_key_to_ecanai(
            "rotated-account-key",
            main_window=main_window,
        )

    assert success
    assert fake_cm.update_calls == [{"DOCLING_API_KEY": "rotated-account-key"}]
    invalidate.assert_called_once_with("llm", "ecanai")


def test_mineru_and_docling_both_ecanai_writes_both_keys():
    """Both parser engines can be in ecanai mode simultaneously; both env
    vars must be written in a single update_config call to avoid an
    intermediate restart between them."""
    fake_cm = _FakeConfigManager(mineru_mode="ecanai", docling_mode="ecanai")

    main_window = _build_main_window({"llm": "openai"})

    with patch("knowledge.lightrag_config_manager.get_config_manager", return_value=fake_cm), \
         patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache"):
        success, _ = provider_settings_helper.sync_account_api_key_to_ecanai(
            "rotated-account-key",
            main_window=main_window,
        )

    assert success
    assert fake_cm.update_calls == [{
        "MINERU_API_TOKEN": "rotated-account-key",
        "DOCLING_API_KEY": "rotated-account-key",
    }]


def test_local_mineru_mode_does_not_touch_env():
    """Local mode owns its own credential; account key rotation MUST NOT
    overwrite MINERU_API_TOKEN (which belongs to the user's local MinerU)."""
    fake_cm = _FakeConfigManager(mineru_mode="local", docling_mode="local")

    main_window = _build_main_window({"llm": "openai"})

    with patch("knowledge.lightrag_config_manager.get_config_manager", return_value=fake_cm), \
         patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache") as invalidate:
        success, _ = provider_settings_helper.sync_account_api_key_to_ecanai(
            "rotated-account-key",
            main_window=main_window,
        )

    assert success
    # No parser env writes happened.
    assert fake_cm.update_calls == []
    # No active consumer at all → no restart trigger.
    invalidate.assert_called_once_with()


def test_official_mineru_mode_does_not_touch_env():
    """Official mode owns its own credential (e.g. a user-purchased
    mineru.net key). Account key rotation MUST NOT leak into MINERU_API_TOKEN."""
    fake_cm = _FakeConfigManager(mineru_mode="official", docling_mode="official")

    main_window = _build_main_window({"llm": "openai"})

    with patch("knowledge.lightrag_config_manager.get_config_manager", return_value=fake_cm), \
         patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache"):
        provider_settings_helper.sync_account_api_key_to_ecanai(
            "rotated-account-key",
            main_window=main_window,
        )

    assert fake_cm.update_calls == []


def test_parser_only_triggers_restart_when_no_active_provider():
    """If LLM/embedding/rerank are NOT eCanAI but mineru IS, the restart
    hook must still fire (currently-running LightRAG has mineru baked in)."""
    fake_cm = _FakeConfigManager(mineru_mode="ecanai", docling_mode="")

    # NO active provider role is eCanAI.
    main_window = _build_main_window(
        {"llm": "openai", "embedding": "openai", "rerank": "openai"}
    )

    with patch("knowledge.lightrag_config_manager.get_config_manager", return_value=fake_cm), \
         patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache") as invalidate:
        provider_settings_helper.sync_account_api_key_to_ecanai(
            "rotated-account-key",
            main_window=main_window,
        )

    invalidate.assert_called_once_with("llm", "ecanai")


def test_broadcast_includes_parser_role_when_parser_was_updated():
    """Frontend Settings UI listens for `lightrag.providersUpdated` and
    re-pulls parser engine current values when a `parser` event fires.
    Without this, an open Settings tab displays the stale account key
    after rotation."""
    fake_cm = _FakeConfigManager(mineru_mode="ecanai", docling_mode="ecanai")

    main_window = _build_main_window({"llm": "ecanai", "embedding": "ecanai", "rerank": "ecanai"})

    broadcast_calls: list[tuple] = []

    class _FakeWSManager:
        def broadcast_sync(self, event: str, payload: dict) -> None:
            broadcast_calls.append((event, payload))

    fake_ws_module = SimpleNamespace(app_ws_manager=_FakeWSManager())

    with patch("knowledge.lightrag_config_manager.get_config_manager", return_value=fake_cm), \
         patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache"), \
         patch.dict("sys.modules", {"gui.LocalServer": fake_ws_module}):
        provider_settings_helper.sync_account_api_key_to_ecanai(
            "rotated-account-key",
            main_window=main_window,
        )

    event_names = [event for event, _ in broadcast_calls]
    # All 3 LLM/embedding/rerank roles broadcast.
    assert event_names.count("lightrag.providersUpdated") == 4
    # The parser broadcast carries the active engines so the UI can
    # selectively re-pull only what it needs.
    parser_payloads = [payload for event, payload in broadcast_calls if payload.get("provider_type") == "parser"]
    assert len(parser_payloads) == 1
    assert parser_payloads[0]["provider"] == "ecanai"
    assert set(parser_payloads[0]["engines"]) == {"mineru", "docling"}


def test_no_broadcast_when_no_parser_was_active():
    """If neither parser is in ecanai mode there is no parser-side event
    to nudge the Settings UI about — keep the broadcast list clean."""
    fake_cm = _FakeConfigManager(mineru_mode="local", docling_mode="local")

    main_window = _build_main_window({"llm": "ecanai"})

    broadcast_calls: list[tuple] = []

    class _FakeWSManager:
        def broadcast_sync(self, event: str, payload: dict) -> None:
            broadcast_calls.append((event, payload))

    fake_ws_module = SimpleNamespace(app_ws_manager=_FakeWSManager())

    with patch("knowledge.lightrag_config_manager.get_config_manager", return_value=fake_cm), \
         patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache"), \
         patch.dict("sys.modules", {"gui.LocalServer": fake_ws_module}):
        provider_settings_helper.sync_account_api_key_to_ecanai(
            "rotated-account-key",
            main_window=main_window,
        )

    parser_events = [
        payload for event, payload in broadcast_calls
        if payload.get("provider_type") == "parser"
    ]
    assert parser_events == []


# ── Edge-case coverage ─────────────────────────────────────────────
# The cases above cover the happy path. The following tests pin down
# the failure modes that an account-key rotation must reject without
# mutating any backing store, plus the agent hot-update hooks for the
# embedding / rerank roles (which mirror the LLM ``update_all_llms``
# call but were previously unobserved).


def test_empty_key_is_rejected_before_touching_store():
    """An empty / whitespace-only key is a no-op for the user. We must
    return failure WITHOUT clearing the previous valid credential in
    secure_store (a real delete path is a separate concern)."""
    main_window = _build_main_window({"llm": "ecanai"})

    with patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache") as invalidate:
        success, error = provider_settings_helper.sync_account_api_key_to_ecanai(
            "   ", main_window=main_window
        )

    assert success is False
    assert error == "Account API key is empty"
    # Cache invalidator must not run on a no-op rotation; otherwise an
    # empty form submission would unnecessarily bounce the LightRAG
    # child process.
    invalidate.assert_not_called()


def test_none_main_window_without_app_context_fails_cleanly():
    """If neither ``main_window`` is passed nor AppContext has one, the
    function must return a clear error without raising. This is the
    path hit during early bootstrap before MainWindow registers."""
    with patch("app_context.AppContext.get_main_window", return_value=None), \
         patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache") as invalidate:
        success, error = provider_settings_helper.sync_account_api_key_to_ecanai(
            "any-key", main_window=None
        )

    assert success is False
    assert "Main window" in (error or "")
    invalidate.assert_not_called()


def test_main_window_without_config_manager_fails_cleanly():
    """A test stub MainWindow without ``config_manager`` is treated as
    not-yet-initialized and rejected with a specific error. We must
    not call into managers that don't exist."""
    main_window = SimpleNamespace()  # no config_manager attribute

    with patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache") as invalidate:
        success, error = provider_settings_helper.sync_account_api_key_to_ecanai(
            "any-key", main_window=main_window
        )

    assert success is False
    assert "Main window" in (error or "")
    invalidate.assert_not_called()


def test_store_api_key_failure_propagates_and_aborts_remaining_roles():
    """If the LLM manager's store_api_key fails, the embedding / rerank
    stores MUST NOT be attempted (the existing per-role loop returns
    early on the first failure). The error mentions which role failed."""
    failure_msg = "keychain locked"

    def llm_manager_factory():
        return SimpleNamespace(
            store_api_key=lambda env_var, value: (False, failure_msg)
        )

    config_manager = SimpleNamespace(
        llm_manager=llm_manager_factory(),
        embedding_manager=SimpleNamespace(
            store_api_key=lambda *a, **k: pytest.fail("embedding store_api_key must not run after llm failure")
        ),
        rerank_manager=SimpleNamespace(
            store_api_key=lambda *a, **k: pytest.fail("rerank store_api_key must not run after llm failure")
        ),
        general_settings=SimpleNamespace(
            default_llm="ecanai", default_embedding="ecanai", default_rerank="ecanai",
            default_llm_model="", default_embedding_model="", default_rerank_model="",
        ),
    )
    main_window = SimpleNamespace(
        config_manager=config_manager,
        agents=[],
        update_all_llms=lambda **_k: True,
    )

    with patch("knowledge.lightrag_config_manager.get_config_manager", return_value=_FakeConfigManager()), \
         patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache") as invalidate:
        success, error = provider_settings_helper.sync_account_api_key_to_ecanai(
            "rotated-key", main_window=main_window
        )

    assert success is False
    assert "llm" in (error or "")
    assert failure_msg in (error or "")
    # Inactive role path: no broadcast, no restart, no parser env touch.
    invalidate.assert_not_called()


def test_active_llm_role_triggers_update_all_llms_hot_reload():
    """When default_llm is ecanai, ``update_all_llms`` MUST run with a
    descriptive reason so a running in-process LLM is replaced with the
    new credential. Non-active roles MUST NOT call into the missing
    embedding/rerank helpers."""
    update_calls: list[dict] = []
    embedding_calls: list[dict] = []
    rerank_calls: list[dict] = []

    main_window = _build_main_window({"llm": "ecanai"})
    main_window.update_all_llms = lambda **kwargs: update_calls.append(kwargs) or True
    main_window.agents = [SimpleNamespace(
        mem_manager=SimpleNamespace(
            update_embeddings=lambda **kwargs: embedding_calls.append(kwargs),
            update_reranks=lambda **kwargs: rerank_calls.append(kwargs),
        )
    )]

    with patch("knowledge.lightrag_config_manager.get_config_manager",
               return_value=_FakeConfigManager()), \
         patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache"):
        success, _ = provider_settings_helper.sync_account_api_key_to_ecanai(
            "rotated-key", main_window=main_window
        )

    assert success
    assert update_calls and "eCanAI" in (update_calls[0].get("reason") or "")
    # Embedding and rerank are not active → no agent hot-update for them.
    assert embedding_calls == []
    assert rerank_calls == []


def test_active_embedding_role_hot_updates_agent_mem_managers():
    """default_embedding=ecanai → every agent's mem_manager.update_embeddings
    is called with the configured default_embedding_model. The LLM
    hot-reload MUST NOT run because the LLM role is not ecanai."""
    update_calls: list[dict] = []
    embedding_calls: list[dict] = []

    main_window = _build_main_window(
        {"llm": "openai", "embedding": "ecanai"},
    )
    main_window.config_manager.general_settings.default_embedding_model = "text-embedding-v3"
    main_window.update_all_llms = lambda **kwargs: update_calls.append(kwargs) or True
    main_window.agents = [SimpleNamespace(
        mem_manager=SimpleNamespace(
            update_embeddings=lambda **kwargs: embedding_calls.append(kwargs),
            update_reranks=lambda **kwargs: pytest.fail("rerank hot-update must not run when only embedding is ecanai"),
        )
    )]

    with patch("knowledge.lightrag_config_manager.get_config_manager",
               return_value=_FakeConfigManager()), \
         patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache"):
        success, _ = provider_settings_helper.sync_account_api_key_to_ecanai(
            "rotated-key", main_window=main_window
        )

    assert success
    # LLM role is openai → its hot-reload must NOT have run.
    assert update_calls == []
    # Embedding role is ecanai → every agent's update_embeddings must have
    # been called with the right provider + model.
    assert embedding_calls == [
        {"provider_name": "ecanai", "model_name": "text-embedding-v3"},
    ]


def test_active_rerank_role_hot_updates_agent_mem_managers():
    """default_rerank=ecanai → every agent's mem_manager.update_reranks
    is called. No LLM/embedding hot-reload."""
    embedding_calls: list[dict] = []
    rerank_calls: list[dict] = []

    main_window = _build_main_window({"llm": "openai", "rerank": "ecanai"})
    main_window.config_manager.general_settings.default_rerank_model = "gte-rerank"
    main_window.update_all_llms = lambda **_k: pytest.fail("llm hot-reload must not run when only rerank is ecanai")
    main_window.agents = [SimpleNamespace(
        mem_manager=SimpleNamespace(
            update_embeddings=lambda **kwargs: embedding_calls.append(kwargs),
            update_reranks=lambda **kwargs: rerank_calls.append(kwargs),
        )
    )]

    with patch("knowledge.lightrag_config_manager.get_config_manager",
               return_value=_FakeConfigManager()), \
         patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache"):
        success, _ = provider_settings_helper.sync_account_api_key_to_ecanai(
            "rotated-key", main_window=main_window
        )

    assert success
    assert embedding_calls == []
    assert rerank_calls == [
        {"provider_name": "ecanai", "model_name": "gte-rerank"},
    ]


def test_agent_without_mem_manager_is_skipped_silently():
    """An agent without a ``mem_manager`` (e.g. an in-flight draft agent
    that hasn't bound memory yet) MUST NOT crash the rotation. We log a
    debug and move on; the existing role loop guards the call site."""
    main_window = _build_main_window(
        {"llm": "openai", "embedding": "ecanai"},
    )
    main_window.config_manager.general_settings.default_embedding_model = "text-embedding-v3"
    # One healthy agent + one without mem_manager; both must be visited
    # without raising.
    healthy_calls: list[dict] = []
    main_window.agents = [
        SimpleNamespace(mem_manager=None),
        SimpleNamespace(mem_manager=SimpleNamespace(
            update_embeddings=lambda **kwargs: healthy_calls.append(kwargs),
            update_reranks=lambda **kwargs: None,
        )),
    ]

    with patch("knowledge.lightrag_config_manager.get_config_manager",
               return_value=_FakeConfigManager()), \
         patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache"):
        success, _ = provider_settings_helper.sync_account_api_key_to_ecanai(
            "rotated-key", main_window=main_window
        )

    assert success
    # The healthy agent still got its hot-update.
    assert healthy_calls == [
        {"provider_name": "ecanai", "model_name": "text-embedding-v3"},
    ]
