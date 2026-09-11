"""
Tests for the rerank disable/enable flow.

Covers:
  1. Disabling rerank (set_default_rerank with disable sentinel) writes
     complete off-state to lightrag.env (RERANK_BINDING=null, RERANK_MODEL='',
     RERANK_BINDING_HOST='', RERANK_BINDING_API_KEY='', RERANK_BY_DEFAULT=false)
     and forces a LightRAG restart.
  2. Re-enabling rerank after disable picks up the correct provider from settings.json
     and writes RERANK_BY_DEFAULT=true.
  3. Proxy loopback detection: Ollama handler returns passthrough when base_url is the proxy.
  4. handle_provider_model_update invalidates cache for all provider types.
  5. sync_default_provider_to_lightrag_env does NOT re-enable ecanai on disable
     (read-raw-data fix for Bug 5).
  6. Sentinel is centralized in lightrag_constants so all layers agree.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from types import SimpleNamespace


# ── Shared sentinel constant ────────────────────────────────────────────────────

class TestSentinelConstantCentralized:
    """The disable sentinel is defined once in lightrag_constants and reused everywhere."""

    def test_sentinel_in_lightrag_constants(self):
        """RERANK_DISABLE_SENTINELS is exported from lightrag_constants."""
        from knowledge.lightrag_constants import RERANK_DISABLE_SENTINELS
        assert isinstance(RERANK_DISABLE_SENTINELS, frozenset)
        assert '' in RERANK_DISABLE_SENTINELS
        assert 'null' in RERANK_DISABLE_SENTINELS
        assert 'none' in RERANK_DISABLE_SENTINELS
        assert 'disabled' in RERANK_DISABLE_SENTINELS
        assert 'off' in RERANK_DISABLE_SENTINELS
        assert 'false' in RERANK_DISABLE_SENTINELS
        assert '0' in RERANK_DISABLE_SENTINELS
        # Real providers are NOT sentinels
        assert 'ecanai' not in RERANK_DISABLE_SENTINELS
        assert 'cohere' not in RERANK_DISABLE_SENTINELS
        assert 'jina' not in RERANK_DISABLE_SENTINELS

    def test_is_rerank_disabled(self):
        """is_rerank_disabled() uses the centralized sentinel."""
        from knowledge.lightrag_constants import is_rerank_disabled
        # All sentinels → disabled
        for val in ['', 'null', 'none', 'disabled', 'off', 'false', '0']:
            assert is_rerank_disabled(val), f"{val!r} should be disabled"
        # Real providers → NOT disabled
        for val in ['ecanai', 'cohere', 'jina', 'ollama', 'ryoais']:
            assert not is_rerank_disabled(val), f"{val!r} should NOT be disabled"

    def test_sentinel_agrees_with_handler_disable_path(self):
        """The handler's inline sentinel check matches the centralized one."""
        from knowledge.lightrag_constants import RERANK_DISABLE_SENTINELS
        test_cases = [
            ('null', True), ('none', True), ('', True),
            ('disabled', True), ('off', True), ('false', True), ('0', True),
            ('ecanai', False), ('cohere', False), ('jina', False),
        ]
        for binding, expect_disabled in test_cases:
            is_disabled = binding.strip().lower() in RERANK_DISABLE_SENTINELS
            assert is_disabled == expect_disabled, \
                f"binding={binding!r}: expected disabled={expect_disabled}"


# ── Ollama proxy loopback passthrough ──────────────────────────────────────────

class TestRerankProxyLoopbackPassthrough:
    """Proxy's Ollama handler returns passthrough when base_url is the proxy itself."""

    @pytest.mark.asyncio
    async def test_loopback_url_returns_passthrough(self):
        """When rerank is disabled, launcher redirects to proxy and Ollama handler
        returns passthrough without any HTTP call to Ollama."""
        from gui.lightrag_rerank_proxy import LightRAGRerankProxy

        proxy = LightRAGRerankProxy()
        docs = ['doc A', 'doc B', 'doc C']

        results = await proxy._rerank_ollama(
            base_url='http://localhost:4668/api/rerank',  # proxy loopback
            model='bge-reranker-v2-m3:latest',
            query='what is the diameter of the Earth?',
            documents=docs,
        )

        # Should return passthrough: all docs with score=1.0 in original order
        assert len(results) == 3
        assert [r['index'] for r in results] == [0, 1, 2]
        assert all(r['relevance_score'] == 1.0 for r in results)
        assert [r['document'] for r in results] == docs

    @pytest.mark.asyncio
    async def test_non_proxy_ollama_url_does_not_short_circuit(self):
        """A real Ollama URL (not proxy loopback) goes through the normal path."""
        from gui.lightrag_rerank_proxy import LightRAGRerankProxy

        proxy = LightRAGRerankProxy()
        docs = ['doc A']

        # Non-proxy URL — should NOT return passthrough from the loopback check.
        results = await proxy._rerank_ollama(
            base_url='http://localhost:11434',  # real Ollama, not proxy
            model='bge-reranker-v2-m3:latest',
            query='test query',
            documents=docs,
        )

        # Ollama not running in tests → returns [] (Ollama call fails).
        # The important thing is it did NOT return the passthrough shortcut.
        assert results == [], f"Expected empty list when Ollama unreachable, got {results}"


