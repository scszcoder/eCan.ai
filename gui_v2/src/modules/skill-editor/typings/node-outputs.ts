/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { JsonSchema } from './json-schema';

export const DEFAULT_NODE_OUTPUTS: JsonSchema = {
  type: 'object',
  properties: {
    result: {
      type: 'object',
      description: 'Node execution result'
    },
    condition: {
      type: 'boolean',
      description: 'Node execution condition'
    },
    resolved: {
      type: 'boolean',
      description: 'Node execution resolved status'
    },
    case: {
      type: 'string',
      description: 'Node execution case'
    }
  }
}; 