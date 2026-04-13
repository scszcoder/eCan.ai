import { nanoid } from 'nanoid';

import { WorkflowNodeType } from '../constants';
import { FlowNodeRegistry } from '../../typings';
import iconTask from '../../assets/icon-task.svg';
import { formMeta } from './form-meta';
import { DEFAULT_NODE_OUTPUTS } from '../../typings/node-outputs';

let index = 0;
export const TaskNodeRegistry: FlowNodeRegistry = {
  type: WorkflowNodeType.Task,
  info: {
    icon: iconTask,
    description: 'nodes.task.description',
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
        name: `Task_${++index}`,
        title: `Task_${index}`,
        type: 'task',
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