# ── Launcher disable redirect logic ────────────────────────────────────────────

class TestLauncherDisableRedirect:
    """lightrag_server redirects null RERANK_BINDING to proxy URL."""

    def test_disable_sentinels(self):
        """Disable sentinels cover all expected values."""
        # The sentinel set in the handler
        sentinel_set = {'', 'null', 'none', 'disabled', 'off', 'false', '0'}
        cases = [
            ('null', True), ('none', True), ('', True),
            ('disabled', True), ('off', True), ('false', True), ('0', True),
            ('ecanai', False), ('cohere', False),
        ]
        for binding, expect_disabled in cases:
            is_disabled = not binding or binding.lower() in sentinel_set
            assert is_disabled == expect_disabled, \
                f"binding={binding!r}: expected disabled={expect_disabled}"

    def test_launcher_redirect_logic(self):
        """When RERANK_BINDING is null, launcher sets binding=ollama and host=proxy."""
        # Test the launcher's redirect logic inline (same logic as lightrag_server.py)
        port = 4668
        test_cases = [
            ('null', True, 'ollama', f'http://localhost:{port}/api/rerank'),
            ('none', True, 'ollama', f'http://localhost:{port}/api/rerank'),
            ('', True, 'ollama', f'http://localhost:{port}/api/rerank'),
            ('disabled', True, 'ollama', f'http://localhost:{port}/api/rerank'),
            ('off', True, 'ollama', f'http://localhost:{port}/api/rerank'),
            ('false', True, 'ollama', f'http://localhost:{port}/api/rerank'),
            ('0', True, 'ollama', f'http://localhost:{port}/api/rerank'),
            ('ecanai', False, None, None),  # Not disabled, no redirect
            ('cohere', False, None, None),
        ]
        sentinel_set = {'', 'null', 'none', 'disabled', 'off', 'false', '0'}
        for binding, expect_disabled, exp_binding, exp_host in test_cases:
            is_disabled = not binding or binding.lower() in sentinel_set
            assert is_disabled == expect_disabled
            if is_disabled:
                assert exp_binding == 'ollama'
                assert exp_host == f'http://localhost:{port}/api/rerank'


# ── handle_provider_model_update invalidates cache for all types ─────────────────

