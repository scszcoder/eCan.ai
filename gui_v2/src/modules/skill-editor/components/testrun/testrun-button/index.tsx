/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { useClientContext, getNodeForm, FlowNodeEntity } from '@flowgram.ai/free-layout-editor';
import { Button, Badge, Notification } from '@douyinfe/semi-ui';
import { IconPlay } from '@douyinfe/semi-icons';

// Removed TestRunSidePanel popup; we trigger the run directly
import { isValidationDisabled } from '../../../services/validation-config';
import { IPCAPI } from '../../../../../services/ipc/api';
import { isWebPlatform } from '../../../../../config/platform';
import { webAuthSession } from '../../../../../services/auth/webAuthSession';
import { useUserStore } from '../../../../../stores/userStore';
import { useSkillInfoStore } from '../../../stores/skill-info-store';
import { useSheetsStore } from '../../../stores/sheets-store';
import { useRunningNodeStore } from '../../../stores/running-node-store';
import { useRuntimeStateStore } from '../../../stores/runtime-state-store';
import { registerDevTaskCleanup } from '../../../services/devTaskCleanup';

import styles from './index.module.less';

export function TestRunButton(props: { disabled: boolean }) {
  const { t } = useTranslation('skillEditor');
  const [errorCount, setErrorCount] = useState(0);
  const [isLaunching, setIsLaunching] = useState(false);
  const clientContext = useClientContext();
  const ipcApi = IPCAPI.getInstance();
  const username = useUserStore((state) => state.username);
  const skillInfo = useSkillInfoStore((state) => state.skillInfo);
  const breakpoints = useSkillInfoStore((state) => state.breakpoints);
  const runInCloud = useSkillInfoStore((state) => state.runInCloud);
  const hybridCloudMode = useSkillInfoStore((state) => state.hybridCloudMode);
  const localHelperSkillId = useSkillInfoStore((state) => state.localHelperSkillId);
  const localHelperMachine = useSkillInfoStore((state) => state.localHelperMachine);
  const setRunningNodeId = useRunningNodeStore((state) => state.setRunningNodeId);

  // Ensure dev-task logout cleanup is registered (idempotent, runs once)
  useEffect(() => { registerDevTaskCleanup(); }, []);

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
    if (isLaunching) return;
    setIsLaunching(true);
    const allNodes = clientContext.document.getAllNodes();
    const allForms = allNodes.map((node) => getNodeForm(node));
    try {
      if (!isValidationDisabled()) {
        await Promise.all(allForms.map(async (form) => form?.validate()));

      const errorMessages: string[] = [];
      allNodes.forEach((node) => {
        const form = getNodeForm(node);
        if (form?.state.invalid) {
          const nodeTitle = node.data?.title || node.id;
          const invalidFields = Object.keys(form.state.errors);
          errorMessages.push(`${t('testrun.validationFailed')}: '${nodeTitle}' - ${invalidFields.join(', ')}`);
        }
      });

        if (errorMessages.length > 0) {
          Notification.error({
            title: t('testrun.validationFailed'),
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
      if (!username || !skillInfo) {
        Notification.error({ title: t('testrun.cannotRun'), content: t('testrun.missingInfo') });
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

      // Build meta_data for cloud runs
      // dev_mode=true enables fixed client_id/run_id for skill editor testing
      // passive_client_id format: {username}_{machine_name} with fallback to SCHOME
      const machineName = localHelperMachine || 'SCHOME';
      const passiveClientId = `${username}_${machineName}`;
      const webJwt = isWebPlatform() ? webAuthSession.getAccessToken() : null;
      const metaData = runInCloud ? {
        dev_mode: true,  // Skill editor always runs in dev mode
        run_in_cloud: true,
        client_id: passiveClientId,
        passive_client_id: passiveClientId,
        run_id: '0123456789',
        hybrid_cloud_mode: hybridCloudMode,
        local_helper_skill_id: localHelperSkillId,
        local_helper_machine: machineName,
        ...(webJwt ? { jwt: webJwt } : {}),
      } : null;

      const response = await ipcApi.runSkill(username, skillPayload, metaData);
      if (!response?.success) {
        Notification.error({
          title: t('testrun.backendRunFailed'),
          content: response?.error?.message || t('testrun.unknownError'),
        });
      }
      // Capture the active run_id so the Stop button can reference it for cancel
      try {
        const returnedRunId = (response as any)?.data?.runId;
        const activeRunId = returnedRunId || (metaData as any)?.run_id || null;
        if (activeRunId) {
          useRunningNodeStore.getState().setActiveRunId(activeRunId);
        }
        // Track dev-mode Fargate tasks for cleanup on logout
        if (runInCloud && activeRunId) {
          const responseData = (response as any)?.data?.data;
          let ecsTaskArn: string | undefined;
          try {
            const parsed = typeof responseData === 'string' ? JSON.parse(responseData) : responseData;
            ecsTaskArn = parsed?.ecs_task_arn;
          } catch {}
          useRunningNodeStore.getState().addDevTask({
            runId: activeRunId,
            skillId: (skillInfo as any)?.skillId || (skillInfo as any)?.skill_id,
            ecsTaskArn,
            startedAt: Date.now(),
          });
        }
      } catch {}
      // Proactively request current state to kick UI updates if backend is slow to push
      try {
        await ipcApi.requestSkillState(username, { id: (skillInfo as any)?.skillId, name: (skillInfo as any)?.skillName });
      } catch {}
    } catch (e: any) {
      Notification.error({ title: t('testrun.runError'), content: e?.message || String(e) });
    } finally {
      setIsLaunching(false);
    }
  }, [clientContext, username, skillInfo, setRunningNodeId, breakpoints, runInCloud, hybridCloudMode, localHelperSkillId, localHelperMachine, isLaunching]);

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
        disabled={props.disabled || isLaunching}
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
