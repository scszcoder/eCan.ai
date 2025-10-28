import React, { useState, useEffect } from 'react';
import { Card, Button, Badge } from 'antd';
import styled from '@emotion/styled';
import SplitPane from 'react-split-pane';
import { MenuFoldOutlined, MenuUnfoldOutlined, RobotOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

// Add全局样式
const GlobalStyles = styled.div`
  height: 100%;
  width: 100%;
  
  /* SplitPane 样式覆盖 */
  .Resizer {
    background: #222;
    opacity: 0.2;
    z-index: 1;
    box-sizing: border-box;
    background-clip: padding-box;
  }

  .Resizer.vertical {
    width: 5px;
    margin: 0 -2px;
    cursor: col-resize;
  }

  .Resizer.vertical:hover {
    opacity: 1;
  }

  .Pane {
    display: flex !important;
    overflow: hidden !important;
  }

  .SplitPane {
    position: relative;
    height: 100% !important;
    width: 100% !important;
  }
  
  /* Custom Badge 样式 */
  .custom-badge .ant-badge-dot {
    width: 10px;
    height: 10px;
    box-shadow: 0 0 0 1px #fff;
  }

  /* Card 标题白色字体样式 */
  .ant-card-head-title {
    color: white !important;
  }
  
  /* 确保AllCard标题都是白色 */
  .ant-card .ant-card-head .ant-card-head-title {
    color: white !important;
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
  position: absolute;
  top: 16px;
  ${({ side }) => (side === 'left' ? 'right: -16px;' : 'left: -16px;')}
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

// Custom红点样式
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

interface ChatLayoutProps {
  listTitle: React.ReactNode;
  detailsTitle: string;
  listContent: React.ReactNode;
  detailsContent: React.ReactNode;
  chatNotificationTitle: React.ReactNode;
  chatNotificationContent: React.ReactNode;
  hasNewAgentNotifications?: boolean;
  onRightPanelToggle?: (collapsed: boolean) => void;
}

const ChatLayout: React.FC<ChatLayoutProps> = ({
  listTitle,
  detailsTitle,
  listContent,
  detailsContent,
  chatNotificationTitle,
  chatNotificationContent,
  hasNewAgentNotifications = false,
  onRightPanelToggle,
}) => {
  const { t } = useTranslation();
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(true);
  const [splitSize, setSplitSize] = useState<string | number>('70%');

  // WhenRight面板Expand/折叠时重新计算分割尺寸
  useEffect(() => {
    if (rightCollapsed) {
      setSplitSize('100%');
    } else {
      setSplitSize('40%'); // 修改为40%，使ChatNotification占60%，聊天框占40%
    }

    // 调用父Component的CallbackFunction
    onRightPanelToggle?.(rightCollapsed);
  }, [rightCollapsed, onRightPanelToggle]);

  // ProcessRight面板的折叠/Expand
  const handleRightPanelToggle = () => {
    setRightCollapsed((c) => {
      const newRightCollapsed = !c;
      // WhenExpandRight面板时，自动折叠Left面板
      if (!newRightCollapsed) {
        setLeftCollapsed(true);
      }
      return newRightCollapsed;
    });
  };

  // 中间卡片的 title 区域，Include左右折叠Button和聊天名
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
      <span style={{ flex: 1, color: 'white' }}>{detailsTitle}</span>
      <div style={{ position: 'relative' }}>
        <AgentButton
          type="text"
          icon={<RobotOutlined style={{ fontSize: '16px' }} />}
          onClick={handleRightPanelToggle}
          title={rightCollapsed ? t('pages.chat.expandRight') : t('pages.chat.collapseRight')}
          aria-label={rightCollapsed ? t('pages.chat.expandRight') : t('pages.chat.collapseRight')}
        />
        {hasNewAgentNotifications && rightCollapsed && <NotificationDot />}
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
        
        {/* @ts-ignore */}
        <SplitPane
          split="vertical"
          minSize={300}
          maxSize={rightCollapsed ? "100%" : "50%"}
          size={splitSize}
          onChange={(size) => setSplitSize(size)}
          allowResize={!rightCollapsed}
          style={{ position: 'relative', flex: 1, overflow: 'hidden' }}
          className="custom-split-pane"
        >
          <CenterPane>
            <Card
              title={centerTitle}
              variant="borderless"
              style={{ height: '100%', width: '100%', borderRadius: 0 }}
              styles={{ body: { height: 'calc(100% - 48px)', padding: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' } }}
            >
              {detailsContent}
            </Card>
          </CenterPane>
          <div style={{ height: '100%', width: '100%', display: 'flex', overflow: 'hidden' }}>
            {!rightCollapsed && (
              <Card
                title={chatNotificationTitle}
                variant="borderless"
                style={{ height: '100%', width: '100%', borderRadius: 0, flex: 1 }}
                styles={{ body: { height: 'calc(100% - 48px)', padding: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' } }}
              >
                {chatNotificationContent}
              </Card>
            )}
          </div>
        </SplitPane>
      </LayoutContainer>
    </GlobalStyles>
  );
};

export default ChatLayout; 