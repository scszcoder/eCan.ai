"""
Provider configuration utilities
Common functions for handling provider updates (LLM, Embedding, Rerank)
"""
from typing import Dict, Optional, Tuple
from utils.logger_helper import logger_helper as logger


def sync_account_api_key_to_ecanai(api_key: str, main_window=None) -> Tuple[bool, Optional[str]]:
    """Store an account API key for all eCanAI provider roles and apply it."""
    value = str(api_key or '').strip()
    if not value:
        return False, 'Account API key is empty'

    try:
        if main_window is None:
            from app_context import AppContext
            main_window = AppContext.get_main_window()
        if not main_window or not getattr(main_window, 'config_manager', None):
            return False, 'Main window is not initialized'

        config_manager = main_window.config_manager
        role_config = (
            ('llm', config_manager.llm_manager, 'ECANAI_LLM_API_KEY'),
            ('embedding', config_manager.embedding_manager, 'ECANAI_EMBEDDING_API_KEY'),
            ('rerank', config_manager.rerank_manager, 'ECANAI_RERANK_API_KEY'),
        )
        for role, manager, env_var in role_config:
            success, error = manager.store_api_key(env_var, value)
            if not success:
                return False, f'Failed to store eCanAI {role} key: {error or "unknown error"}'

        general_settings = config_manager.general_settings
        active_roles = [
            role for role, _, _ in role_config
            if str(getattr(general_settings, f'default_{role}', '') or '').lower() == 'ecanai'
        ]

        # Apply the new credentials to active in-process clients.
        if 'llm' in active_roles and hasattr(main_window, 'update_all_llms'):
            try:
                main_window.update_all_llms(reason='eCanAI account API key synchronized')
            except Exception as exc:
                logger.warning(f'[ProviderUtils] Failed to hot-update eCanAI LLM: {exc}')

        agents = getattr(main_window, 'agents', None) or []
        for role, update_method in (('embedding', 'update_embeddings'), ('rerank', 'update_reranks')):
            if role not in active_roles:
                continue
            model_name = getattr(general_settings, f'default_{role}_model', '')
            for agent in agents:
                mem_manager = getattr(agent, 'mem_manager', None)
                if mem_manager and hasattr(mem_manager, update_method):
                    try:
                        getattr(mem_manager, update_method)(provider_name='ecanai', model_name=model_name)
                    except Exception as exc:
                        logger.warning(f'[ProviderUtils] Failed to update agent eCanAI {role}: {exc}')

        # This invalidates LightRAG's secure-key overlay. When eCanAI is active,
        # it also restarts the existing child process so the new env takes effect.
        # The parser path below (mineru / docling) reuses the same restart hook.
        # LightRAG document-parser eCanAI sync.
        # When mineru/docling is in eCanAI mode the active credential is
        # ``ECANAI_LLM_API_KEY`` but LightRAG reads it via
        # ``MINERU_API_TOKEN`` / ``DOCLING_API_KEY`` in ``lightrag.env``.
        # The save path of resolve_ecanai_parser_secrets refreshes those
        # env vars from secure_store on every settings save — but a
        # standalone account-key rotation (no LightRAG settings save in
        # this turn) MUST also reach ``.env`` and trigger a LightRAG
        # restart, otherwise the running child process keeps using the
        # previous key. Local / official modes own their own credentials
        # and are intentionally NOT touched here.
        parser_active: list = []
        try:
            from knowledge.lightrag_config_manager import get_config_manager as _get_lr_cfg
            lr_cfg = _get_lr_cfg()
            mineru_mode = str(lr_cfg.get_value('MINERU_API_MODE', '') or '').lower()
            docling_mode = str(lr_cfg.get_value('DOCLING_PROVIDER', '') or '').lower()
            parser_updates: Dict[str, str] = {}
            if mineru_mode == 'ecanai':
                parser_updates['MINERU_API_TOKEN'] = value
                parser_active.append('mineru')
            if docling_mode == 'ecanai':
                parser_updates['DOCLING_API_KEY'] = value
                parser_active.append('docling')
            if parser_updates:
                lr_cfg.update_config(parser_updates)
                logger.info(
                    f'[ProviderUtils] Synced eCanAI account API key to '
                    f'parser env: {sorted(parser_updates)}'
                )
        except Exception as exc:
            logger.warning(f'[ProviderUtils] Could not sync parser keys to lightrag.env: {exc}')

        if active_roles or parser_active:
            invalidate_lightrag_provider_cache('llm', 'ecanai')
        else:
            # No active consumer; still invalidate caches for the next read.
            invalidate_lightrag_provider_cache()

        try:
            # Do not import gui.LocalServer here: that module pulls in the full
            # browser stack and can initialize AppKit as a side effect. Broadcast
            # only when the application has already loaded LocalServer.
            import sys
            local_server_module = sys.modules.get('gui.LocalServer')
            app_ws_manager = getattr(local_server_module, 'app_ws_manager', None)
            if app_ws_manager:
                for role, _, _ in role_config:
                    app_ws_manager.broadcast_sync('lightrag.providersUpdated', {
                        'provider_type': role,
                        'provider': 'ecanai',
                    })
                # Also nudge the Settings UI so it re-pulls parser engine
                # values (MINERU_API_TOKEN / DOCLING_API_KEY). Without this
                # the open Settings tab keeps displaying the previous
                # account key value until the user toggles a provider.
                if parser_active:
                    app_ws_manager.broadcast_sync('lightrag.providersUpdated', {
                        'provider_type': 'parser',
                        'provider': 'ecanai',
                        'engines': parser_active,
                    })
        except Exception as exc:
            logger.debug(f'[ProviderUtils] Could not broadcast eCanAI key sync: {exc}')

        logger.info('[ProviderUtils] Account API key synchronized to all eCanAI provider roles')
        return True, None
    except Exception as exc:
        logger.error(f'[ProviderUtils] Failed to synchronize account API key: {exc}')
        return False, str(exc)


