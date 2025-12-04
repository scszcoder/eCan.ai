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
  Variable = 'variable',
  Condition = 'condition',
  Loop = 'loop',
  BlockStart = 'block-start',
  BlockEnd = 'block-end',
  Comment = 'comment',
  Continue = 'continue',
  Break = 'break',
  MCP = 'mcp',
  Chat = 'chat_node',
  Task = 'task',
  ToolPicker = 'tool-picker',
  Dummy = 'dummy',
  PendInput = 'pend_input_node',
  PendEvent = 'pend_event_node',
  Event = 'event',
  BrowserAutomation = 'browser-automation',
  Group = 'group',
}
