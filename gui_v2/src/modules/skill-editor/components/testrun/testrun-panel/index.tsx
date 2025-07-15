/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { FC, useContext, useEffect, useState } from 'react';

import { WorkflowInputs, WorkflowOutputs } from '@flowgram.ai/runtime-interface';
import { useService } from '@flowgram.ai/free-layout-editor';
import { CodeEditor } from '@flowgram.ai/form-materials';
import { Button, SideSheet } from '@douyinfe/semi-ui';
import { IconClose, IconPlay, IconSpin, IconStop } from '@douyinfe/semi-icons';

import { NodeStatusGroup } from '../node-status-bar/group';
import { WorkflowRuntimeService } from '../../../plugins/runtime-plugin/runtime-service';
import { SidebarContext } from '../../../context';

import styles from './index.module.less';

interface TestRunSidePanelProps {
  visible: boolean;
  onCancel: () => void;
}

export const TestRunSidePanel: FC<TestRunSidePanelProps> = ({ visible, onCancel }) => {
  const runtimeService = useService(WorkflowRuntimeService);
  const { nodeId: sidebarNodeId, setNodeId } = useContext(SidebarContext);

  const [isRunning, setRunning] = useState(false);
  const [value, setValue] = useState<string>(`{}`);
  const [errors, setErrors] = useState<string[]>();
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
    setErrors(undefined);
    setRunning(true);
    try {
      await runtimeService.taskRun(value);
    } catch (e: any) {
      setErrors([e.message]);
    }
  };

  const onClose = async () => {
    await runtimeService.taskCancel();
    setValue(`{}`);
    setRunning(false);
    onCancel();
  };

  // runtime effect
  useEffect(() => {
    setNodeId(undefined);
    const disposer = runtimeService.onResultChanged(({ result, errors }) => {
      setRunning(false);
      setResult(result);
      if (errors) {
        setErrors(errors);
      } else {
        setErrors(undefined);
      }
    });
    return () => disposer.dispose();
  }, []);

  // sidebar effect
  useEffect(() => {
    if (sidebarNodeId) {
      onCancel();
    }
  }, [sidebarNodeId]);

  const renderRunning = (
    <div className={styles['testrun-panel-running']}>
      <IconSpin spin size="large" />
      <div className={styles.text}>Running...</div>
    </div>
  );

  const renderForm = (
    <div className={styles['testrun-panel-form']}>
      <div className={styles.title}>Input Form</div>
      <div className={styles['code-editor-container']}>
        <CodeEditor languageId="json" value={value} onChange={setValue} />
      </div>
      {errors?.map((e) => (
        <div className={styles.error} key={e}>
          {e}
        </div>
      ))}
      <NodeStatusGroup title="Inputs Result" data={result?.inputs} optional disableCollapse />
      <NodeStatusGroup title="Outputs Result" data={result?.outputs} optional disableCollapse />
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
      motion={false}
      onCancel={onClose}
      width={368}
      headerStyle={{
        display: 'none',
      }}
      bodyStyle={{
        padding: 0,
      }}
      style={{
        background: 'none',
        boxShadow: 'none',
      }}
    >
      <div className={styles['testrun-panel-container']}>
        <div className={styles['testrun-panel-header']}>
          <div className={styles['testrun-panel-title']}>Test Run</div>
          <Button
            className={styles['testrun-panel-title']}
            type="tertiary"
            icon={<IconClose />}
            size="small"
            theme="borderless"
            onClick={onClose}
          />
        </div>
        <div className={styles['testrun-panel-content']}>
          {isRunning ? renderRunning : renderForm}
        </div>
        <div className={styles['testrun-panel-footer']}>{renderButton}</div>
      </div>
    </SideSheet>
  );
};
