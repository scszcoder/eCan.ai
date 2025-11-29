/**
 * Browser Automation node
 */
import { nanoid } from 'nanoid';

import { WorkflowNodeType } from '../constants';
import { FlowNodeRegistry } from '../../typings';
import iconScript from '../../assets/icon-script.png';
import { DEFAULT_NODE_OUTPUTS } from '../../typings/node-outputs';
import { formMeta } from './form-meta';

let index = 0;

export const BrowserAutomationNodeRegistry: FlowNodeRegistry = {
  type: WorkflowNodeType.BrowserAutomation,
  info: {
    icon: iconScript,
    description: 'Automate browsing tasks using a selected tool with prompts and parameters.',
  },
  meta: {
    size: {
      width: 360,
      height: 420,
    },
  },
  onAdd() {
    return {
      id: `browser_automation_${nanoid(5)}`,
      type: 'browser-automation',
      data: {
        title: `Browser_${++index}`,
        inputsValues: {
          tool: { type: 'constant', content: 'browser-use' },
          browser: { type: 'constant', content: 'new chromium' },
          browserDriver: { type: 'constant', content: 'native' },
          cdpPort: { type: 'constant', content: '' },
          modelProvider: { type: 'constant', content: 'OpenAI' },
          modelName: { type: 'constant', content: 'gpt-3.5-turbo' },
          temperature: { type: 'constant', content: 0.3 },
          systemPrompt: { type: 'template', content: 'You are a helpful browser automation agent.' },
          prompt: { type: 'template', content: '' },
          promptSelection: { type: 'constant', content: 'inline' },
        },
        inputs: {
          type: 'object',
          required: ['tool', 'browser', 'browserDriver', 'modelProvider', 'modelName', 'temperature', 'prompt'],
          properties: {
            tool: { type: 'string', extra: { formComponent: 'input' } },
            browser: { type: 'string', extra: { formComponent: 'input' } },
            browserDriver: { type: 'string', extra: { formComponent: 'input' } },
            cdpPort: { type: 'string', extra: { formComponent: 'input' } },
            modelProvider: { type: 'string', extra: { formComponent: 'input' } },
            modelName: { type: 'string', extra: { formComponent: 'input' } },
            temperature: { type: 'number' },
            systemPrompt: { type: 'string', extra: { formComponent: 'prompt-editor' } },
            prompt: { type: 'string', extra: { formComponent: 'prompt-editor', enablePromptLibrary: true } },
            promptSelection: { type: 'string', extra: { skipDefault: true } },
          },
        },
        outputs: DEFAULT_NODE_OUTPUTS,
      },
    };
  },
  formMeta: formMeta,
};
