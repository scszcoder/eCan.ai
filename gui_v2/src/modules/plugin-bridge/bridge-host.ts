/**
 * BridgeHost — per-iframe instance that vends ``ecan.plugin.*`` over
 * postMessage and routes requests to IPC.
 *
 * Usage:
 *   const host = new BridgeHost(iframeEl, {
 *     bundle: 'feige_chat',
 *     scope: 'global',
 *     allowedMethods: ['config.get', 'config.set', 'storage.get', 'storage.set'],
 *     toolsUi: ['feige_send_message'],
 *     onResize: (h) => setHeight(h),
 *     onNotify: ({type, msg}) => message[type](msg),
 *     getContext: () => ({ theme: 'light', locale: 'en' }),
 *   });
 *   // when unmounting:
 *   host.dispose();
 */

import {
  BRIDGE_PROTOCOL_VERSION,
  BridgeMessage,
  BridgeMethod,
  isBridgeMessage,
  type BridgeHostContext,
} from './bridge-protocol';
import { ipcApi } from '@/services/ipc/api';

const MIN_HEIGHT = 80;
const MAX_HEIGHT = 1800;
const NOTIFY_RATE_MS = 500;

export interface BridgeHostOptions {
  bundle: string;
  scope: 'global' | 'node';
  nodeRef?: { skill_id: string; node_id: string };
  /** Methods the iframe is allowed to call. */
  allowedMethods: BridgeMethod[];
  /** Backend tool names the iframe is allowed to invoke. */
  toolsUi?: string[];
  /** Expected iframe origin (e.g. ``http://127.0.0.1:54321``). */
  expectedOrigin: string;
  onResize?: (heightPx: number) => void;
  onNotify?: (n: { type: 'info' | 'warning' | 'error' | 'success'; msg: string }) => void;
  getContext?: () => Pick<BridgeHostContext, 'theme' | 'locale' | 'agent_id' | 'host_api_version'>;
}

export class BridgeHost {
  private iframe: HTMLIFrameElement;
  private opts: BridgeHostOptions;
  private allowedSet: Set<string>;
  private lastNotifyAt = 0;
  private listener: (e: MessageEvent) => void;

  constructor(iframe: HTMLIFrameElement, opts: BridgeHostOptions) {
    this.iframe = iframe;
    this.opts = opts;
    this.allowedSet = new Set(opts.allowedMethods);

    this.listener = (e: MessageEvent) => {
      // Iframes loaded with sandbox="allow-scripts" (no allow-same-origin)
      // post messages with origin "null" — accept that case as well as the
      // expected localhost origin.
      if (e.origin !== this.opts.expectedOrigin && e.origin !== 'null') return;
      if (e.source !== this.iframe.contentWindow) return;
      if (!isBridgeMessage(e.data)) return;
      if (e.data.type !== 'req') return;
      this.handle(e.data).catch((err) => {
        // Failsafe: never throw out of the listener.
        // eslint-disable-next-line no-console
        console.error('[PluginBridge] unhandled request error', err);
      });
    };
    window.addEventListener('message', this.listener);
  }

  /** Push an event to the iframe (e.g. host.theme_changed). */
  emit(name: string, data?: unknown) {
    this.post({ v: BRIDGE_PROTOCOL_VERSION, type: 'evt', name, data });
  }

  dispose() {
    window.removeEventListener('message', this.listener);
  }

  // -------------------------------------------------------------------------
  private post(msg: BridgeMessage) {
    try {
      this.iframe.contentWindow?.postMessage(msg, '*');
    } catch (e) {
      // ignore — iframe likely detached
    }
  }

  private respondOk(id: string, result?: unknown) {
    this.post({ v: BRIDGE_PROTOCOL_VERSION, type: 'res', id, ok: true, result });
  }

  private respondErr(id: string, code: string, message: string) {
    this.post({
      v: BRIDGE_PROTOCOL_VERSION,
      type: 'res',
      id,
      ok: false,
      error: { code, message },
    });
  }

  private async handle(req: { id: string; method: string; params?: any }) {
    const { id, method } = req;
    const params = (req.params || {}) as Record<string, unknown>;

    if (!this.allowedSet.has(method)) {
      this.respondErr(id, 'DENIED', `method not in allowlist: ${method}`);
      return;
    }

    try {
      switch (method) {
        case 'host.context':
          this.respondOk(id, this.buildContext());
          return;
        case 'ui.resize':
          this.handleResize(id, params);
          return;
        case 'ui.notify':
          this.handleNotify(id, params);
          return;
        case 'config.get':
          await this.handleConfigGet(id);
          return;
        case 'config.set':
          await this.handleConfigSet(id, params);
          return;
        case 'storage.get':
          await this.handleStorageGet(id, params);
          return;
        case 'storage.set':
          await this.handleStorageSet(id, params);
          return;
        case 'storage.keys':
          // No backend storage_keys IPC yet — phase 4. Return empty
          // until then; iframes that need it can probe and fall back.
          this.respondOk(id, { keys: [] });
          return;
        case 'tools.invoke':
          await this.handleToolsInvoke(id, params);
          return;
        default:
          this.respondErr(id, 'UNKNOWN_METHOD', `unknown bridge method: ${method}`);
      }
    } catch (e: any) {
      this.respondErr(id, 'INTERNAL', String(e?.message || e));
    }
  }

