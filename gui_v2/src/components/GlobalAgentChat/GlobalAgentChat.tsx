import React, { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Tooltip } from 'antd';
import styled from 'styled-components';
import {
  ChatPanel,
  ResizableDivider,
  CuteRobotIcon,
} from '@/modules/skill-editor/components/chat-panel';
import { useGlobalAgentChatStore } from '@/stores/globalAgentChatStore';
import { useUserStore } from '@/stores/userStore';

const FloatingButtonWrapper = styled.div<{ $right: number }>`
  position: fixed;
  right: ${(p) => p.$right}px;
  top: 50%;
  transform: translate(50%, -50%);
  z-index: 1000;
  pointer-events: none;
  transition: right 0.3s ease;
`;

const FloatingButton = styled.button`
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
  pointer-events: auto;
  animation: globalAgentFloatingPulse 2.8s ease-in-out infinite;

  @keyframes globalAgentFloatingPulse {
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

export const GlobalAgentChat: React.FC = () => {
  const { t } = useTranslation('skillEditor');
  const username = useUserStore((s) => s.username);
  const isCollapsed = useGlobalAgentChatStore((s) => s.isCollapsed);
  const width = useGlobalAgentChatStore((s) => s.width);
  const mounted = useGlobalAgentChatStore((s) => s.mounted);
  const toggle = useGlobalAgentChatStore((s) => s.toggle);
  const resizeBy = useGlobalAgentChatStore((s) => s.resizeBy);

  const handleToggle = useCallback(() => {
    toggle();
  }, [toggle]);

  if (!username) return null;

  const buttonRight = isCollapsed ? 0 : width;

  return (
    <>
      <ResizableDivider onResize={resizeBy} isVisible={!isCollapsed} />
      {mounted ? (
        <ChatPanel
          isCollapsed={isCollapsed}
          onToggle={handleToggle}
          width={width}
        />
      ) : null}
      <FloatingButtonWrapper $right={buttonRight}>
        <Tooltip
          title={isCollapsed ? t('chatPanel.openAiChat') : t('chatPanel.closeAiChat')}
          placement="left"
        >
          <FloatingButton onClick={handleToggle}>
            <CuteRobotIcon size={26} />
          </FloatingButton>
        </Tooltip>
      </FloatingButtonWrapper>
    </>
  );
};

export default GlobalAgentChat;
