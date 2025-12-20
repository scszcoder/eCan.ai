import { nanoid } from 'nanoid';
import { FlowNodeRegistry } from '../../typings';
import { WorkflowNodeType } from '../constants';
import { formMeta } from './form-meta';
import iconScript from '../../assets/icon-script.png';

let index = 0;
export const SheetCallNodeRegistry: FlowNodeRegistry = {
  // Use explicit string type for consistent panel label and selection
  type: 'sheet-call',
  meta: {
    size: { width: 360, height: 120 },
  },
  info: {
    icon: iconScript,
    description: 'Invoke another sheet and map its inputs/outputs.',
  },
  onAdd() {
    return {
      id: `sheet_call_${nanoid(5)}`,
      type: 'sheet-call',
      data: {
        title: `SheetCall_${++index}`,
        callName: `Call_${index}`,
        targetSheetId: '',
        inputMapping: {},
        outputMapping: {},
      },
    } as any;
  },
  formMeta,
};
