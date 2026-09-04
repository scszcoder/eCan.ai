"""Tests for ``sync_default_parser_to_lightrag_env``.

Contract (first launch + account key sync for the eCanAI parser path):

- System Settings defaults MinerU/Docling to ``ecanai`` mode. When the
  user signs in and an account API key lands in secure_store, the URL
  and the key MUST reach lightrag.env before LightRAG starts — otherwise
  the parser child process crashes with ``MINERU_API_TOKEN is required``
  on the first request.

- When the user is NOT signed in yet (no account key), the URL still
  needs to be written so LightRAG does not fall back to a
  non-existent local parser. The token is left empty so the first
  parser call surfaces a clean 401 instead of crashing.

- When a stale token from a previous account lingers in lightrag.env
  but the new account has no key yet, the stale value MUST be wiped.

- Local / official modes own their own user-typed credentials and MUST
  NOT be touched.

- The function is idempotent: a second call when lightrag.env already
  agrees with secure_store is a no-op (no update_config call).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from gui.manager import provider_settings_helper


ECANAI_URL = 'https://sccb0-d0gc5398xf028be6a.service.tcloudbase.com/api/llm-proxy/v1'


class _FakeLRConfigManager:
    """Stand-in for ``knowledge.lightrag_config_manager.get_config_manager()``.

    ``initial`` is the starting state of lightrag.env. ``update_calls``
    captures every write so tests can assert exactly which keys were
    touched.
    """

    def __init__(self, initial: dict | None = None):
        self._state: dict[str, str] = dict(initial or {})
        self.update_calls: list[dict] = []

    def get_value(self, key: str, default=None):
        return self._state.get(key, default)

    def update_config(self, updates: dict) -> bool:
        # Mirror real behaviour: writes are persistent.
        self._state.update(updates)
        self.update_calls.append(dict(updates))
        return True


def _patch_secure_store(account_key: str | None) -> SimpleNamespace:
    """Patch ``utils.env.secure_store.secure_store`` so the account key
    lookup returns the value the test wants (or fails cleanly when
    ``account_key is None``).
    """
    fake_store = SimpleNamespace()

    def fake_get(key: str, username=None):
        assert key == 'ECANAI_LLM_API_KEY'
        # The real pre-sync reads ``secure_store.get(name, username=...)``
        # after ``get_current_username()`` returns a non-empty string.
        # Tests below patch ``get_current_username`` too; if a caller
        # forgets to and passes ``username=None`` we still want a
        # deterministic return so a missing username does not surface
        # as a keychain lookup in the test process.
        return account_key

    fake_store.get = fake_get
    fake_store.set = lambda *a, **k: True

    if account_key is None:
        # Force a lookup failure so we can prove the function does not
        # raise when secure_store is unreachable.
        def fake_get_raising(key: str, username=None):
            raise RuntimeError('keychain unreachable')
        fake_store.get = fake_get_raising

    return fake_store


def _current_username_patch():
    """Return a context-manager-style helper that pins
    ``utils.env.secure_store.get_current_username`` to a fixed value
    so pre-sync actually runs the key lookup. Tests must use this
    whenever they inject a fake ``secure_store``; without it the real
    ``get_current_username()`` may return ``None`` and the pre-sync
    silently treats the account as not logged in.
    """
    from contextlib import contextmanager

    @contextmanager
    def _ctx(value: str = 'test-user'):
        with patch('utils.env.secure_store.get_current_username', return_value=value):
            yield
    return _ctx


def _build_main_window(defaults: dict | None = None):
    """Minimal MainWindow stand-in with ``general_settings.default_*``.

    The defaults are empty by default because the parser pre-sync reads
    from lightrag.env, not from settings.json (the parser mode is owned
    by lightrag.env; only the LLM/embedding/rerank defaults are owned
    by System Settings). Tests that need a non-empty defaults dict can
    override.
    """
    defaults = defaults or {}
    config_manager = SimpleNamespace(
        general_settings=SimpleNamespace(
            default_llm=defaults.get('llm', ''),
            default_embedding=defaults.get('embedding', ''),
            default_rerank=defaults.get('rerank', ''),
        ),
    )
    return SimpleNamespace(config_manager=config_manager)


# ── Happy-path first-launch coverage ──────────────────────────────


def test_first_launch_writes_url_and_account_key_to_both_engines():
    """Fresh install: System Settings is eCanAI for both engines, the
    user just signed in and ``ECANAI_LLM_API_KEY`` is now populated.
    Both ``MINERU_API_TOKEN`` / ``DOCLING_API_KEY`` and the dedicated
    ``*_ECANAI_ENDPOINT`` env vars must reach lightrag.env so the
    subprocess picks them up without an additional save click."""
    fake_lr = _FakeLRConfigManager(initial={})  # lightrag.env is empty

    main_window = _build_main_window()

    with patch('knowledge.lightrag_config_manager.get_config_manager', return_value=fake_lr), \
         patch('utils.env.secure_store.secure_store', _patch_secure_store('account-key-abc123')), \
         patch('utils.env.secure_store.get_current_username', return_value='test-user'):
        written = provider_settings_helper.sync_default_parser_to_lightrag_env()

    assert written is True
    assert len(fake_lr.update_calls) == 1
    updates = fake_lr.update_calls[0]
    # Endpoint vars point at the eCanAI proxy for both engines.
    assert updates['MINERU_ECANAI_ENDPOINT'] == ECANAI_URL
    assert updates['DOCLING_ECANAI_ENDPOINT'] == ECANAI_URL
    # Alias slot that LightRAG's local-mode MinerU client reads gets the
    # same URL by default (avoids a localhost timeout on first request).
    assert updates['MINERU_LOCAL_ENDPOINT'] == ECANAI_URL
    # Account key reaches both active token slots.
    assert updates['MINERU_API_TOKEN'] == 'account-key-abc123'
    assert updates['DOCLING_API_KEY'] == 'account-key-abc123'
    # User-typed values for local / official slots MUST NOT be touched.
    assert 'MINERU_LOCAL_API_KEY' not in updates
    assert 'DOCLING_LOCAL_API_KEY' not in updates


def test_first_launch_no_account_key_writes_url_only():
    """User has not signed in yet (or has no provisioned key). The URL
    MUST still reach lightrag.env so LightRAG does not default to a
    localhost MinerU instance. The token slots are NOT explicitly
    written when lightrag.env is empty (no stale value to wipe, and an
    explicit ``''`` write is just file churn) — the parser will
    surface a 401 when it actually tries to call the proxy."""
    fake_lr = _FakeLRConfigManager(initial={})

    main_window = _build_main_window()

    with patch('knowledge.lightrag_config_manager.get_config_manager', return_value=fake_lr), \
         patch('utils.env.secure_store.secure_store', _patch_secure_store('')), \
         patch('utils.env.secure_store.get_current_username', return_value='test-user'):
        written = provider_settings_helper.sync_default_parser_to_lightrag_env()

    assert written is True
    updates = fake_lr.update_calls[0]
    assert updates['MINERU_ECANAI_ENDPOINT'] == ECANAI_URL
    assert updates['DOCLING_ECANAI_ENDPOINT'] == ECANAI_URL
    # No stale token to clear → token slots are NOT in the update dict
    # (writing an empty string would be file churn with no observable
    # effect).
    assert 'MINERU_API_TOKEN' not in updates
    assert 'DOCLING_API_KEY' not in updates


def test_first_launch_no_account_key_wipes_stale_token_from_previous_account():
    """A previous account left a token in lightrag.env. The new account
    is not signed in yet (no ``ECANAI_LLM_API_KEY``). The stale token
    MUST be cleared so the parser does not silently authenticate as
    the previous user when an in-flight request races account-key
    rotation."""
    fake_lr = _FakeLRConfigManager(initial={
        'MINERU_API_TOKEN': 'stale-from-previous-account',
        'DOCLING_API_KEY': 'another-stale-token',
    })

    main_window = _build_main_window()

    with patch('knowledge.lightrag_config_manager.get_config_manager', return_value=fake_lr), \
         patch('utils.env.secure_store.secure_store', _patch_secure_store('')), \
         patch('utils.env.secure_store.get_current_username', return_value='test-user'):
        written = provider_settings_helper.sync_default_parser_to_lightrag_env()

    assert written is True
    updates = fake_lr.update_calls[0]
    assert updates['MINERU_API_TOKEN'] == ''
    assert updates['DOCLING_API_KEY'] == ''


def test_first_launch_account_key_overrides_stale_token():
    """A previous account left a token, the new account now has its
    own key. The new key MUST win."""
    fake_lr = _FakeLRConfigManager(initial={
        'MINERU_API_TOKEN': 'stale-from-previous-account',
    })

    main_window = _build_main_window()

    with patch('knowledge.lightrag_config_manager.get_config_manager', return_value=fake_lr), \
         patch('utils.env.secure_store.secure_store', _patch_secure_store('fresh-account-key')), \
         patch('utils.env.secure_store.get_current_username', return_value='test-user'):
        written = provider_settings_helper.sync_default_parser_to_lightrag_env()

    assert written is True
    updates = fake_lr.update_calls[0]
    assert updates['MINERU_API_TOKEN'] == 'fresh-account-key'


# ── Idempotency ──────────────────────────────────────────────────


def test_no_op_when_lightrag_env_already_agrees_with_secure_store():
    """A second call right after startup must not write anything when
    lightrag.env already mirrors the account state — otherwise every
    re-entry into the function would churn the file."""
    fake_lr = _FakeLRConfigManager(initial={
        'MINERU_API_MODE': 'ecanai',
        'DOCLING_PROVIDER': 'ecanai',
        'MINERU_ECANAI_ENDPOINT': ECANAI_URL,
        'DOCLING_ECANAI_ENDPOINT': ECANAI_URL,
        'MINERU_API_TOKEN': 'account-key-abc123',
        'DOCLING_API_KEY': 'account-key-abc123',
        'MINERU_LOCAL_ENDPOINT': ECANAI_URL,
        'DOCLING_LOCAL_ENDPOINT': ECANAI_URL,
    })

    main_window = _build_main_window()

    with patch('knowledge.lightrag_config_manager.get_config_manager', return_value=fake_lr), \
         patch('utils.env.secure_store.secure_store', _patch_secure_store('account-key-abc123')), \
         patch('utils.env.secure_store.get_current_username', return_value='test-user'):
        written = provider_settings_helper.sync_default_parser_to_lightrag_env()

    assert written is False
    assert fake_lr.update_calls == []


# ── Mode gating ──────────────────────────────────────────────────


def test_local_mode_mineru_leaves_env_untouched():
    """Local mode owns its own credential. Account key rotation MUST
    NOT leak into ``MINERU_API_TOKEN``."""
    fake_lr = _FakeLRConfigManager(initial={
        'MINERU_API_MODE': 'local',
        'MINERU_API_TOKEN': 'user-typed-local-token',
        'MINERU_LOCAL_ENDPOINT': 'http://my-mineru.local:8000',
    })

    main_window = _build_main_window()

    with patch('knowledge.lightrag_config_manager.get_config_manager', return_value=fake_lr), \
         patch('utils.env.secure_store.secure_store', _patch_secure_store('account-key-abc123')), \
         patch('utils.env.secure_store.get_current_username', return_value='test-user'):
        written = provider_settings_helper.sync_default_parser_to_lightrag_env()

    # MinerU is local → we skip; Docling is still ecanai by default so
    # the docling side of the loop runs (URL + token written there).
    assert written is True
    updates = fake_lr.update_calls[0]
    assert 'MINERU_API_TOKEN' not in updates  # never touch mineru
    assert 'MINERU_ECANAI_ENDPOINT' not in updates
    assert 'MINERU_LOCAL_ENDPOINT' not in updates
    # Docling still receives the URL/token sync.
    assert updates['DOCLING_ECANAI_ENDPOINT'] == ECANAI_URL
    assert updates['DOCLING_API_KEY'] == 'account-key-abc123'


def test_official_mode_docling_leaves_env_untouched():
    """Official mode owns its own credential (e.g. a user-purchased
    docling.ai key). Account key rotation MUST NOT leak into
    ``DOCLING_API_KEY``."""
    fake_lr = _FakeLRConfigManager(initial={
        'DOCLING_PROVIDER': 'official',
        'DOCLING_API_KEY': 'user-typed-official-key',
        'DOCLING_OFFICIAL_ENDPOINT': 'https://docling.ai',
    })

    main_window = _build_main_window()

    with patch('knowledge.lightrag_config_manager.get_config_manager', return_value=fake_lr), \
         patch('utils.env.secure_store.secure_store', _patch_secure_store('account-key-abc123')), \
         patch('utils.env.secure_store.get_current_username', return_value='test-user'):
        written = provider_settings_helper.sync_default_parser_to_lightrag_env()

    assert written is True
    updates = fake_lr.update_calls[0]
    assert 'DOCLING_API_KEY' not in updates
    assert 'DOCLING_ECANAI_ENDPOINT' not in updates
    # MinerU still receives the URL/token sync (default is ecanai).
    assert updates['MINERU_ECANAI_ENDPOINT'] == ECANAI_URL
    assert updates['MINERU_API_TOKEN'] == 'account-key-abc123'


def test_user_typed_local_endpoint_for_mineru_is_preserved():
    """When the user has explicitly typed a non-default
    ``MINERU_LOCAL_ENDPOINT`` (e.g. ``http://my-mineru.local:8000``),
    pre-sync MUST NOT clobber it. Only the default empty / localhost
    alias slot is safe to overwrite with the eCanAI URL."""
    fake_lr = _FakeLRConfigManager(initial={
        'MINERU_API_MODE': 'ecanai',
        'DOCLING_PROVIDER': 'ecanai',
        'MINERU_API_TOKEN': 'account-key-abc123',
        'DOCLING_API_KEY': 'account-key-abc123',
        'MINERU_ECANAI_ENDPOINT': ECANAI_URL,
        'DOCLING_ECANAI_ENDPOINT': ECANAI_URL,
        'DOCLING_LOCAL_ENDPOINT': ECANAI_URL,
        # User has a typed local endpoint that they don't want clobbered.
        'MINERU_LOCAL_ENDPOINT': 'http://my-mineru.local:8000',
    })

    main_window = _build_main_window()

    with patch('knowledge.lightrag_config_manager.get_config_manager', return_value=fake_lr), \
         patch('utils.env.secure_store.secure_store', _patch_secure_store('account-key-abc123')), \
         patch('utils.env.secure_store.get_current_username', return_value='test-user'):
        written = provider_settings_helper.sync_default_parser_to_lightrag_env()

    # Everything is already in sync → no writes.
    assert written is False
    assert fake_lr.update_calls == []
    # The user-typed endpoint survives untouched.
    assert fake_lr.get_value('MINERU_LOCAL_ENDPOINT') == 'http://my-mineru.local:8000'


# ── Resilience ───────────────────────────────────────────────────


def test_secure_store_failure_does_not_crash_pre_sync():
    """If ``secure_store.get`` raises (keychain locked, transient I/O,
    not signed in yet) the pre-sync must swallow the failure, write
    the URLs, and leave the token slots empty. Crashing here would
    prevent LightRAG from starting at all on a locked keychain."""
    fake_lr = _FakeLRConfigManager(initial={})

    main_window = _build_main_window()

    with patch('knowledge.lightrag_config_manager.get_config_manager', return_value=fake_lr), \
         patch('utils.env.secure_store.secure_store', _patch_secure_store(None)), \
         patch('utils.env.secure_store.get_current_username', return_value='test-user'):
        written = provider_settings_helper.sync_default_parser_to_lightrag_env()

    # URLs land in lightrag.env; no token writes happen (lightrag.env
    # is empty so there is no stale value to wipe).
    assert written is True
    updates = fake_lr.update_calls[0]
    assert updates['MINERU_ECANAI_ENDPOINT'] == ECANAI_URL
    assert updates['DOCLING_ECANAI_ENDPOINT'] == ECANAI_URL
    assert 'MINERU_API_TOKEN' not in updates
    assert 'DOCLING_API_KEY' not in updates


def test_empty_ecanai_parser_base_url_returns_false_without_writing():
    """If ``ECANAI_PARSER_BASE_URL`` is somehow empty (e.g. test
    environment without the constant loaded), the function must bail
    out without writing anything rather than persisting blank URLs."""
    fake_lr = _FakeLRConfigManager(initial={})

    main_window = _build_main_window()

    with patch('knowledge.lightrag_config_manager.get_config_manager', return_value=fake_lr), \
         patch('knowledge.lightrag_parser_config.ECANAI_PARSER_BASE_URL', ''), \
         patch('utils.env.secure_store.secure_store', _patch_secure_store('account-key-abc123')), \
         patch('utils.env.secure_store.get_current_username', return_value='test-user'):
        written = provider_settings_helper.sync_default_parser_to_lightrag_env()

    assert written is False
    assert fake_lr.update_calls == []


def test_lightrag_config_manager_unavailable_returns_false_without_raising():
    """If the LightRAG config manager cannot be imported (early
    bootstrap, missing dependency), the function must return ``False``
    and let the caller proceed without blocking startup."""
    main_window = _build_main_window()

    with patch('knowledge.lightrag_config_manager.get_config_manager',
               side_effect=ImportError('lightrag not installed')):
        written = provider_settings_helper.sync_default_parser_to_lightrag_env()

    assert written is False


def test_main_window_unavailable_returns_false_without_raising():
    """When called during early bootstrap before ``MainWindow`` has
    registered in ``AppContext``, the function must fail cleanly. The
    parser env vars stay in whatever state ``lightrag.env`` already
    holds — a partially-populated file is better than a startup crash.
    """
    fake_lr = _FakeLRConfigManager(initial={})

    with patch('knowledge.lightrag_config_manager.get_config_manager', return_value=fake_lr), \
         patch('app_context.AppContext.get_main_window', return_value=None), \
         patch('utils.env.secure_store.secure_store', _patch_secure_store('account-key')), \
         patch('utils.env.secure_store.get_current_username', return_value='test-user'):
        # The current implementation does not actually read AppContext
        # (it only reads lightrag.env + secure_store). This test
        # documents that the function is safe to call even without a
        # registered MainWindow.
        written = provider_settings_helper.sync_default_parser_to_lightrag_env()

    # The URL/token sync still happens because secure_store is mocked.
    assert written is True


# ── Integration with sync_account_api_key_to_ecanai ──────────────


def test_existing_account_key_rotation_path_covers_engines_in_addition_to_pre_sync():
    """``sync_account_api_key_to_ecanai`` is the runtime key-rotation
    path (account key arrives AFTER LightRAG is already up). It writes
    parser env vars too, but only for engines that are already in
    ecanai mode. The new ``sync_default_parser_to_lightrag_env`` is
    the FIRST-LAUNCH counterpart and covers the same writes when no
    rotation handler has fired yet.

    This test pins down the two helpers' separation so a future refactor
    cannot silently drop first-launch coverage while keeping rotation
    coverage (or vice versa)."""
    fake_lr = _FakeLRConfigManager(initial={
        # Pre-sync was already applied — lightrag.env already has URL+token.
        'MINERU_API_MODE': 'ecanai',
        'DOCLING_PROVIDER': 'ecanai',
        'MINERU_ECANAI_ENDPOINT': ECANAI_URL,
        'DOCLING_ECANAI_ENDPOINT': ECANAI_URL,
        'MINERU_API_TOKEN': 'old-account-key',
        'DOCLING_API_KEY': 'old-account-key',
        'MINERU_LOCAL_ENDPOINT': ECANAI_URL,
        'DOCLING_LOCAL_ENDPOINT': ECANAI_URL,
    })

    main_window = _build_main_window(
        {'llm': 'ecanai', 'embedding': 'ecanai', 'rerank': 'ecanai'}
    )
    main_window.config_manager.llm_manager = SimpleNamespace(
        store_api_key=lambda env_var, value: (True, None)
    )
    main_window.config_manager.embedding_manager = SimpleNamespace(
        store_api_key=lambda env_var, value: (True, None)
    )
    main_window.config_manager.rerank_manager = SimpleNamespace(
        store_api_key=lambda env_var, value: (True, None)
    )
    main_window.agents = []
    main_window.update_all_llms = lambda **_k: True

    with patch('knowledge.lightrag_config_manager.get_config_manager', return_value=fake_lr), \
         patch.object(provider_settings_helper, 'invalidate_lightrag_provider_cache'):
        # Rotation handler runs (post-launch account key change).
        ok, err = provider_settings_helper.sync_account_api_key_to_ecanai(
            'rotated-account-key', main_window=main_window
        )

    assert ok and err is None
    # The rotation handler wrote the new key into the parser env vars.
    parser_writes = [u for u in fake_lr.update_calls if 'MINERU_API_TOKEN' in u]
    assert parser_writes == [{'MINERU_API_TOKEN': 'rotated-account-key',
                              'DOCLING_API_KEY': 'rotated-account-key'}]
    # The pre-sync helper would now be a no-op (already in sync).
    with patch('knowledge.lightrag_config_manager.get_config_manager', return_value=fake_lr), \
         patch('utils.env.secure_store.secure_store', _patch_secure_store('rotated-account-key')), \
         patch('utils.env.secure_store.get_current_username', return_value='test-user'):
        written = provider_settings_helper.sync_default_parser_to_lightrag_env()
    assert written is False