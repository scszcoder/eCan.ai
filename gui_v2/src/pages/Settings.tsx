import React from 'react';
import { Card, Form, Input, Switch, Select, Button, Typography, Space, Divider, Tabs } from 'antd';
import { 
    SettingOutlined,
    UserOutlined,
    LockOutlined,
    BellOutlined,
    GlobalOutlined,
    CloudOutlined,
    SafetyOutlined
} from '@ant-design/icons';
import styled from '@emotion/styled';

const { Title, Text } = Typography;
const { Option } = Select;

const SettingsContainer = styled.div`
    max-width: 800px;
    margin: 0 auto;
    padding: 24px;
`;

const SettingSection = styled(Card)`
    margin-bottom: 24px;
`;

const SettingItem = styled.div`
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 0;
    border-bottom: 1px solid #f0f0f0;
    &:last-child {
        border-bottom: none;
    }
`;

const Settings: React.FC = () => {
    const [form] = Form.useForm();

    const handleSave = (values: any) => {
        console.log('Save settings:', values);
    };

    return (
        <SettingsContainer>
            <Title level={2}>
                <SettingOutlined /> Settings
            </Title>
            <Tabs
                defaultActiveKey="general"
                items={[
                    {
                        key: 'general',
                        label: 'General',
                        children: (
                            <Form
                                form={form}
                                layout="vertical"
                                onFinish={handleSave}
                            >
                                <SettingSection variant="borderless" title="General Settings">
                                    <Form.Item
                                        label="System Name"
                                        name="systemName"
                                        initialValue="ECBot System"
                                    >
                                        <Input prefix={<SettingOutlined />} />
                                    </Form.Item>
                                    <Form.Item
                                        label="Language"
                                        name="language"
                                        initialValue="en"
                                    >
                                        <Select>
                                            <Option value="en">English</Option>
                                            <Option value="zh">中文</Option>
                                        </Select>
                                    </Form.Item>
                                    <Form.Item
                                        label="Time Zone"
                                        name="timezone"
                                        initialValue="UTC+8"
                                    >
                                        <Select>
                                            <Option value="UTC+8">UTC+8 (Beijing)</Option>
                                            <Option value="UTC+0">UTC+0 (London)</Option>
                                            <Option value="UTC-8">UTC-8 (Los Angeles)</Option>
                                        </Select>
                                    </Form.Item>
                                </SettingSection>

                                <SettingSection variant="borderless" title="User Settings">
                                    <Form.Item
                                        label="Username"
                                        name="username"
                                        initialValue="admin"
                                    >
                                        <Input prefix={<UserOutlined />} />
                                    </Form.Item>
                                    <Form.Item
                                        label="Email"
                                        name="email"
                                        initialValue="admin@example.com"
                                    >
                                        <Input type="email" />
                                    </Form.Item>
                                    <Form.Item
                                        label="Password"
                                        name="password"
                                    >
                                        <Input.Password prefix={<LockOutlined />} />
                                    </Form.Item>
                                </SettingSection>

                                <SettingSection variant="borderless" title="Notification Settings">
                                    <Form.Item
                                        label="Email Notifications"
                                        name="emailNotifications"
                                        valuePropName="checked"
                                        initialValue={true}
                                    >
                                        <Switch />
                                    </Form.Item>
                                    <Form.Item
                                        label="System Alerts"
                                        name="systemAlerts"
                                        valuePropName="checked"
                                        initialValue={true}
                                    >
                                        <Switch />
                                    </Form.Item>
                                    <Form.Item
                                        label="Task Updates"
                                        name="taskUpdates"
                                        valuePropName="checked"
                                        initialValue={true}
                                    >
                                        <Switch />
                                    </Form.Item>
                                </SettingSection>

                                <SettingSection variant="borderless" title="System Settings">
                                    <Form.Item
                                        label="Auto Backup"
                                        name="autoBackup"
                                        valuePropName="checked"
                                        initialValue={true}
                                    >
                                        <Switch />
                                    </Form.Item>
                                    <Form.Item
                                        label="Backup Frequency"
                                        name="backupFrequency"
                                        initialValue="daily"
                                    >
                                        <Select>
                                            <Option value="hourly">Hourly</Option>
                                            <Option value="daily">Daily</Option>
                                            <Option value="weekly">Weekly</Option>
                                        </Select>
                                    </Form.Item>
                                    <Form.Item
                                        label="Log Level"
                                        name="logLevel"
                                        initialValue="info"
                                    >
                                        <Select>
                                            <Option value="debug">Debug</Option>
                                            <Option value="info">Info</Option>
                                            <Option value="warning">Warning</Option>
                                            <Option value="error">Error</Option>
                                        </Select>
                                    </Form.Item>
                                </SettingSection>

                                <Form.Item>
                                    <Space>
                                        <Button type="primary" htmlType="submit">
                                            Save Changes
                                        </Button>
                                        <Button>
                                            Reset to Default
                                        </Button>
                                    </Space>
                                </Form.Item>
                            </Form>
                        ),
                    },
                    {
                        key: 'security',
                        label: 'Security',
                        children: (
                            <SettingSection variant="borderless" title="Security Settings">
                                <SettingItem>
                                    <Space>
                                        <SafetyOutlined />
                                        <div>
                                            <Text strong>Two-Factor Authentication</Text>
                                            <br />
                                            <Text type="secondary">Enable 2FA for additional security</Text>
                                        </div>
                                    </Space>
                                    <Switch defaultChecked={false} />
                                </SettingItem>
                                <SettingItem>
                                    <Space>
                                        <LockOutlined />
                                        <div>
                                            <Text strong>Session Timeout</Text>
                                            <br />
                                            <Text type="secondary">Automatically log out after inactivity</Text>
                                        </div>
                                    </Space>
                                    <Select defaultValue="30" style={{ width: 120 }}>
                                        <Option value="15">15 minutes</Option>
                                        <Option value="30">30 minutes</Option>
                                        <Option value="60">1 hour</Option>
                                    </Select>
                                </SettingItem>
                                <SettingItem>
                                    <Space>
                                        <CloudOutlined />
                                        <div>
                                            <Text strong>API Access</Text>
                                            <br />
                                            <Text type="secondary">Manage API keys and access tokens</Text>
                                        </div>
                                    </Space>
                                    <Button>Manage</Button>
                                </SettingItem>
                            </SettingSection>
                        ),
                    },
                ]}
            />
        </SettingsContainer>
    );
};

export default Settings; 