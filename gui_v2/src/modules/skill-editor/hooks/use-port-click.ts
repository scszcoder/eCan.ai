/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { useCallback } from 'react';

import {
  WorkflowNodePanelService,
  WorkflowNodePanelUtils,
} from '@flowgram.ai/free-node-panel-plugin';
import {
  delay,
  usePlayground,
  useService,
  WorkflowDocument,
  WorkflowDragService,
  WorkflowLinesManager,
  WorkflowNodeEntity,
  WorkflowNodeJSON,
  WorkflowPortEntity,
} from '@flowgram.ai/free-layout-editor';

/**
 * click port to trigger node select panel
 * Click端口后唤起节点Select面板
 */
export const usePortClick = () => {
  const playground = usePlayground();
  const nodePanelService = useService(WorkflowNodePanelService);
  const document = useService(WorkflowDocument);
  const dragService = useService(WorkflowDragService);
  const linesManager = useService(WorkflowLinesManager);

  const onPortClick = useCallback(async (e: React.MouseEvent, port: WorkflowPortEntity) => {
    const mousePos = playground.config.getPosFromMouseEvent(e);
    const containerNode = port.node.parent;
    // open node selection panel - Open节点Select面板
    const result = await nodePanelService.singleSelectNodePanel({
      position: mousePos,
      containerNode,
      panelProps: {
        enableScrollClose: true,
      },
    });

    // return if no node selected - If没有Select节点则返回
    if (!result) {
      return;
    }

    // get selected node type and data - GetSelect的节点Type和Data
    const { nodeType, nodeJSON } = result;

    // calculate position for the new node - 计算新节点的Position
    const nodePosition = WorkflowNodePanelUtils.adjustNodePosition({
      nodeType,
      position: {
        x: mousePos.x + 100,
        y: mousePos.y,
      },
      fromPort: port,
      containerNode,
      document,
      dragService,
    });

    // create new workflow node - Create新的工作流节点
    const node: WorkflowNodeEntity = document.createWorkflowNodeByType(
      nodeType,
      nodePosition,
      nodeJSON ?? ({} as WorkflowNodeJSON),
      containerNode?.id
    );

    // wait for node render - 等待节点Render
    await delay(20);

    // build connection line - 构建Connection线
    WorkflowNodePanelUtils.buildLine({
      fromPort: port,
      node,
      linesManager,
    });
  }, []);

  return onPortClick;
};
