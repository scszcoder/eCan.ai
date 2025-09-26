import { useCallback } from 'react';

import { FlowNodeEntity, useNodeRender } from '@flowgram.ai/free-layout-editor';
import { ConfigProvider } from '@douyinfe/semi-ui';

import { NodeStatusBar } from '../testrun/node-status-bar';
import { NodeRenderContext } from '../../context';
import { ErrorIcon } from './styles';
import { NodeWrapper } from './node-wrapper';
import { useNodeStateSchema } from '../../../../stores/nodeStateSchemaStore';
import NodeStatePanel from '../node-state/NodeStatePanel';

export const BaseNode = ({ node }: { node: FlowNodeEntity }) => {
  /**
   * Provides methods related to node rendering
   * 提供节点渲染相关的方法
   */
  const nodeRender = useNodeRender();
  /**
   * It can only be used when nodeEngine is enabled
   * 只有在节点引擎开启时候才能使用表单
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
   * 用于让 Tooltip 跟随节点缩放, 这个可以根据不同的 ui 库自己实现
   */
  const getPopupContainer = useCallback(() => node.renderData.node || document.body, []);

  return (
    <ConfigProvider getPopupContainer={getPopupContainer}>
      <NodeRenderContext.Provider value={nodeRender}>
        <NodeWrapper>
          {form?.state.invalid && <ErrorIcon />}
          {form?.render()}
          {/* Unified Node State panel for all nodes */}
          <div style={{ marginTop: 8, borderTop: '1px solid #eee', paddingTop: 8 }}>
            <div style={{ fontWeight: 600, marginBottom: 8, color: '#333' }}>Node State</div>
            {loading || !schema ? (
              <div style={{ color: '#999' }}>Loading node state schema...</div>
            ) : (
              <NodeStatePanel schema={schema} value={getStateValue() ?? {}} onChange={setStateValue} />
            )}
          </div>
        </NodeWrapper>
        <NodeStatusBar />
      </NodeRenderContext.Provider>
    </ConfigProvider>
  );
};
