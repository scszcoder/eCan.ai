import React from 'react';
import { Layout, Typography, Card } from 'antd';
import styled from '@emotion/styled';

const { Content } = Layout;
const { Title } = Typography;

const ScheduleContainer = styled(Layout)`
  height: calc(100vh - 112px);
  background: transparent;
`;

const ScheduleContent = styled(Content)`
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
`;

const ScheduleHeader = styled.div`
  padding: 16px;
  background: #fff;
  border-radius: 4px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
`;

const ScheduleMain = styled.div`
  flex: 1;
  display: flex;
  gap: 16px;
  min-height: 0;
`;

const ScheduleCalendar = styled(Card)`
  flex: 1;
  .ant-card-body {
    padding: 0;
    height: 100%;
  }
`;

const ScheduleDetails = styled(Card)`
  width: 300px;
  .ant-card-body {
    padding: 0;
    height: 100%;
  }
`;

const Schedule: React.FC = () => {
  return (
    <ScheduleContainer>
      <ScheduleContent>
        <ScheduleHeader>
          <Title level={4} style={{ margin: 0 }}>Schedule</Title>
        </ScheduleHeader>
        <ScheduleMain>
          <ScheduleCalendar variant="borderless">
            {/* Calendar component will be implemented here */}
          </ScheduleCalendar>
          <ScheduleDetails title="Schedule Details" variant="borderless">
            {/* Schedule details will be implemented here */}
          </ScheduleDetails>
        </ScheduleMain>
      </ScheduleContent>
    </ScheduleContainer>
  );
};

export default Schedule; 