/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { FlowNodeJSON } from '@flowgram.ai/free-layout-editor';
import { IJsonSchema } from '@flowgram.ai/form-materials';
import { IFlowConstantRefValue } from '@flowgram.ai/runtime-interface';

export interface RAGNodeJSON extends FlowNodeJSON {
  data: {
    title: string;
    outputs: IJsonSchema<'object'>;
    inputs: IJsonSchema<'object'>;
    inputsValues: Record<string, IFlowConstantRefValue> & {
      knowledgeBase?: IFlowConstantRefValue;
      retrievalMode?: IFlowConstantRefValue;
      topK?: IFlowConstantRefValue;
      scoreThreshold?: IFlowConstantRefValue;
      embeddingModel?: IFlowConstantRefValue;
      query?: IFlowConstantRefValue;
      filters?: IFlowConstantRefValue;
    };
  };
}


