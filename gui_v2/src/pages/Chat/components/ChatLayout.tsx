import React, { useState, useEffect } from 'react';
import { Card, Button, Badge } from 'antd';
import styled from '@emotion/styled';
import SplitPane, { Pane } from 'split-pane-react';
import 'split-pane-react/esm/themes/default.css';
import { useTranslation } from 'react-i18next';
import { MenuFoldOutlined, MenuUnfoldOutlined, InboxOutlined, AppstoreOutlined } from '@ant-design/icons';
import { ContextPanel } from './ContextPanel';

// Add全局样式
const GlobalStyles = styled.div`
  height: 100%;
  width: 100%;
  .SplitPane {
    height: 100% !important;
  }
  /* Resizer styles to make divider grab-friendly */
  .Resizer {
    background: #222;
    opacity: 0.25;
    z-index: 1000; /* keep above Card content */
    box-sizing: border-box;
    background-clip: padding-box;
    position: relative;
    user-select: none;
    -webkit-user-select: none;
  }
  .Resizer.vertical {
    width: 10px; /* easier to grab */
    margin: 0 -5px; /* overlap panes to increase hit area */
    cursor: col-resize;
    touch-action: none; /* prevent touch scroll interference */
  }
  .Resizer:hover {
    opacity: 0.6;
  }
`;

const LayoutContainer = styled.div`
  display: flex;
  height: 100%;
  width: 100%;
  background: transparent;
  overflow: hidden;
`;

const Sider = styled.div<{ collapsed: boolean; side: 'left' | 'right' }>`
  width: ${({ collapsed }) => (collapsed ? '0px' : '300px')};
  min-width: 0;
  max-width: 400px;
  height: 100%;
  transition: width 0.2s;
  overflow: hidden;
  background: transparent;
  display: flex;
  flex-direction: column;
  border-right: ${({ side, collapsed }) => (side === 'left' && !collapsed ? '1px solid #222' : 'none')};
  border-left: ${({ side, collapsed }) => (side === 'right' && !collapsed ? '1px solid #222' : 'none')};
`;

const CollapseButton = styled(Button)<{ side: 'left' | 'right' }>`
  position: relative;
  top: 0;
  ${({ side }) => (side === 'left' ? 'right: 0;' : 'left: 0;')}
  z-index: 10;
  padding: 0;
  width: 24px;
  height: 24px !important;
  border-radius: 50%;
`;

const AgentButton = styled(Button)`
  position: relative;
  padding: 0;
  width: 28px;
  height: 28px !important;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
`;

const NotificationDot = styled.div`
  position: absolute;
  top: -0px;
  right: -0px;
  width: 8px;
  height: 8px;
  background-color: #ff4d4f;
  border-radius: 50%;
  border: 0px solid #fff;
  z-index: 10;
`;

const CenterPane = styled.div`
  height: 100%;
  width: 100%;
  display: flex;
  flex-direction: column;
  background: transparent;
  overflow: hidden;
`;

const CenterTitleBar = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
`;

const TitleText = styled.span`
  flex: 1;
  color: white;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

export interface ChatLayoutProps {
  listTitle: React.ReactNode;
  detailsTitle: React.ReactNode;
  listContent: React.ReactNode;
  detailsContent: React.ReactNode;
  chatNotificationTitle: React.ReactNode;
  chatNotificationContent: React.ReactNode;
  chatContextTitle?: React.ReactNode;
  chatContextContent?: React.ReactNode;
  hasNewAgentNotifications?: boolean;
  onRightPanelToggle?: (rightCollapsed: boolean) => void;
}

