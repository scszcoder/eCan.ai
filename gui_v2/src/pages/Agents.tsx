import React from 'react';
import { Layout, Typography, Card } from 'antd';
import styled from '@emotion/styled';

const { Content } = Layout;
const { Title } = Typography;

const AgentsContainer = styled(Layout)`
  height: calc(100vh - 112px);
  background: transparent;
`;

const AgentsContent = styled(Content)`
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
`;

const AgentsHeader = styled.div`
  padding: 16px;
  background: #fff;
  border-radius: 4px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
`;

const AgentsMain = styled.div`
  flex: 1;
  display: flex;
  gap: 16px;
  min-height: 0;
`;

const AgentsList = styled(Card)`
  width: 280px;
  .ant-card-body {
    padding: 0;
    height: 100%;
  }
`;

const AgentsDetails = styled(Card)`
  flex: 1;
  .ant-card-body {
    padding: 0;
    height: 100%;
  }
`;

const Agents: React.FC = () => {
  return (
    <AgentsContainer>
      <AgentsContent>
        <AgentsHeader>
          <Title level={4} style={{ margin: 0 }}>Agents</Title>
        </AgentsHeader>
        <AgentsMain>
          <AgentsList title="Agents List" variant="borderless">
            {/* Agents list will be implemented here */}
          </AgentsList>
          <AgentsDetails variant="borderless">
            {/* Agents details will be implemented here */}
          </AgentsDetails>
        </AgentsMain>
      </AgentsContent>
    </AgentsContainer>
  );
};

export default Agents; 