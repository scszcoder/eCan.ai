/* Panel logic for config.html — kept OUT of the HTML on purpose.
 *
 * plugin_gui_server serves these pages with `script-src 'self'`, which
 * blocks inline <script>. An inline block therefore never executes in
 * the packaged app: the page renders its shell, no bridge call is made,
 * and the panel looks empty with nothing in the log. Keep panel code in
 * a .js file next to the page. */

// ---- Local mutable state ----
let cfg = {};

// ---- Render helpers ----
function el(tag, attrs = {}, children = []) {
  const e = document.createElement(tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  for (const c of (children || [])) e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
  return e;
}

function renderQR() {
  const root = document.getElementById('quickReplies');
  root.innerHTML = '';
  const qr = (cfg.quick_replies && typeof cfg.quick_replies === 'object') ? cfg.quick_replies : {};
  Object.entries(qr).forEach(([k, v]) => {
    const row = el('div', { class: 'kv-row' });
    const kInp = el('input', { type: 'text', value: k, placeholder: 'trigger' });
    const vInp = el('input', { type: 'text', value: v, placeholder: 'reply' });
    const del = el('button', { class: 'danger' }, ['×']);
    kInp.addEventListener('input', () => { delete cfg.quick_replies[k]; cfg.quick_replies[kInp.value] = vInp.value; });
    vInp.addEventListener('input', () => { cfg.quick_replies[kInp.value] = vInp.value; });
    del.addEventListener('click', () => { delete cfg.quick_replies[kInp.value]; renderQR(); });
    row.appendChild(kInp); row.appendChild(vInp); row.appendChild(del);
    root.appendChild(row);
  });
}

function applyToForm() {
  document.getElementById('cooldown').value = cfg.cooldown_ms ?? 1500;
  document.getElementById('sendAction').value = cfg.send_action ?? 'feige_send_message';
  renderQR();
}

function readForm() {
  cfg.cooldown_ms = parseInt(document.getElementById('cooldown').value, 10);
  cfg.send_action = document.getElementById('sendAction').value || 'feige_send_message';
  if (!cfg.quick_replies) cfg.quick_replies = {};
}

// ---- Wire up ----
document.getElementById('addQR').addEventListener('click', () => {
  if (!cfg.quick_replies) cfg.quick_replies = {};
  cfg.quick_replies[''] = '';
  renderQR();
});

document.getElementById('save').addEventListener('click', async () => {
  readForm();
  const status = document.getElementById('status');
  try {
    await ecan.plugin.config.set(cfg);
    status.textContent = 'Saved.';
    status.className = 'status ok';
    ecan.plugin.ui.notify('success', 'feige_chat config saved');
  } catch (e) {
    status.textContent = e.message || 'Save failed';
    status.className = 'status err';
  }
});

ecan.plugin.config.onChange((data) => {
  // Host pushed an update (e.g. someone else edited the file).
  if (data && data.config_effective) {
    cfg = JSON.parse(JSON.stringify(data.config_effective));
    applyToForm();
  }
  if (data && data.config_user) {
    accountPh = readPh(data.config_user);
    if (currentStore() === '') renderPh();
  }
});

// =====================================================================
// 过渡话术 — account default lives in plugin config, a per-store override
// in the plugin KV under ``placeholder:<store_key>``.  Same three keys in
// both places, so placeholder_config.py resolves store → account → env.
// =====================================================================
const PH_KEYS = ['placeholder_enabled', 'placeholder_timeout_s', 'placeholder_texts'];
const PH_STORE_PREFIX = 'placeholder:';
const PH_MAX_TEXTS = 5;
const PH_DEFAULT_TIMEOUT = 20;

let stores = {};        // store_key -> {label, last_seen, env_timeout_s}
let accountPh = {};     // explicit account-level choices (never manifest defaults)
let storePh = {};       // store_key -> explicit per-store choices
let phDraft = { placeholder_enabled: false, placeholder_timeout_s: 0, placeholder_texts: [] };

function currentStore() {
  return document.getElementById('storeSel').value || '';
}

function readPh(src) {
  const out = {};
  if (!src || typeof src !== 'object') return out;
  for (const k of PH_KEYS) if (src[k] !== undefined && src[k] !== null) out[k] = src[k];
  return out;
}

/** Trim, drop blanks, dedupe, cap — mirrors placeholder_config.sanitize_texts
 *  so the panel can never save a list the runtime would silently shorten. */
function sanitizeTexts(list) {
  const out = [];
  const seen = new Set();
  for (const item of (Array.isArray(list) ? list : [])) {
    const text = String(item == null ? '' : item).trim();
    if (!text || seen.has(text)) continue;
    seen.add(text);
    out.push(text);
    if (out.length >= PH_MAX_TEXTS) break;
  }
  return out;
}

function renderStoreOptions() {
  const sel = document.getElementById('storeSel');
  const keep = sel.value;
  sel.innerHTML = '';
  sel.appendChild(el('option', { value: '' }, ['默认（全部店铺） / Account default']));
  Object.entries(stores)
    .sort((a, b) => (b[1]?.last_seen || 0) - (a[1]?.last_seen || 0))
    .forEach(([key, meta]) => {
      sel.appendChild(el('option', { value: key }, [String((meta && meta.label) || key)]));
    });
  if (keep) sel.value = keep;
}

function renderTexts() {
  const root = document.getElementById('phTexts');
  root.innerHTML = '';
  const list = phDraft.placeholder_texts || [];
  list.forEach((text, idx) => {
    const row = el('div', { class: 'kv-row' });
    const inp = el('input', { type: 'text', value: text, placeholder: '人工服务正在回复中...' });
    const del = el('button', { class: 'danger' }, ['×']);
    inp.addEventListener('input', () => { phDraft.placeholder_texts[idx] = inp.value; });
    del.addEventListener('click', () => {
      phDraft.placeholder_texts.splice(idx, 1);
      renderTexts();
    });
    row.appendChild(inp); row.appendChild(del);
    root.appendChild(row);
  });
  document.getElementById('addText').disabled = list.length >= PH_MAX_TEXTS;
}

function renderPh() {
  const key = currentStore();
  const isStore = key !== '';
  const override = isStore ? (storePh[key] || null) : null;
  const inheriting = isStore && !override;

  document.getElementById('inheritRow').hidden = !isStore;
  document.getElementById('inherit').checked = inheriting;
  document.getElementById('phFields').className = inheriting ? 'muted-block' : '';

  const src = inheriting ? accountPh : (override || accountPh);
  // Nothing configured in the GUI yet, but this machine may still be
  // running a phrase from the pre-GUI text file.  Show THAT, so the panel
  // never claims a default the customer is not actually getting; the
  // runtime mirrors it into the store registry because an iframe cannot
  // read the file itself.  Adopting it is an explicit Save, never a
  // silent rewrite of the customer's config.
  let legacy = null;
  if (!src.placeholder_texts) {
    for (const meta of Object.values(stores)) {
      if (meta && Array.isArray(meta.legacy_texts) && meta.legacy_texts.length) {
        legacy = meta.legacy_texts;
        break;
      }
    }
  }
  phDraft = {
    placeholder_enabled: src.placeholder_enabled === true,
    placeholder_timeout_s: Number(src.placeholder_timeout_s ?? 0) || 0,
    placeholder_texts: sanitizeTexts(src.placeholder_texts || legacy || []),
  };
  document.getElementById('phLegacyNote').hidden = !legacy;

  document.getElementById('phEnabled').checked = phDraft.placeholder_enabled;
  document.getElementById('phTimeout').value = phDraft.placeholder_timeout_s || '';
  renderTexts();

  // Env is invisible from here, so the runtime mirrors it into the store
  // registry; showing it stops support wondering why a number "looks off".
  const envNote = document.getElementById('phEnvNote');
  const envVal = isStore ? stores[key]?.env_timeout_s : null;
  if (envVal !== null && envVal !== undefined) {
    envNote.textContent =
      `该机器设置了环境变量 ECAN_FEIGE_PLACEHOLDER_TIMEOUT_S=${envVal}，界面设置会覆盖它。`;
    envNote.hidden = false;
  } else {
    envNote.hidden = true;
  }
}

function readPhForm() {
  const timeoutRaw = parseFloat(document.getElementById('phTimeout').value);
  const enabled = document.getElementById('phEnabled').checked;
  const texts = sanitizeTexts(phDraft.placeholder_texts || []);
  let timeout = Number.isFinite(timeoutRaw) && timeoutRaw >= 0 ? timeoutRaw : null;
  if (timeout === null) timeout = enabled ? PH_DEFAULT_TIMEOUT : 0;
  return {
    placeholder_enabled: enabled,
    placeholder_timeout_s: timeout,
    placeholder_texts: texts,
  };
}

document.getElementById('storeSel').addEventListener('change', renderPh);

document.getElementById('inherit').addEventListener('change', (e) => {
  const key = currentStore();
  if (!key) return;
  if (e.target.checked) {
    delete storePh[key];          // persisted on Save
  } else {
    storePh[key] = JSON.parse(JSON.stringify(accountPh));
  }
  renderPh();
});

document.getElementById('addText').addEventListener('click', () => {
  if (!phDraft.placeholder_texts) phDraft.placeholder_texts = [];
  if (phDraft.placeholder_texts.length >= PH_MAX_TEXTS) return;
  phDraft.placeholder_texts.push('');
  renderTexts();
});

document.getElementById('phSave').addEventListener('click', async () => {
  const status = document.getElementById('phStatus');
  const key = currentStore();
  const inheriting = key !== '' && document.getElementById('inherit').checked;
  try {
    if (key === '') {
      const patch = readPhForm();
      await ecan.plugin.config.set(patch);
      accountPh = patch;
    } else if (inheriting) {
      await ecan.plugin.storage.del(PH_STORE_PREFIX + key);
      delete storePh[key];
    } else {
      const patch = readPhForm();
      await ecan.plugin.storage.set(PH_STORE_PREFIX + key, patch);
      storePh[key] = patch;
    }
    renderPh();
    status.textContent = '已保存，立即生效。 / Saved — live within a second.';
    status.className = 'status ok';
    ecan.plugin.ui.notify('success', '过渡话术已保存');
  } catch (e) {
    status.textContent = e.message || '保存失败 / Save failed';
    status.className = 'status err';
  }
});

async function initPlaceholder(configUser) {
  accountPh = readPh(configUser);
  try {
    const known = await ecan.plugin.storage.get('stores');
    stores = (known && typeof known === 'object') ? known : {};
  } catch (e) {
    stores = {};
  }
  for (const key of Object.keys(stores)) {
    try {
      const blob = await ecan.plugin.storage.get(PH_STORE_PREFIX + key);
      if (blob && typeof blob === 'object') storePh[key] = readPh(blob);
    } catch (e) { /* a missing per-store blob just means "inherits" */ }
  }
  renderStoreOptions();
  renderPh();
}

(async function init() {
  try {
    const ctx = await ecan.plugin.host.context();
    document.documentElement.setAttribute('data-theme', ctx.theme || 'light');
    const r = await ecan.plugin.config.get();
    cfg = JSON.parse(JSON.stringify(r.config_effective || {}));
    applyToForm();
    await initPlaceholder(r.config_user || {});
    // Right-size the host iframe to our content.
    const h = document.body.scrollHeight + 24;
    ecan.plugin.ui.resize(h);
  } catch (e) {
    document.body.innerHTML = '<p class="err">Bridge not available: ' + e.message + '</p>';
  }
})();
