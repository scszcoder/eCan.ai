import { nanoid } from 'nanoid';

import { WorkflowNodeType } from '../constants';
import { FlowNodeRegistry } from '../../typings';
import iconMcp from '../../assets/icon-basic.png';
import { formMeta } from './form-meta';
import { DEFAULT_NODE_OUTPUTS } from '../../typings/node-outputs';

let index = 0;
export const BasicNodeRegistry: FlowNodeRegistry = {
  type: WorkflowNodeType.Basic,
  info: {
    icon: iconMcp,
    description: 'A basic node with no editor fields. Use it as a simple placeholder or pass-through.',
  },
  meta: {
    size: {
      width: 320,
      height: 160,
    },
  },
  onAdd() {
    return {
      id: `basic_${nanoid(5)}`,
      type: 'basic',
      data: {
        title: `Basic_${++index}`,
        inputsValues: {},
        inputs: {
          type: 'object',
          properties: {} as Record<string, { type: string; description: string }>,
        },
        outputs: DEFAULT_NODE_OUTPUTS,
      },
    };
  },
  formMeta,
};