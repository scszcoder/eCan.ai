/**
 * Chat Node Registry
 */
import { nanoid } from 'nanoid';
import { WorkflowNodeType } from '../constants';
import { FlowNodeRegistry } from '../../typings';
import { DEFAULT_NODE_OUTPUTS } from '../../typings/node-outputs';
import { formMeta } from './form-meta';
import iconChat from '../../assets/icon-chat.svg';

let idx = 0;
export const ChatNodeRegistry: FlowNodeRegistry = {
  type: WorkflowNodeType.Chat,
  info: {
    icon: iconChat,
    description: 'Send a chat message to a selected party (human or agent).',
  },
  meta: {
    size: { width: 360, height: 260 },
  },
  onAdd() {
    return {
      id: `chat_${nanoid(5)}`,
      type: 'chat_node',
      data: {
        title: `Chat_${++idx}`,
        inputsValues: {
          party: { type: 'constant', content: 'human' },
          messageTemplate: { type: 'template', content: '' },
        },
        inputs: {
          type: 'object',
          required: ['party'],
          properties: {
            party: { type: 'string' },
            messageTemplate: { type: 'string', extra: { formComponent: 'prompt-editor' } },
          },
        },
        outputs: DEFAULT_NODE_OUTPUTS,
      },
    };
  },
  formMeta,
};
