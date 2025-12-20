/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

/* eslint-disable no-console */
import { FlowGramAPIName, IRuntimeClient } from '@flowgram.ai/runtime-interface';
import { injectable } from '@flowgram.ai/free-layout-editor';

@injectable()
export class WorkflowRuntimeBrowserClient implements IRuntimeClient {
  constructor() {}

  public [FlowGramAPIName.TaskRun]: IRuntimeClient[FlowGramAPIName.TaskRun] = async (input) => {
    const { TaskRunAPI } = await import('@flowgram.ai/runtime-js'); // Load on demand - 按需Load
    return TaskRunAPI(input);
  };

  public [FlowGramAPIName.TaskReport]: IRuntimeClient[FlowGramAPIName.TaskReport] = async (
    input
  ) => {
    const { TaskReportAPI } = await import('@flowgram.ai/runtime-js'); // Load on demand - 按需Load
    return TaskReportAPI(input);
  };

  public [FlowGramAPIName.TaskResult]: IRuntimeClient[FlowGramAPIName.TaskResult] = async (
    input
  ) => {
    const { TaskResultAPI } = await import('@flowgram.ai/runtime-js'); // Load on demand - 按需Load
    return TaskResultAPI(input);
  };

  public [FlowGramAPIName.TaskCancel]: IRuntimeClient[FlowGramAPIName.TaskCancel] = async (
    input
  ) => {
    const { TaskCancelAPI } = await import('@flowgram.ai/runtime-js'); // Load on demand - 按需Load
    return TaskCancelAPI(input);
  };

  public [FlowGramAPIName.TaskValidate]: IRuntimeClient[FlowGramAPIName.TaskValidate] = async (
    input
  ) => {
    const { TaskValidateAPI } = await import('@flowgram.ai/runtime-js'); // Load on demand - 按需Load
    return TaskValidateAPI(input);
  };
}