def clear_ecanai_account_api_key(main_window=None) -> Tuple[bool, Optional[str]]:
    """Clear the account-level eCanAI credentials from secure_store and
    lightrag.env, then trigger LightRAG to pick up the cleared state.

    Contract:
      * Removes the three ``ECANAI_{LLM,EMBEDDING,RERANK}_API_KEY``
        slots from secure_store so the next ``sync_account_api_key_to_ecanai``
        (Account page mount, keygen, etc.) does not see a stale value.
      * For each LLM / embedding / rerank role whose current default is
        ``ecanai``: the matching ``LLM_BINDING_API_KEY`` /
        ``EMBEDDING_BINDING_API_KEY`` / ``RERANK_BINDING_API_KEY`` is
        blanked in lightrag.env via
        ``sync_default_provider_to_lightrag_env`` (which already wipes
        the secret when secure_store has no value).
      * For each parser engine (``mineru`` / ``docling``) whose current
        mode is ``ecanai``: ``MINERU_API_TOKEN`` / ``DOCLING_API_KEY``
        are blanked via ``sync_default_parser_to_lightrag_env``
        (which already wipes them when no account key is provisioned).
      * Triggers ``invalidate_lightrag_provider_cache`` so a running
        LightRAG child process is restarted with the cleared env vars,
        matching the rotation contract used by ``sync_account_api_key_to_ecanai``.
      * Broadcasts ``lightrag.providersUpdated`` so any open Knowledge
        → Settings tab refreshes its parser engine field values.

    Returns ``(True, None)`` even if secure_store / lightrag.env writes
    found nothing to clear — the caller (Account page) treats this as
    "successfully removed any local eCanAI credentials".

    Failure modes (each is wrapped and returns ``(False, str(error)``
    without raising):
      * No main_window / no config_manager — surfaces the bootstrap
        error to the IPC caller so the UI does not hang.
      * Per-role secure_store delete failures — caught per role and
        logged at WARNING; the loop continues so a failure on one
        role does not leave the other two slots dangling. The function
        still proceeds to clear lightrag.env and broadcast, so a
        partial failure leaves the system in a consistent end state
        (everything we COULD clear is cleared).
      * ``invalidate_lightrag_provider_cache`` failures — logged and
        swallowed; the local store + .env are already cleared so the
        next launch reads the correct (empty) state.
    """
    try:
        if main_window is None:
            from app_context import AppContext
            main_window = AppContext.get_main_window()
        if not main_window or not getattr(main_window, 'config_manager', None):
            return False, 'Main window is not initialized'

        config_manager = main_window.config_manager
        role_config = (
            ('llm', config_manager.llm_manager, 'ECANAI_LLM_API_KEY'),
            ('embedding', config_manager.embedding_manager, 'ECANAI_EMBEDDING_API_KEY'),
            ('rerank', config_manager.rerank_manager, 'ECANAI_RERANK_API_KEY'),
        )

        # 1. Delete each per-role secret from secure_store. We call
        # ``delete_api_key`` rather than ``store_api_key('','...')``
        # so the slot is removed entirely — a subsequent empty-string
        # retrieval (in the absence of a credential) does not look
        # indistinguishable from a never-provisioned user.
        active_roles: list = []
        for role, manager, env_var in role_config:
            try:
                # Some managers expose delete_api_key; some only expose
                # store_api_key('') — try both.
                deleted = False
                if hasattr(manager, 'delete_api_key'):
                    deleted = bool(manager.delete_api_key(env_var))
                if not deleted and hasattr(manager, 'store_api_key'):
                    # ``delete_api_key`` returned False (e.g. slot was
                    # already empty) is not a hard error; the store_api_key
                    # path would overwrite with an empty key and that is
                    # the observable end state we want.
                    success, _ = manager.store_api_key(env_var, '')
                    deleted = bool(success)
                # Mirror for local roles — only mark role as active if
                # the user is currently routed to ecanai (mirrors the
                # sync helper's derivation logic).
                default_value = str(getattr(
                    config_manager.general_settings,
                    f'default_{role}',
                    '',
                ) or '').lower()
                if default_value == 'ecanai':
                    active_roles.append(role)
            except Exception as role_exc:
                logger.warning(
                    f'[ProviderUtils] Failed to clear eCanAI {role} slot: {role_exc}'
                )

        # 2. Mirror the (now-empty) values into lightrag.env. The sync
        # helper already writes ``''`` when secure_store has no value,
        # so calling it here is the single source of truth for both
        # rotation and removal.
        try:
            sync_default_provider_to_lightrag_env()
        except Exception as sync_err:
            logger.warning(
                f'[ProviderUtils] provider env sync during clear failed: {sync_err}'
            )

        # 3. Parser path — mineru / docling in ecanai mode read
        # MINERU_API_TOKEN / DOCLING_API_KEY from lightrag.env. Same
        # wipe semantics as ``sync_account_api_key_to_ecanai``: blanked
        # when secure_store has no value.
        try:
            sync_default_parser_to_lightrag_env()
        except Exception as parser_sync_err:
            logger.warning(
                f'[ProviderUtils] parser env sync during clear failed: {parser_sync_err}'
            )

        # 4. Hot-update in-process LLMs to drop the eCanAI credential,
        # mirroring the sync path.
        if 'llm' in active_roles and hasattr(main_window, 'update_all_llms'):
            try:
                main_window.update_all_llms(reason='eCanAI account API key cleared')
            except Exception as exc:
                logger.warning(f'[ProviderUtils] Failed to hot-update LLM after clear: {exc}')

        # 5. Notify LightRAG so it picks up cleared env vars (or — when
        # running — restarts to drop the in-memory cache).
        try:
            invalidate_lightrag_provider_cache('llm', 'ecanai')
        except Exception as exc:
            logger.debug(f'[ProviderUtils] Could not invalidate LightRAG cache: {exc}')

        # 6. Broadcast so any open Knowledge → Settings tab refetches
        # its parser current values; mirrors the parser broadcast in
        # ``sync_account_api_key_to_ecanai``.
        try:
            import sys
            local_server_module = sys.modules.get('gui.LocalServer')
            app_ws_manager = getattr(local_server_module, 'app_ws_manager', None)
            if app_ws_manager:
                for role in ('llm', 'embedding', 'rerank'):
                    app_ws_manager.broadcast_sync('lightrag.providersUpdated', {
                        'provider_type': role,
                        'provider': 'ecanai',
                    })
                app_ws_manager.broadcast_sync('lightrag.providersUpdated', {
                    'provider_type': 'parser',
                    'provider': 'ecanai',
                    'engines': ['mineru', 'docling'],
                })
        except Exception as exc:
            logger.debug(f'[ProviderUtils] Could not broadcast eCanAI key clear: {exc}')

        logger.info('[ProviderUtils] Cleared eCanAI account API key from all roles and parser')
        return True, None
    except Exception as exc:
        logger.error(f'[ProviderUtils] Failed to clear account API key: {exc}')
        return False, str(exc)


