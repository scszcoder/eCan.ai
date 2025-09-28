import { nanoid } from 'nanoid';
import { FlowNodeRegistry } from '../../typings';
import { WorkflowNodeType } from '../constants';
import { formMeta } from './form-meta';

let index = 0;
export const SheetCallNodeRegistry: FlowNodeRegistry = {
  type: WorkflowNodeType.Custom as any, // falls back if no dedicated enum; engine uses string `type` below
  meta: {
    size: { width: 360, height: 120 },
  },
  info: {
    icon: '',
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
