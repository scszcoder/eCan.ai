"""
Plugin IPC handlers — list / get / install_local / uninstall /
enable / disable / dependents / get_autoload_errors.

Phase 1 surface only. Catalog, config-form, and per-node config wiring
come in later phases.

All methods are gated by the standard registry (token + system-ready
checks); they are NOT whitelisted, so they require an active session.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from utils.logger_helper import logger_helper as logger

from ..registry import IPCHandlerRegistry
from ..types import (
    IPCRequest,
    IPCResponse,
    create_error_response,
    create_success_response,
)


def _entry_to_dict(entry) -> Dict[str, Any]:
    """Serialize a PluginEntry for the wire."""
    return entry.model_dump()


def _dependent_to_dict(dep) -> Dict[str, Any]:
    return {
        "skill_id": dep.skill_id,
        "skill_name": dep.skill_name,
        "skill_path": dep.skill_path,
        "node_id": dep.node_id,
        "node_name": dep.node_name,
    }


@IPCHandlerRegistry.handler('plugin.list')
def handle_plugin_list(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """List plugins.

    Params:
        source: "all" (default) | "installed" | "builtin"
    """
    try:
        from agent.ec_skills.browser_use_extension import plugin_registry
        source = (params or {}).get('source', 'all')
        if source == 'installed':
            items = plugin_registry.list_installed()
        elif source == 'builtin':
            items = [e for e in plugin_registry.list_all() if e.install_source == 'builtin']
        else:
            items = plugin_registry.list_all()
        return create_success_response(request, {
            'items': [_entry_to_dict(e) for e in items],
        })
    except Exception as e:
        logger.error(f"[Plugin] list failed: {e}", exc_info=True)
        return create_error_response(request, 'LIST_FAILED', str(e))


@IPCHandlerRegistry.handler('plugin.get')
def handle_plugin_get(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get one plugin by name."""
    try:
        bundle = (params or {}).get('bundle', '').strip()
        if not bundle:
            return create_error_response(request, 'BAD_ARGS', "'bundle' is required")
        from agent.ec_skills.browser_use_extension import plugin_registry
        entry = plugin_registry.get(bundle)
        if entry is None:
            return create_error_response(request, 'NOT_FOUND', f"plugin not found: {bundle!r}")
        return create_success_response(request, {'item': _entry_to_dict(entry)})
    except Exception as e:
        logger.error(f"[Plugin] get failed: {e}", exc_info=True)
        return create_error_response(request, 'GET_FAILED', str(e))


