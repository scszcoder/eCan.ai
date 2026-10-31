"""Page-side helpers for a page's own form data, shared by the form browser
actions (form_store_tools) and the recipes built from them (store.recipe_script):
the code that finds, reads and writes a form store, tested once (抖店 2026-10-30)."""

# No "{{" or "}}": skills put these scripts in prompts.
HELPERS = r"""
const fiberOf = el => { const k = Object.keys(el).find(k => k.startsWith('__reactFiber$') || k.startsWith('__reactInternalInstance$')); return k ? el[k] : null };
const namesOf = form => { let v; try { v = form.getFieldsValue(true) } catch (e) { } if (!v || typeof v !== 'object' || !Object.keys(v).length) { try { v = form.getFieldsValue() } catch (e) { } } return v || {} };
const nested = (key, v) => key.split('.').reduceRight((acc, k) => ({ [k]: acc }), v);
const safe = (x, n) => { try { return JSON.stringify(x, (k, v) => (v && typeof v === 'object' && (v instanceof Element || v.$$typeof || k === 'root' || k === 'parent' || k === 'children' || k === 'form')) ? undefined : v).slice(0, n || 6000) } catch (e) { return 'unreadable: ' + e.message } };
const valOf = f => { try { const v = f.value; return (v && typeof v === 'object' && '_value' in v) ? v._value : v } catch (e) { return undefined } };
const stores = start => {
  const seen = new Set(), out = [];
  const els = start ? [start] : [...document.querySelectorAll('input,textarea,select')].slice(0, 300);
  for (const el of els) {
    let f = fiberOf(el);
    for (let i = 0; i < 45 && f; i++) {
      for (const v of Object.values(f.memoizedProps || {})) {
        if (!v || typeof v !== 'object') continue;
        if (v.root && v.root.value !== undefined && !seen.has(v.root)) { seen.add(v.root); out.push({ kind: 'path', root: v.root, depth: i }) }
        if (typeof v.getFieldsValue === 'function' && !seen.has(v)) { seen.add(v); out.push({ kind: 'named', form: v, depth: i }) }
      }
      f = f.return;
    }
    // No early stop: the first input with a store can be a side widget's (a
    // discount box, 抖店 run 61) while the field lives in the main form.
  }
  return out;
};
const fieldOf = (root, key) => {
  const kids = typeof root.getAllChildren === 'function' ? root.getAllChildren() : [];
  return kids.find(c => c && c.address && String(c.address.string || '') === key) || null;
};
const locate = key => {
  for (const s of stores(null)) {
    if (s.kind === 'path') {
      const f = fieldOf(s.root, key);
      if (f) return { get: () => valOf(f), set: v => f.setValue(v) };
    } else {
      // antd 4+ takes a name path (array); antd 3 / rc-form takes a "a.b" string.
      const parts = key.split('/'), name = parts.length === 1 ? parts[0] : parts;
      try { if (s.form.getFieldValue(name) !== undefined) return { get: () => s.form.getFieldValue(name), set: v => s.form.setFieldValue ? s.form.setFieldValue(name, v) : s.form.setFieldsValue(nested(String(name), v)) } } catch (e) { }
    }
  }
  return null;
};
window.__ecanFieldBackup = window.__ecanFieldBackup || {};
// Equal only when both serialise and match: an unreadable value is never "the
// same" (safe(undefined) === safe(undefined) passed a recipe that wrote undefined
// into 抖店's spec data and wiped the form, KEN 2026-10-31).
const sameJSON = (a, b) => { try { const x = JSON.stringify(a), y = JSON.stringify(b); return x !== undefined && x === y } catch (e) { return false } };
const kindOf = v => v === null ? 'null' : Array.isArray(v) ? 'array' : typeof v;
const copyOf = v => { try { return JSON.parse(JSON.stringify(v)) } catch (e) { return v } };
// One write, guarded: refuse a value of the wrong kind, skip one already in place,
// read back, and put the old value back when it did not take.
const guardedWrite = async (key, loc, want) => {
  const old = copyOf(loc.get());
  if (want === undefined || want === null) return { key, same_as_written: false, refused: 'the new value is ' + want };
  if (old !== undefined && old !== null && kindOf(old) !== kindOf(want))
    return { key, same_as_written: false, refused: 'the field holds ' + kindOf(old) + ', the new value is ' + kindOf(want) };
  if (sameJSON(old, want)) return { key, same_as_written: true, skipped: 'already this value' };
  try { await loc.set(want) } catch (e) { return { key, same_as_written: false, error: 'set failed: ' + e.message } }
  await new Promise(r => setTimeout(r, 600));
  const again = locate(key);
  if (!again) return { key, same_as_written: false, error: 'the field is gone after the write (the page reset?)' };
  const got = again.get();
  if (sameJSON(got, want)) return { key, same_as_written: true };
  try { await again.set(old) } catch (e) { }
  return { key, same_as_written: false, restored: true, now: got };
};
"""

