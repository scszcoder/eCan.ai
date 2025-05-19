import React from 'react';
import { Layout, Typography, Card } from 'antd';
import styled from '@emotion/styled';

const { Content } = Layout;
const { Title } = Typography;

const AppsContainer = styled(Layout)`
  height: calc(100vh - 112px);
  background: transparent;
`;

const AppsContent = styled(Content)`
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
`;

const AppsHeader = styled.div`
  padding: 16px;
  background: #fff;
  border-radius: 4px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
`;

const AppsMain = styled.div`
  flex: 1;
  display: flex;
  gap: 16px;
  min-height: 0;
`;

const AppsList = styled(Card)`
  width: 280px;
  .ant-card-body {
    padding: 0;
    height: 100%;
  }
`;

const AppsDetails = styled(Card)`
  flex: 1;
  .ant-card-body {
    padding: 0;
    height: 100%;
  }
`;

const Apps: React.FC = () => {
  return (
    <AppsContainer>
      <AppsContent>
        <AppsHeader>
          <Title level={4} style={{ margin: 0 }}>Apps</Title>
        </AppsHeader>
        <AppsMain>
          <AppsList title="Apps List" variant="borderless">
            {/* Apps list will be implemented here */}
          </AppsList>
          <AppsDetails variant="borderless">
            {/* Apps details will be implemented here */}
          </AppsDetails>
        </AppsMain>
      </AppsContent>
    </AppsContainer>
  );
};

export default Apps; 