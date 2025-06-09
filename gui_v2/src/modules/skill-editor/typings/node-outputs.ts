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