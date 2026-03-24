/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import React, { useMemo, useState, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useNodeRender, FlowNodeEntity } from '@flowgram.ai/free-layout-editor';

import { NodeRenderContext } from '../../context';
import { useNodeStateSchema } from '../../../../stores/nodeStateSchemaStore';
import NodeStatePanel from '../node-state/NodeStatePanel';
import MappingEditor, { type MappingConfig } from '../mapping/MappingEditor';
import SkillLevelMappingEditor, { type SkillLevelMappingConfig } from '../mapping/SkillLevelMappingEditor';
import { IPCAPI } from '../../../../services/ipc/api';
import { useSkillInfoStore } from '../../stores/skill-info-store';
import { useRuntimeStateStore } from '../../stores/runtime-state-store';
import { useNodeNoteStore } from '../../stores/node-note-store';
import { WorkflowNodeType } from '../../nodes/constants';

export function SidebarNodeRenderer(props: { node: FlowNodeEntity }) {
  const { t } = useTranslation('skillEditor');
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
    // Get the actual node type - prefer flowNodeType (set by the editor's node registry)
    const extractTypeFromId = (id: string) => {
      if (id.startsWith('block_start_')) return 'block-start';
      if (id.startsWith('block_end_')) return 'block-end';
      if (id.startsWith('browser_automation_')) return 'browser-automation';
      if (id.startsWith('pend_event_')) return 'pend_event_node';
      if (id.startsWith('pend_input_')) return 'pend_input_node';
      if (id.startsWith('mcp_tool_')) return 'mcp';
      if (id.startsWith('chat_node_')) return 'chat_node';
      return id.split('_')[0];
    };
    const nodeType = node.flowNodeType || (node as any).json?.type || extractTypeFromId(node.id);
    
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

  // --- Node Note state (backed by useNodeNoteStore) ---
  // The flowgram form model does not expose setFieldValue, so we use an
  // external zustand store. prepareDiagramForSave injects notes from this
  // store into the serialised diagram before writing.
  const noteFromStore = useNodeNoteStore((s) => s.getNote(node.id));
  const setNoteInStore = useNodeNoteStore((s) => s.setNote);

  const [noteText, setNoteText] = useState(() => noteFromStore);
  const [noteExpanded, setNoteExpanded] = useState(false);

  // Sync note text when node / store value changes
  useEffect(() => {
    setNoteText(noteFromStore);
  }, [noteFromStore]);

  const saveNote = useCallback((val: string) => {
    try {
      setHasUnsavedChanges(true);
      setNoteInStore(node.id, val);
    } catch (e) {
      console.error('[NoteSection] persist agentNote failed', e);
    }
  }, [node.id, setHasUnsavedChanges, setNoteInStore]);

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
        {/* --- Note Section --- */}
        <div style={{ marginTop: 8, borderTop: '1px solid #eee', padding: '8px 12px', background: '#fff' }}>
          <div
            style={{ fontWeight: 600, marginBottom: 6, color: '#333', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
            onClick={() => setNoteExpanded(prev => !prev)}
          >
            <span>Note</span>
            <span style={{ fontSize: 12, color: '#999' }}>{noteExpanded ? '▾' : '▸'}</span>
          </div>
          {noteExpanded && (
            <textarea
              value={noteText}
              onChange={(e) => {
                setNoteText(e.target.value);
                saveNote(e.target.value);
              }}
              placeholder="Add a note about this node's purpose…"
              style={{
                width: '100%',
                minHeight: 60,
                maxHeight: 200,
                resize: 'vertical',
                padding: 8,
                fontSize: 12,
                lineHeight: '1.5',
                border: '1px solid #d9d9d9',
                borderRadius: 4,
                fontFamily: 'inherit',
                color: '#333',
                background: '#fafafa',
                boxSizing: 'border-box',
              }}
            />
          )}
        </div>
        {shouldShowNodeState && (
          <div style={{ marginTop: 8, borderTop: '1px solid #eee', padding: '8px 12px', background: '#fff' }}>
            <div style={{ fontWeight: 600, marginBottom: 8, color: '#333' }}>{t('nodeState.title')}</div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
            <button
              type="button"
              style={{ fontSize: 12, padding: '2px 8px', border: '1px solid #d9d9d9', borderRadius: 4, background: '#f5f5f5', color: '#333', cursor: 'pointer' }}
              onClick={async () => {
                try {
                  const api = IPCAPI.getInstance();
                  const last = await api.getLastLoginInfo<any>();
                  const username = (last.success && (last.data as any)?.last_login?.username) || '';
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
            >{t('nodeState.refreshState')}</button>
            <button
              type="button"
              style={{ fontSize: 12, padding: '2px 8px', border: '1px solid #d9d9d9', borderRadius: 4, background: '#f5f5f5', color: '#333', cursor: 'pointer' }}
              onClick={async () => {
                try {
                  const api = IPCAPI.getInstance();
                  const last = await api.getLastLoginInfo<any>();
                  const username = (last.success && (last.data as any)?.last_login?.username) || '';
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
            >{t('nodeState.injectAndResume')}</button>
          </div>
          {loading || !schema ? (
            <div style={{ color: '#999' }}>{t('nodeState.loadingSchema')}</div>
          ) : (
            <NodeStatePanel schema={schema} value={getStateValue() ?? {}} onChange={setStateValue} />
          )}
          {/* Runtime state (read-only, from backend) */}
          <div style={{ marginTop: 12, borderTop: '1px dashed #eee', paddingTop: 8 }}>
            <div style={{ fontWeight: 600, marginBottom: 6, color: '#222' }}>{t('nodeState.runtimeStateTitle')}</div>
            <div style={{ fontSize: 12, color: '#333', marginBottom: 6 }}>{t('nodeState.nodeId')}: <code style={{ color: '#222' }}>{node.id}</code></div>
            {runtimeEntry ? (
              <>
                <div style={{ fontSize: 12, color: '#333', marginBottom: 6 }}>
                  {t('nodeState.status')}: <b>{runtimeEntry.status || 'n/a'}</b>
                  <span style={{ marginLeft: 8, color: '#999' }}>{t('nodeState.updated')}: {new Date(runtimeEntry.updatedAt).toLocaleTimeString()}</span>
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
                  >{t('nodeState.syncToForm')}</button>
                </div>
              </>
            ) : (
              <div style={{ fontSize: 12, color: '#999' }}>{t('nodeState.noRuntimeData')}</div>
            )}
          </div>
        </div>
        )}
        {/* Mapping rules editor - different for START node vs other nodes */}
        <div style={{ marginTop: 16, borderTop: '1px solid #eee', paddingTop: 12, padding: '12px' }}>
            {isStartNode ? (
              <>
                <div style={{ fontWeight: 600, marginBottom: 8, color: '#333' }}>{t('nodeState.skillLevelMappingTitle')}</div>
                <div style={{ fontSize: 12, color: '#666', marginBottom: 8 }}>
                  {t('nodeState.skillLevelMappingDesc')}
                </div>
                <SkillLevelMappingEditor 
                  value={getSkillLevelMappingRules()} 
                  onChange={setSkillLevelMappingRules} 
                />
              </>
            ) : (
              <>
                <div style={{ fontWeight: 600, marginBottom: 8, color: '#333' }}>{t('nodeState.nodeTransferMappingTitle')}</div>
                <div style={{ fontSize: 12, color: '#666', marginBottom: 8 }}>
                  {t('nodeState.nodeTransferMappingDesc')}
                </div>
                <div style={{ marginBottom: 8, padding: 8, borderRadius: 6, background: '#f7f9fc', border: '1px solid #e5ebf5' }}>
                  <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 6, color: '#2f3a4f' }}>
                    {t('nodeState.autoPromptVarsTitle')}
                  </div>
                  <div style={{ fontSize: 12, color: '#5b6475', lineHeight: 1.5 }}>
                    {t('nodeState.autoPromptVarsDesc')}
                  </div>
                  <div style={{ fontSize: 12, marginTop: 6, color: '#2f3a4f', lineHeight: 1.6 }}>
                    <div><code>{'{{previous_node_output}}'}</code> - {t('nodeState.autoVarPreviousOutput')}</div>
                    <div><code>{'{{previous_node_id}}'}</code> - {t('nodeState.autoVarPreviousNodeId')}</div>
                    <div><code>{'{{upstream_outputs}}'}</code> - {t('nodeState.autoVarUpstreamOutputs')}</div>
                    <div><code>{'{{upstream_node_ids}}'}</code> - {t('nodeState.autoVarUpstreamNodeIds')}</div>
                  </div>
                </div>
                <div style={{ fontSize: 12, color: '#666', marginBottom: 8 }}>
                  {t('nodeState.nodeTransferMappingOptionalDesc')}
                </div>
                <MappingEditor value={getMappingRules()} onChange={setMappingRules} />
                <div style={{ fontSize: 11, color: '#888', marginTop: 6 }}>
                  {t('nodeState.nodeTransferMappingExample')}
                </div>
              </>
            )}
          </div>
      </div>
    </NodeRenderContext.Provider>
  );
}
