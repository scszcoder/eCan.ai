import React, { useRef, useEffect } from 'react';
import { Empty, Divider } from 'antd';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { useChatNotifications, NOTIF_PAGE_SIZE } from '../hooks/useChatNotifications';
import ProductSearchNotification from './ProductSearchNotification';
import i18n from '../../../i18n';

// 日期格式化函数
const formatDate = (timestamp: string | number) => {
  if (!timestamp) return '';
  
  const date = new Date(timestamp);
  
  // 简单的日期格式化实现
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
  overflow-y: auto;
  height: 100%;
  width: 100%;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
  position: relative;
`;

const EmptyContainer = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  width: 100%;
  position: relative;
  z-index: 1;
`;

const NotificationTemplateRenderer: React.FC<{ content: any }> = ({ content }) => {
  const { t } = useTranslation();
  const defaultTemplate = t('pages.chat.chatNotification.templates.product_search');
  const template = content?.render_template || defaultTemplate;
  switch (template) {
    case defaultTemplate:
    default:
      return <ProductSearchNotification content={content} />;
  }
};

interface ChatNotificationProps {
  chatId: string;
  isInitialLoading?: boolean;
}

const ChatNotification: React.FC<ChatNotificationProps> = ({ chatId, isInitialLoading }) => {
  const { t } = useTranslation();
  const { chatNotificationItems, hasMore, loadMore, loadingMore } = useChatNotifications(chatId, NOTIF_PAGE_SIZE, true);
  const containerRef = useRef<HTMLDivElement>(null);
  const prevScrollHeightRef = useRef(0);
  const prevScrollTopRef = useRef(0);
  const hasInitLoadedRef = useRef(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const loadMoreLock = useRef(false);
  const autoFillActiveRef = useRef(true);
  const autoLoadCooldownRef = useRef(0); // 自动加载冷却时间戳
  const recursiveLoadCount = useRef(0); // 递归加载计数器
  const maxRecursiveLoads = 5; // 最大递归加载次数

  // 平滑分页：加载更多前记录 scrollHeight 和 scrollTop，加载后补偿 scrollTop，保持用户当前视图不跳动（新数据加载在底部）
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

  // 只在首次加载时自动滚到顶部
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    if (!isInitialLoading && chatNotificationItems.length > 0 && !hasInitLoadedRef.current) {
      hasInitLoadedRef.current = true;
      container.scrollTop = 0;
    }
  }, [isInitialLoading, chatNotificationItems.length]);

  // 切换 chatId 时重置自动补齐标志和滚动状态
  useEffect(() => {
    autoFillActiveRef.current = true;
    hasInitLoadedRef.current = false;
    recursiveLoadCount.current = 0; // 重置递归计数器
  }, [chatId]);

  // 监听 scroll 事件，用户向下滚动到底部时自动加载更多
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

  // 分页后补偿 scrollTop，保持用户当前视图不跳动（新数据加载在底部）
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

  // 数据和界面更新后再检查 bottomRef 是否可见，递归触发 handleLoadMore（带保护机制）
  useEffect(() => {
    const container = containerRef.current;
    if (!container || !bottomRef.current || loadingMore || !hasMore) return;
    
    // 检查递归加载次数限制
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
        // 加载完成后，如果还有更多数据且未达到限制，允许继续
        if (!hasMore) {
          recursiveLoadCount.current = 0; // 没有更多数据时重置计数器
        }
      });
    }
  }, [chatNotificationItems, loadingMore, hasMore, handleLoadMore]);

  const displayChatNotifications = chatNotificationItems.filter((n: any) => !!n);

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
    <NotifyContainer ref={containerRef}>
      {displayChatNotifications.map((n, i) => (
        <React.Fragment key={`${n.uid}_${i}`}>
          <div style={{ marginBottom: 16 }}>
            <NotificationTemplateRenderer content={n.content} />
          </div>
          {i < displayChatNotifications.length - 1 && (
            <Divider orientation="center" style={{ color: '#aaa', fontSize: 12 }}>
              {n.timestamp ? formatDate(n.timestamp) : ''}
            </Divider>
          )}
        </React.Fragment>
      ))}
      <div ref={bottomRef} style={{ height: 20 }} />
      {!hasMore && <div style={{textAlign: 'center'}}>{t('pages.chat.chatNotification.noMore')}</div>}
    </NotifyContainer>
  );
};

export default ChatNotification;