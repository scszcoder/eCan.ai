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
  /* Let node width come from node meta or content instead of fixed 200px */
  width: auto;
  min-width: 200px;
  border-radius: 4px;
  background-color: var(--flow-node-bg-color);
  border: 1px solid var(--flow-node-border-color);
  box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  overflow: visible; /* ensure absolutely-positioned children/ports can be visible */

  &.is-running {
    ${RunningIcon} {
      display: block;
    }
    /* Glowing animation for running emphasis */
    animation: runningGlow 1200ms ease-in-out infinite;
  }

  @keyframes runningGlow {
    0% { box-shadow: 0 0 0 2px rgba(255,77,79,0.20), 0 0 8px rgba(255,77,79,0.15); }
    50% { box-shadow: 0 0 0 3px rgba(255,77,79,0.35), 0 0 14px rgba(255,77,79,0.30); }
    100% { box-shadow: 0 0 0 2px rgba(255,77,79,0.20), 0 0 8px rgba(255,77,79,0.15); }
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
  top: 4px;
  left: 4px;
  width: 10px;
  height: 10px;
  background: #ff3b30; /* bright red */
  border-radius: 50%;
  box-shadow: 0 0 0 2px #ffffff; /* white ring for contrast */
  z-index: 11;
`;
