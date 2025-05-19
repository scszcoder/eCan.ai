import React from 'react';
import { Layout, Typography, Card } from 'antd';
import styled from '@emotion/styled';

const { Content } = Layout;
const { Title } = Typography;

const SkillsContainer = styled(Layout)`
  height: calc(100vh - 112px);
  background: transparent;
`;

const SkillsContent = styled(Content)`
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
`;

const SkillsHeader = styled.div`
  padding: 16px;
  background: #fff;
  border-radius: 4px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
`;

const SkillsMain = styled.div`
  flex: 1;
  display: flex;
  gap: 16px;
  min-height: 0;
`;

const SkillsList = styled(Card)`
  width: 280px;
  .ant-card-body {
    padding: 0;
    height: 100%;
  }
`;

const SkillsDetails = styled(Card)`
  flex: 1;
  .ant-card-body {
    padding: 0;
    height: 100%;
  }
`;

const Skills: React.FC = () => {
  return (
    <SkillsContainer>
      <SkillsContent>
        <SkillsHeader>
          <Title level={4} style={{ margin: 0 }}>Skills</Title>
        </SkillsHeader>
        <SkillsMain>
          <SkillsList title="Skills List" variant="borderless">
            {/* Skills list will be implemented here */}
          </SkillsList>
          <SkillsDetails variant="borderless">
            {/* Skills details will be implemented here */}
          </SkillsDetails>
        </SkillsMain>
      </SkillsContent>
    </SkillsContainer>
  );
};

export default Skills; 