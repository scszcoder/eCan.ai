import { nanoid } from 'nanoid';
import { FlowNodeRegistry } from '../../typings';
import { WorkflowNodeType } from '../constants';
import { formMeta } from './form-meta';
import iconVariable from '../../assets/icon-variable.png';

let index = 0;
export const SheetOutputsNodeRegistry: FlowNodeRegistry = {
  // Use explicit string type for consistent panel label and selection
  type: 'sheet-outputs',
  meta: {
    size: { width: 320, height: 100 },
    defaultPorts: [
      { type: 'input', key: 'in' },
    ],
  },
  info: {
    icon: iconVariable,
    description: 'Defines the output interface (ports) for this sheet.',
  },
  onAdd() {
    return {
      id: `sheet_outputs_${nanoid(5)}`,
      type: 'sheet-outputs',
      data: {
        title: `SheetOutputs_${++index}`,
        inputs: { type: 'object', properties: {} },
        outputs: { type: 'object', properties: {} },
        inputsValues: {},
        interface: { outputs: [{ name: 'result' }] },
      },
    } as any;
  },
  formMeta,
};
