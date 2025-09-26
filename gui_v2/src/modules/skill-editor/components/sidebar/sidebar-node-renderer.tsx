/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { useNodeRender, FlowNodeEntity } from '@flowgram.ai/free-layout-editor';

import { NodeRenderContext } from '../../context';
import { useNodeStateSchema } from '../../../../stores/nodeStateSchemaStore';
import NodeStatePanel from '../node-state/NodeStatePanel';

export function SidebarNodeRenderer(props: { node: FlowNodeEntity }) {
  const { node } = props;
  const nodeRender = useNodeRender(node);
  const { schema, loading } = useNodeStateSchema();

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

  return (
    <NodeRenderContext.Provider value={nodeRender}>
      <div
        style={{
          background: 'rgb(251, 251, 251)',
          height: '100%',
          margin: '8px 8px 8px 0',
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
          {loading || !schema ? (
            <div style={{ color: '#999' }}>Loading node state schema...</div>
          ) : (
            <NodeStatePanel schema={schema} value={getStateValue() ?? {}} onChange={setStateValue} />
          )}
        </div>
      </div>
    </NodeRenderContext.Provider>
  );
}