const ChatLayout: React.FC<ChatLayoutProps> = ({
  listTitle,
  detailsTitle,
  listContent,
  detailsContent,
  chatNotificationTitle,
  chatNotificationContent,
  chatContextTitle,
  chatContextContent,
  hasNewAgentNotifications = false,
  onRightPanelToggle,
}) => {
  const { t } = useTranslation();
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(true);
  const [sizes, setSizes] = useState<(string | number)[]>(['60%', '40%']);
  const [rightMode, setRightMode] = useState<'notifications' | 'context' | null>(null);

  useEffect(() => {
    onRightPanelToggle?.(rightCollapsed);
  }, [rightCollapsed, onRightPanelToggle]);

  const openRightMode = (mode: 'notifications' | 'context') => {
    setRightCollapsed((c) => {
      if (!c && rightMode === mode) {
        setRightMode(null);
        return true;
      }
      setRightMode(mode);
      setLeftCollapsed(true);
      return false;
    });
  };

  const centerTitle = (
    <CenterTitleBar>
      <CollapseButton
        type="text"
        icon={leftCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
        onClick={() => setLeftCollapsed((c) => !c)}
        side="left"
        style={{ position: 'static' }}
        title={leftCollapsed ? t('pages.chat.expandLeft') : t('pages.chat.collapseLeft')}
        aria-label={leftCollapsed ? t('pages.chat.expandLeft') : t('pages.chat.collapseLeft')}
      />
      <TitleText>{detailsTitle}</TitleText>
      <div style={{ position: 'relative', display: 'flex', gap: 8, flexShrink: 0 }}>
        <AgentButton
          type="text"
          icon={<AppstoreOutlined style={{ fontSize: '16px' }} />}
          onClick={() => openRightMode('context')}
          title={rightCollapsed || rightMode !== 'context' ? t('pages.chat.expandRight') : t('pages.chat.collapseRight')}
          aria-label={rightCollapsed || rightMode !== 'context' ? t('pages.chat.expandRight') : t('pages.chat.collapseRight')}
        />
        <div style={{ position: 'relative' }}>
          <AgentButton
            type="text"
            icon={<InboxOutlined style={{ fontSize: '16px' }} />}
            onClick={() => openRightMode('notifications')}
            title={rightCollapsed || rightMode !== 'notifications' ? t('pages.chat.expandRight') : t('pages.chat.collapseRight')}
            aria-label={rightCollapsed || rightMode !== 'notifications' ? t('pages.chat.expandRight') : t('pages.chat.collapseRight')}
          />
          {hasNewAgentNotifications && (rightCollapsed || rightMode !== 'notifications') && <NotificationDot />}
        </div>
      </div>
    </CenterTitleBar>
  );

  return (
    <GlobalStyles>
      <LayoutContainer>
        <Sider collapsed={leftCollapsed} side="left">
          {!leftCollapsed && (
            <Card
              title={listTitle}
              variant="borderless"
              style={{ height: '100%', width: '100%', borderRadius: 0 }}
              styles={{ body: { height: 'calc(100% - 48px)', padding: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' } }}
            >
              {listContent}
            </Card>
          )}
        </Sider>
        <SplitPane
          split="vertical"
          sizes={rightCollapsed ? ['100%', '0%'] : sizes}
          allowResize={!rightCollapsed}
          onChange={(newSizes) => {
            if (!rightCollapsed) {
              setSizes(newSizes);
            }
          }}
          sashRender={(index, active) => (rightCollapsed ? null : undefined)}
          style={{ position: 'relative', flex: 1, overflow: 'hidden', minWidth: 0 }}
          className="custom-split-pane"
        >
          <Pane minSize='30%' maxSize='90%'>
            <CenterPane>
              <Card
                title={centerTitle}
                variant="borderless"
                style={{ height: '100%', width: '100%', borderRadius: 0 }}
                styles={{ body: { height: 'calc(100% - 56px)', padding: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' } }}
              >
                {detailsContent}
              </Card>
            </CenterPane>
          </Pane>
          <Pane minSize={rightCollapsed ? 0 : '10%'} maxSize={rightCollapsed ? 0 : '70%'}>
            <div style={{ height: '100%', width: '100%', display: 'flex', overflow: 'visible', minWidth: 0 }}>
              <Card
                title={rightMode === 'context' ? (chatContextTitle ?? 'Context') : chatNotificationTitle}
                variant="borderless"
                style={{ height: '100%', width: '100%', borderRadius: 0, flex: 1, display: 'flex', flexDirection: 'column' }}
                styles={{ body: { flex: 1, minHeight: 0, padding: 0, overflow: 'auto' } }}
              >
                {rightMode === 'context' ? (chatContextContent ?? <ContextPanel />) : chatNotificationContent}
              </Card>
            </div>
          </Pane>
        </SplitPane>
      </LayoutContainer>
    </GlobalStyles>
  );
};

export default ChatLayout;