def update_ollama_base_url(
    provider_identifier: str,
    base_url: str,
    provider_type: str  # 'llm', 'embedding', or 'rerank'
) -> Tuple[bool, Optional[str]]:
    """
    Update Ollama base_url in settings.json.
    
    Args:
        provider_identifier: Provider identifier (e.g., 'ollama')
        base_url: New base URL (e.g., 'http://localhost:11434')
        provider_type: Type of provider ('llm', 'embedding', or 'rerank')
    
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    try:
        if provider_identifier.lower() not in ['ollama', 'ryoais']:
            return False, f"update_ollama_base_url only supports 'ollama' or 'ryoais', got '{provider_identifier}'"
        
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        
        if not main_window:
            error_msg = "Cannot update base_url: main_window not available"
            logger.error(f"[ProviderUtils] {error_msg}")
            return False, error_msg
        
        # Update base_url in memory (don't save yet, will be saved by caller)
        general_settings = main_window.config_manager.general_settings
        provider_lower = provider_identifier.lower()
        
        if provider_type == 'llm':
            if provider_lower == 'ollama':
                general_settings.ollama_llm_base_url = base_url
            elif provider_lower == 'ryoais':
                general_settings.ryoais_llm_base_url = base_url
        elif provider_type == 'embedding':
            if provider_lower == 'ollama':
                general_settings.ollama_embedding_base_url = base_url
            elif provider_lower == 'ryoais':
                general_settings.ryoais_embedding_base_url = base_url
        elif provider_type == 'rerank':
            if provider_lower == 'ollama':
                general_settings.ollama_rerank_base_url = base_url
            elif provider_lower == 'ryoais':
                general_settings.ryoais_rerank_base_url = base_url
        else:
            error_msg = f"Unknown provider_type: {provider_type}"
            logger.error(f"[ProviderUtils] {error_msg}")
            return False, error_msg
        
        # Sync to lightrag.env if this provider is the currently active binding.
        # Without this, Settings saves to settings.json but LightRAG server reads
        # lightrag.env on next start, so the new address would be ignored until
        # the user also opens LightRAG Settings and saves there.
        _sync_base_url_to_lightrag_env(provider_lower, provider_type, base_url)

        logger.info(f"[ProviderUtils] Updated {provider_identifier} {provider_type} base_url: {base_url}")
        return True, None

    except Exception as e:
        error_msg = f"Failed to update base_url: {e}"
        logger.error(f"[ProviderUtils] {error_msg}")
        return False, error_msg


def sync_default_provider_to_lightrag_env(provider_type: str = '', provider_identifier: str = '') -> bool:
    """
    Mirror the active System Settings default provider into lightrag.env.

    The LightRAG server reads ``lightrag.env`` on startup, but System
    Settings persists provider state in ``settings.json`` (default_llm /
    default_embedding / default_rerank). Without this helper, switching
    the default in System Settings would leave the running LightRAG
    server pointing at the previous provider until the user also opened
    LightRAG Settings and saved. The merged Models tab in the new UI is
    read-only for provider info precisely to avoid that drift — this
    helper makes the actual sync happen automatically.

    Behaviour:
      * Looks up the active default for each requested role (or all
        three when ``provider_type`` is empty).
      * Reads the matching provider config from the relevant manager
        (LLM / embedding / rerank) — including ``base_url``,
        ``default_model``, ``api_key_env_vars``.
      * Writes the new ``*_BINDING``, ``*_BINDING_HOST``, ``*_MODEL``
        and ``*_BINDING_API_KEY`` values into lightrag.env via
        ``config_manager.update_config`` so the change is persisted
        atomically with whatever the caller is already doing.
      * Removes any leftover per-provider-only env keys that belonged to
        the previous binding (e.g. AZURE_OPENAI_ENDPOINT when switching
        from azure_openai to openai) so LightRAG never reads a stale
        value from the old provider.
      * Returns ``True`` when any change was actually written. Callers
        use the return value to decide whether a LightRAG restart is
        needed.

    The function is intentionally a no-op for self-hosted providers
    (ollama / ryoais) that read their base_url from ``settings.json`` —
    the existing ``_sync_base_url_to_lightrag_env`` flow already handles
    them. We only enforce consistency here for the canonical binding
    fields and for API keys, which were the only pieces that previously
    fell out of sync.
    """
    try:
        from knowledge.lightrag_config_manager import get_config_manager
        lr_config = get_config_manager()
    except Exception as e:
        logger.debug(f"[ProviderUtils] Could not import lightrag config manager: {e}")
        return False

    try:
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        if not main_window or not getattr(main_window, 'config_manager', None):
            logger.debug("[ProviderUtils] MainWindow not ready; skipping default-provider sync")
            return False

        general_settings = main_window.config_manager.general_settings
        config_manager = main_window.config_manager

        # Baseline summary — printed on EVERY entry so a fresh-launch log
        # tells the operator which provider each role is currently bound
        # to. The "Synced X → Y" line below only fires when something
        # actually changes, so without this line a clean first launch
        # leaves the operator blind when triaging "why is LightRAG using
        # the wrong provider?".
        try:
            active_llm = str(getattr(general_settings, 'default_llm', '') or '').strip() or '(unset)'
            active_emb = str(getattr(general_settings, 'default_embedding', '') or '').strip() or '(unset)'
            active_rerank = str(getattr(general_settings, 'default_rerank', '') or '').strip() or '(unset)'
            logger.info(
                f"[ProviderUtils] Active providers (System Settings): "
                f"llm={active_llm}, embedding={active_emb}, rerank={active_rerank}"
            )
        except Exception as summary_err:
            logger.debug(f"[ProviderUtils] Could not log active providers summary: {summary_err}")

        role_specs = [
            ('llm', 'LLM_BINDING', 'LLM_BINDING_HOST', 'LLM_MODEL', 'LLM_BINDING_API_KEY',
             'default_llm', 'default_llm_model',
             getattr(config_manager, 'llm_manager', None),
             _LLM_PROVIDER_ONLY_KEYS),
            ('embedding', 'EMBEDDING_BINDING', 'EMBEDDING_BINDING_HOST', 'EMBEDDING_MODEL',
             'EMBEDDING_BINDING_API_KEY', 'default_embedding', 'default_embedding_model',
             getattr(config_manager, 'embedding_manager', None),
             _EMBEDDING_PROVIDER_ONLY_KEYS),
            ('rerank', 'RERANK_BINDING', 'RERANK_BINDING_HOST', 'RERANK_MODEL',
             'RERANK_BINDING_API_KEY', 'default_rerank', 'default_rerank_model',
             getattr(config_manager, 'rerank_manager', None),
             _RERANK_PROVIDER_ONLY_KEYS),
        ]

        any_written = False
        for (role, binding_key, host_key, model_key, api_key_key,
             default_attr, default_model_attr, manager, provider_only_keys) in role_specs:
            if provider_type and provider_type != role:
                continue
            if manager is None:
                continue

            new_provider = str(getattr(general_settings, default_attr, '') or '').strip()
            if not new_provider:
                continue

            # Resolve provider config from the matching manager. The
            # provider identifier in System Settings is lowercase, so
            # compare case-insensitively to avoid missing case-only diffs.
            provider_config = None
            try:
                provider_config = manager.get_provider(new_provider)
            except Exception:
                provider_config = None

            current_binding = str(lr_config.get_value(binding_key, '') or '').strip()
            current_host = str(lr_config.get_value(host_key, '') or '').strip()
            current_model = str(lr_config.get_value(model_key, '') or '').strip()
            current_api_key = str(lr_config.get_value(api_key_key, '') or '').strip()

            updates: Dict[str, str] = {}

            # 1. Binding identifier
            if current_binding.lower() != new_provider.lower():
                updates[binding_key] = new_provider

            # 2. Host / base URL — pull from the manager's provider config.
            # Only update if the new provider actually exposes one; some
            # providers (Azure, eCanAI) manage their own endpoint via
            # dedicated env vars rather than BINDING_HOST.
            new_host = ''
            if provider_config is not None:
                try:
                    new_host = str(provider_config.get('base_url', '') or '').strip()
                except Exception:
                    new_host = ''

            # Self-hosted providers (ollama / ryoais) keep their base URL
            # in settings.json; lightrag.env BINDING_HOST is not the source
            # of truth for them. _sync_base_url_to_lightrag_env already
            # mirrors the new URL when the user edits it. Skip here so we
            # don't stomp on the value those helpers manage.
            if new_host and new_provider.lower() not in ('ollama', 'ryoais'):
                if new_host != current_host:
                    updates[host_key] = new_host

            # 3. Default model — prefer the System Settings default
            # (general_settings.default_*_model), fall back to the
            # provider config's default_model.
            new_model = str(getattr(general_settings, default_model_attr, '') or '').strip()
            if not new_model and provider_config is not None:
                try:
                    new_model = str(provider_config.get('default_model', '') or '').strip()
                except Exception:
                    new_model = ''
            if new_model and new_model != current_model:
                updates[model_key] = new_model

            # 4. API key — pull from the secure store via the manager.
            new_api_key = ''
            if provider_config is not None:
                env_vars = []
                try:
                    env_vars = list(provider_config.get('api_key_env_vars', []) or [])
                except Exception:
                    env_vars = []
                if env_vars and hasattr(manager, 'retrieve_api_key'):
                    try:
                        new_api_key = str(manager.retrieve_api_key(env_vars[0]) or '').strip()
                    except Exception:
                        new_api_key = ''

            if new_api_key:
                if new_api_key != current_api_key:
                    updates[api_key_key] = new_api_key
            elif current_api_key:
                # The new provider has no API key configured (e.g. user
                # cleared the key, or the provider is local). Wipe any
                # stale secret from lightrag.env so LightRAG does not
                # silently use it.
                updates[api_key_key] = ''

            # 5. Clean up provider-only env keys from the OLD binding so
            # LightRAG never reads a stale credential. We don't have the
            # old binding here without another config read; fall through
            # to that below.
            if updates or current_binding.lower() != new_provider.lower():
                if current_binding and current_binding.lower() != new_provider.lower():
                    for stale_key in provider_only_keys:
                        try:
                            if lr_config.get_value(stale_key, '') is not None:
                                updates[stale_key] = ''
                        except Exception:
                            pass

            if updates:
                try:
                    lr_config.update_config(updates)
                    any_written = True
                    logger.info(
                        f"[ProviderUtils] Synced {role} default provider "
                        f"{current_binding!r} → {new_provider!r} "
                        f"({len(updates)} env keys updated)"
                    )
                except Exception as write_err:
                    logger.warning(
                        f"[ProviderUtils] Failed to write {role} binding to lightrag.env: {write_err}"
                    )

        return any_written
    except Exception as exc:
        logger.warning(f"[ProviderUtils] sync_default_provider_to_lightrag_env failed: {exc}")
        return False


# ── Per-provider-only env keys that must be cleared when switching
#    bindings. Each list contains keys that ONLY make sense for a
#    specific provider family; if we leave a stale value behind, LightRAG
#    may read it instead of the new provider's settings.
_LLM_PROVIDER_ONLY_KEYS = (
    'AZURE_OPENAI_API_VERSION', 'AZURE_OPENAI_DEPLOYMENT',
    'AZURE_OPENAI_ENDPOINT', 'AZURE_OPENAI_API_KEY',
    'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_REGION',
    'OPENAI_LLM_REASONING_EFFORT', 'OPENAI_LLM_EXTRA_BODY',
    'OPENAI_LLM_TEMPERATURE', 'OPENAI_LLM_MAX_TOKENS',
    'OPENAI_LLM_MAX_COMPLETION_TOKENS',
    'OLLAMA_LLM_NUM_CTX', 'OLLAMA_LLM_NUM_PREDICT', 'OLLAMA_LLM_STOP',
    'BEDROCK_LLM_TEMPERATURE',
    'GEMINI_LLM_MAX_OUTPUT_TOKENS', 'GEMINI_LLM_TEMPERATURE',
    'GEMINI_LLM_THINKING_CONFIG',
    'LLM_TEMPERATURE',
)
_EMBEDDING_PROVIDER_ONLY_KEYS = (
    'AZURE_EMBEDDING_API_VERSION', 'AZURE_EMBEDDING_DEPLOYMENT',
    'AZURE_EMBEDDING_ENDPOINT', 'AZURE_EMBEDDING_API_KEY',
    'OLLAMA_EMBEDDING_NUM_CTX',
    'EMBEDDING_DIM', 'EMBEDDING_SEND_DIM', 'EMBEDDING_TOKEN_LIMIT',
)
_RERANK_PROVIDER_ONLY_KEYS = (
    '_RERANK_RUNTIME_HOST', '_RERANK_USES_PROXY',
)


# ── Parser env vars owned by System Settings ────────────────────────────
# When the user puts MinerU / Docling into ``ecanai`` mode the URL and
# the API key are account-managed — they come from the eCanAI proxy
# (``ECANAI_PARSER_BASE_URL``) and the account-level
# ``ECANAI_LLM_API_KEY`` in secure_store respectively. Local / official
# modes keep their own user-typed credentials and MUST NOT be touched.
_PARSER_ECANAI_FIELDS = (
    # (mode_var, mode_value, endpoint_var, token_var, alias_var)
    # alias_var is the runtime endpoint that LightRAG's local-mode MinerU
    # client reads when eCanAI is an alias for ``local``. We mirror the
    # dedicated eCanAI endpoint into the alias slot so an existing
    # LightRAG process (which may already be wired to the alias) keeps
    # pointing at the right host.
    ('MINERU_API_MODE', 'ecanai', 'MINERU_ECANAI_ENDPOINT',
     'MINERU_API_TOKEN', 'MINERU_LOCAL_ENDPOINT'),
    ('DOCLING_PROVIDER', 'ecanai', 'DOCLING_ECANAI_ENDPOINT',
     'DOCLING_API_KEY', 'DOCLING_LOCAL_ENDPOINT'),
)


def sync_default_parser_to_lightrag_env() -> bool:
    """
    Mirror the eCanAI parser configuration into lightrag.env.

    First-launch contract:
      * System Settings defaults MinerU/Docling to ``ecanai`` mode (see
        ``derive_mineru_provider`` / ``derive_docling_provider``).
      * When the user signs in and an account API key is provisioned
        (``ECANAI_LLM_API_KEY`` in secure_store), that key MUST reach
        ``MINERU_API_TOKEN`` / ``DOCLING_API_KEY`` before LightRAG is
        started, otherwise the parser child process raises
        ``MINERU_API_TOKEN is required when MINERU_API_MODE=local`` on
        the first request.
      * When the user is NOT signed in yet (no account key), the URL
        still needs to be present so LightRAG does not fall back to a
        non-existent local parser. The token is left empty so the first
        parser call surfaces a clean 401 instead of crashing with a
        stack trace.
      * When a stale token from a previous account lingers in
        lightrag.env but the new account has no key yet, we wipe the
        stale value so it cannot be silently reused.

    Local / official modes own their own credentials and are
    intentionally NOT touched. We only intervene when the active mode
    for an engine is ``ecanai``.

    The function is idempotent: a second call when lightrag.env already
    agrees with secure_store is a no-op (no write at all).

    Returns ``True`` when at least one env var was written, ``False``
    otherwise.
    """
    try:
        from knowledge.lightrag_config_manager import get_config_manager
        lr_config = get_config_manager()
    except Exception as exc:
        logger.debug(f"[ProviderUtils] Could not import lightrag config manager: {exc}")
        return False

    # Baseline summary — printed on EVERY entry so the operator can
    # grep the log to see which parser engines are currently in ecanai
    # mode (vs local / official) without having to diff lightrag.env
    # against settings.json. Mirrors the "Active providers" line in
    # ``sync_default_provider_to_lightrag_env``.
    try:
        mineru_mode_summary = str(lr_config.get_value('MINERU_API_MODE', '') or '').strip().lower() or '(unset=default-ecanai)'
        docling_mode_summary = str(lr_config.get_value('DOCLING_PROVIDER', '') or '').strip().lower() or '(unset=default-ecanai)'
    except Exception:
        mineru_mode_summary = docling_mode_summary = '(unavailable)'

    try:
        # The eCanAI parser proxy is a single endpoint shared by MinerU
        # and Docling. Reading it from the canonical source keeps the UI
        # default, the save path, and the startup pre-sync in lock-step.
        from knowledge.lightrag_parser_config import ECANAI_PARSER_BASE_URL
        ecanai_url = str(ECANAI_PARSER_BASE_URL or '').strip()
        if not ecanai_url:
            logger.debug('[ProviderUtils] ECANAI_PARSER_BASE_URL is empty; skipping parser pre-sync')
            logger.info(
                f"[ProviderUtils] Parser modes (lightrag.env): "
                f"mineru={mineru_mode_summary}, docling={docling_mode_summary}, "
                f"ecanai_base_url=(empty)"
            )
            return False
    except Exception as exc:
        logger.warning(f'[ProviderUtils] Could not import parser base URL: {exc}')
        return False

    logger.info(
        f"[ProviderUtils] Parser modes (lightrag.env): "
        f"mineru={mineru_mode_summary}, docling={docling_mode_summary}, "
        f"ecanai_base_url={ecanai_url}"
    )

    account_key = ''
    try:
        from utils.env.secure_store import secure_store, get_current_username
        username = get_current_username()
        if username:
            account_key = str(
                secure_store.get('ECANAI_LLM_API_KEY', username=username) or ''
            ).strip()
    except Exception as exc:
        # secure_store failures must NEVER block LightRAG startup — fall
        # back to the empty-key state and let the request layer surface
        # the missing credential.
        logger.debug(f'[ProviderUtils] Account key lookup during parser pre-sync failed: {exc}')

    updates: Dict[str, str] = {}
    for mode_var, mode_value, endpoint_var, token_var, alias_var in _PARSER_ECANAI_FIELDS:
        try:
            current_mode = str(lr_config.get_value(mode_var, '') or '').strip().lower()
        except Exception:
            current_mode = ''
        # Default is also ``ecanai`` when the var is unset (mirrors
        # ``derive_mineru_provider`` / ``derive_docling_provider`` in
        # ``lightrag_parser_config``).
        is_ecanai = current_mode == mode_value or current_mode == ''
        if not is_ecanai:
            # Local / official — user owns the credentials, do not touch.
            continue

        # Endpoint — keep the dedicated eCanAI env var in lock-step with
        # the canonical URL. Without this, a fresh install starts
        # LightRAG with ``MINERU_ECANAI_ENDPOINT=''`` and the local-mode
        # MinerU client (which eCanAI is an alias for) tries to reach
        # ``http://localhost:...`` and times out.
        try:
            current_endpoint = str(lr_config.get_value(endpoint_var, '') or '').strip()
        except Exception:
            current_endpoint = ''
        if current_endpoint != ecanai_url:
            updates[endpoint_var] = ecanai_url

        # Alias slot — LightRAG's MinerU local client reads
        # ``MINERU_LOCAL_ENDPOINT``; we mirror the eCanAI URL there so a
        # running child process sees the right host without an extra
        # restart. Skip if the alias is currently owned by a different
        # (non-default) value the user typed for local mode — we don't
        # want to clobber a user-typed local URL. The `==` comparison
        # only fires for the literal default.
        try:
            current_alias = str(lr_config.get_value(alias_var, '') or '').strip()
        except Exception:
            current_alias = ''
        alias_default = 'http://localhost:8000'
        if current_alias in ('', alias_default) and alias_var == 'MINERU_LOCAL_ENDPOINT':
            updates[alias_var] = ecanai_url
        elif current_alias == '' and alias_var == 'DOCLING_LOCAL_ENDPOINT':
            updates[alias_var] = ecanai_url

        # Token — sourced from the account store on first launch so the
        # running LightRAG process does not need a save click to pick
        # up the account key.
        try:
            current_token = str(lr_config.get_value(token_var, '') or '').strip()
        except Exception:
            current_token = ''
        if account_key:
            if account_key != current_token:
                updates[token_var] = account_key
        elif current_token:
            # No account key yet but a stale value from a previous
            # account lingers — clear it so the parser does not
            # silently authenticate as the previous user.
            updates[token_var] = ''

    if not updates:
        return False

    try:
        lr_config.update_config(updates)
        logger.info(
            '[ProviderUtils] Synced eCanAI parser config to lightrag.env: '
            f'{sorted(updates)} (account_key={"set" if account_key else "empty"})'
        )
        return True
    except Exception as write_err:
        logger.warning(f'[ProviderUtils] Failed to sync parser config to lightrag.env: {write_err}')
        return False


def _sync_base_url_to_lightrag_env(provider_identifier: str, provider_type: str, base_url: str):
    """
    If the given provider is the currently active LLM/Embedding/Rerank binding,
    write the new base_url into the workspace's lightrag.env so the next
    LightRAG server start picks it up without requiring a second save from the
    LightRAG Settings UI.

    Falls back gracefully if lightrag.env is unavailable.
    """
    try:
        binding_key_map = {
            'llm': 'LLM_BINDING',
            'embedding': 'EMBEDDING_BINDING',
            'rerank': 'RERANK_BINDING',
        }
        host_key_map = {
            'llm': 'LLM_BINDING_HOST',
            'embedding': 'EMBEDDING_BINDING_HOST',
            'rerank': 'RERANK_BINDING_HOST',
        }
        binding_key = binding_key_map.get(provider_type)
        host_key = host_key_map.get(provider_type)
        if not binding_key or not host_key:
            return

        from knowledge.lightrag_config_manager import get_config_manager as get_lr_config
        lr_config = get_lr_config()

        # Check if this provider is the active binding
        current_binding = lr_config.get_value(binding_key, '')
        if current_binding.lower() != provider_identifier.lower():
            logger.debug(
                f"[ProviderUtils] {provider_identifier} is not the active {binding_key} "
                f"(active={current_binding}), skipping lightrag.env sync"
            )
            return

        # Write directly into lightrag.env
        lr_config.update_config({host_key: base_url})
        logger.info(
            f"[ProviderUtils] Synced {provider_identifier} → lightrag.env "
            f"{host_key}={base_url}"
        )
    except Exception as e:
        logger.debug(f"[ProviderUtils] Could not sync base_url to lightrag.env: {e}")


def get_ollama_base_url(provider_type: str, provider_config = None, provider_identifier: str = 'ollama') -> str:
    """
    Get Ollama/RyoAIS base_url from settings.json or provider config.
    
    Args:
        provider_type: Type of provider ('llm', 'embedding', or 'rerank')
        provider_config: Optional provider config (dict or object) with default base_url
        provider_identifier: Provider identifier ('ollama' or 'ryoais')
    
    Returns:
        Base URL string
    """
    provider_lower = provider_identifier.lower()

    # Safety: only allow ollama/ryoais to prevent misuse with cloud providers
    if provider_lower not in ['ollama', 'ryoais']:
        if provider_config:
            return provider_config.get('base_url', '') if isinstance(provider_config, dict) else getattr(provider_config, 'base_url', '')
        return ''
    
    # Get base_url from provider_config (fallback)
    default_url = 'http://localhost/v1' if provider_lower == 'ryoais' else 'http://localhost:11434'
    if provider_config:
        base_url = provider_config.get('base_url', default_url) if isinstance(provider_config, dict) else getattr(provider_config, 'base_url', default_url)
    else:
        base_url = default_url
    
    # Override with settings.json if available
    try:
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        if not main_window:
            return base_url
        
        general_settings = main_window.config_manager.general_settings
        settings_map = {
            'llm': (general_settings.ryoais_llm_base_url, general_settings.ollama_llm_base_url),
            'embedding': (general_settings.ryoais_embedding_base_url, general_settings.ollama_embedding_base_url),
            'rerank': (general_settings.ryoais_rerank_base_url, general_settings.ollama_rerank_base_url),
        }
        
        if provider_type not in settings_map:
            logger.warning(f"[ProviderUtils] Unknown provider_type: {provider_type}")
            return base_url
        
        settings_url = settings_map[provider_type][0 if provider_lower == 'ryoais' else 1]
        if settings_url:
            logger.debug(f"[ProviderUtils] Using {provider_identifier} {provider_type} base_url from settings.json: {settings_url}")
            return settings_url
            
    except Exception as e:
        logger.debug(f"[ProviderUtils] Could not get {provider_identifier}_{provider_type}_base_url from settings: {e}")
    
    return base_url


def get_ollama_api_key(provider_type: str, provider_identifier: str = 'ollama') -> str:
    """
    Get Ollama/RyoAIS API key from Secure Store.
    
    Args:
        provider_type: Type of provider ('llm', 'embedding', or 'rerank')
        provider_identifier: Provider identifier ('ollama' or 'ryoais')
    
    Returns:
        API key string (or provider name as dummy if not configured)
    """
    try:
        from utils.env.secure_store import get_current_username, secure_store
        
        provider_lower = provider_identifier.lower()
        provider_upper = provider_identifier.upper()
        
        # Determine the environment variable name based on provider type
        if provider_type == 'llm':
            env_var = f'{provider_upper}_LLM_API_KEY' if provider_lower == 'ryoais' else 'OLLAMA_LLM_API_KEY'
        elif provider_type == 'embedding':
            env_var = f'{provider_upper}_EMBEDDING_API_KEY' if provider_lower == 'ryoais' else 'OLLAMA_EMBEDDING_API_KEY'
        elif provider_type == 'rerank':
            env_var = f'{provider_upper}_RERANK_API_KEY' if provider_lower == 'ryoais' else 'OLLAMA_RERANK_API_KEY'
        else:
            logger.warning(f"[ProviderUtils] Unknown provider_type: {provider_type}")
            return provider_lower
        
        username = get_current_username()
        api_key = secure_store.get(env_var, username=username)
        if not api_key or not api_key.strip():
            # For local providers without authentication, use dummy key
            logger.debug(f"[ProviderUtils] {env_var} not configured, using dummy key for local access")
            return provider_lower
        
        return api_key
    except Exception as e:
        logger.debug(f"[ProviderUtils] Failed to get {provider_identifier} API key: {e}")
        return provider_identifier.lower()


def update_ollama_model(
    provider_identifier: str,
    model_name: str,
    provider_type: str  # 'llm', 'embedding', or 'rerank'
) -> Tuple[bool, Optional[str]]:
    """
    Update Ollama/RyoAIS model selection in settings.json.
    
    Args:
        provider_identifier: Provider identifier (e.g., 'ollama', 'ryoais')
        model_name: Model name to save
        provider_type: Type of provider ('llm', 'embedding', or 'rerank')
    
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    try:
        if provider_identifier.lower() not in ['ollama', 'ryoais']:
            return False, f"update_ollama_model only supports 'ollama' or 'ryoais', got '{provider_identifier}'"
        
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        
        if not main_window:
            error_msg = "Cannot update model: main_window not available"
            logger.error(f"[ProviderUtils] {error_msg}")
            return False, error_msg
        
        # Update model in memory (don't save yet, will be saved by caller)
        general_settings = main_window.config_manager.general_settings
        provider_lower = provider_identifier.lower()
        
        if provider_type == 'llm':
            if provider_lower == 'ollama':
                general_settings.ollama_llm_model = model_name
            elif provider_lower == 'ryoais':
                general_settings.ryoais_llm_model = model_name
        elif provider_type == 'embedding':
            if provider_lower == 'ollama':
                general_settings.ollama_embedding_model = model_name
            elif provider_lower == 'ryoais':
                general_settings.ryoais_embedding_model = model_name
        elif provider_type == 'rerank':
            if provider_lower == 'ollama':
                general_settings.ollama_rerank_model = model_name
            elif provider_lower == 'ryoais':
                general_settings.ryoais_rerank_model = model_name
        else:
            error_msg = f"Unknown provider_type: {provider_type}"
            logger.error(f"[ProviderUtils] {error_msg}")
            return False, error_msg
        
        logger.info(f"[ProviderUtils] Updated {provider_identifier} {provider_type} model: {model_name}")
        return True, None
        
    except Exception as e:
        error_msg = f"Failed to update model: {e}"
        logger.error(f"[ProviderUtils] {error_msg}")
        return False, error_msg


