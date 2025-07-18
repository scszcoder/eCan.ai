/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import React, { useCallback } from 'react';

import { Typography, Tooltip } from '@douyinfe/semi-ui';

import { TypeTag } from '../type-tag';
import './index.css';

const { Text } = Typography;

interface FormItemProps {
  children: React.ReactNode;
  name: string;
  type?: string;
  required?: boolean;
  description?: string;
  labelWidth?: number;
  vertical?: boolean;
  style?: React.CSSProperties;
}
export function FormItem({
  children,
  name,
  required,
  description,
  type,
  labelWidth,
  vertical,
  style,
}: FormItemProps): JSX.Element {
  const renderTitle = useCallback(
    (showTooltip?: boolean) => (
      <div style={{ width: '0', display: 'flex', flex: '1' }}>
        <Text style={{ width: '100%' }} ellipsis={{ showTooltip: !!showTooltip }}>
          {name}
          {required && <span style={{ color: '#f93920', paddingLeft: '2px' }}>*</span>}
        </Text>
      </div>
    ),
    []
  );
  return (
    <div
      style={{
        fontSize: 12,
        marginBottom: 6,
        width: '100%',
        position: 'relative',
        display: 'flex',
        gap: 8,
        ...(vertical
          ? { flexDirection: 'column' }
          : {
              justifyContent: 'center',
              alignItems: 'center',
            }),
        ...style,
      }}
    >
      <div
        style={{
          justifyContent: 'center',
          alignItems: 'center',
          color: 'var(--semi-color-text-0)',
          width: labelWidth || 118,
          minWidth: labelWidth || 118,
          maxWidth: labelWidth || 118,
          position: 'relative',
          display: 'flex',
          columnGap: 4,
          flexShrink: 0,
        }}
      >
        {type && <TypeTag className="form-item-type-tag" type={type} />}
        {description ? <Tooltip content={description}>{renderTitle()}</Tooltip> : renderTitle(true)}
      </div>

      <div
        style={{
          flexGrow: 1,
          minWidth: 0,
        }}
      >
        {children}
      </div>
    </div>
  );
}
