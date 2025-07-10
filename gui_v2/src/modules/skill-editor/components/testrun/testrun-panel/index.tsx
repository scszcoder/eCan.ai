/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { FC, useEffect, useState } from 'react';

import { WorkflowInputs, WorkflowOutputs } from '@flowgram.ai/runtime-interface';
import { useService } from '@flowgram.ai/free-layout-editor';
import { CodeEditor } from '@flowgram.ai/form-materials';
import { Button, SideSheet } from '@douyinfe/semi-ui';
import { IconPlay, IconSpin, IconStop } from '@douyinfe/semi-icons';

import { NodeStatusGroup } from '../node-status-bar/group';
import { WorkflowRuntimeService } from '../../../plugins/runtime-plugin/runtime-service';

import styles from './index.module.less';

interface TestRunSidePanelProps {
  visible: boolean;
  onCancel: () => void;
}

export const TestRunSidePanel: FC<TestRunSidePanelProps> = ({ visible, onCancel }) => {
  const runtimeService = useService(WorkflowRuntimeService);
  const [isRunning, setRunning] = useState(false);
  const [value, setValue] = useState<string>(`{}`);
  const [error, setError] = useState<string | undefined>();
  const [result, setResult] = useState<
    | {
        inputs: WorkflowInputs;
        outputs: WorkflowOutputs;
      }
    | undefined
  >();

  const onTestRun = async () => {
    if (isRunning) {
      await runtimeService.taskCancel();
      return;
    }
    setResult(undefined);
    setError(undefined);
    setRunning(true);
    try {
      await runtimeService.taskRun(value);
    } catch (e: any) {
      setError(e.message);
    }
  };

  const onClose = async () => {
    await runtimeService.taskCancel();
    setValue(`{}`);
    setRunning(false);
    onCancel();
  };

  useEffect(() => {
    const disposer = runtimeService.onTerminated(({ result }) => {
      setRunning(false);
      setResult(result);
    });
    return () => disposer.dispose();
  }, []);

  const renderRunning = (
    <div className={styles['testrun-panel-running']}>
      <IconSpin spin size="large" />
      <div className={styles.text}>Running...</div>
    </div>
  );

  const renderForm = (
    <div className={styles['testrun-panel-form']}>
      <div className={styles.title}>Input</div>
      <div className={styles['code-editor-container']}>
        <CodeEditor languageId="json" value={value} onChange={setValue} />
      </div>
      <div className={styles.error}>{error}</div>

      <NodeStatusGroup title="Inputs" data={result?.inputs} optional disableCollapse />
      <NodeStatusGroup title="Outputs" data={result?.outputs} optional disableCollapse />
    </div>
  );

  const renderButton = (
    <Button
      onClick={onTestRun}
      icon={isRunning ? <IconStop size="small" /> : <IconPlay size="small" />}
      className={`${styles.button} ${isRunning ? styles.running : styles.default}`}
    >
      {isRunning ? 'Cancel' : 'Test Run'}
    </Button>
  );

  return (
    <SideSheet
      title="Test Run"
      visible={visible}
      mask={false}
      onCancel={onClose}
      footer={renderButton}
    >
      {isRunning ? renderRunning : renderForm}
    </SideSheet>
  );
};
