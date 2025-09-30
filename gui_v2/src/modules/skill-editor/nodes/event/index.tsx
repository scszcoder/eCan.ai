/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { nanoid } from 'nanoid';
import { WorkflowNodeType } from '../constants';
import { FlowNodeRegistry } from '../../typings';
import iconCode from '../../assets/icon-script.png';
import { formMeta } from './form-meta';
import { DEFAULT_NODE_OUTPUTS } from '../../typings/node-outputs';

const defaultPython = `# Event handler: implement your logic here
# Access state and runtime like other nodes
from typing import Any, Dict

def main(state: Dict[str, Any], *, runtime, store):
  # Set outputs based on your logic
  state['result'] = {'event': state.get('event_type'), 'i_tag': state.get('i_tag')}
  return {'status': 'ok'}
`;

export const EventNodeRegistry: FlowNodeRegistry = {
  type: WorkflowNodeType.Event,
  info: {
    icon: iconCode,
    description: 'Event trigger node',
  },
  meta: {
    defaultPorts: [{ type: 'output' }],
    size: {
      width: 360,
      height: 300,
    },
    nodePanelVisible: false,
  },
  onAdd() {
    return {
      id: `event_${nanoid(5)}`,
      type: 'event',
      data: {
        title: 'Event',
        inputsValues: {
          input: { type: 'constant', content: '' },
        },
        event: {
          type: 'timer',
          i_tag: '',
        },
        script: {
          language: 'python',
          content: defaultPython,
        },
        outputs: DEFAULT_NODE_OUTPUTS,
      },
    };
  },
  formMeta: formMeta,
};
