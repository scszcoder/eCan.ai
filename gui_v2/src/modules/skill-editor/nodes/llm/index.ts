/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { nanoid } from 'nanoid';

import { WorkflowNodeType } from '../constants';
import { FlowNodeRegistry } from '../../typings';
import iconLLM from '../../assets/icon-llm.jpg';
import { DEFAULT_NODE_OUTPUTS } from '../../typings/node-outputs';
import { formMeta } from './form-meta';

let index = 0;
export const LLMNodeRegistry: FlowNodeRegistry = {
  type: WorkflowNodeType.LLM,
  info: {
    icon: iconLLM,
    description:
      'Call the large language model and use variables and prompt words to generate responses.',
  },
  meta: {
    size: {
      width: 360,
      height: 390,
    },
  },
  onAdd() {
    return {
      id: `llm_${nanoid(5)}`,
      type: 'llm',
      data: {
        title: `LLM_${++index}`,
        inputsValues: {
          modelProvider: {
            type: 'constant',
            content: 'OpenAI',
          },
          modelName: {
            type: 'constant',
            content: 'gpt-4o-mini',
          },
          attachments: {
            type: 'constant',
            content: [],
          },
          apiKey: {
            type: 'constant',
            content: 'sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
          },
          apiHost: {
            type: 'constant',
            content: 'https://api.openai.com/v1',
          },
          temperature: {
            type: 'constant',
            content: 0.5,
          },
          systemPrompt: {
            type: 'template',
            content: '# Role\nYou are an AI assistant.\n',
          },
          prompt: {
            type: 'template',
            content: '',
          },
          promptSelection: {
            type: 'constant',
            content: 'inline',
          },
        },
        inputs: {
          type: 'object',
          required: ['modelProvider', 'modelName', 'apiKey', 'apiHost', 'temperature', 'prompt'],
          properties: {
            modelProvider: {
              type: 'string',
              extra: { formComponent: 'input' },
            },
            modelName: {
              type: 'string',
              extra: { formComponent: 'input' },
            },
            attachments: {
              type: 'array',
              extra: { formComponent: 'custom-attachments', skipDefault: true },
            },
            apiKey: {
              type: 'string',
              extra: { formComponent: 'input' },
            },
            apiHost: {
              type: 'string',
              extra: { formComponent: 'input' },
            },
            temperature: {
              type: 'number',
            },
            systemPrompt: {
              type: 'string',
              extra: {
                formComponent: 'prompt-editor',
              },
            },
            prompt: {
              type: 'string',
              extra: {
                formComponent: 'prompt-editor',
              },
            },
            promptSelection: {
              type: 'string',
              extra: {
                skipDefault: true,
              },
            },
          },
        },
        outputs: DEFAULT_NODE_OUTPUTS,
      },
    };
  },
  formMeta: formMeta,
};
