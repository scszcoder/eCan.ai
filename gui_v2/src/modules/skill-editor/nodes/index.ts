/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { FlowNodeRegistry } from '../typings';
import { VariableNodeRegistry } from './variable';
import { StartNodeRegistry } from './start';
import { LoopNodeRegistry } from './loop';
import { LLMNodeRegistry } from './llm';
import { HTTPNodeRegistry } from './http';
import { GroupNodeRegistry } from './group';
import { EndNodeRegistry } from './end';
import { ContinueNodeRegistry } from './continue';
import { ConditionNodeRegistry } from './condition';
import { CommentNodeRegistry } from './comment';
import { CodeNodeRegistry } from './code';
import { BreakNodeRegistry } from './break';
import { BlockStartNodeRegistry } from './block-start';
import { BlockEndNodeRegistry } from './block-end';
import { MCPNodeRegistry } from './mcp';
import { ChatNodeRegistry } from './chat';
import { TaskNodeRegistry } from './task';
import { ToolPickerNodeRegistry } from './tool-picker';
import { DummyNodeRegistry } from './dummy';
import { PendInputNodeRegistry } from './pend-input';
import { PendEventNodeRegistry } from './pend-event';
import { EventNodeRegistry } from './event';
import { BrowserAutomationNodeRegistry } from './browser-automation';
import { SheetCallNodeRegistry } from './sheet-call';
import { SheetInputsNodeRegistry } from './sheet-inputs';
import { SheetOutputsNodeRegistry } from './sheet-outputs';
export { WorkflowNodeType } from './constants';

export const nodeRegistries: FlowNodeRegistry[] = [
  ConditionNodeRegistry,
  StartNodeRegistry,
  EndNodeRegistry,
  LLMNodeRegistry,
  LoopNodeRegistry,
  CommentNodeRegistry,
  BlockStartNodeRegistry,
  BlockEndNodeRegistry,
  HTTPNodeRegistry,
  CodeNodeRegistry,
  ContinueNodeRegistry,
  BreakNodeRegistry,
  VariableNodeRegistry,
  GroupNodeRegistry,
  MCPNodeRegistry,
  ChatNodeRegistry,
  TaskNodeRegistry,
  ToolPickerNodeRegistry,
  DummyNodeRegistry,
  // Keep PendInput for backward compatibility; prefer PendEvent
  PendEventNodeRegistry,
  PendInputNodeRegistry,
  EventNodeRegistry,
  BrowserAutomationNodeRegistry,
  SheetCallNodeRegistry,
  SheetInputsNodeRegistry,
  SheetOutputsNodeRegistry,
];