  private buildContext(): BridgeHostContext {
    const ctx = this.opts.getContext?.() || { theme: 'light', locale: 'en', host_api_version: 1 };
    return {
      bundle: this.opts.bundle,
      scope: this.opts.scope,
      node_ref: this.opts.nodeRef,
      agent_id: ctx.agent_id,
      theme: ctx.theme,
      locale: ctx.locale,
      host_api_version: ctx.host_api_version,
    };
  }

  private handleResize(id: string, params: Record<string, unknown>) {
    const raw = Number(params.height ?? params.h);
    if (!Number.isFinite(raw)) {
      this.respondErr(id, 'BAD_ARGS', "'height' must be a number");
      return;
    }
    const clamped = Math.max(MIN_HEIGHT, Math.min(MAX_HEIGHT, raw));
    this.opts.onResize?.(clamped);
    this.respondOk(id, { height: clamped });
  }

  private handleNotify(id: string, params: Record<string, unknown>) {
    const now = Date.now();
    if (now - this.lastNotifyAt < NOTIFY_RATE_MS) {
      this.respondErr(id, 'RATE_LIMITED', 'notify rate limit');
      return;
    }
    this.lastNotifyAt = now;
    const type = (params.type as string) || 'info';
    const msg = String(params.msg || params.message || '');
    if (!['info', 'warning', 'error', 'success'].includes(type)) {
      this.respondErr(id, 'BAD_ARGS', "'type' must be info|warning|error|success");
      return;
    }
    this.opts.onNotify?.({ type: type as any, msg });
    this.respondOk(id, { ok: true });
  }

  private async handleConfigGet(id: string) {
    const resp = await ipcApi.executeRequest<{ config_user: any; config_effective: any; config_schema: any }>(
      'plugin.get_config',
      { bundle: this.opts.bundle }
    );
    if (resp.success && resp.data) {
      this.respondOk(id, resp.data);
    } else {
      this.respondErr(id, resp.error?.code || 'IPC_FAILED', resp.error?.message || 'config.get failed');
    }
  }

  private async handleConfigSet(id: string, params: Record<string, unknown>) {
    if (this.opts.scope === 'node') {
      // Per-node config lives in skill JSON; the iframe should write via
      // ui events to the host, not via this IPC. Reject explicitly.
      this.respondErr(id, 'WRONG_SCOPE', "config.set against per-node scope must use ui.notify-driven host write");
      return;
    }
    const patch = params.patch || {};
    if (typeof patch !== 'object' || patch === null) {
      this.respondErr(id, 'BAD_ARGS', "'patch' must be an object");
      return;
    }
    const resp = await ipcApi.executeRequest<{ config_user: any; config_effective: any }>(
      'plugin.set_config',
      { bundle: this.opts.bundle, patch }
    );
    if (resp.success && resp.data) {
      this.respondOk(id, resp.data);
      // Notify iframe so it can refresh its view without re-fetching.
      this.emit('config.changed', resp.data);
    } else {
      this.respondErr(id, resp.error?.code || 'IPC_FAILED', resp.error?.message || 'config.set failed');
    }
  }

  private async handleStorageGet(id: string, params: Record<string, unknown>) {
    const key = String(params.key || '');
    if (!key) {
      this.respondErr(id, 'BAD_ARGS', "'key' is required");
      return;
    }
    const resp = await ipcApi.executeRequest<{ value: any }>(
      'plugin.storage_get',
      { bundle: this.opts.bundle, key }
    );
    if (resp.success && resp.data) {
      this.respondOk(id, resp.data);
    } else {
      this.respondErr(id, resp.error?.code || 'IPC_FAILED', resp.error?.message || 'storage.get failed');
    }
  }

  private async handleStorageSet(id: string, params: Record<string, unknown>) {
    const key = String(params.key || '');
    const value = params.value;
    if (!key) {
      this.respondErr(id, 'BAD_ARGS', "'key' is required");
      return;
    }
    const resp = await ipcApi.executeRequest<{ ok: boolean }>(
      'plugin.storage_set',
      { bundle: this.opts.bundle, key, value }
    );
    if (resp.success && resp.data) {
      this.respondOk(id, resp.data);
    } else {
      this.respondErr(id, resp.error?.code || 'IPC_FAILED', resp.error?.message || 'storage.set failed');
    }
  }

  private async handleToolsInvoke(id: string, params: Record<string, unknown>) {
    const tool = String(params.tool || '');
    // params.args is forwarded to the backend once tools.invoke wiring lands.
    if (!tool) {
      this.respondErr(id, 'BAD_ARGS', "'tool' is required");
      return;
    }
    const allow = this.opts.toolsUi || [];
    if (!allow.includes(tool)) {
      this.respondErr(id, 'DENIED', `tool not in gui.permissions.tools_ui: ${tool}`);
      return;
    }
    // For Phase 3 we don't yet bind to the dispatcher's ScopedToolProxy
    // from the IPC side — that's Phase 4's plugin.invoke_tool handler.
    // Until then, surface a clear NOT_IMPLEMENTED so iframe authors
    // know the host plumbing is pending.
    this.respondErr(id, 'NOT_IMPLEMENTED', 'tools.invoke wiring lands in a follow-on phase');
  }
}
