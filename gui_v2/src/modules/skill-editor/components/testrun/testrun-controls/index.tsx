/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { Button, Tooltip } from '@douyinfe/semi-ui';
import React from 'react';
import styles from './index.module.less';

interface TestRunControlButtonProps {
  icon: React.ReactNode;
  onClick: () => void;
  tooltip: string;
  disabled?: boolean;
}

export const TestRunControlButton: React.FC<TestRunControlButtonProps> = ({
  icon,
  onClick,
  tooltip,
  disabled,
}) => {
  return (
    <Tooltip content={tooltip}>
      <Button
        disabled={disabled}
        onClick={onClick}
        icon={icon}
        className={styles.controlButton}
        type="tertiary"
        theme="borderless"
      />
    </Tooltip>
  );
};