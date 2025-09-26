/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

export enum WorkflowNodeType {
  Start = 'start',
  End = 'end',
  LLM = 'llm',
  HTTP = 'http',
  Code = 'code',
  HttpApi = 'http-api',
  Variable = 'variable',
  Condition = 'condition',
  Loop = 'loop',
  BlockStart = 'block-start',
  BlockEnd = 'block-end',
  Comment = 'comment',
  Continue = 'continue',
  Break = 'break',
  MCP = 'mcp',
  RAG = 'rag',
  Chat = 'chat_node',
  PendInput = 'pend_input_node',
  Event = 'event',
  BrowserAutomation = 'browser-automation',
}
