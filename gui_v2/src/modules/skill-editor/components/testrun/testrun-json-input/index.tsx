/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { FC } from 'react';

import { SafeCodeEditor } from '../../SafeCodeEditor';

import { useFormMeta, useSyncDefault } from '../hooks';

import styles from './index.module.less';

interface TestRunJsonInputProps {
  values: Record<string, unknown>;
  setValues: (values: Record<string, unknown>) => void;
}

export const TestRunJsonInput: FC<TestRunJsonInputProps> = ({ values, setValues }) => {
  const formMeta = useFormMeta();

  useSyncDefault({
    formMeta,
    values,
    setValues,
  });

  return (
    <div className={styles['testrun-json-input']}>
      <SafeCodeEditor
        languageId="json"
        value={JSON.stringify(values, null, 2)}
        onChange={(value) => {
          // Avoid echo updates
          const current = JSON.stringify(values, null, 2);
          if (value === current) return;
          // Parse and defer to avoid re-entrant editor updates
          try {
            const next = JSON.parse(value);
            Promise.resolve().then(() => setValues(next));
          } catch (e) {
            // Ignore until user finishes typing valid JSON
          }
        }}
      />
    </div>
  );
};
