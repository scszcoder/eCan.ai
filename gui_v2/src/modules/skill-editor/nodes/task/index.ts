import { nanoid } from 'nanoid';

import { WorkflowNodeType } from '../constants';
import { FlowNodeRegistry } from '../../typings';
import iconTask from '../../assets/icon-basic.png';
import { formMeta } from './form-meta';
import { DEFAULT_NODE_OUTPUTS } from '../../typings/node-outputs';

let index = 0;
export const TaskNodeRegistry: FlowNodeRegistry = {
  type: WorkflowNodeType.Task,
  info: {
    icon: iconTask,
    description: 'A task node for organizing workflow steps',
  },
  meta: {
    size: {
      width: 320,
      height: 160,
    },
  },
  onAdd() {
    return {
      id: `task_${nanoid(5)}`,
      type: 'task',
      data: {
        title: `Task_${++index}`,
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
