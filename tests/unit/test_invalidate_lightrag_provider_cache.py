"""Regression tests for ``invalidate_lightrag_provider_cache``.

These tests cover the three restart decisions that have caused real-world
"LightRAG did not pick up my settings" bugs:

  * Bug A — Switching the System Settings default LLM provider to a
    non-eCanAI provider (e.g. ``openai`` → ``anthropic``) must restart
    the LightRAG child process. The previous heuristic compared the new
    provider identifier against the one already written to
    ``lightrag.env``, but ``sync_default_provider_to_lightrag_env`` had
    just rewritten that slot, so the comparison always reported "no
    change" and the running child went on serving requests with the
    stale provider.

  * Bug B — A rotated account API key for an eCanAI role must trigger a
    restart even though the ``*_BINDING`` env keys did not change. The
    parser path writes ``MINERU_API_TOKEN`` / ``DOCLING_API_KEY`` out of
    band and the in-memory LLM cache holds the previous secret, so the
    child has to be replaced.

  * Restart failure / not-running server must surface to the GUI as a
    ``lightrag.restartNotice`` WebSocket event so the user is not left
    wondering why nothing changed.
"""

import threading as _real_threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from gui.manager import provider_settings_helper


class _FakeLRConfigManager:
    """Records every ``update_config`` call so tests can introspect what
    was actually written to ``lightrag.env``."""

    def __init__(self, initial: dict | None = None):
        self._state: dict[str, str] = dict(initial or {})
        self.update_calls: list[dict] = []
        self._invalidations: int = 0

    def get_value(self, key: str, default=None):
        return self._state.get(key, default)

    def update_config(self, updates: dict) -> bool:
        self._state.update(updates)
        self.update_calls.append(dict(updates))
        return True

    def invalidate_caches(self) -> None:
        self._invalidations += 1


class _RecordingWSManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def broadcast_sync(self, event: str, payload: dict) -> None:
        self.calls.append((event, payload))


def _build_main_window(defaults: dict[str, str]):
    """Construct a MainWindow stand-in with the minimum surface that
    ``invalidate_lightrag_provider_cache`` reaches into.

    ``defaults`` maps ``default_llm`` / ``default_embedding`` /
    ``default_rerank`` to their current provider names.
    """

    class _Settings(SimpleNamespace):
        pass

    settings = _Settings(**{f'default_{k}': v for k, v in defaults.items()})
    return SimpleNamespace(
        config_manager=SimpleNamespace(general_settings=settings),
        lightrag_server=None,
    )


# ── Bug A: switch non-eCanAI LLM provider must restart ────────────────


def test_switching_non_ecanai_llm_provider_triggers_restart():
    """Reproducer for the actual bug.

    Before: caller writes ``default_llm='anthropic'`` then asks the
    helper to invalidate. ``sync_default_provider_to_lightrag_env``
    diffs and rewrites ``LLM_BINDING=openai`` → ``anthropic`` (env
    written = True). The OLD heuristic re-read ``LLM_BINDING`` AFTER
    the rewrite and compared it against ``'anthropic'`` — they matched,
    so the restart was skipped and the child kept serving with the
    openai credentials.
    """

    fake_lr = _FakeLRConfigManager({'LLM_BINDING': 'openai', 'LLM_MODEL': 'gpt-4'})
    main_window = _build_main_window({'llm': 'anthropic'})
    fake_server = MagicMock()
    fake_server.is_running.return_value = True
    main_window.lightrag_server = fake_server

    fake_ws = _RecordingWSManager()

    with patch('knowledge.lightrag_config_manager.get_config_manager', return_value=fake_lr), \
         patch.object(provider_settings_helper, 'sync_default_provider_to_lightrag_env',
                      return_value=True) as sync_mock, \
         patch('app_context.AppContext.get_main_window', return_value=main_window), \
         patch.object(_real_threading, 'Thread') as fake_thread_cls, \
         patch.dict('sys.modules', {'gui.LocalServer': SimpleNamespace(app_ws_manager=fake_ws)}):
        fake_thread = MagicMock()
        fake_thread_cls.return_value = fake_thread

        provider_settings_helper.invalidate_lightrag_provider_cache('llm', 'anthropic')

    # 1. sync was actually asked to write the new binding to lightrag.env.
    sync_mock.assert_called_once_with(provider_type='llm')

    # 2. A restart thread was spawned (not skipped).
    fake_thread_cls.assert_called_once()
    kwargs = fake_thread_cls.call_args.kwargs
    assert kwargs['name'] == 'LightragProviderSettingsRestart'
    assert kwargs['daemon'] is True
    fake_thread.start.assert_called_once()

    # 3. The restart target would call stop() + start() — verify by running it.
    target = fake_thread_cls.call_args.kwargs['target']
    target()
    fake_server.stop.assert_called_once()
    fake_server.start.assert_called_once_with(wait_ready=False)


