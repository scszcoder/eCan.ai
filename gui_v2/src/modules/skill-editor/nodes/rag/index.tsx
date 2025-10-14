import { nanoid } from 'nanoid';

import { WorkflowNodeType } from '../constants';
import { FlowNodeRegistry } from '../../typings';
import iconRAG from '../../assets/icon-rag.png';
import { formMeta } from './form-meta';
import { DEFAULT_NODE_OUTPUTS } from '../../typings/node-outputs';

let index = 0;
export const RAGNodeRegistry: FlowNodeRegistry = {
  type: WorkflowNodeType.RAG,
  info: {
    icon: iconRAG,
    description: 'Retrieve and generate responses using RAG (Retrieval-Augmented Generation) with vector databases.',
  },
  meta: {
    size: {
      width: 360,
      height: 400,
    },
  },
  formMeta,
  onAdd() {
    return {
      id: `rag_${nanoid(5)}`,
      type: 'rag_node',
      data: {
        title: `RAG_${++index}`,
        inputsValues: {
          knowledgeBase: {
            type: 'constant',
            content: 'default',
          },
          retrievalMode: {
            type: 'constant',
            content: 'vector',
          },
          topK: {
            type: 'constant',
            content: 5,
          },
          scoreThreshold: {
            type: 'constant',
            content: 0.7,
          },
          embeddingModel: {
            type: 'constant',
            content: 'text-embedding-ada-002',
          },
          query: {
            type: 'constant',
            content: '',
          },
          filters: {
            type: 'constant',
            content: '',
          },
        },
        inputs: {
          type: 'object',
          required: ['knowledgeBase', 'retrievalMode', 'query'],
          properties: {
            knowledgeBase: {
              type: 'string',
              description: 'Select the target vector database/document store',
            },
            retrievalMode: {
              type: 'string',
              enum: ['vector', 'keyword', 'hybrid'],
              description: 'Choose retrieval mode: vector search, keyword search, or hybrid',
            },
            topK: {
              type: 'number',
              description: 'Number of top results to retrieve',
            },
            scoreThreshold: {
              type: 'number',
              description: 'Minimum similarity score threshold',
            },
            embeddingModel: {
              type: 'string',
              description: 'Select the embedding model for vector search',
            },
            query: {
              type: 'string',
              description: 'The search query',
            },
            filters: {
              type: 'string',
              description: 'Additional filtering conditions in JSON format',
            },
          },
        },
        outputs: DEFAULT_NODE_OUTPUTS,
      },
    };
  }
}; 