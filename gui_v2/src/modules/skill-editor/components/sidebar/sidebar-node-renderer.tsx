/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import React, { useMemo } from 'react';
import { useNodeRender, FlowNodeEntity } from '@flowgram.ai/free-layout-editor';

import { NodeRenderContext } from '../../context';
import { useNodeStateSchema } from '../../../../stores/nodeStateSchemaStore';
import NodeStatePanel from '../node-state/NodeStatePanel';
import MappingEditor, { type MappingConfig } from '../mapping/MappingEditor';
import SkillLevelMappingEditor, { type SkillLevelMappingConfig } from '../mapping/SkillLevelMappingEditor';
import { IPCAPI } from '../../../../services/ipc/api';
import { useSkillInfoStore } from '../../stores/skill-info-store';
import { useRuntimeStateStore } from '../../stores/runtime-state-store';
import { WorkflowNodeType } from '../../nodes/constants';

export function SidebarNodeRenderer(props: { node: FlowNodeEntity }) {
  const { node } = props;
  const nodeRender = useNodeRender(node);
  const { schema, loading } = useNodeStateSchema();
  const { skillInfo, setSkillInfo } = useSkillInfoStore();
  const setHasUnsavedChanges = useSkillInfoStore((s) => s.setHasUnsavedChanges);
  
  // Detect if this is the START node (skill-level mapping editor)
  const isStartNode = useMemo(() => {
    const nodeType = node.type;
    const nodeId = node.id;
    // START node can be: type='start', type='event', or id='start'
    return nodeType === 'start' || nodeType === 'event' || nodeId === 'start';
  }, [node]);
  
  // Check if node state should be hidden (for Loop, BlockStart, BlockEnd)
  const shouldShowNodeState = useMemo(() => {
    // Get the actual node type from the JSON data
    // Extract type from node ID (e.g., "loop_xxx" -> "loop", "block_start_xxx" -> "block-start")
    const extractTypeFromId = (id: string) => {
      if (id.startsWith('block_start_')) return 'block-start';
      if (id.startsWith('block_end_')) return 'block-end';
      return id.split('_')[0];
    };
    const nodeType = (node as any).json?.type || extractTypeFromId(node.id);
    
    const shouldHide = 
      nodeType === WorkflowNodeType.Loop || 
      nodeType === 'block-start' || 
      nodeType === 'block-end';
    
    return !shouldHide;
  }, [node]);
  
  // live runtime state for this node (from backend updates)
  const runtimeEntry = useRuntimeStateStore((s) => s.byNodeId[node.id]);
  // dev: log when runtime entry changes for this node
  try {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    React.useEffect(() => {
      try { console.info('[NodeRuntime] sidebar', { nodeId: node.id, runtimeEntry }); } catch {}
    }, [node.id, runtimeEntry]);
  } catch {}

  // Bind 'state' field helpers
  const form = nodeRender.form as any;
  const getStateValue = () => {
    try {
      if (form?.getFieldValue) return form.getFieldValue('state');
      if (form?.state?.values) return (form.state.values as any).state;
    } catch {}
    return undefined;
  };
  const setStateValue = (val: any) => {
    try {
      if (form?.setFieldValue) return form.setFieldValue('state', val);
    } catch {}
  };

  // Node-to-Node Mapping Rules bindings (persist to node.data.mapping_rules)
  const getMappingRules = (): MappingConfig | null => {
    try {
      const dataAny = (node as any).data as any;
      const cfg = dataAny?.mapping_rules;
      if (cfg && typeof cfg === 'object') return cfg as MappingConfig;
    } catch {}
    return null;
  };
  const setMappingRules = (cfg: MappingConfig) => {
    try {
      // Mark unsaved changes in skill store so Save prompts/flags work
      try { setHasUnsavedChanges(true); } catch {}
      // Best-effort setters depending on editor runtime
      const current = (node as any).data || {};
      const next = { ...current, mapping_rules: cfg };
      if (typeof (node as any).setData === 'function') {
        (node as any).setData(next);
        return;
      }
      if (typeof (node as any).updateData === 'function') {
        (node as any).updateData(next);
        return;
      }
      // Fallback: mutate in-place (some editors proxy writes)
      (node as any).data = next;
    } catch (e) {
      console.error('[MappingEditor] persist mapping_rules failed', e);
    }
  };
  
  // Skill-Level Mapping Rules bindings (persist to skillInfo.config.skill_mapping)
  const getSkillLevelMappingRules = (): SkillLevelMappingConfig | null => {
    try {
      const cfg = skillInfo?.config?.skill_mapping;
      if (cfg && typeof cfg === 'object') return cfg as SkillLevelMappingConfig;
    } catch {}
    return null;
  };
  const setSkillLevelMappingRules = (cfg: SkillLevelMappingConfig) => {
    try {
      if (!skillInfo) return;
      setHasUnsavedChanges(true);
      const updated = {
        ...skillInfo,
        config: {
          ...(skillInfo.config || {}),
          skill_mapping: cfg
        }
      };
      setSkillInfo(updated);
    } catch (e) {
      console.error('[SkillLevelMapping] persist failed', e);
    }
  };

  return (
    <NodeRenderContext.Provider value={nodeRender}>
      <div
        style={{
          background: 'rgb(251, 251, 251)',
          height: '100%',
          margin: '8px 0 8px 0',
          width: '100%',
          borderRadius: 8,
          border: '1px solid rgba(82,100,154, 0.13)',
          overflowY: 'auto',
          overflowX: 'hidden'
        }}
      >
        <div style={{ padding: '8px 12px 0 12px' }}>
          {nodeRender.form?.render()}
        </div>
        {shouldShowNodeState && (
          <div style={{ marginTop: 8, borderTop: '1px solid #eee', padding: '8px 12px', background: '#fff' }}>
            <div style={{ fontWeight: 600, marginBottom: 8, color: '#333' }}>Node State</div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
            <button
              type="button"
              style={{ fontSize: 12, padding: '2px 8px', border: '1px solid #d9d9d9', borderRadius: 4, background: '#f5f5f5', color: '#333', cursor: 'pointer' }}
              onClick={async () => {
                try {
                  const api = IPCAPI.getInstance();
                  const last = await api.getLastLoginInfo<any>();
                  const username = (last.success && (last.data as any)?.username) || '';
                  if (!username || !skillInfo) {
                    console.warn('[NodeState] Refresh skipped: missing username or skillInfo');
                    return;
                  }
                  console.debug('[NodeState] requestSkillState', { username, skillId: skillInfo.skillId, nodeId: node.id });
                  await api.requestSkillState(username, { ...skillInfo, nodeId: node.id } as any);
                } catch (e) {
                  console.error('requestSkillState failed', e);
                }
              }}
            >Refresh State</button>
            <button
              type="button"
              style={{ fontSize: 12, padding: '2px 8px', border: '1px solid #d9d9d9', borderRadius: 4, background: '#f5f5f5', color: '#333', cursor: 'pointer' }}
              onClick={async () => {
                try {
                  const api = IPCAPI.getInstance();
                  const last = await api.getLastLoginInfo<any>();
                  const username = (last.success && (last.data as any)?.username) || '';
                  if (!username || !skillInfo) {
                    console.warn('[NodeState] Inject skipped: missing username or skillInfo');
                    return;
                  }
                  const currentState = getStateValue() ?? {};
                  const payload: any = { ...skillInfo, runtimeStatePatch: { nodeId: node.id, state: currentState } };
                  console.debug('[NodeState] injectSkillState', { username, skillId: skillInfo.skillId, nodeId: node.id });
                  await api.injectSkillState(username, payload);
                  // Optional: attempt resume
                  await api.resumeRunSkill(username, skillInfo as any);
                } catch (e) {
                  console.error('injectSkillState/resume failed', e);
                }
              }}
            >Inject & Resume</button>
          </div>
          {loading || !schema ? (
            <div style={{ color: '#999' }}>Loading node state schema...</div>
          ) : (
            <NodeStatePanel schema={schema} value={getStateValue() ?? {}} onChange={setStateValue} />
          )}
          {/* Runtime state (read-only, from backend) */}
          <div style={{ marginTop: 12, borderTop: '1px dashed #eee', paddingTop: 8 }}>
            <div style={{ fontWeight: 600, marginBottom: 6, color: '#222' }}>Runtime State (read-only)</div>
            <div style={{ fontSize: 12, color: '#333', marginBottom: 6 }}>Node ID: <code style={{ color: '#222' }}>{node.id}</code></div>
            {runtimeEntry ? (
              <>
                <div style={{ fontSize: 12, color: '#333', marginBottom: 6 }}>
                  Status: <b>{runtimeEntry.status || 'n/a'}</b>
                  <span style={{ marginLeft: 8, color: '#999' }}>Updated: {new Date(runtimeEntry.updatedAt).toLocaleTimeString()}</span>
                </div>
                <pre style={{ maxHeight: 180, overflow: 'auto', color: '#111', background: '#fff', border: '1px solid #e5e5e5', padding: 8, borderRadius: 4 }}>
                  {JSON.stringify(runtimeEntry.state ?? {}, null, 2)}
                </pre>
                {/* Optional: sync button to copy runtime into editable form 'state' */}
                <div style={{ marginTop: 8 }}>
                  <button
                    type="button"
                    style={{ fontSize: 12, padding: '2px 8px', border: '1px solid #d9d9d9', borderRadius: 4, background: '#f5f5f5', color: '#333', cursor: 'pointer' }}
                    onClick={() => {
                      try {
                        const incoming = runtimeEntry.state ?? {};
                        setStateValue(incoming);
                        try { setHasUnsavedChanges(true); } catch {}
                      } catch (e) {
                        console.error('[NodeState] Sync to Form failed', e);
                      }
                    }}
                  >Sync to Form</button>
                </div>
              </>
            ) : (
              <div style={{ fontSize: 12, color: '#999' }}>No runtime data for this node yet. Make sure this exact node is being executed.</div>
            )}
          </div>
        </div>
        )}
        {/* Mapping rules editor - different for START node vs other nodes */}
        <div style={{ marginTop: 16, borderTop: '1px solid #eee', paddingTop: 12, padding: '12px' }}>
            {isStartNode ? (
              <>
                <div style={{ fontWeight: 600, marginBottom: 8, color: '#333' }}>Skill-Level Mapping Rules</div>
                <div style={{ fontSize: 12, color: '#666', marginBottom: 8 }}>
                  Configure event-to-state mappings and event routing for the entire skill.
                </div>
                <SkillLevelMappingEditor 
                  value={getSkillLevelMappingRules()} 
                  onChange={setSkillLevelMappingRules} 
                />
              </>
            ) : (
              <>
                <div style={{ fontWeight: 600, marginBottom: 8, color: '#333' }}>Node Transfer Mapping</div>
                <div style={{ fontSize: 12, color: '#666', marginBottom: 8 }}>
                  Maps data from preceding node(s) to this node's input state.
                </div>
                <MappingEditor value={getMappingRules()} onChange={setMappingRules} />
              </>
            )}
          </div>
      </div>
    </NodeRenderContext.Provider>
  );
}
