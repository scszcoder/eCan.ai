/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import styled from 'styled-components';
import { IconInfoCircle, IconCode } from '@douyinfe/semi-icons';
import runningGif from '/src/assets/gifs/running0.gif';

export const RunningIcon = styled.div`
  display: none; // Hidden by default
  position: absolute;
  top: 4px;
  left: 50%;
  transform: translateX(-50%);
  width: 32px;
  height: 32px;
  background-image: url(${runningGif});
  background-size: contain;
  z-index: 10;
`;

export const NodeWrapperStyle = styled.div`
  position: relative;
  width: 200px;
  border-radius: 4px;
  background-color: var(--flow-node-bg-color);
  border: 1px solid var(--flow-node-border-color);
  box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);

  &.is-running {
    ${RunningIcon} {
      display: block;
    }
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

export const BreakpointIcon = styled.div`
  position: absolute;
  color: 'darkgreen',
  left: -8,
  top: -8,
  zIndex: 1,
  background: 'white',
  borderRadius: '50%',
  padding: '2px',
`;