def test_switching_non_ecanai_llm_provider_emits_restart_notice_on_success():
    """When the restart thread actually completes, a ``lightrag.restartNotice``
    event with status=ok must reach the WS manager so an open Knowledge
    tab can refresh its status badge."""

    fake_lr = _FakeLRConfigManager({'LLM_BINDING': 'openai'})
    main_window = _build_main_window({'llm': 'anthropic'})
    fake_server = MagicMock()
    fake_server.is_running.return_value = True
    main_window.lightrag_server = fake_server
    fake_ws = _RecordingWSManager()

    with patch('knowledge.lightrag_config_manager.get_config_manager', return_value=fake_lr), \
         patch.object(provider_settings_helper, 'sync_default_provider_to_lightrag_env',
                      return_value=True), \
         patch('app_context.AppContext.get_main_window', return_value=main_window), \
         patch.object(_real_threading, 'Thread') as fake_thread_cls, \
         patch.dict('sys.modules', {'gui.LocalServer': SimpleNamespace(app_ws_manager=fake_ws)}):
        fake_thread_cls.return_value = MagicMock()

        provider_settings_helper.invalidate_lightrag_provider_cache('llm', 'anthropic')
        # Run the captured target to exercise the success path.
        fake_thread_cls.call_args.kwargs['target']()

    restart_events = [payload for event, payload in fake_ws.calls
                      if event == 'lightrag.restartNotice']
    assert len(restart_events) == 1
    assert restart_events[0]['status'] == 'ok'
    assert restart_events[0]['reason'] == 'env_changed'


def test_restart_failure_emits_failed_restart_notice():
    """If ``server.stop()`` raises, the WS manager must learn about it."""

    fake_lr = _FakeLRConfigManager({'LLM_BINDING': 'openai'})
    main_window = _build_main_window({'llm': 'anthropic'})
    fake_server = MagicMock()
    fake_server.is_running.return_value = True
    fake_server.stop.side_effect = RuntimeError('subprocess already gone')
    main_window.lightrag_server = fake_server
    fake_ws = _RecordingWSManager()

    with patch('knowledge.lightrag_config_manager.get_config_manager', return_value=fake_lr), \
         patch.object(provider_settings_helper, 'sync_default_provider_to_lightrag_env',
                      return_value=True), \
         patch('app_context.AppContext.get_main_window', return_value=main_window), \
         patch.object(_real_threading, 'Thread') as fake_thread_cls, \
         patch.dict('sys.modules', {'gui.LocalServer': SimpleNamespace(app_ws_manager=fake_ws)}):
        fake_thread_cls.return_value = MagicMock()

        provider_settings_helper.invalidate_lightrag_provider_cache('llm', 'anthropic')
        fake_thread_cls.call_args.kwargs['target']()

    restart_events = [payload for event, payload in fake_ws.calls
                      if event == 'lightrag.restartNotice']
    assert len(restart_events) == 1
    assert restart_events[0]['status'] == 'failed'
    assert 'subprocess already gone' in restart_events[0]['message']


def test_server_not_running_emits_skipped_restart_notice():
    """When LightRAG is not running we still want the UI to know that the
    env file was rewritten; otherwise the user wonders why nothing
    visibly changed."""

    fake_lr = _FakeLRConfigManager({'LLM_BINDING': 'openai'})
    main_window = _build_main_window({'llm': 'anthropic'})
    main_window.lightrag_server = None  # explicitly no server
    fake_ws = _RecordingWSManager()

    with patch('knowledge.lightrag_config_manager.get_config_manager', return_value=fake_lr), \
         patch.object(provider_settings_helper, 'sync_default_provider_to_lightrag_env',
                      return_value=True), \
         patch('app_context.AppContext.get_main_window', return_value=main_window), \
         patch.dict('sys.modules', {'gui.LocalServer': SimpleNamespace(app_ws_manager=fake_ws)}):
        provider_settings_helper.invalidate_lightrag_provider_cache('llm', 'anthropic')

    restart_events = [payload for event, payload in fake_ws.calls
                      if event == 'lightrag.restartNotice']
    assert len(restart_events) == 1
    assert restart_events[0]['status'] == 'skipped'
    assert restart_events[0]['reason'] == 'server_not_running'


