/* eslint-disable */
/**
 * ecan-plugin-bridge — vendorable shim for plugin GUI authors.
 *
 * Copy this file into your plugin's gui/ folder. Load it BEFORE any
 * inline script that wants to call ``window.ecan.plugin.*``. See
 * ``docs/PLUGIN_AUTHORING.md`` for the full method catalogue.
 *
 * Wire format (one request per call):
 *   { v:1, type:"req", id:<uuid>, method:"config.get", params:{...} }
 * The host responds with:
 *   { v:1, type:"res", id:<uuid>, ok:true,  result:<any> }
 * or { v:1, type:"res", id:<uuid>, ok:false, error:{code,message} }
 * The host may also push events:
 *   { v:1, type:"evt", name:"config.changed", data:<any> }
 */
(function () {
  if (window.ecan && window.ecan.plugin) return; // already loaded

  const V = 1;
  const pending = new Map();
  const listeners = new Map(); // event name → Set of callbacks
  let nextId = 1;

  function newId() {
    return `req-${Date.now().toString(36)}-${nextId++}`;
  }

  function call(method, params) {
    return new Promise((resolve, reject) => {
      const id = newId();
      pending.set(id, { resolve, reject });
      const msg = { v: V, type: 'req', id, method, params: params || {} };
      window.parent.postMessage(msg, '*');
    });
  }

  function on(name, cb) {
    if (!listeners.has(name)) listeners.set(name, new Set());
    listeners.get(name).add(cb);
    return () => listeners.get(name).delete(cb);
  }

  window.addEventListener('message', function (e) {
    const m = e.data;
    if (!m || typeof m !== 'object' || m.v !== V) return;
    if (m.type === 'res') {
      const slot = pending.get(m.id);
      if (!slot) return;
      pending.delete(m.id);
      if (m.ok) slot.resolve(m.result);
      else slot.reject(Object.assign(new Error(m.error?.message || 'bridge error'), {
        code: m.error?.code || 'UNKNOWN',
      }));
    } else if (m.type === 'evt') {
      const subs = listeners.get(m.name);
      if (subs) subs.forEach((cb) => { try { cb(m.data); } catch (e) { /* swallow */ } });
    }
  });

  window.ecan = window.ecan || {};
  window.ecan.plugin = {
    /** Read merged effective config + user override + schema. */
    config: {
      get: () => call('config.get'),
      set: (patch) => call('config.set', { patch }),
      onChange: (cb) => on('config.changed', cb),
    },
    /** Per-plugin KV store. Pass value=null to delete. */
    storage: {
      get: (key) => call('storage.get', { key }).then((r) => r && r.value),
      set: (key, value) => call('storage.set', { key, value }),
      del: (key) => call('storage.set', { key, value: null }),
      keys: () => call('storage.keys').then((r) => (r && r.keys) || []),
    },
    /** UI hints to the host. */
    ui: {
      resize: (height) => call('ui.resize', { height }),
      notify: (type, msg) => call('ui.notify', { type, msg }),
    },
    /** Host-supplied context (theme, locale, bundle, scope, etc.). */
    host: {
      context: () => call('host.context'),
    },
    /** Backend tool invocation (subject to gui.permissions.tools_ui). */
    tools: {
      invoke: (tool, args) => call('tools.invoke', { tool, args: args || {} }),
    },
  };
})();
