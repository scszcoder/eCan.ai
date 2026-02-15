import { useCallback } from 'react';
import React from 'react';

import { FlowNodeEntity, useNodeRender } from '@flowgram.ai/free-layout-editor';
import { ConfigProvider } from '@douyinfe/semi-ui';

import { NodeStatusBar } from '../testrun/node-status-bar';
import { NodeRenderContext } from '../../context';
import { ErrorIcon } from './styles';
import { NodeWrapper } from './node-wrapper';
import { useNodeStateSchema } from '../../../../stores/nodeStateSchemaStore';
import NodeStatePanel from '../node-state/NodeStatePanel';
import { WorkflowNodeType } from '../../nodes/constants';

// Error boundary for individual nodes to prevent cascading failures
class NodeErrorBoundary extends React.Component<
  { children: React.ReactNode; nodeId: string; nodeType: string },
  { hasError: boolean; error?: Error }
> {
  constructor(props: { children: React.ReactNode; nodeId: string; nodeType: string }) {
    super(props);
    this.state = { hasError: false };
  }
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }
  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error(`[BaseNode] Node ${this.props.nodeId} (${this.props.nodeType}) crashed:`, error, info);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 12, background: '#fff3f3', border: '1px solid #ff4d4f', borderRadius: 4 }}>
          <div style={{ fontWeight: 600, color: '#ff4d4f', marginBottom: 4 }}>Node Error</div>
          <div style={{ fontSize: 11, color: '#666' }}>
            ID: {this.props.nodeId}<br />
            Type: {this.props.nodeType}<br />
            {this.state.error?.message}
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export const BaseNode = ({ node }: { node: FlowNodeEntity }) => {
  console.log('[BaseNode] Rendering node:', { nodeId: node?.id, nodeType: node?.flowNodeType });
  /**
   * Provides methods related to node rendering
   * 提供节点RenderRelated toMethod
   */
  const nodeRender = useNodeRender();
  /**
   * It can only be used when nodeEngine is enabled
   * 只有在节点引擎开启时候才能使用Form
   */
  const form = nodeRender.form;
  const { schema, loading } = useNodeStateSchema();

  // Safe helpers to read/write the 'state' field on the node form
  const getStateValue = () => {
    try {
      // Prefer form API if available
      // @ts-ignore
      if (form?.getFieldValue) return form.getFieldValue('state');
      // @ts-ignore
      if (form?.state?.values) return (form.state.values as any).state;
    } catch {}
    return undefined;
  };
  const setStateValue = (val: any) => {
    try {
      // @ts-ignore
      if (form?.setFieldValue) return form.setFieldValue('state', val);
      // Fallback: noop if API not available
    } catch {}
  };

  /**
   * Used to make the Tooltip scale with the node, which can be implemented by itself depending on the UI library
   * Used for让 Tooltip 跟随节点Scale, 这个Can根据不同的 ui 库自己Implementation
   */
  const getPopupContainer = useCallback(() => node.renderData.node || document.body, []);

  // Get the actual node type - prefer flowNodeType (set by the editor's node registry)
  // Fallback to extracting from the node ID prefix
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
  
  // Check if node is Loop, BlockStart, or BlockEnd to hide nodeState UI
  const shouldHideNodeState = 
    nodeType === WorkflowNodeType.Loop || 
    nodeType === 'block-start' || 
    nodeType === 'block-end';
  const shouldShowNodeState = !shouldHideNodeState;

  return (
    <NodeErrorBoundary nodeId={node.id} nodeType={nodeType}>
      <ConfigProvider getPopupContainer={getPopupContainer}>
        <NodeRenderContext.Provider value={nodeRender}>
          <NodeWrapper>
            {form?.state.invalid && <ErrorIcon />}
            {form?.render()}
            {/* Unified Node State panel for all nodes (hidden for Loop, BlockStart, BlockEnd) */}
            {shouldShowNodeState && (
              <div style={{ marginTop: 8, borderTop: '1px solid #eee', paddingTop: 8 }}>
                <div style={{ fontWeight: 600, marginBottom: 8, color: '#333' }}>Node State</div>
                {loading || !schema ? (
                  <div style={{ color: '#999' }}>Loading node state schema...</div>
                ) : (
                  <NodeStatePanel schema={schema} value={getStateValue() ?? {}} onChange={setStateValue} />
                )}
              </div>
            )}
          </NodeWrapper>
          <NodeStatusBar />
        </NodeRenderContext.Provider>
      </ConfigProvider>
    </NodeErrorBoundary>
  );
};
