/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { FlowNodeRegistry } from '../../typings';
import iconEnd from '../../assets/icon-end.jpg';
import { formMeta } from './form-meta';
import { WorkflowNodeType } from '../constants';
import { nanoid } from 'nanoid';
import { DEFAULT_NODE_OUTPUTS } from '../../typings/node-outputs';

export const EndNodeRegistry: FlowNodeRegistry = {
  type: WorkflowNodeType.End,
  meta: {
    deleteDisable: false,
    copyDisable: true,
    nodePanelVisible: true,
    defaultPorts: [{ type: 'input' }],
    size: {
      width: 360,
      height: 211,
    },
  },
  info: {
    icon: iconEnd,
    description:
      'The final node of the workflow, used to return the result information after the workflow is run.',
  },
  /**
   * Render node via formMeta
   */
  formMeta,
  /**
   * End Node cannot be added
   */
  canAdd() {
    return true;
  },
  onAdd() {
    return {
      id: `end_${nanoid(5)}`,
      type: 'end',
      data: {
        title: 'End',
        outputs: DEFAULT_NODE_OUTPUTS,
      }
    };
  }
};
