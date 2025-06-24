import React from 'react';
import { Empty } from 'antd';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';

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
  notifications: Array<{ id: string; title: string; content: string; time?: string }>;
}

const AgentNotify: React.FC<AgentNotifyProps> = ({ notifications }) => {
  const { t } = useTranslation();
  
  if (!notifications || notifications.length === 0) {
    return (
      <EmptyContainer>
        <Empty description={t('pages.chat.noAgentResults')} />
      </EmptyContainer>
    );
  }
  return (
    <NotifyContainer>
      {notifications.map((item) => (
        <div key={item.id} style={{ marginBottom: 24, borderBottom: '1px solid #eee', paddingBottom: 12 }}>
          <div style={{ fontWeight: 600, fontSize: 16 }}>{item.title}</div>
          <div style={{ color: '#888', fontSize: 12, margin: '4px 0' }}>{item.time}</div>
          <div style={{ marginTop: 4 }}>{item.content}</div>
        </div>
      ))}
    </NotifyContainer>
  );
};

export default AgentNotify; 