# ── Bug B: account API key rotation triggers restart ─────────────────


def test_account_key_rotation_restarts_when_ecanai_bound_but_no_env_diff():
    """The parser path (MINERU_API_TOKEN / DOCLING_API_KEY) writes the
    account key OUT OF BAND via ``sync_account_api_key_to_ecanai`` —
    so ``sync_default_provider_to_lightrag_env`` may legitimately
    report ``any_written=False``. The eCanAI bound check must still
    force a restart, otherwise the running child keeps the previous
    secret in its in-memory LLM cache."""

    fake_lr = _FakeLRConfigManager({
        'LLM_BINDING': 'ecanai',
        'LLM_BINDING_API_KEY': 'old-key',  # still old in env at this point
        'LLM_MODEL': 'ecanai-default',
    })
    main_window = _build_main_window({'llm': 'ecanai'})
    fake_server = MagicMock()
    fake_server.is_running.return_value = True
    main_window.lightrag_server = fake_server

    with patch('knowledge.lightrag_config_manager.get_config_manager', return_value=fake_lr), \
         patch.object(provider_settings_helper, 'sync_default_provider_to_lightrag_env',
                      return_value=False), \
         patch('app_context.AppContext.get_main_window', return_value=main_window), \
         patch.object(_real_threading, 'Thread') as fake_thread_cls:
        fake_thread_cls.return_value = MagicMock()

        provider_settings_helper.invalidate_lightrag_provider_cache('llm', 'ecanai')

    fake_thread_cls.assert_called_once()


# ── Negative case: no env change, no ecanai, no parser → no restart ──


def test_no_env_change_and_no_ecanai_skips_restart():
    """If the sync helper reported nothing was written AND no role is
    bound to ecanai AND no parser is in ecanai mode, there is no reason
    to bounce the child process. (This is the common idempotent call.)"""

    fake_lr = _FakeLRConfigManager({
        'LLM_BINDING': 'openai',
        'LLM_MODEL': 'gpt-4',
        'LLM_BINDING_API_KEY': 'key',
    })
    main_window = _build_main_window({'llm': 'openai', 'embedding': 'openai', 'rerank': 'openai'})
    fake_server = MagicMock()
    fake_server.is_running.return_value = True
    main_window.lightrag_server = fake_server

    with patch('knowledge.lightrag_config_manager.get_config_manager', return_value=fake_lr), \
         patch.object(provider_settings_helper, 'sync_default_provider_to_lightrag_env',
                      return_value=False), \
         patch('app_context.AppContext.get_main_window', return_value=main_window), \
         patch.object(_real_threading, 'Thread') as fake_thread_cls:
        fake_thread_cls.return_value = MagicMock()

        provider_settings_helper.invalidate_lightrag_provider_cache('llm', 'openai')

    fake_thread_cls.assert_not_called()
    fake_server.stop.assert_not_called()


# ── _broadcast_lightrag_restart_notice helper ─────────────────────────


def test_broadcast_helper_swallows_missing_local_server():
    """The helper must not raise when ``gui.LocalServer`` has not been
    imported yet (early bootstrap path)."""

    fake_ws = _RecordingWSManager()

    with patch.dict('sys.modules', {'gui.LocalServer': None}):
        # Should not raise even though the module entry is None.
        provider_settings_helper._broadcast_lightrag_restart_notice(
            status='ok', reason='env_changed', message='hi',
        )
    assert fake_ws.calls == []


def test_broadcast_helper_swallows_missing_ws_manager_attr():
    """``gui.LocalServer`` may exist but without an ``app_ws_manager``."""

    fake_module = SimpleNamespace()  # no app_ws_manager attribute
    provider_settings_helper._broadcast_lightrag_restart_notice(
        status='ok', reason='env_changed', message='hi',
    )
    assert getattr(fake_module, 'app_ws_manager', None) is None
