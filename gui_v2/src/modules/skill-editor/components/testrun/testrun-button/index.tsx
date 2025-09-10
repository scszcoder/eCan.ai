/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { useState, useEffect, useCallback } from 'react';

import { useClientContext, getNodeForm, FlowNodeEntity } from '@flowgram.ai/free-layout-editor';
import { Button, Badge, Notification } from '@douyinfe/semi-ui';
import { IconPlay } from '@douyinfe/semi-icons';

import { TestRunSidePanel } from '../testrun-panel';

import styles from './index.module.less';

export function TestRunButton(props: { disabled: boolean }) {
  const [errorCount, setErrorCount] = useState(0);
  const clientContext = useClientContext();
  const [visible, setVisible] = useState(false);

  const updateValidateData = useCallback(() => {
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

    console.log('>>>>> save data: ', clientContext.document.toJSON());
    setVisible(true);
  }, [clientContext]);

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
      <TestRunSidePanel visible={visible} onCancel={() => setVisible(false)} />
    </>
  );
}
