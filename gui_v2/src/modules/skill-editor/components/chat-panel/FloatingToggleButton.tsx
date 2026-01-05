/**
 * FloatingToggleButton - Floating robot icon to toggle chat panel
 */

import React from 'react';
import { Tooltip } from 'antd';
import styled from 'styled-components';

// Cute robot SVG icon
const CuteRobotIcon: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    {/* Robot head */}
    <rect x="4" y="6" width="16" height="14" rx="3" fill="white" />
    {/* Antenna */}
    <circle cx="12" cy="3" r="2" fill="#FFD93D" />
    <rect x="11" y="4" width="2" height="3" fill="white" />
    {/* Left eye */}
    <circle cx="8.5" cy="11" r="2.5" fill="#3B82F6" />
    <circle cx="9" cy="10.5" r="1" fill="white" />
    {/* Right eye */}
    <circle cx="15.5" cy="11" r="2.5" fill="#3B82F6" />
    <circle cx="16" cy="10.5" r="1" fill="white" />
    {/* Smile */}
    <path
      d="M8 15.5C8 15.5 9.5 17.5 12 17.5C14.5 17.5 16 15.5 16 15.5"
      stroke="#3B82F6"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
    {/* Cheeks */}
    <circle cx="6" cy="14" r="1.5" fill="#FFB6C1" opacity="0.6" />
    <circle cx="18" cy="14" r="1.5" fill="#FFB6C1" opacity="0.6" />
  </svg>
);

interface FloatingToggleButtonProps {
  isCollapsed: boolean;
  onClick: () => void;
  leftOffset: number;
}

const FloatingButton = styled.button<{ $leftOffset: number }>`
  position: absolute;
  left: ${props => props.$leftOffset}px;
  top: 50%;
  transform: translateY(-50%) translateX(-50%);
  z-index: 1000;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
  border: 2px solid rgba(255, 255, 255, 0.2);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.3s ease;
  
  &:hover {
    transform: translateY(-50%) translateX(-50%) scale(1.1);
    box-shadow: 0 6px 16px rgba(59, 130, 246, 0.5);
  }
  
  &:active {
    transform: translateY(-50%) translateX(-50%) scale(0.95);
  }
  
`;

export const FloatingToggleButton: React.FC<FloatingToggleButtonProps> = ({
  isCollapsed,
  onClick,
  leftOffset,
}) => {
  return (
    <Tooltip 
      title={isCollapsed ? 'Open AI Chat' : 'Close AI Chat'} 
      placement="right"
    >
      <FloatingButton $leftOffset={leftOffset} onClick={onClick}>
        <CuteRobotIcon size={26} />
      </FloatingButton>
    </Tooltip>
  );
};

export default FloatingToggleButton;