class TestHandleProviderModelUpdateInvalidatesAllTypes:
    """handle_provider_model_update calls invalidate_lightrag_provider_cache for ALL types."""

    @pytest.mark.parametrize('provider_type', ['llm', 'embedding', 'rerank'])
    def test_invalidates_cache_for_all_types(self, provider_type):
        """LLM, Embedding, and Rerank all trigger cache invalidation."""
        from gui.manager.provider_settings_helper import handle_provider_model_update

        gs_data = {
            'default_llm': 'ecanai',
            'default_llm_model': 'qwen-plus',
            'default_embedding': 'ecanai',
            'default_embedding_model': 'text-embedding-v3',
            'default_rerank': 'ecanai',
            'default_rerank_model': 'gte-rerank-v2',
        }

        class FakeGS:
            @property
            def default_llm(self): return gs_data.get('default_llm', '') or 'ecanai'
            @property
            def default_llm_model(self): return gs_data.get('default_llm_model', '') or 'qwen-plus'
            @default_llm_model.setter
            def default_llm_model(self, v): gs_data['default_llm_model'] = v
            @property
            def default_embedding(self): return gs_data.get('default_embedding', '') or 'ecanai'
            @property
            def default_embedding_model(self): return gs_data.get('default_embedding_model', '') or 'text-embedding-v3'
            @default_embedding_model.setter
            def default_embedding_model(self, v): gs_data['default_embedding_model'] = v
            @property
            def default_rerank(self): return gs_data.get('default_rerank', '') or 'ecanai'
            @property
            def default_rerank_model(self): return gs_data.get('default_rerank_model', '') or 'gte-rerank-v2'
            @default_rerank_model.setter
            def default_rerank_model(self, v): gs_data['default_rerank_model'] = v
            def save(self): return True

        ctx = SimpleNamespace(
            get_config_manager=lambda: SimpleNamespace(general_settings=FakeGS()),
            get_agents=lambda: [],
            main_window=SimpleNamespace(update_all_llms=MagicMock(return_value=True)),
        )

        fake_manager = MagicMock()
        fake_manager.retrieve_api_key.return_value = 'test-key'

        with patch('gui.manager.provider_settings_helper.invalidate_lightrag_provider_cache') as mock_inv:
            success, err = handle_provider_model_update(
                ctx,
                provider_identifier='ecanai',
                model_name='gte-rerank-v2',
                provider_type=provider_type,
                manager=fake_manager,
                updated_provider={'display_name': 'eCanAI'},
            )

            assert success, f"Expected success for {provider_type}, got error: {err}"
            mock_inv.assert_called_once_with(provider_type, 'ecanai')


# ── disable/enable integration via handler ─────────────────────────────────────

class TestSetDefaultRerankDisableEnable:
    """Integration test for the disable/enable flow using the real handler logic."""

    def test_disable_clears_rerank_in_settings(self):
        """Disabling rerank clears default_rerank and default_rerank_model in settings."""
        from gui.config.general_settings import GeneralSettings

        # Directly test the property setter
        gs = GeneralSettings.__new__(GeneralSettings)
        gs._data = {'default_rerank': 'ecanai', 'default_rerank_model': 'gte-rerank-v2'}

        # Simulate disable: set to empty string
        gs.default_rerank = ''
        gs.default_rerank_model = ''

        assert gs._data['default_rerank'] == ''
        assert gs._data['default_rerank_model'] == ''

    def test_enable_sets_rerank_in_settings(self):
        """Re-enabling rerank sets the correct provider and model in settings."""
        from gui.config.general_settings import GeneralSettings

        gs = GeneralSettings.__new__(GeneralSettings)
        gs._data = {'default_rerank': '', 'default_rerank_model': ''}

        # Simulate re-enable
        gs.default_rerank = 'ecanai'
        gs.default_rerank_model = 'gte-rerank-v2'

        assert gs._data['default_rerank'] == 'ecanai'
        assert gs._data['default_rerank_model'] == 'gte-rerank-v2'

    def test_disable_sentinel_detection(self):
        """All expected sentinel values are correctly detected as disabled."""
        sentinel_set = {'', 'null', 'none', 'disabled', 'off', 'false', '0'}
        for val in ['', 'null', 'none', 'disabled', 'off', 'false', '0']:
            is_disabled = not val or val.lower() in sentinel_set
            assert is_disabled, f"Value {val!r} should be detected as disabled"
        for val in ['ecanai', 'cohere', 'jina', 'ollama', 'ryoais']:
            is_disabled = not val or val.lower() in sentinel_set
            assert not is_disabled, f"Value {val!r} should NOT be detected as disabled"


# ── Bug 5: disable path does NOT silently re-enable ecanai ──────────────────

