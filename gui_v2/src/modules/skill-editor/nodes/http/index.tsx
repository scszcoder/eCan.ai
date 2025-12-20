/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { nanoid } from 'nanoid';

import { WorkflowNodeType } from '../constants';
import { FlowNodeRegistry } from '../../typings';
import iconHTTP from '../../assets/icon-http.svg';
import { formMeta, FormRender } from './form-meta';
import { DEFAULT_NODE_OUTPUTS } from '../../typings/node-outputs';
import { HTTPNodeJSON, HTTPNodeInput } from './types';

let index = 0;

export const HTTPNodeRegistry: FlowNodeRegistry = {
  type: WorkflowNodeType.HTTP,
  info: {
    icon: iconHTTP,
    description: 'Call the HTTP API',
  },
  meta: {
    size: {
      width: 360,
      height: 390,
    },
  },
  onAdd() {
    return {
      id: `http_${nanoid(5)}`,
      type: 'http',
      data: {
        title: `HTTP_${++index}`,
        inputsValues: {
          apiKey: { type: 'constant', content: '' },
        },
        api: {
          method: 'GET',
        },
        body: {
          bodyType: 'JSON',
        },
        headers: {},
        params: {},
        outputs: DEFAULT_NODE_OUTPUTS,
      },
    };
  },
  formMeta: formMeta,
  runtime: async (inputs: HTTPNodeInput) => {
    // This is a mock runtime for the frontend. It does not make a real HTTP request.
    // It immediately returns a success state with a mock response.
    console.log('Mock HTTP Runtime. Inputs:', inputs);
    return {
      outputs: {
        status: 200,
        headers: { 'content-type': 'application/json' },
        body: { message: 'This is a mock response' },
      },
      __isError: false,
    };
  },
};

export const HTTPNode = {
  meta: {
    label: 'HTTP',
    description: 'HTTP request',
    inputs: {
      type: 'object',
      properties: {
        apiKey: { type: 'string' },
        api: { type: 'object' },
        headers: { type: 'object' },
        params: { type: 'object' },
        body: { type: 'object' },
        timeout: { type: 'number', default: 10 },
      },
    },
  },
  form: formMeta,
  render: (props) => <FormRender {...props} />,
};
