/**
 * Pend Event Node Registry
 */
import { nanoid } from 'nanoid';
import { WorkflowNodeType } from '../constants';
import { FlowNodeRegistry } from '../../typings';
import { DEFAULT_NODE_OUTPUTS } from '../../typings/node-outputs';
import { formMeta } from './form-meta';
import iconBreak from '../../assets/icon-break.jpg';

let idx = 0;
export const PendEventNodeRegistry: FlowNodeRegistry = {
  type: WorkflowNodeType.PendEvent as any,
  info: {
    icon: iconBreak,
    description: 'Pause the flow until a specified event type arrives, then resume.',
  },
  meta: {
    defaultPorts: [
      { type: 'input', key: 'in_primary' },
      { type: 'input', key: 'in_event' },
      { type: 'output', key: 'out' },
    ],
    size: { width: 380, height: 300 },
  },
  onAdd() {
    return {
      id: `pend_event_${nanoid(5)}`,
      type: 'pend_event_node',
      data: {
        title: `PendEvent_${++idx}`,
        inputsValues: {
          eventType: { type: 'constant', content: 'human_chat' },
          messageType: { type: 'constant', content: '' },
          agentIds: { type: 'constant', content: '' },
          // Backward compat: keep pendingSources but prefer pendingEvents for UI
          pendingSources: { type: 'constant', content: [] },
          pendingEvents: { type: 'constant', content: [] },
          timeoutSec: { type: 'constant', content: 0 },
          resumePolicy: { type: 'constant', content: 'first' },
        },
        inputs: {
          type: 'object',
          required: ['eventType'],
          properties: {
            eventType: { type: 'string' },
            messageType: { type: 'string' },
            agentIds: { type: 'string' },
            pendingSources: { type: 'array' },
            pendingEvents: { type: 'array' },
            timeoutSec: { type: 'number' },
            resumePolicy: { type: 'string' },
          },
        },
        outputs: DEFAULT_NODE_OUTPUTS,
      },
    } as any;
  },
  formMeta,
};