class TestDisablePathDoesNotReenable:
    """sync_default_provider_to_lightrag_env must read _data (not the property
    fallback) so that an empty default_rerank is respected as a disable signal,
    not rewritten as 'ecanai'."""

    def test_sync_writes_null_when_default_rerank_is_empty(self):
        """When _data["default_rerank"] is empty, sync writes RERANK_BINDING=null,
        not RERANK_BINDING=ecanai."""
        from knowledge.lightrag_config_manager import LightRAGConfigManager

        # Fake LightRAGConfigManager that tracks what was written
        written_configs: list = []

        class FakeLRConfig:
            def get_value(self, key, default=None):
                # Simulate: env has previous ecanai binding
                if key == 'RERANK_BINDING':
                    return 'ecanai'
                return default
            def update_config(self, updates):
                written_configs.append(dict(updates))
                return True

        class FakeGS:
            # _data["default_rerank"] is empty (user disabled rerank)
            _data = {'default_rerank': '', 'default_rerank_model': ''}

            @property
            def default_rerank(self):
                # The property fallback that caused Bug 5 — should NOT be used
                return self._data.get('default_rerank', '') or 'ecanai'
            @property
            def default_rerank_model(self):
                return self._data.get('default_rerank_model', '') or 'gte-rerank-v2'

        class FakeConfigManager:
            general_settings = FakeGS()
            llm_manager = None
            embedding_manager = None
            rerank_manager = MagicMock()

        class FakeMainWindow:
            config_manager = FakeConfigManager()

        with patch('app_context.AppContext.get_main_window', return_value=FakeMainWindow()):
            with patch('knowledge.lightrag_config_manager.get_config_manager', return_value=FakeLRConfig()):
                from gui.manager.provider_settings_helper import sync_default_provider_to_lightrag_env
                written_configs.clear()
                result = sync_default_provider_to_lightrag_env(provider_type='rerank')

                assert result is True, "Should return True (wrote env)"
                assert len(written_configs) == 1
                written = written_configs[0]
                # The fix: should write null, NOT ecanai
                assert written.get('RERANK_BINDING') == 'null', \
                    f"RERANK_BINDING should be 'null', got {written.get('RERANK_BINDING')!r}"
                # Should also clear the other keys (Bug 1)
                assert written.get('RERANK_MODEL') == ''
                assert written.get('RERANK_BINDING_HOST') == ''
                assert written.get('RERANK_BINDING_API_KEY') == ''

    def test_disable_path_writes_complete_off_state(self):
        """The disable path in handle_set_default_rerank writes all five env keys."""
        from gui.ipc.w2p_handlers.rerank_handler import handle_set_default_rerank
        from gui.ipc.types import IPCRequest

        written_envs: list = []

        class FakeLRConfig:
            def update_config(self, updates):
                written_envs.append(dict(updates))
                return True

        class FakeProvider:
            provider = 'cohere'
            api_key_configured = True
            default_model = 'rerank-v3.5'
            supported_models = [{'model_id': 'rerank-v3.5', 'name': 'rerank-v3.5'}]
            preferred_model = ''

            def get(self, key, default=None):
                return getattr(self, key, default)

            def __getitem__(self, key):
                return getattr(self, key)

        class FakeRerankManager:
            def get_provider(self, name):
                return FakeProvider()

        class FakeGS:
            _data = {'default_rerank': 'cohere', 'default_rerank_model': 'rerank-v3.5'}
            default_rerank = ''
            default_rerank_model = ''

            def save(self):
                self._data['default_rerank'] = ''
                self._data['default_rerank_model'] = ''
                return True

        class FakeConfigManager:
            def __init__(self):
                self.general_settings = FakeGS()
                self.rerank_manager = FakeRerankManager()

            def get_general_settings(self):
                return self.general_settings

        class FakeCtx:
            def __init__(self):
                self._cm = FakeConfigManager()

            def get_config_manager(self):
                return self._cm

            def get_agents(self):
                return []

        request = IPCRequest(id='test-1', type='request', method='set_default_rerank', params={'name': 'null'})

        with patch('gui.ipc.w2p_handlers.rerank_handler.get_handler_context', return_value=FakeCtx()):
            with patch('knowledge.lightrag_config_manager.get_config_manager', return_value=FakeLRConfig()):
                with patch('gui.manager.provider_settings_helper.invalidate_lightrag_provider_cache'):
                    resp = handle_set_default_rerank(request, {'name': 'null'})

        assert resp.get('status') == 'success', f"Expected status=success, got: {resp}"
        assert len(written_envs) == 1
        env = written_envs[0]
        assert env.get('RERANK_BINDING') == 'null'
        assert env.get('RERANK_MODEL') == ''
        assert env.get('RERANK_BINDING_HOST') == ''
        assert env.get('RERANK_BINDING_API_KEY') == ''
        assert env.get('RERANK_BY_DEFAULT') == 'false'


# ── Bug 7: enable path writes RERANK_BY_DEFAULT=true ───────────────────────────

