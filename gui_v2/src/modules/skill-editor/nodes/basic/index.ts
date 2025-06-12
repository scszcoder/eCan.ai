import { nanoid } from 'nanoid';

import { WorkflowNodeType } from '../constants';
import { FlowNodeRegistry } from '../../typings';
import iconBasic from '../../assets/icon-basic.png';
import { formMeta } from './form-meta';
import { DEFAULT_NODE_OUTPUTS } from '../../typings/node-outputs';

let index = 0;
export const BasicNodeRegistry: FlowNodeRegistry = {
  type: WorkflowNodeType.Basic,
  info: {
    icon: iconBasic,
    description: 'A basic node for executing general tasks with simple input and output.',
  },
  meta: {
    size: {
      width: 360,
      height: 305,
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