import React, { useState } from 'react';
import { Layout, List, Card, Typography, Button, Space, Form, Input, Switch, Select, Slider, Radio } from 'antd';
import styled from '@emotion/styled';

const { Content } = Layout;
const { Text } = Typography;

const SettingsContainer = styled(Layout)`
  height: calc(100vh - 112px);
`;

const SettingsList = styled.div`
  width: 25%;
  border-right: 1px solid #f0f0f0;
  overflow-y: auto;
`;

const SettingsMain = styled.div`
  width: 75%;
  display: flex;
  flex-direction: column;
`;

const SettingsForm = styled.div`
  flex: 3;
  padding: 20px;
  overflow-y: auto;
`;

const SettingsActions = styled.div`
  flex: 1;
  padding: 20px;
  border-top: 1px solid #f0f0f0;
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 16px;
`;

const Settings: React.FC = () => {
  const [settings] = useState([
    { id: 'fingerprints', name: 'Fingerprints' },
    { id: 'schedule', name: 'Schedule' },
    { id: 'debug', name: 'Debug' },
    { id: 'network', name: 'Network' },
    { id: 'printer', name: 'Printer' },
  ]);

  const [selectedSetting] = useState(settings[0]);

  return (
    <SettingsContainer>
      <SettingsList>
        <List
          dataSource={settings}
          renderItem={item => (
            <List.Item>
              <Text>{item.name}</Text>
            </List.Item>
          )}
        />
      </SettingsList>
      <SettingsMain>
        <SettingsForm>
          <Card>
            <Form layout="vertical">
              <Form.Item label="Enable Debug Mode">
                <Switch defaultChecked />
              </Form.Item>

              <Form.Item label="Log Level">
                <Select
                  defaultValue="info"
                  options={[
                    { value: 'debug', label: 'Debug' },
                    { value: 'info', label: 'Info' },
                    { value: 'warn', label: 'Warning' },
                    { value: 'error', label: 'Error' },
                  ]}
                />
              </Form.Item>

              <Form.Item label="API Endpoint">
                <Input defaultValue="http://localhost:3000/api" />
              </Form.Item>

              <Form.Item label="Connection Timeout (ms)">
                <Slider
                  min={1000}
                  max={10000}
                  step={1000}
                  defaultValue={5000}
                  marks={{
                    1000: '1s',
                    5000: '5s',
                    10000: '10s',
                  }}
                />
              </Form.Item>

              <Form.Item label="Authentication Method">
                <Radio.Group defaultValue="jwt">
                  <Radio value="jwt">JWT</Radio>
                  <Radio value="oauth">OAuth</Radio>
                  <Radio value="basic">Basic Auth</Radio>
                </Radio.Group>
              </Form.Item>

              <Form.Item label="Cache Duration">
                <Select
                  defaultValue="1h"
                  options={[
                    { value: '5m', label: '5 minutes' },
                    { value: '15m', label: '15 minutes' },
                    { value: '30m', label: '30 minutes' },
                    { value: '1h', label: '1 hour' },
                    { value: '4h', label: '4 hours' },
                    { value: '1d', label: '1 day' },
                  ]}
                />
              </Form.Item>

              <Form.Item label="Max Retry Attempts">
                <Input type="number" defaultValue={3} min={1} max={10} />
              </Form.Item>

              <Form.Item label="Enable Auto-Save">
                <Switch defaultChecked />
              </Form.Item>

              <Form.Item label="Auto-Save Interval">
                <Select
                  defaultValue="5m"
                  options={[
                    { value: '1m', label: '1 minute' },
                    { value: '5m', label: '5 minutes' },
                    { value: '15m', label: '15 minutes' },
                    { value: '30m', label: '30 minutes' },
                  ]}
                />
              </Form.Item>
            </Form>
          </Card>
        </SettingsForm>
        <SettingsActions>
          <Button>Cancel</Button>
          <Button type="primary">Save Changes</Button>
        </SettingsActions>
      </SettingsMain>
    </SettingsContainer>
  );
};

export default Settings; 