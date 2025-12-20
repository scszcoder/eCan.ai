import { nanoid } from 'nanoid';

import { WorkflowNodeType } from '../constants';
import { FlowNodeRegistry } from '../../typings';
import iconDummy from '../../assets/icon-basic.png';
import { formMeta } from './form-meta';
import { DEFAULT_NODE_OUTPUTS } from '../../typings/node-outputs';

let index = 0;
export const DummyNodeRegistry: FlowNodeRegistry = {
  type: WorkflowNodeType.Dummy,
  info: {
    icon: iconDummy,
    description: 'A dummy node for testing and placeholder purposes',
  },
  meta: {
    size: {
      width: 320,
      height: 160,
    },
  },
  onAdd() {
    return {
      id: `dummy_${nanoid(5)}`,
      type: 'dummy',
      data: {
        name: `Dummy_${++index}`,
        title: `Dummy_${index}`,
        type: 'dummy',
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
