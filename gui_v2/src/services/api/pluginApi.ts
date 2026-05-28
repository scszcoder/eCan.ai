/**
 * Plugin API — TypeScript wrappers for the plugin.* IPC handlers.
 *
 * Backend lives in agent/ec_skills/browser_use_extension/plugin_*.py and
 * gui/ipc/w2p_handlers/plugin_handler.py. This module is just a thin
 * typed layer over IPCAPI.executeRequest.
 */

import { ipcApi } from '../ipc/api';
import type { APIResponse } from '../ipc/api';

// ---------------------------------------------------------------------------
// Types — mirror PluginEntry / Dependent in plugin_registry.py.
// ---------------------------------------------------------------------------
export type InstallSource = 'builtin' | 'local' | 'catalog';
export type SignatureStatus = 'trusted' | 'verified' | 'unsigned' | 'untrusted' | 'n/a';

export interface PluginHookSummary {
  name: string;
  stage: string;
  runtime: string;
  tier: number;
  priority: number;
}

export interface PluginManifestSummary {
  author?: string;
  description?: string;
  hooks?: PluginHookSummary[];
  config_defaults?: Record<string, unknown>;
  config_schema?: Record<string, unknown> | null;
  kind?: string;
}

export interface PluginEntry {
  name: string;
  version: string;
  kind: string;
  install_source: InstallSource;
  install_path: string;
  enabled: boolean;
  installed_at: number;
  signature_status: SignatureStatus;
  manifest_summary: PluginManifestSummary;
}

export interface PluginDependent {
  skill_id: string;
  skill_name: string;
  skill_path: string;
  node_id: string;
  node_name: string;
}

export interface PluginInstallResult {
  name: string;
  version: string;
  install_path: string;
  install_source: InstallSource;
  signature_status: SignatureStatus;
  kind: string;
}

export interface AutoloadStatus {
  errors: Array<{ bundle: string; install_path: string; message: string; when: number }>;
  loaded: string[];
}

// ---------------------------------------------------------------------------
// API surface
// ---------------------------------------------------------------------------
export type ListSource = 'all' | 'installed' | 'builtin';

export async function listPlugins(source: ListSource = 'all'): Promise<APIResponse<{ items: PluginEntry[] }>> {
  return ipcApi.executeRequest('plugin.list', { source });
}

export async function getPlugin(bundle: string): Promise<APIResponse<{ item: PluginEntry }>> {
  return ipcApi.executeRequest('plugin.get', { bundle });
}

export async function installLocalPlugin(path: string): Promise<APIResponse<PluginInstallResult>> {
  return ipcApi.executeRequest('plugin.install_local', { path });
}

export async function uninstallPlugin(
  bundle: string,
  options?: { force?: boolean }
): Promise<APIResponse<{ ok: boolean }>> {
  return ipcApi.executeRequest('plugin.uninstall', { bundle, force: !!options?.force });
}

export async function enablePlugin(bundle: string): Promise<APIResponse<{ ok: boolean; enabled: boolean }>> {
  return ipcApi.executeRequest('plugin.enable', { bundle });
}

export async function disablePlugin(bundle: string): Promise<APIResponse<{ ok: boolean; enabled: boolean }>> {
  return ipcApi.executeRequest('plugin.disable', { bundle });
}

export async function pluginDependents(bundle: string): Promise<APIResponse<{ dependents: PluginDependent[] }>> {
  return ipcApi.executeRequest('plugin.dependents', { bundle });
}

export async function getAutoloadStatus(): Promise<APIResponse<AutoloadStatus>> {
  return ipcApi.executeRequest('plugin.get_autoload_errors');
}
