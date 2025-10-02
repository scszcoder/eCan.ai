/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import {
  IReport,
  NodeReport,
  WorkflowInputs,
  WorkflowOutputs,
  WorkflowStatus,
} from '@flowgram.ai/runtime-interface';
import {
  injectable,
  inject,
  WorkflowDocument,
  Playground,
  WorkflowLineEntity,
  WorkflowNodeEntity,
  WorkflowNodeLinesData,
  Emitter,
  getNodeForm,
} from '@flowgram.ai/free-layout-editor';

import { WorkflowRuntimeClient } from '../client';
import { WorkflowNodeType } from '../../../nodes';
import { isValidationDisabled } from '../../../services/validation-config';
import { useSheetsStore } from '../../../stores/sheets-store';

const SYNC_TASK_REPORT_INTERVAL = 500;

interface NodeRunningStatus {
  nodeID: string;
  status: WorkflowStatus;
  nodeResultLength: number;
}

@injectable()
export class WorkflowRuntimeService {
  @inject(Playground) playground: Playground;

  @inject(WorkflowDocument) document: WorkflowDocument;

  @inject(WorkflowRuntimeClient) runtimeClient: WorkflowRuntimeClient;

  private runningNodes: WorkflowNodeEntity[] = [];

  private taskID?: string;

  private syncTaskReportIntervalID?: ReturnType<typeof setInterval>;

  private reportEmitter = new Emitter<NodeReport>();

  private resetEmitter = new Emitter<{}>();

  private resultEmitter = new Emitter<{
    errors?: string[];
    result?: {
      inputs: WorkflowInputs;
      outputs: WorkflowOutputs;
    };
  }>();

  private nodeRunningStatus: Map<string, NodeRunningStatus>;

  public onNodeReportChange = this.reportEmitter.event;

  public onReset = this.resetEmitter.event;

  public onResultChanged = this.resultEmitter.event;

  public isFlowingLine(line: WorkflowLineEntity) {
    return this.runningNodes.some((node) =>
      node.getData(WorkflowNodeLinesData).inputLines.includes(line)
    );
  }

  public async taskRun(inputs: WorkflowInputs): Promise<string | undefined> {
    if (this.taskID) {
      await this.taskCancel();
    }
    if (!isValidationDisabled()) {
      const isFormValid = await this.validateForm();
      if (!isFormValid) {
        this.resultEmitter.fire({
          errors: ['Form validation failed'],
        });
        return;
      }
    }
    const schema = this.document.toJSON();
    // Compose bundle.sheets from sheets-store to include all sheets for backend
    const allSheets = useSheetsStore.getState().getAllSheets();
    const mainSheet = allSheets.sheets.find((s) => s.id === allSheets.mainSheetId) || allSheets.sheets[0];
    const bundle = {
      sheets: allSheets.sheets.map((s) => ({ name: s.name || s.id, document: s.document || {} })),
    } as any;
    const composedSchema = {
      ...(schema || {}),
      workFlow: (mainSheet && mainSheet.document) ? mainSheet.document : (schema as any)?.workFlow,
      bundle,
    };
    if (!isValidationDisabled()) {
      const validateResult = await this.runtimeClient.TaskValidate({
        schema: JSON.stringify(composedSchema),
        inputs,
      });
      if (!validateResult?.valid) {
        this.resultEmitter.fire({
          errors: validateResult?.errors ?? ['Internal Server Error'],
        });
        return;
      }
    }
    this.reset();
    let taskID: string | undefined;
    try {
      const output = await this.runtimeClient.TaskRun({
        schema: JSON.stringify(composedSchema),
        inputs,
      });
      taskID = output?.taskID;
    } catch (e) {
      this.resultEmitter.fire({
        errors: [(e as Error)?.message],
      });
      return;
    }
    if (!taskID) {
      this.resultEmitter.fire({
        errors: ['Task run failed'],
      });
      return;
    }
    this.taskID = taskID;
    this.syncTaskReportIntervalID = setInterval(() => {
      this.syncTaskReport();
    }, SYNC_TASK_REPORT_INTERVAL);
    return this.taskID;
  }

  public async taskCancel(): Promise<void> {
    if (!this.taskID) {
      return;
    }
    await this.runtimeClient.TaskCancel({
      taskID: this.taskID,
    });
  }

  private async validateForm(): Promise<boolean> {
    if (isValidationDisabled()) return true;
    const allForms = this.document.getAllNodes().map((node) => getNodeForm(node));
    const formValidations = await Promise.all(allForms.map(async (form) => form?.validate()));
    const validations = formValidations.filter((validation) => validation !== undefined);
    const isValid = validations.every((validation) => validation);
    return isValid;
  }

  private reset(): void {
    this.taskID = undefined;
    this.nodeRunningStatus = new Map();
    this.runningNodes = [];
    if (this.syncTaskReportIntervalID) {
      clearInterval(this.syncTaskReportIntervalID);
    }
    this.resetEmitter.fire({});
  }

  private async syncTaskReport(): Promise<void> {
    if (!this.taskID) {
      return;
    }
    const report = await this.runtimeClient.TaskReport({
      taskID: this.taskID,
    });
    if (!report) {
      clearInterval(this.syncTaskReportIntervalID);
      console.error('Sync task report failed');
      return;
    }
    const { workflowStatus, inputs, outputs, messages } = report;
    if (workflowStatus.terminated) {
      clearInterval(this.syncTaskReportIntervalID);
      if (Object.keys(outputs).length > 0) {
        this.resultEmitter.fire({ result: { inputs, outputs } });
      } else {
        this.resultEmitter.fire({
          errors: messages?.error?.map((message) =>
            message.nodeID ? `${message.nodeID}: ${message.message}` : message.message
          ),
        });
      }
    }
    this.updateReport(report);
  }

  private updateReport(report: IReport): void {
    const { reports } = report;
    this.runningNodes = [];
    this.document
      .getAllNodes()
      .filter(
        (node) =>
          ![WorkflowNodeType.BlockStart, WorkflowNodeType.BlockEnd].includes(
            node.flowNodeType as WorkflowNodeType
          )
      )
      .forEach((node) => {
        const nodeID = node.id;
        const nodeReport = reports[nodeID];
        if (!nodeReport) {
          return;
        }
        if (nodeReport.status === WorkflowStatus.Processing) {
          this.runningNodes.push(node);
        }
        const runningStatus = this.nodeRunningStatus.get(nodeID);
        if (
          !runningStatus ||
          nodeReport.status !== runningStatus.status ||
          nodeReport.snapshots.length !== runningStatus.nodeResultLength
        ) {
          this.nodeRunningStatus.set(nodeID, {
            nodeID,
            status: nodeReport.status,
            nodeResultLength: nodeReport.snapshots.length,
          });
          this.reportEmitter.fire(nodeReport);
          this.document.linesManager.forceUpdate();
        } else if (nodeReport.status === WorkflowStatus.Processing) {
          this.reportEmitter.fire(nodeReport);
        }
      });
  }

  /**
   * Cleanup method for logout or component unmount
   */
  public cleanup(): void {
    // Cancel any running task
    if (this.taskID) {
      this.taskCancel().catch(console.error);
    }
    
    // Clear interval
    if (this.syncTaskReportIntervalID) {
      clearInterval(this.syncTaskReportIntervalID);
      this.syncTaskReportIntervalID = undefined;
    }
    
    // Reset state
    this.reset();
    
    // Dispose emitters
    this.reportEmitter.dispose();
    this.resetEmitter.dispose();
    this.resultEmitter.dispose();
  }
}
