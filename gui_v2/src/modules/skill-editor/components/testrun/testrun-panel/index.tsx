/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { FC, useContext, useEffect, useState, useCallback } from 'react';

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
import { useRunningNodeStore } from '../../../stores/running-node-store';

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
  const setRunningNodeId = useRunningNodeStore((state) => state.setRunningNodeId);

  const [isRunning, setRunning] = useState(false);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [errors, setErrors] = useState<string[] | undefined>();
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

  const onTestRun = useCallback(() => {
    if (isRunning) {
      // TODO: Implement backend cancel
      setRunning(false);
      setRunningNodeId(null); // Clear indicator on cancel
      return;
    }

    // 1. Set the initial state
    setResult(undefined);
    setErrors(undefined);
    setRunning(true);
    const startNode = document.toJSON().nodes.find((node: any) => node.id === 'start');
    if (startNode) {
      setRunningNodeId(startNode.id);
    }

    // 2. Use setTimeout to allow the UI to update before proceeding
    setTimeout(async () => {
      if (!username || !skillInfo) {
        Notification.error({ title: 'Cannot run test', content: 'User or skill info is missing.' });
        setRunning(false);
        setRunningNodeId(null);
        return;
      }

      const diagram = document.toJSON();

      // Create a deep copy to avoid mutating the original diagram state
      const diagramWithBreakpoints = JSON.parse(JSON.stringify(diagram));

      // Inject breakpoint info
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
        testInputs: values,
      };

      // Send the skill payload to the backend
      const response = await ipcApi.runSkill(username, skillPayload);

      if (!response.success) {
        setRunning(false);
        setRunningNodeId(null);
        Notification.error({
          title: 'Backend Run Failed',
          content: response.error?.message || 'An unknown error occurred.',
        });
        setErrors([response.error?.message || 'An unknown error occurred.']);
      }
    }, 0);
  }, [document, isRunning, username, skillInfo, breakpoints, setRunningNodeId, values]);

  const onClose = async () => {
    if (isRunning) {
      // TODO: Implement backend cancel
      setRunning(false);
      setRunningNodeId(null); // Clear indicator on close
    }
    setValues({});
    onCancel();
  };

  // runtime effect - Only close the node editor sidebar when TestRun panel is visible
  useEffect(() => {
    if (visible && sidebarNodeId) {
      setNodeId(undefined);
    }
  }, [visible, sidebarNodeId]);

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
          {renderForm}
        </div>
        <div className={styles['testrun-panel-footer']}>{renderButton}</div>
      </div>
    </SideSheet>
  );
};
