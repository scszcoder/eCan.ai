/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { FC, useContext, useEffect, useState } from 'react';

import classnames from 'classnames';
import { WorkflowInputs, WorkflowOutputs } from '@flowgram.ai/runtime-interface';
import { useClientContext, useService } from '@flowgram.ai/free-layout-editor';
import { Button, SideSheet, Switch, Notification } from '@douyinfe/semi-ui';
import { IconClose, IconPlay, IconSpin } from '@douyinfe/semi-icons';

import { TestRunJsonInput } from '../testrun-json-input';
import { TestRunForm } from '../testrun-form';
import { NodeStatusGroup } from '../node-status-bar/group';
import { WorkflowRuntimeService } from '../../../plugins/runtime-plugin/runtime-service';
import { SidebarContext } from '../../../context';
import { IconCancel } from '../../../assets/icon-cancel';
import { IPCAPI } from '../../../../../services/ipc/api';
import { useUserStore } from '../../../../../stores/userStore';
import { useSkillInfoStore } from '../../../stores/skill-info-store';

import styles from './index.module.less';

interface TestRunSidePanelProps {
  visible: boolean;
  onCancel: () => void;
}

export const TestRunSidePanel: FC<TestRunSidePanelProps> = ({ visible, onCancel }) => {
  const runtimeService = useService(WorkflowRuntimeService);
  const { document } = useClientContext();
  const { nodeId: sidebarNodeId, setNodeId } = useContext(SidebarContext);
  const ipcApi = IPCAPI.getInstance();
  const username = useUserStore((state) => state.username);
  const skillInfo = useSkillInfoStore((state) => state.skillInfo);
  const breakpoints = useSkillInfoStore((state) => state.breakpoints);

  const [isRunning, setRunning] = useState(false);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [errors, setErrors] = useState<string[]>();
  const [result, setResult] = useState<
    | {
        inputs: WorkflowInputs;
        outputs: WorkflowOutputs;
      }
    | undefined
  >();

  // en - Use localStorage to persist the JSON mode state
  const [inputJSONMode, _setInputJSONMode] = useState(() => {
    const savedMode = localStorage.getItem('testrun-input-json-mode');
    return savedMode ? JSON.parse(savedMode) : false;
  });

  const setInputJSONMode = (checked: boolean) => {
    _setInputJSONMode(checked);
    localStorage.setItem('testrun-input-json-mode', JSON.stringify(checked));
  };

  const onTestRun = async () => {
    if (isRunning) {
      // TODO: Implement backend cancel
      setRunning(false);
      return;
    }
    setResult(undefined);
    setErrors(undefined);

    if (!username || !skillInfo) {
      Notification.error({ title: 'Cannot run test', content: 'User or skill info is missing.' });
      return;
    }

    const diagram = document.toJSON();

    // Create a deep copy to avoid mutating the original diagram state
    const diagramWithBreakpoints = JSON.parse(JSON.stringify(diagram));

    // Inject breakpoint information
    diagramWithBreakpoints.nodes.forEach((node: any) => {
      if (breakpoints.includes(node.id)) {
        if (!node.data) {
          node.data = {};
        }
        node.data.break_point = true;
      }
    });

    const skillPayload = {
      ...skillInfo,
      diagram: diagramWithBreakpoints,
      testInputs: values, // Pass form values to the backend
    };

    setRunning(true);
    console.log('Sending skill to backend for execution:', skillPayload);
    const response = await ipcApi.runSkill(username, skillPayload);
    setRunning(false);

    if (response.success) {
      console.log('Backend execution successful:', response.data);
      Notification.success({ title: 'Backend Run Successful' });
      // TODO: Display results from backend
    } else {
      console.error('Backend execution failed:', response.error);
      Notification.error({
        title: 'Backend Run Failed',
        content: response.error?.message || 'An unknown error occurred.',
      });
      setErrors([response.error?.message || 'An unknown error occurred.']);
    }
  };

  const onClose = async () => {
    if (isRunning) {
      // TODO: Implement backend cancel
      setRunning(false);
    }
    setValues({});
    onCancel();
  };

  // runtime effect - This can be removed or replaced with a listener for backend events
  useEffect(() => {
    setNodeId(undefined);
    const disposer = runtimeService.onResultChanged(({ result, errors }) => {
      // This logic is now handled by the IPC call
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
      <div className={styles.text}>Running on Backend...</div>
    </div>
  );

  const renderForm = (
    <div className={styles['testrun-panel-form']}>
      <div className={styles['testrun-panel-input']}>
        <div className={styles.title}>Input Form</div>
        <div>JSON Mode</div>
        <Switch
          checked={inputJSONMode}
          onChange={(checked: boolean) => setInputJSONMode(checked)}
          size="small"
        />
      </div>
      {inputJSONMode ? (
        <TestRunJsonInput values={values} setValues={setValues} />
      ) : (
        <TestRunForm values={values} setValues={setValues} />
      )}
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
      icon={isRunning ? <IconCancel /> : <IconPlay size="small" />}
      className={classnames(styles.button, {
        [styles.running]: isRunning,
        [styles.default]: !isRunning,
      })}
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
      width={400}
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
