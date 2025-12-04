import { nanoid } from 'nanoid';

import { WorkflowNodeType } from '../constants';
import { FlowNodeRegistry } from '../../typings';
import iconToolPicker from '../../assets/icon-basic.png';
import { formMeta } from './form-meta';
import { DEFAULT_NODE_OUTPUTS } from '../../typings/node-outputs';

let index = 0;
export const ToolPickerNodeRegistry: FlowNodeRegistry = {
  type: WorkflowNodeType.ToolPicker,
  info: {
    icon: iconToolPicker,
    description: 'A tool picker node for selecting and invoking tools',
  },
  meta: {
    size: {
      width: 320,
      height: 160,
    },
  },
  onAdd() {
    return {
      id: `tool-picker_${nanoid(5)}`,
      type: 'tool-picker',
      data: {
        title: `ToolPicker_${++index}`,
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
