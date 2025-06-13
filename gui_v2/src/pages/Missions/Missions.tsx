import React, { useState } from 'react';
import { Layout, List, Avatar, Select, Card, Typography, Tag, Button, Space } from 'antd';
import { RocketOutlined, EditOutlined, PauseOutlined, PlayCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import {ipc_api} from '../../services/ipc_api';

const { Content } = Layout;
const { Text } = Typography;

const MissionsContainer = styled(Layout)`
  height: calc(100vh - 112px);
`;

const MissionList = styled.div`
  width: 25%;
  border-right: 1px solid #f0f0f0;
  overflow-y: auto;
`;

const MissionMain = styled.div`
  width: 75%;
  display: flex;
  flex-direction: column;
`;

const MissionDetails = styled.div`
  flex: 1;
  padding: 20px;
  overflow-y: auto;
`;

const MissionLog = styled.div`
  flex: 1;
  padding: 20px;
  border-top: 1px solid #f0f0f0;
  background: #f5f5f5;
  font-family: monospace;
  overflow-y: auto;
`;

const SortSelect = styled(Select)`
  width: 100%;
  margin-bottom: 16px;
`;

const Missions: React.FC = () => {
  const [missions] = useState([
    {
      id: 1,
      name: 'Mission 1',
      type: 'browse',
      status: 'running',
      botId: 'BOT001',
    },
    {
      id: 2,
      name: 'Mission 2',
      type: 'buy',
      status: 'completed',
      botId: 'BOT002',
    },
  ]);

  const [selectedMission] = useState(missions[0]);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running':
        return 'processing';
      case 'completed':
        return 'success';
      case 'failed':
        return 'error';
      default:
        return 'default';
    }
  };

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'browse':
        return 'blue';
      case 'buy':
        return 'green';
      case 'sell':
        return 'red';
      default:
        return 'default';
    }
  };

  return (
    <MissionsContainer>
      <MissionList>
        <SortSelect
          defaultValue="name"
          options={[
            { value: 'name', label: 'By Name' },
            { value: 'id', label: 'By ID' },
            { value: 'date', label: 'By Date' },
          ]}
        />
        <List
          dataSource={missions}
          renderItem={item => (
            <List.Item>
              <List.Item.Meta
                avatar={<Avatar icon={<RocketOutlined />} />}
                title={item.name}
                description={`ID: ${item.id}`}
              />
            </List.Item>
          )}
        />
      </MissionList>
      <MissionMain>
        <MissionDetails>
          <Card>
            <Space direction="vertical" size="large" style={{ width: '100%' }}>
              <div>
                <Avatar size={64} icon={<RocketOutlined />} />
                <div style={{ marginTop: 16 }}>
                  <Text strong>ID: </Text>
                  <Text>{selectedMission.id}</Text>
                  <br />
                  <Text strong>Name: </Text>
                  <Text>{selectedMission.name}</Text>
                  <br />
                  <Text strong>Type: </Text>
                  <Tag color={getTypeColor(selectedMission.type)}>
                    {selectedMission.type.toUpperCase()}
                  </Tag>
                  <br />
                  <Text strong>Bot: </Text>
                  <Text>{selectedMission.botId}</Text>
                  <br />
                  <Text strong>Status: </Text>
                  <Tag color={getStatusColor(selectedMission.status)}>
                    {selectedMission.status.toUpperCase()}
                  </Tag>
                </div>
              </div>
              <div>
                <Text strong>Required Skills:</Text>
                <List
                  size="small"
                  dataSource={['Skill 1', 'Skill 2', 'Skill 3']}
                  renderItem={item => (
                    <List.Item>
                      <Text>{item}</Text>
                    </List.Item>
                  )}
                />
              </div>
            </Space>
          </Card>
        </MissionDetails>
        <MissionLog>
          <div style={{ marginBottom: 16 }}>
            <Space>
              <Button icon={<EditOutlined />}>Edit</Button>
              <Button icon={<PauseOutlined />}>Pause</Button>
              <Button icon={<PlayCircleOutlined />}>Resume</Button>
              <Button icon={<ReloadOutlined />}>Rerun</Button>
            </Space>
          </div>
          <div>
            <Text type="secondary">[10:00:00] Mission started</Text>
            <br />
            <Text type="secondary">[10:00:01] Initializing bot...</Text>
            <br />
            <Text type="secondary">[10:00:02] Bot connected successfully</Text>
            <br />
            <Text type="secondary">[10:00:03] Starting mission execution...</Text>
          </div>
        </MissionLog>
      </MissionMain>
    </MissionsContainer>
  );
};

export default Missions; 