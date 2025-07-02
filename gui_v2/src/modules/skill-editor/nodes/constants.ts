/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

export enum WorkflowNodeType {
  Start = 'start',
  End = 'end',
  LLM = 'llm',
  Http = 'http',
  Condition = 'condition',
  Loop = 'loop',
  Comment = 'comment',
  Basic = 'basic',
  RAG = 'rag',
}
