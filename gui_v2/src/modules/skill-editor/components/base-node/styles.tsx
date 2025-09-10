/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import styled from 'styled-components';
import { IconInfoCircle, IconCode } from '@douyinfe/semi-icons';

export const NodeWrapperStyle = styled.div`
  position: relative; // This is the key fix for positioning the absolute indicator
  align-items: flex-start;
  background-color: #fff;
  border: 1px solid rgba(6, 7, 9, 0.15);
  border-radius: 8px;
  box-shadow: 0 2px 6px 0 rgba(0, 0, 0, 0.04), 0 4px 12px 0 rgba(0, 0, 0, 0.02);
  display: flex;
  flex-direction: column;
  justify-content: center;
  width: 360px;
  height: auto;

  &.selected {
    border: 1px solid #4e40e5;
  }
`;

export const ErrorIcon = () => (
  <IconInfoCircle
    style={{
      position: 'absolute',
      color: 'red',
      left: -6,
      top: -6,
      zIndex: 1,
      background: 'white',
      borderRadius: 8,
    }}
  />
);

export const BreakpointIcon = () => (
  <IconCode
    style={{
      position: 'absolute',
      color: 'darkgreen',
      left: -8,
      top: -8,
      zIndex: 1,
      background: 'white',
      borderRadius: '50%',
      padding: '2px',
    }}
  />
);
