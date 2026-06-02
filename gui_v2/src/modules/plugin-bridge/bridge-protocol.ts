/**
 * Plugin Bridge protocol — postMessage envelopes between the host
 * (Plugins page / skill editor) and a sandboxed plugin iframe.
 *
 * Wire format
 * -----------
 *   { v, type: "req"|"res"|"evt", id?, method?, params?, ok?, result?, error?, name?, data? }
 *
 * Versioned via ``v``; bumped only when the envelope shape itself
 * changes. Method-level additions don't need a bump.
 *
 * Permission model
 * ----------------
 * Each plugin manifest may declare a ``gui.permissions.bridge_methods``
 * allowlist. The host's BridgeHost enforces that — methods absent from
 * the allowlist are rejected with code DENIED. Methods that need extra
 * scope (e.g. tools.invoke against permissions.tools_ui) are gated on
 * top of the allowlist.
 *
 * Method namespaces
 * -----------------
 *   config.get   — read merged effective config
 *   config.set   — patch global override config
 *   storage.get  — read from plugin KV
 *   storage.set  — write to plugin KV (null deletes)
 *   storage.keys — list keys
 *   ui.resize    — request iframe height change (host clamps)
 *   ui.notify    — toast in host UI
 *   host.context — read-only context (theme, locale, bundle, scope)
 *   tools.invoke — call a backend tool (gated by gui.permissions.tools_ui)
 */

export const BRIDGE_PROTOCOL_VERSION = 1;

export type BridgeMethod =
  | 'config.get'
  | 'config.set'
  | 'storage.get'
  | 'storage.set'
  | 'storage.keys'
  | 'ui.resize'
  | 'ui.notify'
  | 'host.context'
  | 'tools.invoke';

export interface BridgeRequest {
  v: number;
  type: 'req';
  id: string;
  method: BridgeMethod | string;
  params?: unknown;
}

export interface BridgeResponseOk {
  v: number;
  type: 'res';
  id: string;
  ok: true;
  result?: unknown;
}

export interface BridgeResponseErr {
  v: number;
  type: 'res';
  id: string;
  ok: false;
  error: { code: string; message: string };
}

export type BridgeResponse = BridgeResponseOk | BridgeResponseErr;

export interface BridgeEvent {
  v: number;
  type: 'evt';
  name: string;
  data?: unknown;
}

export type BridgeMessage = BridgeRequest | BridgeResponse | BridgeEvent;

export function isBridgeMessage(v: unknown): v is BridgeMessage {
  if (!v || typeof v !== 'object') return false;
  const o = v as any;
  return typeof o.v === 'number' && (o.type === 'req' || o.type === 'res' || o.type === 'evt');
}

/** Context exposed to the iframe via host.context. */
export interface BridgeHostContext {
  bundle: string;
  scope: 'global' | 'node';
  node_ref?: { skill_id: string; node_id: string };
  agent_id?: string;
  theme: 'dark' | 'light';
  locale: string;
  host_api_version: number;
}

/** Method-level allowlist enforced by BridgeHost; defaults when manifest is silent. */
export const DEFAULT_BRIDGE_METHODS: BridgeMethod[] = [
  'config.get',
  'storage.get',
  'storage.set',
  'storage.keys',
  'ui.resize',
  'ui.notify',
  'host.context',
];
