import { nanoid } from 'nanoid';
import { FlowNodeRegistry } from '../../typings';
import { WorkflowNodeType } from '../constants';
import { formMeta } from './form-meta';

let index = 0;
export const SheetInputsNodeRegistry: FlowNodeRegistry = {
  type: WorkflowNodeType.Custom as any,
  meta: {
    size: { width: 320, height: 100 },
    defaultPorts: [],
  },
  info: {
    icon: '',
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
