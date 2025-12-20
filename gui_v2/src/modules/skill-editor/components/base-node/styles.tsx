/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import styled from 'styled-components';
import { IconInfoCircle, IconCode } from '@douyinfe/semi-icons';
// import runningGif from '/src/assets/gifs/running0.gif';
import runningGif from '/src/assets/gifs/red_running0.gif';
import pausedPng from '/src/assets/gifs/red_running0.png';

export const RunningIcon = styled.div`
  display: none; // Hidden by default
  position: absolute;
  top: 4px;
  left: 50%;
  transform: translateX(-50%);
  width: 64px;
  height: 48px;
  background-image: url(${runningGif});
  background-repeat: no-repeat;
  background-position: center center;
  background-size: contain;
  z-index: 1000;
  pointer-events: none;
`;

export const PausedIcon = styled.div`
  display: none; // Hidden by default
  position: absolute;
  top: 4px;
  left: 50%;
  transform: translateX(-50%);
  width: 64px;
  height: 48px;
  background-image: url(${pausedPng});
  background-repeat: no-repeat;
  background-position: center center;
  background-size: contain;
  z-index: 1000;
  pointer-events: none;
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
      /* Ensure GIF resumes when running */
      background-image: url(${runningGif}) !important;
    }
    ${PausedIcon} {
      display: none;
    }
    /* Breathing boundary glow: green only */
    animation: runningGlow 1800ms ease-in-out infinite;
  }

  &.is-breakpoint-stalled {
    /* Orange breathing glow when paused at a breakpoint */
    animation: breakpointGlow 1600ms ease-in-out infinite;
    /* Hide GIF and show static PNG while paused */
    ${RunningIcon} { display: none; }
    ${PausedIcon} { display: block; }
  }

  @keyframes runningGlow {
    0% {
      border-color: #20c020; /* green */
      box-shadow: 0 0 0 2px rgba(32,192,32,0.25), 0 0 8px rgba(32,192,32,0.20);
    }
    50% {
      border-color: #20c020; /* green */
      box-shadow: 0 0 0 3px rgba(32,192,32,0.35), 0 0 14px rgba(32,192,32,0.30);
    }
    100% {
      border-color: #20c020; /* green */
      box-shadow: 0 0 0 2px rgba(32,192,32,0.25), 0 0 8px rgba(32,192,32,0.20);
    }
  }

  @keyframes breakpointGlow {
    0%, 100% {
      border-color: #fb8c00; /* orange */
      box-shadow: 0 0 0 2px rgba(251,140,0,0.35), 0 0 8px rgba(251,140,0,0.25);
    }
    50% {
      border-color: #fb8c00; /* orange */
      box-shadow: 0 0 0 3px rgba(251,140,0,0.55), 0 0 14px rgba(251,140,0,0.45);
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
  top: 4px;
  left: 4px;
  width: 10px;
  height: 10px;
  background: #fb8c00; /* orange */
  border-radius: 50%;
  box-shadow: 0 0 0 2px #ffffff; /* white ring for contrast */
  z-index: 11;
`;

export const StatusBadgeContainer = styled.div`
  position: absolute;
  top: -6px;
  right: -6px;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #fff;
  border-radius: 10px;
  border: 2px solid #fff;
  box-shadow: 0 2px 6px rgba(0,0,0,0.2);
  z-index: 12;
`;
