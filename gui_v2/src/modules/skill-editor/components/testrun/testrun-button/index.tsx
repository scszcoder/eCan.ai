/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { useState, useEffect, useCallback } from 'react';

import { useClientContext, getNodeForm, FlowNodeEntity } from '@flowgram.ai/free-layout-editor';
import { Button, Badge, Notification } from '@douyinfe/semi-ui';
import { IconPlay } from '@douyinfe/semi-icons';

// Removed TestRunSidePanel popup; we trigger the run directly
import { isValidationDisabled } from '../../../services/validation-config';
import { IPCAPI } from '../../../../../services/ipc/api';
import { useUserStore } from '../../../../../stores/userStore';
import { useSkillInfoStore } from '../../../stores/skill-info-store';
import { useSheetsStore } from '../../../stores/sheets-store';
import { useRunningNodeStore } from '../../../stores/running-node-store';
import { useRuntimeStateStore } from '../../../stores/runtime-state-store';

import styles from './index.module.less';

export function TestRunButton(props: { disabled: boolean }) {
  const [errorCount, setErrorCount] = useState(0);
  const clientContext = useClientContext();
  const ipcApi = IPCAPI.getInstance();
  const username = useUserStore((state) => state.username);
  const skillInfo = useSkillInfoStore((state) => state.skillInfo);
  const breakpoints = useSkillInfoStore((state) => state.breakpoints);
  const setRunningNodeId = useRunningNodeStore((state) => state.setRunningNodeId);

  const updateValidateData = useCallback(() => {
    if (isValidationDisabled()) {
      setErrorCount(0);
      return;
    }
    const allForms = clientContext.document.getAllNodes().map((node) => getNodeForm(node));
    const count = allForms.filter((form) => form?.state.invalid).length;
    setErrorCount(count);
  }, [clientContext]);

  /**
   * Validate all node and Save
   */
  const onTestRun = useCallback(async () => {
    const allNodes = clientContext.document.getAllNodes();
    const allForms = allNodes.map((node) => getNodeForm(node));
    if (!isValidationDisabled()) {
      await Promise.all(allForms.map(async (form) => form?.validate()));

      const errorMessages: string[] = [];
      allNodes.forEach((node) => {
        const form = getNodeForm(node);
        if (form?.state.invalid) {
          const nodeTitle = node.data?.title || node.id;
          const invalidFields = Object.keys(form.state.errors);
          errorMessages.push(`Node '${nodeTitle}': Invalid fields - ${invalidFields.join(', ')}`);
        }
      });

      if (errorMessages.length > 0) {
        Notification.error({
          title: 'Validation Failed',
          content: (
            <ul style={{ listStyle: 'none', padding: 0 }}>
              {errorMessages.map((msg, i) => <li key={i}>{msg}</li>)}
            </ul>
          ),
          duration: 5,
        });
        return;
      }
    }
    // Mirror original popup start behavior: set indicator, compose diagram+bundle+breakpoints, call IPC
    try {
      if (!username || !skillInfo) {
        Notification.error({ title: 'Cannot run test', content: 'User or skill info is missing.' });
        return;
      }

      // Set running indicator to Start node if present
      try {
        const startNode = clientContext.document.toJSON().nodes.find((n: any) => n.id === 'start');
        if (startNode) setRunningNodeId(startNode.id);
      } catch {}

      // Clear all per-node runtime states so badges reset at the start of a new run
      try { useRuntimeStateStore.getState().clearAll(); } catch {}

      // Deep copy diagram (base)
      const diagram = clientContext.document.toJSON();
      const diagramCopy: any = JSON.parse(JSON.stringify(diagram || {}));

      // Compose bundle and ensure workFlow points to main sheet document if present
      const allSheets = useSheetsStore.getState().getAllSheets();
      const mainSheet = allSheets.sheets.find((s) => s.id === allSheets.mainSheetId) || allSheets.sheets[0];
      const composedDiagram: any = {
        ...(diagramCopy || {}),
        ...(mainSheet && (mainSheet as any).document ? { workFlow: (mainSheet as any).document } : {}),
        bundle: {
          sheets: allSheets.sheets.map((s) => ({ name: s.name || s.id, document: (s as any).document || {} })),
        },
      } as any;

      // Inject breakpoint info into the actual workFlow used for backend
      try {
        const wf = composedDiagram?.workFlow;
        if (wf && Array.isArray(wf.nodes)) {
          wf.nodes.forEach((node: any) => {
            if (breakpoints.includes(node.id)) {
              node.data = node.data || {};
              node.data.break_point = true;
            } else if (node?.data?.break_point) {
              // ensure no stale flags
              delete node.data.break_point;
            }
          });
        }
      } catch {}

      const skillPayload = {
        ...skillInfo,
        diagram: composedDiagram,
        testInputs: {},
      } as any;

      const response = await ipcApi.runSkill(username, skillPayload);
      if (!response?.success) {
        Notification.error({
          title: 'Backend Run Failed',
          content: response?.error?.message || 'An unknown error occurred.',
        });
      }
      // Proactively request current state to kick UI updates if backend is slow to push
      try {
        await ipcApi.requestSkillState(username, { id: (skillInfo as any)?.skillId, name: (skillInfo as any)?.skillName });
      } catch {}
    } catch (e: any) {
      Notification.error({ title: 'Run Error', content: e?.message || String(e) });
    }
  }, [clientContext, username, skillInfo, setRunningNodeId, breakpoints]);

  /**
   * Listen single node validate
   */
  useEffect(() => {
    const listenSingleNodeValidate = (node: FlowNodeEntity) => {
      const form = getNodeForm(node);
      if (form) {
        const formValidateDispose = form.onValidate(() => updateValidateData());
        node.onDispose(() => formValidateDispose.dispose());
      }
    };
    clientContext.document.getAllNodes().map((node) => listenSingleNodeValidate(node));
    const dispose = clientContext.document.onNodeCreate(({ node }) =>
      listenSingleNodeValidate(node)
    );
    return () => dispose.dispose();
  }, [clientContext]);

  const button =
    errorCount === 0 ? (
      <Button
        disabled={props.disabled}
        onClick={onTestRun}
        icon={<IconPlay size="small" />}
        className={styles.testrunSuccessButton}
      >
      </Button>
    ) : (
      <Badge count={errorCount} position="rightTop" type="danger">
        <Button
          type="danger"
          disabled={props.disabled}
          onClick={onTestRun}
          icon={<IconPlay size="small" />}
          className={styles.testrunErrorButton}
        >
        </Button>
      </Badge>
    );

  return (
    <>
      {button}
    </>
  );
}
