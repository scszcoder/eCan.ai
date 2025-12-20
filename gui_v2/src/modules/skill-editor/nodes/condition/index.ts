/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { nanoid } from 'nanoid';

import { FlowNodeRegistry } from '../../typings';
import iconCondition from '../../assets/icon-condition.svg';
import { formMeta } from './form-meta';
import { WorkflowNodeType } from '../constants';
import { DEFAULT_NODE_OUTPUTS } from '../../typings/node-outputs';

export const ConditionNodeRegistry: FlowNodeRegistry = {
  type: WorkflowNodeType.Condition,
  info: {
    icon: iconCondition,
    description:
      'Connect multiple downstream branches. Only the corresponding branch will be executed if the set conditions are met.',
  },
  meta: {
    defaultPorts: [
      { type: 'input', key: 'in' },
    ],
    useDynamicPort: true,
    expandable: true,
    size: {
      width: 360,
      height: 240,
    },
  },
  formMeta,
  onAdd() {
    const ifKey = `if_${nanoid(5)}`;
    const elseKey = `else_${nanoid(5)}`;
    return {
      id: `condition_${nanoid(5)}`,
      type: 'condition',
      data: {
        title: 'Condition',
        conditions: [
          {
            key: ifKey,
            value: {},
          },
          {
            key: elseKey,
            value: {},
          },
        ],
        outputs: DEFAULT_NODE_OUTPUTS,
      },
    };
  },
};