@IPCHandlerRegistry.handler('plugin.install_local')
def handle_plugin_install_local(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Install a plugin from a local zip or directory.

    Params:
        path: absolute path to a zip file or bundle directory
    """
    try:
        path = (params or {}).get('path', '').strip()
        if not path:
            return create_error_response(request, 'BAD_ARGS', "'path' is required")
        src = Path(path)
        if not src.exists():
            return create_error_response(request, 'NOT_FOUND', f"path does not exist: {path}")

        from agent.ec_skills.browser_use_extension import plugin_installer
        try:
            if src.is_file():
                result = plugin_installer.install_from_zip(src)
            elif src.is_dir():
                result = plugin_installer.install_from_dir(src)
            else:
                return create_error_response(request, 'BAD_ARGS', f"path is neither file nor directory: {path}")
        except plugin_installer.InvalidBundleError as e:
            return create_error_response(request, 'INVALID_BUNDLE', str(e))
        except plugin_installer.PluginInstallerError as e:
            return create_error_response(request, 'INSTALL_FAILED', str(e))

        return create_success_response(request, {
            'name': result.name,
            'version': result.version,
            'install_path': result.install_path,
            'install_source': result.install_source,
            'signature_status': result.signature_status,
            'kind': result.kind,
        })
    except Exception as e:
        logger.error(f"[Plugin] install_local failed: {e}", exc_info=True)
        return create_error_response(request, 'INSTALL_FAILED', str(e))


@IPCHandlerRegistry.handler('plugin.uninstall')
def handle_plugin_uninstall(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Uninstall a plugin.

    Params:
        bundle: bundle name
        force:  optional bool; if True, override dependents check
    """
    try:
        bundle = (params or {}).get('bundle', '').strip()
        if not bundle:
            return create_error_response(request, 'BAD_ARGS', "'bundle' is required")
        force = bool((params or {}).get('force', False))

        from agent.ec_skills.browser_use_extension import plugin_installer
        try:
            plugin_installer.uninstall(bundle, force=force)
        except plugin_installer.DependentsBlockedError as e:
            return create_error_response(
                request, 'DEPENDENTS_BLOCKED',
                str(e),
            )
        except plugin_installer.PluginInstallerError as e:
            return create_error_response(request, 'UNINSTALL_FAILED', str(e))
        return create_success_response(request, {'ok': True})
    except Exception as e:
        logger.error(f"[Plugin] uninstall failed: {e}", exc_info=True)
        return create_error_response(request, 'UNINSTALL_FAILED', str(e))


@IPCHandlerRegistry.handler('plugin.enable')
def handle_plugin_enable(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    return _set_enabled(request, params, True)


@IPCHandlerRegistry.handler('plugin.disable')
def handle_plugin_disable(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    return _set_enabled(request, params, False)


def _set_enabled(request: IPCRequest, params: Optional[Dict[str, Any]], enabled: bool) -> IPCResponse:
    try:
        bundle = (params or {}).get('bundle', '').strip()
        if not bundle:
            return create_error_response(request, 'BAD_ARGS', "'bundle' is required")
        from agent.ec_skills.browser_use_extension import plugin_registry
        ok = plugin_registry.set_enabled(bundle, enabled)
        if not ok:
            return create_error_response(
                request, 'NOT_FOUND',
                f"plugin not in user registry: {bundle!r} (builtins can't be toggled here)",
            )
        return create_success_response(request, {'ok': True, 'enabled': enabled})
    except Exception as e:
        logger.error(f"[Plugin] enable/disable failed: {e}", exc_info=True)
        return create_error_response(request, 'SET_ENABLED_FAILED', str(e))


@IPCHandlerRegistry.handler('plugin.dependents')
def handle_plugin_dependents(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """List skill nodes that reference a bundle by name."""
    try:
        bundle = (params or {}).get('bundle', '').strip()
        if not bundle:
            return create_error_response(request, 'BAD_ARGS', "'bundle' is required")
        from agent.ec_skills.browser_use_extension import plugin_dependents
        deps = plugin_dependents.find_dependents(bundle)
        return create_success_response(request, {
            'dependents': [_dependent_to_dict(d) for d in deps],
        })
    except Exception as e:
        logger.error(f"[Plugin] dependents failed: {e}", exc_info=True)
        return create_error_response(request, 'DEPENDENTS_FAILED', str(e))


@IPCHandlerRegistry.handler('plugin.get_autoload_errors')
def handle_plugin_get_autoload_errors(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Return any boot-time plugin autoload errors for the GUI to display."""
    try:
        from agent.ec_skills.browser_use_extension import plugin_autoload
        return create_success_response(request, {
            'errors': plugin_autoload.get_autoload_errors(),
            'loaded': plugin_autoload.get_loaded_bundles(),
        })
    except Exception as e:
        logger.error(f"[Plugin] get_autoload_errors failed: {e}", exc_info=True)
        return create_error_response(request, 'AUTOLOAD_ERRORS_FAILED', str(e))


# ============================================================================
# Phase 3: GUI bridge, config, storage, catalog
# ============================================================================

@IPCHandlerRegistry.handler('plugin.get_gui_url')
def handle_plugin_get_gui_url(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Return the iframe URL for a plugin's GUI slot, or null if none declared.

    Params:
        bundle: bundle name
        slot:   one of "config_panel", "node_config", "status_widget"
    """
    try:
        bundle = (params or {}).get('bundle', '').strip()
        slot = (params or {}).get('slot', '').strip()
        if not bundle or not slot:
            return create_error_response(request, 'BAD_ARGS', "'bundle' and 'slot' are required")
        from agent.ec_skills.browser_use_extension import plugin_gui_server
        url = plugin_gui_server.get_gui_url(bundle, slot)
        slots = plugin_gui_server.gui_slots(bundle)
        return create_success_response(request, {
            'url': url,
            'port': plugin_gui_server.port(),
            'slots': list(slots.keys()),
            'slot_config': slots.get(slot),
        })
    except Exception as e:
        logger.error(f"[Plugin] get_gui_url failed: {e}", exc_info=True)
        return create_error_response(request, 'GUI_URL_FAILED', str(e))


@IPCHandlerRegistry.handler('plugin.get_config')
def handle_plugin_get_config(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Return the plugin's user-override config + merged effective config.

    Params:
        bundle: bundle name
    Returns:
        { config_user, config_effective, config_schema }
    """
    try:
        bundle = (params or {}).get('bundle', '').strip()
        if not bundle:
            return create_error_response(request, 'BAD_ARGS', "'bundle' is required")
        from agent.ec_skills.browser_use_extension import plugin_config, plugin_registry
        entry = plugin_registry.get(bundle)
        if entry is None:
            return create_error_response(request, 'NOT_FOUND', f"plugin not found: {bundle!r}")
        return create_success_response(request, {
            'config_user': plugin_config.get(bundle),
            'config_effective': plugin_config.merged(bundle),
            'config_schema': entry.manifest_summary.get('config_schema'),
        })
    except Exception as e:
        logger.error(f"[Plugin] get_config failed: {e}", exc_info=True)
        return create_error_response(request, 'GET_CONFIG_FAILED', str(e))


@IPCHandlerRegistry.handler('plugin.set_config')
def handle_plugin_set_config(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Merge ``patch`` into the plugin's global user-override config.

    Params:
        bundle: bundle name
        patch:  object to merge (validated against config_schema)
        replace: optional bool; when true, full-replace instead of merge
    """
    try:
        bundle = (params or {}).get('bundle', '').strip()
        patch = (params or {}).get('patch')
        replace_mode = bool((params or {}).get('replace', False))
        if not bundle:
            return create_error_response(request, 'BAD_ARGS', "'bundle' is required")
        if not isinstance(patch, dict):
            return create_error_response(request, 'BAD_ARGS', "'patch' must be an object")
        from agent.ec_skills.browser_use_extension import plugin_config
        try:
            new_cfg = plugin_config.replace(bundle, patch) if replace_mode else plugin_config.set(bundle, patch)
        except plugin_config.ConfigValidationError as e:
            return create_error_response(request, 'VALIDATION_FAILED', str(e))
        except plugin_config.ConfigError as e:
            return create_error_response(request, 'CONFIG_FAILED', str(e))
        return create_success_response(request, {
            'config_user': new_cfg,
            'config_effective': plugin_config.merged(bundle),
        })
    except Exception as e:
        logger.error(f"[Plugin] set_config failed: {e}", exc_info=True)
        return create_error_response(request, 'SET_CONFIG_FAILED', str(e))


@IPCHandlerRegistry.handler('plugin.storage_get')
def handle_plugin_storage_get(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Read a key from the plugin's KV store.

    Params:
        bundle: bundle name
        key:    string key (required, non-empty)
    """
    try:
        bundle = (params or {}).get('bundle', '').strip()
        key = (params or {}).get('key', '')
        if not bundle:
            return create_error_response(request, 'BAD_ARGS', "'bundle' is required")
        if not isinstance(key, str) or not key:
            return create_error_response(request, 'BAD_ARGS', "'key' must be a non-empty string")
        from agent.ec_skills.browser_use_extension import plugin_storage
        try:
            value = plugin_storage.get(bundle, key)
        except plugin_storage.StorageError as e:
            return create_error_response(request, 'STORAGE_FAILED', str(e))
        return create_success_response(request, {'value': value})
    except Exception as e:
        logger.error(f"[Plugin] storage_get failed: {e}", exc_info=True)
        return create_error_response(request, 'STORAGE_GET_FAILED', str(e))


@IPCHandlerRegistry.handler('plugin.storage_set')
def handle_plugin_storage_set(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Write a key/value into the plugin's KV store.

    Params:
        bundle: bundle name
        key:    string key
        value:  JSON-serializable value (null deletes)
    """
    try:
        bundle = (params or {}).get('bundle', '').strip()
        key = (params or {}).get('key', '')
        value = (params or {}).get('value')
        if not bundle:
            return create_error_response(request, 'BAD_ARGS', "'bundle' is required")
        if not isinstance(key, str) or not key:
            return create_error_response(request, 'BAD_ARGS', "'key' must be a non-empty string")
        from agent.ec_skills.browser_use_extension import plugin_storage
        try:
            if value is None:
                plugin_storage.delete(bundle, key)
            else:
                plugin_storage.set(bundle, key, value)
        except plugin_storage.StorageLimitError as e:
            return create_error_response(request, 'STORAGE_LIMIT', str(e))
        except plugin_storage.StorageError as e:
            return create_error_response(request, 'STORAGE_FAILED', str(e))
        return create_success_response(request, {'ok': True})
    except Exception as e:
        logger.error(f"[Plugin] storage_set failed: {e}", exc_info=True)
        return create_error_response(request, 'STORAGE_SET_FAILED', str(e))


@IPCHandlerRegistry.handler('plugin.catalog_index')
def handle_plugin_catalog_index(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Return the current catalog index. Stub when ECAN_PLUGIN_CATALOG_URL is unset."""
    try:
        force = bool((params or {}).get('force', False))
        from agent.ec_skills.browser_use_extension import catalog_client
        idx = catalog_client.fetch_index(force=force)
        return create_success_response(request, idx.to_dict())
    except Exception as e:
        logger.error(f"[Plugin] catalog_index failed: {e}", exc_info=True)
        return create_error_response(request, 'CATALOG_FAILED', str(e))


# Module-load marker — confirms registration ran.
logger.info("[Plugin] plugin_handler module loaded (plugin.* IPC handlers registered)")
