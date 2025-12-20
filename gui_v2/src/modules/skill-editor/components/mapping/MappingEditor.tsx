import React, { useCallback, useEffect, useMemo, useState } from 'react';

/**
 * Lightweight front-end mapping preview engine aligned with agent/tasks_resume.py DSL
 * 
 * Node-to-Node Transfer Mapping:
 * - "from" paths use "node.*" to reference preceding node's output
 * - "to" paths use "state.*" to write to current node's input state
 * 
 * Example:
 * {
 *   "from": ["node.result.api_response"],
 *   "to": [{"target": "state.tool_input.data"}],
 *   "transform": "parse_json"
 * }
 */

type Json = Record<string, any>;

type MappingTarget = {
  target: string; // e.g. "state.attributes.x" | "state.metadata.y" | "state.tool_input.z" | "resume.foo"
};

type MappingRule = {
  from: string[];
  to: MappingTarget[];
  transform?: string | { name: string; args?: Record<string, any> };
  on_conflict?: 'overwrite' | 'skip' | 'merge_shallow' | 'merge_deep' | 'append';
  when?: string; // not evaluated in preview for simplicity
};

export type MappingConfig = {
  mappings: MappingRule[];
  options?: {
    strict?: boolean;
    default_on_missing?: any;
    apply_order?: 'top_down';
  };
};

function safeGet(obj: any, path: string, def?: any) {
  if (!obj) return def;
  const parts = path.split('.');
  let cur: any = obj;
  for (const p of parts) {
    if (cur && typeof cur === 'object' && p in cur) cur = cur[p];
    else return def;
  }
  return cur;
}

function ensurePath(obj: Json, path: string): [Json, string] {
  const parts = path.split('.');
  for (const p of parts.slice(0, -1)) {
    if (!obj[p] || typeof obj[p] !== 'object') obj[p] = {};
    obj = obj[p];
  }
  return [obj, parts[parts.length - 1]];
}

function deepMerge(a: Json, b: Json): Json {
  const out: Json = { ...a };
  for (const k of Object.keys(b)) {
    const av = out[k];
    const bv = (b as any)[k];
    if (av && typeof av === 'object' && !Array.isArray(av) && bv && typeof bv === 'object' && !Array.isArray(bv)) {
      out[k] = deepMerge(av, bv);
    } else {
      out[k] = bv;
    }
  }
  return out;
}

function write(obj: Json, path: string, value: any, on_conflict: MappingRule['on_conflict'] = 'overwrite') {
  const [parent, leaf] = ensurePath(obj, path);
  if (leaf in parent && parent[leaf] !== undefined && parent[leaf] !== null) {
    if (on_conflict === 'skip') return;
    if ((on_conflict === 'merge_deep' || on_conflict === 'merge_shallow') && typeof parent[leaf] === 'object' && typeof value === 'object') {
      parent[leaf] = on_conflict === 'merge_deep' ? deepMerge(parent[leaf], value) : { ...parent[leaf], ...value };
      return;
    }
    if (on_conflict === 'append' && Array.isArray(parent[leaf]) && Array.isArray(value)) {
      parent[leaf] = [...parent[leaf], ...value];
      return;
    }
  }
  parent[leaf] = value;
}

function toStringV(v: any) {
  if (typeof v === 'string') return v;
  try { return JSON.stringify(v); } catch { return String(v); }
}

function applyTransform(val: any, transform?: MappingRule['transform']) {
  if (!transform) return val;
  let name = typeof transform === 'string' ? transform : transform.name;
  const args = typeof transform === 'object' ? transform.args || {} : {};
  if (name === 'identity') return val;
  if (name === 'to_string') return toStringV(val);
  if (name === 'parse_json') {
    try {
      if (typeof val === 'string') return JSON.parse(val);
      return val;
    } catch { return val; }
  }
  if (name === 'pick') {
    const p = args.path as string | undefined;
    if (!p) return undefined;
    if (val && typeof val === 'object') return safeGet(val, p);
    try { const parsed = typeof val === 'string' ? JSON.parse(val) : {}; return safeGet(parsed, p); } catch { return undefined; }
  }
  if (name === 'coalesce') {
    const paths = (args.paths as string[]) || [];
    if (val && typeof val === 'object') {
      for (const p of paths) { const v = safeGet(val, p); if (v !== undefined && v !== null) return v; }
      return undefined;
    }
    return val ?? undefined;
  }
  return val;
}

