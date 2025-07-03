/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { delay, WorkflowDocument, WorkflowNodeEntity } from '@flowgram.ai/free-layout-editor';

import { WorkflowNodeType } from '../constants';

export const createBuiltInNodes = async (node: WorkflowNodeEntity) => {
  // wait for node render - 等待节点渲染
  await delay(16);
  if (node.blocks.length) {
    return;
  }
  const document = node.document as WorkflowDocument;
  document.createWorkflowNode(
    {
      id: `block_start_${node.id}`,
      type: WorkflowNodeType.BlockStart,
      meta: {
        position: {
          x: -80,
          y: 0,
        },
      },
      data: {},
    },
    false,
    node.id
  );
  document.createWorkflowNode(
    {
      id: `block_end_${node.id}`,
      type: WorkflowNodeType.BlockEnd,
      meta: {
        position: {
          x: 80,
          y: 0,
        },
      },
      data: {},
    },
    false,
    node.id
  );
};
