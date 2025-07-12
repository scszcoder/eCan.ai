import React from 'react';
import { Empty } from 'antd';
import styled from '@emotion/styled';
import { useNotifications } from '../hooks/useNotifications';
import ProductSearchNotification from './ProductSearchNotification';


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

const NotificationTemplateRenderer: React.FC<{ notification: any }> = ({ notification }) => {
  const template = notification?.render_template || 'product_search';
  switch (template) {
    case 'product_search':
    default:
      return <ProductSearchNotification notification={notification} />;
  }
};

interface ChatNotificationProps {
  chatId: string;
}

const ChatNotification: React.FC<ChatNotificationProps> = ({ chatId }) => {
  console.log('ChatNotification loaded', chatId);
  const { notifications } = useNotifications(chatId);
  const displayNotifications = notifications.filter(n => !!n);

  if (!displayNotifications || displayNotifications.length === 0) {
    return (
      <EmptyContainer>
        <Empty description="No search results" />
      </EmptyContainer>
    );
  }

  // displayNotifications.map((notification, index) => (
  //   console.log("render chatid:", chatId, "notificationid:", notification.id)
  // ))

  return (
    <NotifyContainer>
      {displayNotifications.map((notification, index) => (
        <NotificationTemplateRenderer key={notification.id || index} notification={notification} />
      ))}
    </NotifyContainer>
  );
};

export default ChatNotification;