def handle_provider_model_update(
    ctx,
    provider_identifier: str,
    model_name: str,
    provider_type: str,  # 'llm', 'embedding', or 'rerank'
    manager,
    updated_provider: dict
) -> Tuple[bool, Optional[str]]:
    """
    Unified handler for provider model updates across LLM, Embedding, and Rerank.
    
    Handles:
    1. Local provider (Ollama/RyoAIS) model persistence to settings.json
    2. Default provider model update
    3. Hot-update of active instances (LLMs, embeddings, reranks)
    
    Args:
        ctx: Handler context with config_manager and main_window
        provider_identifier: Provider name (e.g., 'ollama', 'openai')
        model_name: Model name to set
        provider_type: Type of provider ('llm', 'embedding', or 'rerank')
        manager: Provider manager instance (llm_manager, embedding_manager, or rerank_manager)
        updated_provider: Updated provider info dict
    
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    try:
        # Step 1: For local providers (Ollama, RyoAIS), save model selection to settings.json
        model_updated = False
        if provider_identifier.lower() in ['ollama', 'ryoais']:
            success_model, error_msg_model = update_ollama_model(provider_identifier, model_name, provider_type)
            if success_model:
                model_updated = True
                # Save immediately for local providers
                save_general_settings_if_needed(False, False, model_updated)
            elif error_msg_model:
                logger.warning(f"[{provider_type.upper()}] Failed to update model in settings: {error_msg_model}")
        
        # Step 2: If this is the current default provider, also update default_xxx_model
        general_settings = ctx.get_config_manager().general_settings
        
        # Get current default provider based on type
        if provider_type == 'llm':
            current_default = (general_settings.default_llm or "").lower()
            default_model_attr = 'default_llm_model'
        elif provider_type == 'embedding':
            current_default = (general_settings.default_embedding or "").lower()
            default_model_attr = 'default_embedding_model'
        elif provider_type == 'rerank':
            current_default = (general_settings.default_rerank or "").lower()
            default_model_attr = 'default_rerank_model'
        else:
            return False, f"Unknown provider_type: {provider_type}"
        
        # Update default model if this is the default provider
        default_updated = False
        if current_default == (provider_identifier or "").lower():
            setattr(general_settings, default_model_attr, model_name)
            general_settings.save()
            default_updated = True
            logger.info(f"[{provider_type.upper()}] Updated {default_model_attr} to {model_name} for current provider {provider_identifier}")
            
            # Step 3: Hot-update active instances
            _perform_hot_update(ctx, provider_type, provider_identifier, model_name, updated_provider)
        
        return True, None
        
    except Exception as e:
        error_msg = f"Failed to handle provider model update: {e}"
        logger.error(f"[ProviderUtils] {error_msg}")
        import traceback
        logger.error(traceback.format_exc())
        return False, error_msg


def _perform_hot_update(ctx, provider_type: str, provider_identifier: str, model_name: str, updated_provider: dict):
    """
    Perform hot-update of active instances based on provider type.
    
    Args:
        ctx: Handler context
        provider_type: 'llm', 'embedding', or 'rerank'
        provider_identifier: Provider name
        model_name: New model name
        updated_provider: Updated provider info
    """
    try:
        if provider_type == 'llm':
            # Hot-update: Use unified method to update all LLMs (including browser_use)
            provider_info = f"{updated_provider.get('display_name', provider_identifier)}, Model: {model_name}"
            update_success = ctx.main_window.update_all_llms(reason=f"Model changed to {provider_info}")
            
            if not update_success:
                logger.warning(f"[LLM] Failed to update LLM instances after model change, but settings were saved")
        
        elif provider_type in ['embedding', 'rerank']:
            # Hot-update: Update all agents' memoryManager embeddings/reranks
            if ctx.get_agents():
                updated_agents = 0
                update_method = 'update_embeddings' if provider_type == 'embedding' else 'update_reranks'
                
                for agent in ctx.get_agents():
                    if hasattr(agent, 'mem_manager') and agent.mem_manager:
                        try:
                            getattr(agent.mem_manager, update_method)(provider_name=provider_identifier, model_name=model_name)
                            updated_agents += 1
                            logger.debug(f"[{provider_type.upper()}] Updated {provider_type} for agent: {agent.card.name}")
                        except Exception as e:
                            logger.warning(f"[{provider_type.upper()}] Failed to update {provider_type} for agent {agent.card.name}: {e}")
                
                logger.info(f"[{provider_type.upper()}] ✅ Updated {provider_type} for {updated_agents} agents (model change)")
    
    except Exception as e:
        logger.error(f"[{provider_type.upper()}] ❌ Error during hot-update: {e}")
        logger.warning(f"Model settings updated but hot-update failed. Restart may be required for full effect.")


def save_general_settings_if_needed(base_url_updated: bool, auto_set_as_default: bool, model_updated: bool = False) -> bool:
    """
    Save general_settings if any updates were made.
    
    Args:
        base_url_updated: Whether base_url was updated
        auto_set_as_default: Whether default provider was auto-set
        model_updated: Whether model selection was updated
    
    Returns:
        True if saved successfully or no save needed, False otherwise
    """
    logger.debug(f"[ProviderUtils] save_general_settings_if_needed called: base_url_updated={base_url_updated}, auto_set_as_default={auto_set_as_default}, model_updated={model_updated}")
    
    if not (base_url_updated or auto_set_as_default or model_updated):
        logger.debug("[ProviderUtils] No save needed (no updates)")
        return True  # No save needed
    
    try:
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        
        if not main_window:
            logger.error("[ProviderUtils] Cannot save: main_window not available")
            return False
        
        logger.debug("[ProviderUtils] Attempting to save general_settings...")
        general_settings = main_window.config_manager.general_settings
        success = general_settings.save()
        
        if success:
            logger.info("[ProviderUtils] ✅ Saved general_settings to disk (base_url and/or default provider and/or model)")
        else:
            logger.error("[ProviderUtils] ❌ Failed to save general_settings")
        
        return success
        
    except Exception as e:
        logger.error(f"[ProviderUtils] ❌ Exception while saving general_settings: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def invalidate_lightrag_provider_cache(provider_type: str = '', provider_identifier: str = '') -> None:
    """
    Expose provider changes to LightRAG and restart it.

    When the user changes the System Settings default provider
    (``default_llm`` / ``default_embedding`` / ``default_rerank``), the
    new value lands in ``settings.json`` immediately, but LightRAG reads
    from ``lightrag.env``. Without a sync, the user would have to also
    open LightRAG Settings and re-save to push the change through — and
    even then, a running child process cannot pick up new env vars until
    it is replaced. So this function does three things:

      1. Calls ``sync_default_provider_to_lightrag_env`` to mirror the
         active System Settings default (provider identifier, base URL,
         default model, API key from the per-provider secret store) into
         the matching ``LLM_BINDING*`` / ``EMBEDDING_BINDING*`` /
         ``RERANK_BINDING*`` slots of ``lightrag.env``.
      2. Invalidates the LightRAG config cache so the next read picks up
         the new env values.
      3. Restarts the running LightRAG server in a background thread
         (the previous behaviour, which only restarted on eCanAI, has
         been extended to *any* provider switch).

    The legacy eCanAI-only fast path is preserved as a short-circuit so
    account-key rotations that touch no other env var still pay zero
    cost on top of what ``sync_account_api_key_to_ecanai`` already wrote.
    """
    try:
        from knowledge.lightrag_config_manager import get_config_manager
        lr_config = get_config_manager()
        lr_config.invalidate_caches()

        # Always try to sync the active default provider's binding info
        # to lightrag.env, regardless of which provider the user just
        # touched. This is the path that keeps LightRAG in lock-step with
        # System Settings; without it, the merged Models tab would show
        # the right provider but the server would still be using the old
        # one.
        sync_default_provider_to_lightrag_env(provider_type=provider_type)

        from app_context import AppContext
        main_window = AppContext.get_main_window()
        if not main_window:
            return
        general_settings = main_window.config_manager.general_settings

        # Legacy eCanAI fast path: account-key rotation already wrote the
        # .env, so just check whether anything is still bound to eCanAI
        # to decide whether a restart is needed.
        any_ecanai_bound = any(
            hasattr(general_settings, f'default_{role}')
            and str(getattr(general_settings, f'default_{role}', '') or '').lower() == 'ecanai'
            for role in ('llm', 'embedding', 'rerank')
        )

        # LightRAG parser: mineru / docling in ecanai mode also read the
        # account key via MINERU_API_TOKEN / DOCLING_API_KEY. Same restart
        # story — the child process cannot see the new env until it is
        # replaced.
        if not any_ecanai_bound:
            try:
                mineru_mode = str(lr_config.get_value('MINERU_API_MODE', '') or '').lower()
                docling_mode = str(lr_config.get_value('DOCLING_PROVIDER', '') or '').lower()
                if mineru_mode == 'ecanai' or docling_mode == 'ecanai':
                    any_ecanai_bound = True
            except Exception:
                pass

        # Determine whether the provider-switch actually changed anything
        # that requires a restart. ``sync_default_provider_to_lightrag_env``
        # already compared current vs new binding/host/model — we only
        # need to additionally check here for changes outside that
        # helper's scope (e.g. parser env keys when only the parser was
        # touched).
        needs_restart = any_ecanai_bound
        if not needs_restart and provider_type:
            try:
                current = str(lr_config.get_value(
                    {'llm': 'LLM_BINDING', 'embedding': 'EMBEDDING_BINDING', 'rerank': 'RERANK_BINDING'}.get(provider_type, ''),
                    '',
                ) or '').lower()
                # If the caller specified a different provider_identifier
                # than what is currently written to lightrag.env, the
                # active binding was just changed and the child process
                # MUST be replaced.
                if provider_identifier and current != (provider_identifier or '').lower():
                    needs_restart = True
            except Exception:
                pass

        if not needs_restart:
            return

        server = getattr(main_window, 'lightrag_server', None)
        if not server or not server.is_running():
            return

        # A running child process cannot receive new environment variables.
        # Match the server's existing proxy-change behaviour and restart away
        # from the IPC thread so saving provider settings remains responsive.
        import threading

        def restart_with_updated_env() -> None:
            try:
                logger.info('[ProviderUtils] Restarting LightRAG to apply eCanAI settings')
                server.stop()
                server.start(wait_ready=False)
            except Exception as exc:
                logger.error(f'[ProviderUtils] Failed to restart LightRAG: {exc}')

        threading.Thread(
            target=restart_with_updated_env,
            name='LightragECanAIProviderRestart',
            daemon=True,
        ).start()
    except Exception as exc:
        logger.warning(f"[ProviderUtils] Failed to invalidate LightRAG provider cache: {exc}")
