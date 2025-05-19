import React from 'react';
import { Layout, Typography, Card } from 'antd';
import styled from '@emotion/styled';

const { Content } = Layout;
const { Title } = Typography;

const ChatContainer = styled(Layout)`
  height: calc(100vh - 112px);
  background: transparent;
`;

const ChatContent = styled(Content)`
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
`;

const ChatHeader = styled.div`
  padding: 16px;
  background: #fff;
  border-radius: 4px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
`;

const ChatMain = styled.div`
  flex: 1;
  display: flex;
  gap: 16px;
  min-height: 0;
`;

const ChatList = styled(Card)`
  width: 280px;
  .ant-card-body {
    padding: 0;
    height: 100%;
  }
`;

const ChatMessages = styled(Card)`
  flex: 1;
  .ant-card-body {
    padding: 0;
    height: 100%;
  }
`;

const Chat: React.FC = () => {
  return (
    <ChatContainer>
      <ChatContent>
        <ChatHeader>
          <Title level={4} style={{ margin: 0 }}>Chat</Title>
        </ChatHeader>
        <ChatMain>
          <ChatList title="Conversations" variant="borderless">
            {/* Conversation list will be implemented here */}
          </ChatList>
          <ChatMessages variant="borderless">
            {/* Chat messages will be implemented here */}
          </ChatMessages>
        </ChatMain>
      </ChatContent>
    </ChatContainer>
  );
};

export default Chat; 