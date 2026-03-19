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
    description: 'nodes.browserAutomation.description',
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
          cdpPort: { type: 'constant', content: '9228' },
          runEnvironment: { type: 'constant', content: 'full_local' },
          privacyStrategy: { type: 'constant', content: 'none' },
          enableJudge: { type: 'constant', content: false },
          shopName: { type: 'constant', content: 'amazon' },
          customShopName: { type: 'constant', content: '' },
          modelProvider: { type: 'constant', content: 'OpenAI' },
          modelName: { type: 'constant', content: 'gpt-3.5-turbo' },
          temperature: { type: 'constant', content: 0.3 },
          useThinking: { type: 'constant', content: false },
          useVision: { type: 'constant', content: false },
          profile: { type: 'constant', content: '' },
          flashMode: { type: 'constant', content: false },
          maxSteps: { type: 'constant', content: '' },
          maxActionsPerStep: { type: 'constant', content: '' },
          systemPrompt: { 
            type: 'template', 
            content: 'You are a helpful browser automation agent.\n\n⚠️ CRITICAL: You MUST respond with VALID JSON ONLY. No text before or after the JSON.\n\nRequired JSON Format:\n{\n  "evaluation_previous_goal": "string - evaluate the previous step",\n  "memory": "string - important information to remember",\n  "next_goal": "string - what to do next",\n  "action": [\n    {"action_name": {action_parameters}}\n  ]\n}\n\nAvailable Actions:\n- go_to_url: {"url": "https://..."}\n- click: {"xpath": "//button[@id=\'submit\']"}\n- input_text: {"xpath": "//input[@name=\'q\']", "text": "search query"}\n- scroll: {"direction": "down", "amount": 500}\n- extract: {"xpath": "//div[@class=\'content\']"}\n- done: {"text": "Task completed", "success": true}\n- search_google: {"query": "search term"}\n- open_tab, close_tab, switch_tab, go_back\n- list_files, read_file, upload_file and other registered local tools when needed\n\nExample Response:\n{\n  "evaluation_previous_goal": "Started the task",\n  "memory": "Need to inspect local materials before web research",\n  "next_goal": "List the local material directory",\n  "action": [{"list_files": {"directory": "/path/to/materials"}}]\n}\n\nIMPORTANT Rules:\n1. ALWAYS output valid JSON with all 4 required fields\n2. "action" MUST be an array with at least 1 element\n3. Local file tools are allowed when needed for the task\n4. Use "done" action when task is complete\n5. NO text outside the JSON structure' 
          },
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
            runEnvironment: { type: 'string', extra: { formComponent: 'select' } },
            privacyStrategy: { type: 'string', extra: { formComponent: 'select' } },
            enableJudge: { type: 'boolean', extra: { formComponent: 'checkbox' } },
            shopName: { type: 'string', extra: { formComponent: 'input' } },
            customShopName: { type: 'string', extra: { formComponent: 'input' } },
            modelProvider: { type: 'string', extra: { formComponent: 'input' } },
            modelName: { type: 'string', extra: { formComponent: 'input' } },
            temperature: { type: 'number' },
            useThinking: { type: 'boolean', extra: { formComponent: 'checkbox' } },
            useVision: { type: 'boolean', extra: { formComponent: 'checkbox' } },
            profile: { type: 'string', extra: { formComponent: 'input' } },
            flashMode: { type: 'boolean', extra: { formComponent: 'checkbox' } },
            maxSteps: { type: 'number' },
            maxActionsPerStep: { type: 'number' },
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
