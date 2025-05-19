import React from 'react';
import { Layout, Typography, Card } from 'antd';
import styled from '@emotion/styled';

const { Content } = Layout;
const { Title } = Typography;

const AnalyticsContainer = styled(Layout)`
  height: calc(100vh - 112px);
  background: transparent;
`;

const AnalyticsContent = styled(Content)`
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
`;

const AnalyticsHeader = styled.div`
  padding: 16px;
  background: #fff;
  border-radius: 4px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
`;

const AnalyticsMain = styled.div`
  flex: 1;
  display: flex;
  gap: 16px;
  min-height: 0;
`;

const AnalyticsChart = styled(Card)`
  flex: 1;
  .ant-card-body {
    padding: 0;
    height: 100%;
  }
`;

const AnalyticsStats = styled(Card)`
  width: 300px;
  .ant-card-body {
    padding: 0;
    height: 100%;
  }
`;

const Analytics: React.FC = () => {
  return (
    <AnalyticsContainer>
      <AnalyticsContent>
        <AnalyticsHeader>
          <Title level={4} style={{ margin: 0 }}>Analytics</Title>
        </AnalyticsHeader>
        <AnalyticsMain>
          <AnalyticsChart variant="borderless">
            {/* Analytics charts will be implemented here */}
          </AnalyticsChart>
          <AnalyticsStats title="Statistics" variant="borderless">
            {/* Analytics statistics will be implemented here */}
          </AnalyticsStats>
        </AnalyticsMain>
      </AnalyticsContent>
    </AnalyticsContainer>
  );
};

export default Analytics; 