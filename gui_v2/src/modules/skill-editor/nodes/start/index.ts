/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { FlowNodeRegistry } from '../../typings';
import iconStart from '../../assets/icon-start.jpg';
import { formMeta } from './form-meta';
import { WorkflowNodeType } from '../constants';
import { nanoid } from 'nanoid';
import { DEFAULT_NODE_OUTPUTS } from '../../typings/node-outputs';

export const StartNodeRegistry: FlowNodeRegistry = {
  type: WorkflowNodeType.Start,
  meta: {
    isStart: true,
    deleteDisable: false,
    copyDisable: true,
    nodePanelVisible: true,
    defaultPorts: [{ type: 'output' }],
    size: {
      width: 360,
      height: 211,
    },
  },
  info: {
    icon: iconStart,
    description:
      'The starting node of the workflow, used to set the information needed to initiate the workflow.',
  },
  /**
   * Render node via formMeta
   */
  formMeta,
  /**
   * Start Node cannot be added
   */
  onAdd() {
    return {
      id: `start_${nanoid(5)}`,
      type: 'start',
      data: {
        title: 'Start',
        outputs: DEFAULT_NODE_OUTPUTS,
      }
    };
  }
};