function resolveFrom(event: Json, node: Json, state: Json, from: string[], def?: any) {
  for (const f of from) {
    const [root, ...rest] = f.split('.');
    const path = rest.join('.');
    if (root === 'event') {
      const v = safeGet(event, path, undefined); if (v !== undefined && v !== null) return v;
    } else if (root === 'node') {
      const v = safeGet(node, path, undefined); if (v !== undefined && v !== null) return v;
    } else if (root === 'state') {
      const v = safeGet(state, path, undefined); if (v !== undefined && v !== null) return v;
    }
  }
  return def;
}

function runPreview(mapping: MappingConfig, event: Json, state: Json, nodeOutput?: Json) {
  const resume: Json = {};
  const statePatch: Json = {};
  const rules = mapping?.mappings || [];
  const defMissing = mapping?.options?.default_on_missing;
  for (const rule of rules) {
    const v0 = resolveFrom(event, nodeOutput || {}, state || {}, rule.from || [], defMissing);
    if (v0 === undefined || v0 === null) continue;
    const v = applyTransform(v0, rule.transform);
    for (const tgt of rule.to || []) {
      const [root, ...rest] = (tgt.target || '').split('.');
      const path = rest.join('.');
      if (root === 'resume') write(resume, path, v, rule.on_conflict);
      else if (root === 'state') write(statePatch, path, v, rule.on_conflict);
    }
  }
  return { resume, statePatch };
}

