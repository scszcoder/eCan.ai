import React, { useMemo, useState } from 'react';
import { JSONSchema } from '../../../../stores/nodeStateSchemaStore';

export interface NodeStatePanelProps {
  schema: JSONSchema;
  value: any;
  onChange: (next: any) => void;
  title?: string;
}

function isObject(val: any) {
  return val && typeof val === 'object' && !Array.isArray(val);
}

function pathJoin(base: string, key: string | number) {
  return base ? `${base}.${String(key)}` : String(key);
}

export const NodeStatePanel: React.FC<NodeStatePanelProps> = ({ schema, value, onChange, title = 'Node State' }) => {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({ root: true });
  const [panelCollapsed, setPanelCollapsed] = useState<boolean>(true);
  const [pendingAdd, setPendingAdd] = useState<Record<string, { key: string; type: 'int' | 'float' | 'boolean' | 'string' | 'list' | 'dict'; tempValue?: any; error?: string } | undefined>>({});
  const [pendingArrayType, setPendingArrayType] = useState<Record<string, 'int' | 'float' | 'boolean' | 'string' | 'list' | 'dict'>>({});
  const textColor = '#333';
  const mutedText = '#666';
  const inputStyle: React.CSSProperties = {
    color: '#333',
    background: '#fff',
    border: '1px solid #d9d9d9',
    borderRadius: 4,
    padding: '4px 8px',
    width: '100%',
    boxSizing: 'border-box'
  };

  const selectStyle: React.CSSProperties = {
    ...inputStyle,
    width: 'auto'
  };

  const defaultValueForType = (t: 'int' | 'float' | 'boolean' | 'string' | 'list' | 'dict') => {
    switch (t) {
      case 'int':
        return 0;
      case 'float':
        return 0.0;
      case 'boolean':
        return false;
      case 'string':
        return '';
      case 'list':
        return [] as any[];
      case 'dict':
        return {} as Record<string, any>;
      default:
        return '';
    }
  };

  const toggle = (p: string) => setExpanded((s) => ({ ...s, [p]: !s[p] }));

  const renderLeafEditor = (v: any, onEdit: (nv: any) => void, type?: string) => {
    switch (type) {
      case 'integer':
      case 'number':
        return (
          <input
            type="number"
            className="ns-input"
            style={inputStyle}
            value={v ?? ''}
            onChange={(e) => onEdit(e.target.value === '' ? null : Number(e.target.value))}
          />
        );
      case 'boolean':
        return (
          <input
            type="checkbox"
            checked={!!v}
            onChange={(e) => onEdit(e.target.checked)}
          />
        );
      default:
        return (
          <input
            type="text"
            className="ns-input"
            style={inputStyle}
            value={v ?? ''}
            onChange={(e) => onEdit(e.target.value)}
          />
        );
    }
  };

  const renderNode = (
    nodeSchema: JSONSchema,
    nodeVal: any,
    p: string,
    onEdit: (nv: any) => void,
    keyLabel?: string,
    inAttrsMetaSubtree: boolean = false,
    depth: number = 0
  ) => {
    const type = nodeSchema?.type as string | string[] | undefined;
    const schemaProps: Record<string, JSONSchema> = (nodeSchema?.properties || {}) as Record<string, JSONSchema>;
    const hasSchemaProps = !!schemaProps && Object.keys(schemaProps).length > 0;
    const isArray = type === 'array' || Array.isArray(nodeVal);
    // Treat as dict if schema says object OR we have schema properties OR the value is an object
    const isDict = type === 'object' || hasSchemaProps || isObject(nodeVal);

    // Container header with expand/collapse
    if (isArray || isDict) {
      const open = expanded[p] ?? false;
      // Allow add/remove at any depth once inside attributes/metadata subtree
      const atAttrsMetaRoot = keyLabel === 'attributes' || keyLabel === 'metadata';
      const canAddRemove = (inAttrsMetaSubtree || atAttrsMetaRoot) && depth < 3; // enforce max 3 levels for adds

      return (
        <div className="ns-node" key={p} style={{ paddingLeft: depth * 12 }}>
          <div className="ns-node-header" style={{ color: textColor }}>
            <button className="ns-toggle" onClick={() => toggle(p)}>{open ? '▾' : '▸'}</button>
            <span className="ns-key">{keyLabel || nodeSchema?.title || p || 'root'}</span>
            {canAddRemove && (
              <button
                className="ns-add"
                style={{ marginLeft: 8 }}
                onClick={() => {
                  setPendingAdd((s) => ({ ...s, [p]: { key: '', type: 'string', tempValue: '' } }));
                  setExpanded((s) => ({ ...s, [p]: true }));
                }}
              >+ Add</button>
            )}
          </div>
          {open && (
            <div className="ns-children">
              {canAddRemove && pendingAdd[p] && !isArray && (
                <div className="ns-add-row" style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '4px 0' }}>
                  <span style={{ color: mutedText }}>New</span>
                  <input
                    type="text"
                    placeholder="key"
                    style={{ ...inputStyle, width: 160 }}
                    value={pendingAdd[p]?.key || ''}
                    onChange={(e) => setPendingAdd((s) => ({ ...s, [p]: { ...(s[p] as any), key: e.target.value, error: undefined } }))}
                  />
                  <select
                    style={selectStyle}
                    value={pendingAdd[p]?.type || 'string'}
                    onChange={(e) => {
                      const newType = e.target.value as any;
                      setPendingAdd((s) => ({
                        ...s,
                        [p]: {
                          ...(s[p] as any),
                          type: newType,
                          tempValue: newType === 'boolean' ? false : (newType === 'int' || newType === 'float') ? 0 : newType === 'string' ? '' : undefined
                        }
                      }));
                    }}
                  >
                    <option value="int">int</option>
                    <option value="float">float</option>
                    <option value="boolean">boolean</option>
                    <option value="string">string</option>
                    <option value="list">list</option>
                    <option value="dict">dict</option>
                  </select>
                  {/* Primitive initial value editor */}
                  {(['int','float','boolean','string'] as const).includes((pendingAdd[p]?.type as any)) && (
                    pendingAdd[p]?.type === 'boolean' ? (
                      <label style={{ display: 'flex', alignItems: 'center', gap: 6, color: mutedText }}>
                        <span>value</span>
                        <input
                          type="checkbox"
                          checked={!!pendingAdd[p]?.tempValue}
                          onChange={(e) => setPendingAdd((s) => ({ ...s, [p]: { ...(s[p] as any), tempValue: e.target.checked } }))}
                        />
                      </label>
                    ) : (
                      <input
                        type={pendingAdd[p]?.type === 'string' ? 'text' : 'number'}
                        placeholder="value"
                        style={{ ...inputStyle, width: 160 }}
                        value={pendingAdd[p]?.tempValue ?? ''}
                        onChange={(e) => setPendingAdd((s) => ({
                          ...s,
                          [p]: { ...(s[p] as any), tempValue: (s[p]?.type === 'string' ? e.target.value : (e.target.value === '' ? '' : Number(e.target.value))) }
                        }))}
                      />
                    )
                  )}
                  <button
                    className="ns-action-button"
                    onClick={() => {
                      const pad = pendingAdd[p]!;
                      const valueObj = isObject(nodeVal) ? (nodeVal as Record<string, any>) : {};
                      if (!pad.key) {
                        setPendingAdd((s) => ({ ...s, [p]: { ...(s[p] as any), error: 'Key is required' } }));
                        return;
                      }
                      if (valueObj[pad.key] !== undefined) {
                        setPendingAdd((s) => ({ ...s, [p]: { ...(s[p] as any), error: 'Duplicate key' } }));
                        return;
                      }
                      const base = { ...valueObj } as Record<string, any>;
                      if (base[pad.key] === undefined) {
                        if (pad.type === 'int') {
                          base[pad.key] = typeof pad.tempValue === 'number' ? Math.trunc(pad.tempValue) : 0;
                        } else if (pad.type === 'float') {
                          base[pad.key] = typeof pad.tempValue === 'number' ? pad.tempValue : 0.0;
                        } else if (pad.type === 'boolean') {
                          base[pad.key] = !!pad.tempValue;
                        } else if (pad.type === 'string') {
                          base[pad.key] = (pad.tempValue ?? '').toString();
                        } else if (pad.type === 'list' || pad.type === 'dict') {
                          base[pad.key] = defaultValueForType(pad.type);
                        } else {
                          base[pad.key] = defaultValueForType(pad.type);
                        }
                        onEdit(base);
                        // auto expand the newly created container
                        if (pad.type === 'list' || pad.type === 'dict') {
                          setExpanded((s) => ({ ...s, [p]: true, [pathJoin(p, pad.key)]: true }));
                        }
                        try { console.debug('[NodeStatePanel] added key', pad.key, 'at', p, 'type', pad.type); } catch (_) {}
                      }
                      setPendingAdd((s) => ({ ...s, [p]: undefined }));
                    }}
                  >Add</button>
                  <button
                    className="ns-action-button"
                    onClick={() => setPendingAdd((s) => ({ ...s, [p]: undefined }))}
                  >Cancel</button>
                  {pendingAdd[p]?.error && (
                    <span style={{ color: '#d46b08', marginLeft: 8 }}>{pendingAdd[p]?.error}</span>
                  )}
                </div>
              )}
              {isArray && canAddRemove && (
                <div className="ns-add-array" style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '4px 0' }}>
                  <span style={{ color: mutedText }}>New item</span>
                  <select
                    style={selectStyle}
                    value={pendingArrayType[p] || 'string'}
                    onChange={(e) => setPendingArrayType((s) => ({ ...s, [p]: e.target.value as any }))}
                  >
                    <option value="int">int</option>
                    <option value="float">float</option>
                    <option value="boolean">boolean</option>
                    <option value="string">string</option>
                    <option value="list">list</option>
                    <option value="dict">dict</option>
                  </select>
                  <button
                    className="ns-action-button"
                    onClick={() => {
                      const t = pendingArrayType[p] || 'string';
                      const next = Array.isArray(nodeVal) ? [...nodeVal] : [] as any[];
                      next.push(defaultValueForType(t));
                      onEdit(next);
                      setExpanded((s)=>({ ...s, [p]: true }));
                      try { console.debug('[NodeStatePanel] added array item at', p, 'type', t); } catch (_) {}
                    }}
                  >Add</button>
                </div>
              )}
              {isArray && Array.isArray(nodeVal) && nodeVal.map((item, idx) => (
                <div className="ns-item" key={pathJoin(p, idx)}>
                  <div className="ns-array-item" style={{ color: mutedText }}>
                    <span className="ns-index">[{idx}]</span>
                    <button
                      className="ns-remove"
                      style={{ marginLeft: 8 }}
                      onClick={() => {
                        const next = [...nodeVal];
                        next.splice(idx, 1);
                        onEdit(next);
                      }}
                    >Remove</button>
                  </div>
                  {renderNode(nodeSchema?.items ?? {}, item, pathJoin(p, idx), (nv) => {
                    const next = [...nodeVal];
                    next[idx] = nv;
                    onEdit(next);
                  }, keyLabel, canAddRemove, depth + 1)}
                </div>
              ))}
              {isDict && (
                (() => {
                  const valueObj = isObject(nodeVal) ? nodeVal as Record<string, any> : {};
                  const keys = Array.from(new Set([
                    ...Object.keys(schemaProps || {}),
                    ...Object.keys(valueObj)
                  ]));
                  if (keys.length === 0) {
                    return (
                      <div className="ns-empty" style={{ color: '#999', fontStyle: 'italic', padding: '4px 8px' }}>
                        (empty)
                      </div>
                    );
                  }
                  return keys.map((k) => (
                    <div className="ns-item" key={pathJoin(p, k)}>
                      <div className="ns-dict-item" style={{ color: mutedText }}>
                        <span className="ns-key" style={{ color: textColor, marginRight: 6 }}>{k}</span>
                        {canAddRemove && (
                          <button
                            className="ns-action-button"
                            style={{ marginRight: 6 }}
                            onClick={() => {
                              const newLabel = prompt('Rename key', k);
                              if (!newLabel || newLabel === k) return;
                              const next = { ...valueObj } as Record<string, any>;
                              if (next[newLabel] === undefined) {
                                next[newLabel] = next[k];
                                delete next[k];
                                onEdit(next);
                              }
                            }}
                          >Rename</button>
                        )}
                        {canAddRemove && (
                          <button
                            className="ns-remove"
                            style={{ marginLeft: 8 }}
                            onClick={() => {
                              const next = { ...valueObj } as Record<string, any>;
                              delete next[k];
                              onEdit(next);
                            }}
                          >Remove</button>
                        )}
                      </div>
                      {renderNode((schemaProps || {})[k] ?? {}, valueObj[k], pathJoin(p, k), (nv) => {
                        const next = { ...valueObj, [k]: nv } as Record<string, any>;
                        onEdit(next);
                      }, k, canAddRemove, depth + 1)}
                    </div>
                  ));
                })()
              )}
            </div>
          )}
        </div>
      );
    }

    // Leaf editor
    return (
      <div className="ns-leaf" key={p} style={{ paddingLeft: depth * 12 }}>
        {renderLeafEditor(nodeVal, onEdit, typeof nodeVal === 'number' ? 'number' : (typeof nodeVal === 'boolean' ? 'boolean' : 'string'))}
      </div>
    );
  };

  const topSchema = useMemo(() => schema || { type: 'object', properties: {} }, [schema]);
  const topValue = value ?? {};

  // Debug: log root-level schema and value once per render to verify what we received
  // try {
  //   const rootKeys = Object.keys((topSchema as any)?.properties || {});
  //   // Only log a concise snapshot to avoid noisy logs
  //   // eslint-disable-next-line no-console
  //   console.debug('[NodeStatePanel] root schema keys:', rootKeys, 'value keys:', Object.keys(isObject(topValue) ? topValue : {}));
  // } catch (_) {
  //   // ignore
  // }

  return (
    <div className="node-state-panel" style={{ borderTop: '1px solid #eee', paddingTop: 8 }}>
      <div className="ns-title" style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, marginBottom: panelCollapsed ? 0 : 8, color: '#333' }}>
        <button
          type="button"
          className="ns-toggle-panel"
          onClick={() => setPanelCollapsed((c) => !c)}
        >{panelCollapsed ? '▸' : '▾'}</button>
        <span>{title}</span>
      </div>
      {!panelCollapsed && (
        <div style={{ maxHeight: 260, overflowY: 'auto', marginTop: 8 }}>
          {renderNode(topSchema, topValue, 'root', onChange)}
        </div>
      )}
    </div>
  );
};

export default NodeStatePanel;
