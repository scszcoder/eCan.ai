/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import {
  WorkflowNodePanelService,
  WorkflowNodePanelUtils,
} from '@flowgram.ai/free-node-panel-plugin';
import {
  delay,
  FreeLayoutPluginContext,
  onDragLineEndParams,
  WorkflowDragService,
  WorkflowLinesManager,
  WorkflowNodeEntity,
  WorkflowNodeJSON,
} from '@flowgram.ai/free-layout-editor';

/**
 * Drag the end of the line to create an add panel (feature optional)
 * Drag线条结束NeedCreate一个Add面板 （功能Optional）
 */
export const onDragLineEnd = async (ctx: FreeLayoutPluginContext, params: onDragLineEndParams) => {
  // get services from context - 从上下文GetService
  const nodePanelService = ctx.get(WorkflowNodePanelService);
  const document = ctx.document;
  const dragService = ctx.get(WorkflowDragService);
  const linesManager = ctx.get(WorkflowLinesManager);

  // get params from drag event - 从DragEventGetParameter
  const { fromPort, toPort, mousePos, line, originLine } = params;

  // return if invalid line state - If线条Status无效则返回
  if (originLine || !line) {
    return;
  }

  // return if target port exists - If目标端口存在则返回
  if (toPort) {
    return;
  }

  // get container node for the new node - Get新节点的Container节点
  const containerNode = fromPort.node.parent;

  // open node selection panel - Open节点Select面板
  const result = await nodePanelService.singleSelectNodePanel({
    position: mousePos,
    containerNode,
    panelProps: {
      enableNodePlaceholder: true,
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
    position: mousePos,
    fromPort,
    toPort,
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
    fromPort,
    node,
    linesManager,
  });
};
