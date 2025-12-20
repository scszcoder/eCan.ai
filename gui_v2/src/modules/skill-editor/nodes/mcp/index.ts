import { nanoid } from 'nanoid';

import { WorkflowNodeType } from '../constants';
import { FlowNodeRegistry } from '../../typings';
import iconMcp from '../../assets/icon-basic.png';
import { formMeta } from './form-meta';
import { DEFAULT_NODE_OUTPUTS } from '../../typings/node-outputs';

let index = 0;
export const MCPNodeRegistry: FlowNodeRegistry = {
  type: WorkflowNodeType.MCP,
  info: {
    icon: iconMcp,
    description: 'An MCP node for executing general tasks via MCP tools with simple input and output.',
  },
  meta: {
    size: {
      width: 360,
      height: 305,
    },
  },
  onAdd() {
    return {
      id: `mcp_${nanoid(5)}`,
      type: 'mcp',
      data: {
        title: `MCP_${++index}`,
        callable: {
          id: 'llm-auto-select',
          name: 'llm auto select',
          desc: 'Let the LLM automatically select the appropriate tool based on the context',
          params: { type: 'object', properties: {} },
          returns: { type: 'object', properties: {} },
          type: 'system',
          source: '',
        },
        inputsValues: {},
        inputs: {
          type: 'object',
          properties: {} as Record<string, { type: string; description: string }>,
        },
        outputs: DEFAULT_NODE_OUTPUTS,
      },
    };
  },
  formMeta,
};
