import { nanoid } from 'nanoid';
import { FlowNodeRegistry } from '../../typings';
import { WorkflowNodeType } from '../constants';
import { formMeta } from './form-meta';
import iconVariable from '../../assets/icon-variable.png';

let index = 0;
export const SheetInputsNodeRegistry: FlowNodeRegistry = {
  // Use explicit string type for consistent panel label and selection
  type: 'sheet-inputs',
  meta: {
    size: { width: 320, height: 100 },
    defaultPorts: [
      { type: 'output', key: 'out' },
    ],
  },
  info: {
    icon: iconVariable,
    description: 'Defines the input interface (ports) for this sheet.',
  },
  onAdd() {
    return {
      id: `sheet_inputs_${nanoid(5)}`,
      type: 'sheet-inputs',
      data: {
        title: `SheetInputs_${++index}`,
        inputs: { type: 'object', properties: {} },
        outputs: { type: 'object', properties: {} },
        // Interface list; editor UI can render from here
        inputsValues: {},
        interface: { inputs: [{ name: 'x' }, { name: 'y' }] },
      },
    } as any;
  },
  formMeta,
};
