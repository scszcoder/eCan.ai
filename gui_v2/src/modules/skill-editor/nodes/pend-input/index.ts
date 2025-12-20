/**
 * Pend Input Node Registry
 */
import { nanoid } from 'nanoid';
import { WorkflowNodeType } from '../constants';
import { FlowNodeRegistry } from '../../typings';
import { DEFAULT_NODE_OUTPUTS } from '../../typings/node-outputs';
import { formMeta } from './form-meta';
import iconBreak from '../../assets/icon-break.jpg';

let idx = 0;
export const PendInputNodeRegistry: FlowNodeRegistry = {
  type: WorkflowNodeType.PendInput,
  info: {
    icon: iconBreak,
    description: 'Pause the flow until a message arrives from selected queues/events.',
  },
  meta: {
    defaultPorts: [
      { type: 'input', key: 'in_primary' },
      { type: 'input', key: 'in_event' },
      { type: 'output', key: 'out' },
    ],
    size: { width: 380, height: 300 },
    nodePanelVisible: false,
  },
  onAdd() {
    return {
      id: `pend_${nanoid(5)}`,
      type: 'pend_input_node',
      data: {
        title: `PendInput_${++idx}`,
        inputsValues: {
          pendingSources: { type: 'constant', content: [] },
          timeoutSec: { type: 'constant', content: 0 },
          resumePolicy: { type: 'constant', content: 'first' },
        },
        inputs: {
          type: 'object',
          required: ['pendingSources'],
          properties: {
            pendingSources: { type: 'array' },
            timeoutSec: { type: 'number' },
            resumePolicy: { type: 'string' },
          },
        },
        outputs: DEFAULT_NODE_OUTPUTS,
      },
    };
  },
  formMeta,
};
