/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { useNodeRender, FlowNodeEntity } from '@flowgram.ai/free-layout-editor';

import { NodeRenderContext } from '../../context';
import { useNodeStateSchema } from '../../../../stores/nodeStateSchemaStore';
import NodeStatePanel from '../node-state/NodeStatePanel';
import MappingEditor, { type MappingConfig } from '../mapping/MappingEditor';
import { IPCAPI } from '../../../../services/ipc/api';
import { useSkillInfoStore } from '../../stores/skill-info-store';

export function SidebarNodeRenderer(props: { node: FlowNodeEntity }) {
  const { node } = props;
  const nodeRender = useNodeRender(node);
  const { schema, loading } = useNodeStateSchema();
  const { skillInfo } = useSkillInfoStore();
  const setHasUnsavedChanges = useSkillInfoStore((s) => s.setHasUnsavedChanges);

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

  // Mapping Rules bindings (persist to node.data.mapping_rules)
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
          {/* Mapping rules editor */}
          <div style={{ marginTop: 16 }}>
            <div style={{ fontWeight: 600, marginBottom: 8, color: '#333' }}>Mapping Rules</div>
            <MappingEditor value={getMappingRules()} onChange={setMappingRules} />
          </div>
        </div>
      </div>
    </NodeRenderContext.Provider>
  );
}
