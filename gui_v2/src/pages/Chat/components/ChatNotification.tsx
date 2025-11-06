import React, { useRef, useEffect, useState } from 'react';
import { Empty, Divider, Button, Collapse } from 'antd';
import { ClearOutlined, DownOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { useChatNotifications, NOTIF_PAGE_SIZE } from '../hooks/useChatNotifications';
import ProductSearchNotification from './ProductSearchNotification';
import i18n from '../../../i18n';
import { notificationManager } from '../managers/NotificationManager';

const { Panel } = Collapse;

// DateFormatFunction
const formatDate = (timestamp: string | number) => {
  if (!timestamp) return '';
  
  const date = new Date(timestamp);
  
  // Simple的DateFormatImplementation
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  
  // 根据语言返回不同格式
  const currentLang = i18n.language;
  if (currentLang === 'zh-CN') {
    return `${year}年${month}月${day}日 ${hours}:${minutes}`;
  } else {
    const ampm = date.getHours() >= 12 ? 'PM' : 'AM';
    const displayHours = date.getHours() % 12 || 12;
    return `${month}/${day}/${year}, ${displayHours}:${minutes} ${ampm}`;
  }
};

const NotifyContainer = styled.div`
  padding: 32px 40px;
  padding-top: 60px;
  overflow-y: auto;
  height: 100%;
  width: 100%;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
  position: relative;
`;

const HeaderContainer = styled.div`
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 60px;
  padding: 12px 40px;
  display: flex;
  justify-content: flex-end;
  align-items: center;
  background: rgba(26, 26, 46, 0.95);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  z-index: 10;
`;

const TimestampText = styled.div`
  font-size: 12px;
  color: rgba(255, 255, 255, 0.5);
  margin-top: 8px;
  text-align: right;
`;

const StyledCollapse = styled(Collapse)`
  background: transparent;
  border: none;
  
  .ant-collapse-item {
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 8px;
    margin-bottom: 16px;
    background: rgba(255, 255, 255, 0.05);
    overflow: hidden;
  }
  
  .ant-collapse-header {
    color: rgba(255, 255, 255, 0.85) !important;
    padding: 12px 16px !important;
    background: rgba(255, 255, 255, 0.03);
    
    &:hover {
      background: rgba(255, 255, 255, 0.08);
    }
  }
  
  .ant-collapse-content {
    background: transparent;
    border-top: 1px solid rgba(255, 255, 255, 0.1);
  }
  
  .ant-collapse-content-box {
    padding: 16px;
  }
`;

const EmptyContainer = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
`;

const NotificationTemplateRenderer: React.FC<{ content: any }> = ({ content }) => {
  const { t } = useTranslation();
  const defaultTemplate = t('pages.chat.chatNotification.templates.product_search');
  const template = content?.render_template || defaultTemplate;
  switch (template) {
    case defaultTemplate:
    default:
      // Support multiple shapes:
      // 1) content is already the notification body { title, Items, ... }
      // 2) content.content or content.content.content is the body
      // 3) body.notification may be an object or a JSON string
      const body = (content && typeof content === 'object')
        ? (content?.content?.content ?? content?.content ?? content)
        : content;
      let normalized: any = body?.notification ?? body;
      if (normalized && typeof normalized === 'string') {
        try { normalized = JSON.parse(normalized); }
        catch {
          try { normalized = JSON.parse(normalized.replace(/'/g, '"')); } catch {}
        }
      }
      try {
        // eslint-disable-next-line no-console
        console.log('[ChatNotification] normalized keys', Object.keys(normalized || {}), {
          hasItems: Array.isArray((normalized as any)?.Items),
          itemsLen: Array.isArray((normalized as any)?.Items) ? (normalized as any).Items.length : 'n/a',
        });
      } catch {}
      return <ProductSearchNotification content={normalized} />;
  }
};

interface ChatNotificationProps {
  chatId: string;
  isInitialLoading?: boolean;
}
const ChatNotification: React.FC<ChatNotificationProps> = ({ chatId, isInitialLoading }) => {
  const { t } = useTranslation();
  const { chatNotificationItems, hasMore, loadMore, loadingMore } = useChatNotifications(chatId, NOTIF_PAGE_SIZE, true);
  const [activeKeys, setActiveKeys] = useState<string[]>([]);
  const containerRef = useRef<HTMLDivElement>(null);
  const prevScrollHeightRef = useRef(0);
  const prevScrollTopRef = useRef(0);
  const hasInitLoadedRef = useRef(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const loadMoreLock = useRef(false);
  const autoFillActiveRef = useRef(true);
  const autoLoadCooldownRef = useRef(0); // 自动Load冷却Time戳
  const recursiveLoadCount = useRef(0); // RecursiveLoad计数器
  const maxRecursiveLoads = 5; // MaximumRecursiveLoad次数

  // 平滑分页：Load更多前记录 scrollHeight 和 scrollTop，Load后补偿 scrollTop，保持UserWhen前视图不跳动（新DataLoad在Bottom）
  const handleLoadMore = React.useCallback(async () => {
    if (loadMoreLock.current) {
      return;
    }
    loadMoreLock.current = true;
    const container = containerRef.current;
    if (container) {
      prevScrollHeightRef.current = container.scrollHeight;
      prevScrollTopRef.current = container.scrollTop;
    }
    await loadMore();
    loadMoreLock.current = false;
  }, [loadMore]);

  // 只在首次Load时自动滚到Top
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    if (!isInitialLoading && chatNotificationItems.length > 0 && !hasInitLoadedRef.current) {
      hasInitLoadedRef.current = true;
      container.scrollTop = 0;
    }
  }, [isInitialLoading, chatNotificationItems.length]);

  // Toggle chatId 时Reset自动补齐标志和ScrollStatus
  useEffect(() => {
    autoFillActiveRef.current = true;
    hasInitLoadedRef.current = false;
    recursiveLoadCount.current = 0; // ResetRecursive计数器
  }, [chatId]);

  // Listen scroll Event，User向下Scroll到Bottom时自动Load更多
  useEffect(() => {
    if (isInitialLoading) return;
    const container = containerRef.current;
    if (!container) return;

    const handleScroll = () => {
      if (
        hasMore &&
        !loadingMore &&
        hasInitLoadedRef.current &&
        container.scrollTop + container.clientHeight >= container.scrollHeight - 50
      ) {
        handleLoadMore();
      }
    };

    container.addEventListener('scroll', handleScroll);
    return () => container.removeEventListener('scroll', handleScroll);
  }, [isInitialLoading, chatNotificationItems.length, hasMore, loadingMore]);

  // 分页后补偿 scrollTop，保持UserWhen前视图不跳动（新DataLoad在Bottom）
  useEffect(() => {
    if (loadingMore) return;
    const container = containerRef.current;
    if (!container) return;
    if (prevScrollHeightRef.current > 0) {
      container.scrollTop = prevScrollTopRef.current;
      prevScrollHeightRef.current = 0;
      prevScrollTopRef.current = 0;
      if (autoFillActiveRef.current && container.scrollHeight <= container.clientHeight && hasMore) {
        const now = Date.now();
        if (now - autoLoadCooldownRef.current > 250) {
          autoLoadCooldownRef.current = now;
          handleLoadMore();
        }
      } else {
        autoFillActiveRef.current = false;
      }
    }
  }, [chatNotificationItems, loadingMore, hasMore, handleLoadMore]);

  // Data和界面Update后再Check bottomRef 是否可见，RecursiveTrigger handleLoadMore（带保护机制）
  useEffect(() => {
    const container = containerRef.current;
    if (!container || !bottomRef.current || loadingMore || !hasMore) return;
    
    // CheckRecursiveLoad次数Limit
    if (recursiveLoadCount.current >= maxRecursiveLoads) {
      console.warn('[ChatNotification] Recursive load limit reached, stopping auto-load');
      return;
    }
    
    const containerRect = container.getBoundingClientRect();
    const bottomRect = bottomRef.current.getBoundingClientRect();
    if (bottomRect.top < containerRect.bottom && bottomRect.bottom > containerRect.top) {
      const now = Date.now();
      if (now - autoLoadCooldownRef.current <= 250) {
        return;
      }
      autoLoadCooldownRef.current = now;
      recursiveLoadCount.current += 1;
      console.debug(`[ChatNotification] Auto-loading more (${recursiveLoadCount.current}/${maxRecursiveLoads})`);
      handleLoadMore().then(() => {
        // LoadCompleted后，If还有更多Data且未达到Limit，Allow继续
        if (!hasMore) {
          recursiveLoadCount.current = 0; // 没有更多Data时Reset计数器
        }
      });
    }
  }, [chatNotificationItems, loadingMore, hasMore, handleLoadMore]);

  const displayChatNotifications = chatNotificationItems.filter((n: any) => !!n);

  const handleClearAll = () => {
    if (chatId) {
      notificationManager.clear(chatId);
    }
  };

  // Auto-expand first notification on load
  useEffect(() => {
    if (displayChatNotifications.length > 0 && activeKeys.length === 0) {
      setActiveKeys([`${displayChatNotifications[0].uid}_0`]);
    }
  }, [displayChatNotifications.length]);

  if (isInitialLoading) {
    return (
      <EmptyContainer>
        <Empty description={t('pages.chat.chatNotification.loading')} />
      </EmptyContainer>
    );
  }

  if (!displayChatNotifications || displayChatNotifications.length === 0) {
    return (
      <EmptyContainer>
        <Empty description={t('pages.chat.chatNotification.noResults')} />
      </EmptyContainer>
    );
  }

  return (
    <>
      <HeaderContainer>
        <Button
          type="text"
          icon={<ClearOutlined />}
          onClick={handleClearAll}
          style={{ color: 'rgba(255, 255, 255, 0.65)' }}
        >
          Clear All
        </Button>
      </HeaderContainer>
      <NotifyContainer ref={containerRef}>
        <StyledCollapse
          activeKey={activeKeys}
          onChange={(keys) => setActiveKeys(keys as string[])}
          expandIcon={({ isActive }) => <DownOutlined rotate={isActive ? 180 : 0} />}
          ghost
        >
          {[...displayChatNotifications].reverse().map((n, i) => {
            const key = `${n.uid}_${i}`;
            const timestamp = n.timestamp ? formatDate(n.timestamp) : '';
            return (
              <Panel
                header={
                  <div>
                    <div style={{ fontWeight: 500 }}>
                      {t('pages.chat.chatNotification.notification')} #{i + 1}
                    </div>
                    <TimestampText>{timestamp}</TimestampText>
                  </div>
                }
                key={key}
              >
                <NotificationTemplateRenderer content={n.content} />
              </Panel>
            );
          })}
        </StyledCollapse>
        <div ref={bottomRef} style={{ height: 20 }} />
        {!hasMore && displayChatNotifications.length > 0 && (
          <div style={{ textAlign: 'center', color: 'rgba(255, 255, 255, 0.5)', marginTop: 16 }}>
            {t('pages.chat.chatNotification.noMore')}
          </div>
        )}
      </NotifyContainer>
    </>
  );
};

export default ChatNotification;