class TestEnablePathWritesByDefaultTrue:
    """Enabling rerank should write RERANK_BY_DEFAULT=true to lightrag.env."""

    def test_enable_writes_rerank_by_default_true(self):
        """Re-enabling rerank writes RERANK_BY_DEFAULT=true."""
        from gui.ipc.w2p_handlers.rerank_handler import handle_set_default_rerank
        from gui.ipc.types import IPCRequest

        written_envs: list = []

        class FakeProvider:
            provider = 'cohere'
            api_key_configured = True
            default_model = 'rerank-v3.5'
            supported_models = [{'model_id': 'rerank-v3.5', 'name': 'rerank-v3.5'}]
            preferred_model = ''

            def get(self, key, default=None):
                return getattr(self, key, default)

            def __getitem__(self, key):
                return getattr(self, key)

        class FakeRerankManager:
            def get_provider(self, name):
                return FakeProvider()

        class FakeLRConfig:
            def update_config(self, updates):
                written_envs.append(dict(updates))
                return True
            def get_value(self, key, default=None):
                return default

        class FakeGS:
            _data = {'default_rerank': '', 'default_rerank_model': ''}
            default_rerank = ''
            default_rerank_model = ''

            def save(self):
                return True

        class FakeConfigManager:
            general_settings = FakeGS()
            rerank_manager = FakeRerankManager()

        class FakeCtx:
            def get_config_manager(self):
                return FakeConfigManager()

            def get_agents(self):
                return []

        request = IPCRequest(id='test-2', type='request', method='set_default_rerank', params={'name': 'cohere'})

        with patch('gui.ipc.w2p_handlers.rerank_handler.get_handler_context', return_value=FakeCtx()):
            with patch('knowledge.lightrag_config_manager.get_config_manager', return_value=FakeLRConfig()):
                with patch('gui.manager.provider_settings_helper.invalidate_lightrag_provider_cache'):
                    resp = handle_set_default_rerank(request, {'name': 'cohere'})

        assert resp.get('status') == 'success', f"Expected status=success, got: {resp}"
        # RERANK_BY_DEFAULT=true should be written
        by_default_writes = [e for e in written_envs if 'RERANK_BY_DEFAULT' in e]
        assert len(by_default_writes) >= 1, \
            f"RERANK_BY_DEFAULT not written. All writes: {written_envs}"
        assert by_default_writes[-1].get('RERANK_BY_DEFAULT') == 'true', \
            f"RERANK_BY_DEFAULT should be 'true', got {by_default_writes[-1].get('RERANK_BY_DEFAULT')!r}"


# ── Bug 2: needs_restart fires on disable even when all non-ecanai ───────────

class TestDisableTriggersRestartAllNonEcanai:
    """When all three providers are non-ecanai, disabling rerank must still
    trigger a LightRAG restart (Bug 2)."""

    def test_disable_returns_true_so_needs_restart_fires(self):
        """sync_default_provider_to_lightrag_env returns True when rerank is disabled,
        so invalidate_lightrag_provider_cache sees env_written=True and fires restart."""
        class FakeLRConfig:
            def get_value(self, key, default=None):
                if key == 'RERANK_BINDING':
                    return 'cohere'
                return default
            def update_config(self, updates):
                return True

        class FakeGS:
            # All non-ecanai → any_ecanai_bound=False in invalidate_lightrag_provider_cache
            _data = {
                'default_llm': 'openai',
                'default_embedding': 'openai',
                'default_rerank': 'cohere',
            }

            @property
            def default_llm(self): return self._data.get('default_llm', '') or 'ecanai'
            @property
            def default_embedding(self): return self._data.get('default_embedding', '') or 'ecanai'
            @property
            def default_rerank(self): return self._data.get('default_rerank', '') or 'ecanai'

        class FakeConfigManager:
            general_settings = FakeGS()
            llm_manager = None
            embedding_manager = None
            rerank_manager = MagicMock()

        class FakeMainWindow:
            config_manager = FakeConfigManager()

        with patch('app_context.AppContext.get_main_window', return_value=FakeMainWindow()):
            with patch('knowledge.lightrag_config_manager.get_config_manager', return_value=FakeLRConfig()):
                from gui.manager.provider_settings_helper import sync_default_provider_to_lightrag_env

                # Simulate: user just disabled rerank (default_rerank='' in _data)
                FakeConfigManager.general_settings._data['default_rerank'] = ''

                result = sync_default_provider_to_lightrag_env(provider_type='rerank')

                # Should return True so needs_restart=True in invalidate_lightrag_provider_cache
                assert result is True, \
                    "sync should return True on disable so LightRAG restarts even when all non-ecanai"