export function MappingEditor(props: {
  value?: MappingConfig | null;
  onChange?: (cfg: MappingConfig) => void;
}) {
  const [config, setConfig] = useState<MappingConfig>(() => props.value || { mappings: [], options: { strict: false, apply_order: 'top_down' } });
  const [sampleEvent, setSampleEvent] = useState<string>(JSON.stringify({ type: 'human_chat', data: { human_text: 'hi' } }, null, 2));
  const [sampleState, setSampleState] = useState<string>(JSON.stringify({ attributes: {}, metadata: {}, tool_input: {} }, null, 2));
  const [sampleNode, setSampleNode] = useState<string>(JSON.stringify({ output: {} }, null, 2));
  const [preview, setPreview] = useState<{ resume: Json; statePatch: Json } | null>(null);

  useEffect(() => { if (props.value) setConfig(props.value); }, [props.value]);

  const update = useCallback((next: MappingConfig) => {
    setConfig(next);
    props.onChange?.(next);
  }, [props.onChange]);

  const addRule = useCallback(() => {
    const next: MappingConfig = {
      ...config,
      mappings: [
        ...config.mappings,
        { from: ['event.data.human_text'], to: [{ target: 'resume.human_text' }], on_conflict: 'overwrite' },
      ],
    };
    update(next);
  }, [config, update]);

  const removeRule = useCallback((idx: number) => {
    const next = { ...config, mappings: config.mappings.filter((_, i) => i !== idx) };
    update(next);
  }, [config, update]);

  const setRuleField = useCallback((idx: number, field: keyof MappingRule, value: any) => {
    const rules = config.mappings.slice();
    const r = { ...rules[idx], [field]: value } as MappingRule;
    rules[idx] = r;
    update({ ...config, mappings: rules });
  }, [config, update]);

  const setTargets = useCallback((idx: number, targets: MappingTarget[]) => {
    const rules = config.mappings.slice();
    const r = { ...rules[idx], to: targets } as MappingRule;
    rules[idx] = r;
    update({ ...config, mappings: rules });
  }, [config, update]);

  const doPreview = useCallback(() => {
    try {
      const ev = JSON.parse(sampleEvent || '{}');
      const st = JSON.parse(sampleState || '{}');
      const nd = JSON.parse(sampleNode || '{}');
      const out = runPreview(config, ev, st, nd);
      setPreview(out);
    } catch (e) {
      setPreview({ resume: { error: String(e) }, statePatch: {} });
    }
  }, [config, sampleEvent, sampleState, sampleNode]);

  return (
    <div style={{ border: '1px solid #eee', borderRadius: 6, padding: 8, background: '#ffffff', marginTop: 8, color: '#222' }}>
      <div style={{ fontWeight: 600, marginBottom: 8, color: '#333' }}>Mapping Rules</div>

      {/* Rules editor */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {config.mappings.map((rule, idx) => (
          <div key={idx} style={{ border: '1px solid #e6e6e6', borderRadius: 6, padding: 8 }}>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <div style={{ flex: '1 1 240px' }}>
                <div style={{ fontSize: 12, color: '#555' }}>From (comma-separated paths)</div>
                <input
                  style={{ width: '100%', color: '#222', background: '#fff', border: '1px solid #d9d9d9', borderRadius: 4, padding: '4px 6px' }}
                  value={(rule.from || []).join(', ')}
                  onChange={(e) => setRuleField(idx, 'from', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                  placeholder="event.data.qa_form_to_agent, event.data.qa_form"
                />
              </div>
              <div style={{ flex: '1 1 220px' }}>
                <div style={{ fontSize: 12, color: '#555' }}>Transform</div>
                <select
                  value={typeof rule.transform === 'string' ? rule.transform : (rule.transform?.name || '')}
                  onChange={(e) => setRuleField(idx, 'transform', e.target.value || undefined)}
                  style={{ width: '100%', color: '#222', background: '#fff', border: '1px solid #d9d9d9', borderRadius: 4, padding: '4px 6px' }}
                >
                  <option value="">(none)</option>
                  <option value="identity">identity</option>
                  <option value="to_string">to_string</option>
                  <option value="parse_json">parse_json</option>
                  <option value="pick">pick (requires args.path)</option>
                  <option value="coalesce">coalesce (requires args.paths)</option>
                </select>
                {/* Simple args UI */}
                {(() => {
                  const name = typeof rule.transform === 'string' ? rule.transform : rule.transform?.name;
                  if (name === 'pick') {
                    const cur = typeof rule.transform === 'object' ? rule.transform : { name: 'pick', args: { path: '' } };
                    const path = cur.args?.path || '';
                    return (
                      <input
                        style={{ width: '100%', marginTop: 4, color: '#222', background: '#fff', border: '1px solid #d9d9d9', borderRadius: 4, padding: '4px 6px' }}
                        placeholder="args.path"
                        value={path}
                        onChange={(e) => setRuleField(idx, 'transform', { name: 'pick', args: { path: e.target.value } })}
                      />
                    );
                  }
                  if (name === 'coalesce') {
                    const cur = typeof rule.transform === 'object' ? rule.transform : { name: 'coalesce', args: { paths: [] } };
                    const paths = (cur.args?.paths || []) as string[];
                    return (
                      <input
                        style={{ width: '100%', marginTop: 4, color: '#222', background: '#fff', border: '1px solid #d9d9d9', borderRadius: 4, padding: '4px 6px' }}
                        placeholder="args.paths (comma-separated)"
                        value={paths.join(', ')}
                        onChange={(e) => setRuleField(idx, 'transform', { name: 'coalesce', args: { paths: e.target.value.split(',').map(s => s.trim()).filter(Boolean) } })}
                      />
                    );
                  }
                  return null;
                })()}
              </div>
              <div style={{ flex: '0 0 160px' }}>
                <div style={{ fontSize: 12, color: '#555' }}>Conflict</div>
                <select
                  value={rule.on_conflict || 'overwrite'}
                  onChange={(e) => setRuleField(idx, 'on_conflict', e.target.value as any)}
                  style={{ width: '100%', color: '#222', background: '#fff', border: '1px solid #d9d9d9', borderRadius: 4, padding: '4px 6px' }}
                >
                  <option value="overwrite">overwrite</option>
                  <option value="skip">skip</option>
                  <option value="merge_shallow">merge_shallow</option>
                  <option value="merge_deep">merge_deep</option>
                  <option value="append">append</option>
                </select>
              </div>
              <div style={{ flex: '1 1 320px' }}>
                <div style={{ fontSize: 12, color: '#555' }}>Targets</div>
                <TargetsEditor
                  value={rule.to || []}
                  onChange={(targets) => setTargets(idx, targets)}
                />
              </div>
            </div>
            <div style={{ marginTop: 6, display: 'flex', justifyContent: 'space-between' }}>
              <button type="button" style={btn()} onClick={() => removeRule(idx)}>Remove Rule</button>
            </div>
          </div>
        ))}
        <div>
          <button type="button" style={btn()} onClick={addRule}>Add Rule</button>
        </div>
      </div>

      {/* Raw JSON view */}
      <div style={{ marginTop: 12 }}>
        <div style={{ fontSize: 12, color: '#555', marginBottom: 4 }}>Raw Mapping JSON</div>
        <textarea
          style={{ width: '100%', minHeight: 120, fontFamily: 'monospace', fontSize: 12, color: '#222', background: '#fff', border: '1px solid #d9d9d9', borderRadius: 4, padding: 8 }}
          value={JSON.stringify(config, null, 2)}
          onChange={(e) => {
            try { const js = JSON.parse(e.target.value); update(js); } catch { /* ignore */ }
          }}
        />
      </div>

      {/* Preview */}
      <div style={{ marginTop: 12, display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
        <div>
          <div style={{ fontSize: 12, color: '#555', marginBottom: 4 }}>Sample Event</div>
          <textarea style={{ width: '100%', minHeight: 120, fontFamily: 'monospace', fontSize: 12, color: '#222', background: '#fff', border: '1px solid #d9d9d9', borderRadius: 4, padding: 8 }} value={sampleEvent} onChange={(e) => setSampleEvent(e.target.value)} />
        </div>
        <div>
          <div style={{ fontSize: 12, color: '#555', marginBottom: 4 }}>Sample State</div>
          <textarea style={{ width: '100%', minHeight: 120, fontFamily: 'monospace', fontSize: 12, color: '#222', background: '#fff', border: '1px solid #d9d9d9', borderRadius: 4, padding: 8 }} value={sampleState} onChange={(e) => setSampleState(e.target.value)} />
        </div>
        <div>
          <div style={{ fontSize: 12, color: '#555', marginBottom: 4 }}>Sample Node Output</div>
          <textarea style={{ width: '100%', minHeight: 120, fontFamily: 'monospace', fontSize: 12, color: '#222', background: '#fff', border: '1px solid #d9d9d9', borderRadius: 4, padding: 8 }} value={sampleNode} onChange={(e) => setSampleNode(e.target.value)} />
        </div>
      </div>
      <div style={{ marginTop: 8 }}>
        <button type="button" style={btn()} onClick={doPreview}>Preview</button>
      </div>
      {preview && (
        <div style={{ marginTop: 8, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          <div>
            <div style={{ fontSize: 12, color: '#555' }}>Preview Resume</div>
            <pre style={pre()}>{JSON.stringify(preview.resume, null, 2)}</pre>
          </div>
          <div>
            <div style={{ fontSize: 12, color: '#555' }}>Preview State Patch</div>
            <pre style={pre()}>{JSON.stringify(preview.statePatch, null, 2)}</pre>
          </div>
        </div>
      )}
    </div>
  );
}

function TargetsEditor(props: { value: MappingTarget[]; onChange: (v: MappingTarget[]) => void }) {
  const addTarget = () => props.onChange([...(props.value || []), { target: 'resume.human_text' }]);
  const setTarget = (i: number, t: string) => {
    const arr = (props.value || []).slice();
    arr[i] = { target: t };
    props.onChange(arr);
  };
  const remove = (i: number) => props.onChange((props.value || []).filter((_, idx) => idx !== i));

  return (
    <div>
      {(props.value || []).map((t, i) => (
        <div key={i} style={{ display: 'flex', gap: 6, marginBottom: 4 }}>
          <select
            value={(t.target || 'resume.human_text').split('.')[0] + ''}
            onChange={(e) => {
              const root = e.target.value;
              const rest = (t.target || '').split('.').slice(1).join('.') || (root === 'resume' ? 'human_text' : 'attributes.x');
              setTarget(i, `${root}.${rest}`);
            }}
            style={{ color: '#222', background: '#fff', border: '1px solid #d9d9d9', borderRadius: 4, padding: '4px 6px' }}
          >
            <option value="resume">resume</option>
            <option value="state">state</option>
          </select>
          <input
            style={{ flex: 1, color: '#222', background: '#fff', border: '1px solid #d9d9d9', borderRadius: 4, padding: '4px 6px' }}
            placeholder={"path e.g. " + ((t.target || '').startsWith('resume') ? 'human_text' : 'attributes.x')}
            value={(t.target || '').split('.').slice(1).join('.')}
            onChange={(e) => {
              const root = (t.target || 'resume.human_text').split('.')[0];
              setTarget(i, `${root}.${e.target.value}`);
            }}
          />
          <button type="button" style={btn()} onClick={() => remove(i)}>Remove</button>
        </div>
      ))}
      <button type="button" style={btn()} onClick={addTarget}>Add Target</button>
    </div>
  );
}

function btn() {
  return { fontSize: 12, padding: '2px 8px', border: '1px solid #d9d9d9', borderRadius: 4, background: '#f5f5f5', color: '#333', cursor: 'pointer' } as React.CSSProperties;
}
function pre() {
  return { whiteSpace: 'pre-wrap', background: '#fafafa', color: '#222', padding: 8, border: '1px solid #eee', borderRadius: 6, fontSize: 12 } as React.CSSProperties;
}

export default MappingEditor;
