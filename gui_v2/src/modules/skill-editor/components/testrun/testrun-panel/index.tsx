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
import { useSheetsStore } from '../../../stores/sheets-store';
import { useSkillInfoStore } from '../../../stores/skill-info-store';
import { useRunningNodeStore } from '../../../stores/running-node-store';
import { useRuntimeStateStore } from '../../../stores/runtime-state-store';

import styles from './index.module.less';

interface TestRunSidePanelProps {
  visible: boolean;
  onCancel: () => void;
}

export const TestRunSidePanel: FC<TestRunSidePanelProps> = ({ visible, onCancel }) => {
  let runtimeService: WorkflowRuntimeService | null = null;
  try {
    runtimeService = useService(WorkflowRuntimeService);
  } catch {
    // WorkflowRuntimeService not available
  }
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
      try { useRuntimeStateStore.getState().clearAll(); } catch {}
      return;
    }

    // 1. Set the initial state
    setResult(undefined);
    setErrors(undefined);
    setRunning(true);
    // Clear all runtime states so badges from previous runs are removed
    try { useRuntimeStateStore.getState().clearAll(); } catch {}
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

      // Compose bundle.sheets from sheets-store so backend receives all sheets
      const allSheets = useSheetsStore.getState().getAllSheets();
      const mainSheet = allSheets.sheets.find((s) => s.id === allSheets.mainSheetId) || allSheets.sheets[0];
      const composedDiagram = {
        ...(diagramWithBreakpoints || {}),
        // Ensure workFlow points to main sheet document if available
        ...(mainSheet && mainSheet.document ? { workFlow: mainSheet.document } : {}),
        bundle: {
          sheets: allSheets.sheets.map((s) => ({ name: s.name || s.id, document: s.document || {} })),
        },
      } as any;

      const skillPayload = {
        ...skillInfo,
        diagram: composedDiagram,
        testInputs: values,
      };

      // Debug logs to verify bundle presence on FE side
      try {
        const sheetNames = (allSheets.sheets || []).map((s) => `${s.id}:${s.name}`);
        // eslint-disable-next-line no-console
        console.debug('[RunSkill][FE] sheets in store:', sheetNames);
        // eslint-disable-next-line no-console
        console.debug('[RunSkill][FE] composedDiagram.workFlow nodes:', (composedDiagram?.workFlow?.nodes || []).length, 'edges:', (composedDiagram?.workFlow?.edges || []).length);
        // eslint-disable-next-line no-console
        console.debug('[RunSkill][FE] composedDiagram.bundle.sheet_count:', (composedDiagram?.bundle?.sheets || []).length);
      } catch {}

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
      try { useRuntimeStateStore.getState().clearAll(); } catch {}
    }
    setValues({});
    onCancel();
  };

  // Removed auto-closing of node editor to allow editing during Test Run

  // Removed input form UI per request: only keep a minimal Start/Cancel button

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

  // Minimal floating popup (button only) so it doesn't block the canvas
  if (!visible) return null;

  return (
    <div
      style={{
        position: 'fixed',
        right: 16,
        bottom: 16,
        zIndex: 1000,
        background: 'var(--semi-color-bg-1)',
        border: '1px solid var(--semi-color-border)',
        borderRadius: 8,
        boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
        padding: 8,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      {renderButton}
    </div>
  );
};
