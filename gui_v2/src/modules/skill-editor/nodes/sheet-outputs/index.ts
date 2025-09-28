import { nanoid } from 'nanoid';
import { FlowNodeRegistry } from '../../typings';
import { WorkflowNodeType } from '../constants';

let index = 0;
export const SheetOutputsNodeRegistry: FlowNodeRegistry = {
  type: WorkflowNodeType.Custom as any,
  meta: {
    size: { width: 320, height: 100 },
    defaultPorts: [],
  },
  info: {
    icon: '',
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
};
