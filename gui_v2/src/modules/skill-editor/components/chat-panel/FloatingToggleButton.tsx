/**
 * FloatingToggleButton - Floating robot icon to toggle chat panel
 */

import React from 'react';
import { useTranslation } from 'react-i18next';
import { Tooltip } from 'antd';
import styled from 'styled-components';
import { CuteRobotIcon } from './CuteRobotIcon';

interface FloatingToggleButtonProps {
  isCollapsed: boolean;
  onClick: () => void;
  leftOffset: number;
}

const FloatingButtonWrapper = styled.div<{ $leftOffset: number }>`
  position: absolute;
  left: ${props => props.$leftOffset}px;
  top: 50%;
  transform: translateY(-50%) translateX(-50%);
  z-index: 1000;
  display: flex;
  align-items: center;
  pointer-events: none;
`;

const FloatingButton = styled.button<{ $leftOffset: number }>`
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
  position: relative;
  pointer-events: auto;
  animation: floatingPulse 2.8s ease-in-out infinite;

  @keyframes floatingPulse {
    0%, 100% {
      box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4), 0 0 0 0 rgba(99, 102, 241, 0.38);
    }
    50% {
      box-shadow: 0 8px 22px rgba(99, 102, 241, 0.48), 0 0 0 10px rgba(99, 102, 241, 0);
    }
  }
  
  &:hover {
    transform: scale(1.1);
    box-shadow: 0 6px 16px rgba(59, 130, 246, 0.5);
    animation-play-state: paused;
  }
  
  &:active {
    transform: scale(0.95);
  }
`;

export const FloatingToggleButton: React.FC<FloatingToggleButtonProps> = ({
  isCollapsed,
  onClick,
  leftOffset,
}) => {
  const { t } = useTranslation();

  return (
    <FloatingButtonWrapper $leftOffset={leftOffset}>
      <Tooltip 
        title={isCollapsed ? t('chatPanel.openAiChat') : t('chatPanel.closeAiChat')} 
        placement="right"
      >
        <FloatingButton $leftOffset={leftOffset} onClick={onClick}>
          <CuteRobotIcon size={26} />
        </FloatingButton>
      </Tooltip>
    </FloatingButtonWrapper>
  );
};

export default FloatingToggleButton;
