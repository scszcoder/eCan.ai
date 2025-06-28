import React from 'react';
import { Empty } from 'antd';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { useNotifications } from '../hooks/useNotifications';

const NotifyContainer = styled.div`
  padding: 16px;
  overflow-y: auto;
  height: 100%;
  width: 100%;
`;

const EmptyContainer = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  width: 100%;
`;

interface AgentNotifyProps {
  notifications?: Array<any>; // 保持向后兼容
}

const AgentNotify: React.FC<AgentNotifyProps> = ({ notifications: propNotifications }) => {
  const { t } = useTranslation();
  const { notifications, clearAll } = useNotifications();
  
  // 使用全局通知管理器管理的通知，如果有 props 传入则使用 props（向后兼容）
  const displayNotifications = propNotifications || notifications;
  
  if (!displayNotifications || displayNotifications.length === 0) {
    return (
      <EmptyContainer>
        <Empty description={t('pages.chat.noAgentResults')} />
      </EmptyContainer>
    );
  }
  
  return (
    <NotifyContainer>
      {displayNotifications.map((item) => (
        <div key={item.id} style={{ marginBottom: 24, borderBottom: '1px solid #eee', paddingBottom: 12 }}>
          <div style={{ fontWeight: 600, fontSize: 16 }}>{item.title}</div>
          <div style={{ color: '#888', fontSize: 12, margin: '4px 0' }}>{item.time}</div>
          <div style={{ marginTop: 4 }}>{item.content}</div>
          {item.type && (
            <div style={{ color: '#666', fontSize: 11, marginTop: 4 }}>
              Type: {item.type}
            </div>
          )}
          {item.status && (
            <div style={{ color: '#666', fontSize: 11, marginTop: 2 }}>
              Status: {item.status}
            </div>
          )}
        </div>
      ))}
    </NotifyContainer>
  );
};

export default AgentNotify;