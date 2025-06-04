import { nanoid } from 'nanoid';

import { WorkflowNodeType } from '../constants';
import { FlowNodeRegistry } from '../../typings';
import iconBasic from '../../assets/icon-basic.jpg';
import { defaultFormMeta } from '../default-form-meta';

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
          properties: {
            input: {
              type: 'string',
              description: 'Input value',
            },
          },
        },
        outputs: {
          type: 'object',
          properties: {
            output: {
              type: 'string',
              description: 'Output value',
            },
          },
        },
      },
    };
  },
  formMeta: defaultFormMeta,
}; 