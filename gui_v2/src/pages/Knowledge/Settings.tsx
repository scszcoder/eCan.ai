import React, { useState } from 'react';
import { 
  Card, 
  Form, 
  Input, 
  Button, 
  Switch, 
  Select, 
  Space, 
  Typography, 
  Divider,
  message,
  Tabs,
  Upload,
  Avatar
} from 'antd';
import { 
  UserOutlined,
  SettingOutlined,
  BellOutlined,
  SecurityScanOutlined,
  SaveOutlined,
  UploadOutlined
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

const { Option } = Select;
const { Title, Text } = Typography;
const { TabPane } = Tabs;

const Settings: React.FC = () => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);

  // Process save settings
  const handleSave = async (values: any) => {
    setLoading(true);
    try {
      // Simulate save
      await new Promise(resolve => setTimeout(resolve, 1000));
      message.success(t('pages.settings.settingsSaveSuccess'));
    } catch (error) {
      message.error(t('pages.settings.saveFailed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <Title level={4} style={{ margin: 0 }}>{t('pages.settings.system')}</Title>
      </div>

      <Tabs
        defaultActiveKey="profile"
        size="large"
        items={[
          {
            key: 'profile',
            label: <span><UserOutlined /> {t('pages.settings.profile')}</span>,
            children: (
              <Card>
                <Form
                  form={form}
                  layout="vertical"
                  onFinish={handleSave}
                  initialValues={{
                    username: 'Current User',
                    email: 'user@company.com',
                    department: 'Tech Department',
                    position: 'Development Engineer',
                    language: 'zh-CN',
                    timezone: 'Asia/Shanghai',
                  }}
                >
                  <div style={{ display: 'flex', gap: 24, marginBottom: 24 }}>
                    <div>
                      <Avatar size={80} icon={<UserOutlined />} />
                      <div style={{ marginTop: 8 }}>
                        <Upload>
                          <Button icon={<UploadOutlined />} size="small">
                            {t('pages.settings.changeAvatar')}
                          </Button>
                        </Upload>
                      </div>
                    </div>
                    <div style={{ flex: 1 }}>
                      <Form.Item
                        name="username"
                        label={t('pages.settings.username')}
                        rules={[{ required: true, message: t('pages.settings.pleaseEnterUsername') }]}
                      >
                        <Input />
                      </Form.Item>
                      
                      <Form.Item
                        name="email"
                        label={t('pages.settings.email')}
                        rules={[
                          { required: true, message: t('pages.settings.pleaseEnterEmail') },
                          { type: 'email', message: t('pages.settings.pleaseEnterValidEmail') }
                        ]}
                      >
                        <Input />
                      </Form.Item>
                    </div>
                  </div>

                  <Form.Item name="department" label={t('pages.settings.department')}>
                    <Input />
                  </Form.Item>

                  <Form.Item name="position" label={t('pages.settings.position')}>
                    <Input />
                  </Form.Item>

                  <Form.Item name="language" label={t('pages.settings.language')}>
                    <Select>
                      <Option value="zh-CN">{t('languages.zh-CN')}</Option>
                      <Option value="en-US">{t('languages.en-US')}</Option>
                    </Select>
                  </Form.Item>

                  <Form.Item name="timezone" label={t('pages.settings.timezone')}>
                    <Select>
                      <Option value="Asia/Shanghai">Asia/Shanghai (UTC+8)</Option>
                      <Option value="America/New_York">America/New_York (UTC-5)</Option>
                      <Option value="Europe/London">Europe/London (UTC+0)</Option>
                    </Select>
                  </Form.Item>

                  <Form.Item>
                    <Button type="primary" icon={<SaveOutlined />} loading={loading}>
                      {t('common.save')}
                    </Button>
                  </Form.Item>
                </Form>
              </Card>
            ),
          },
          {
            key: 'system',
            label: <span><SettingOutlined /> {t('pages.settings.system')}</span>,
            children: (
              <Card>
                <Form layout="vertical" onFinish={handleSave}>
                  <Title level={5}>{t('pages.settings.knowledgeSettings')}</Title>
                  
                  <Form.Item label={t('pages.settings.defaultKnowledge')}>
                    <Select defaultValue="default">
                      <Option value="default">{t('pages.settings.defaultKnowledgeBase')}</Option>
                      <Option value="tech">{t('pages.settings.technicalDocumentation')}</Option>
                      <Option value="product">{t('pages.settings.productDocumentation')}</Option>
                    </Select>
                  </Form.Item>

                  <Form.Item label={t('pages.settings.autoSaveDocument')}>
                    <Switch defaultChecked />
                  </Form.Item>

                  <Form.Item label={t('pages.settings.autoSaveInterval')}>
                    <Select defaultValue="30" disabled>
                      <Option value="30">{t('pages.settings.30seconds')}</Option>
                      <Option value="60">{t('pages.settings.1minute')}</Option>
                      <Option value="300">{t('pages.settings.5minutes')}</Option>
                    </Select>
                  </Form.Item>

                  <Divider />

                  <Title level={5}>{t('pages.settings.qaSettings')}</Title>
                  
                  <Form.Item label={t('pages.settings.answerLength')}>
                    <Select defaultValue="detailed">
                      <Option value="brief">{t('pages.settings.brief')}</Option>
                      <Option value="detailed">{t('pages.settings.detailed')}</Option>
                      <Option value="comprehensive">{t('pages.settings.comprehensive')}</Option>
                    </Select>
                  </Form.Item>

                  <Form.Item label={t('pages.settings.autoTransfer')}>
                    <Switch defaultChecked />
                  </Form.Item>

                  <Form.Item label={t('pages.settings.autoCategory')}>
                    <Switch defaultChecked />
                  </Form.Item>

                  <Divider />

                  <Title level={5}>{t('pages.settings.uiSettings')}</Title>
                  
                  <Form.Item label={t('pages.settings.theme')}>
                    <Select defaultValue="light">
                      <Option value="light">{t('pages.settings.lightTheme')}</Option>
                      <Option value="dark">{t('pages.settings.darkTheme')}</Option>
                      <Option value="auto">{t('pages.settings.followSystem')}</Option>
                    </Select>
                  </Form.Item>

                  <Form.Item label={t('pages.settings.fontSize')}>
                    <Select defaultValue="medium">
                      <Option value="small">{t('pages.settings.small')}</Option>
                      <Option value="medium">{t('pages.settings.medium')}</Option>
                      <Option value="large">{t('pages.settings.large')}</Option>
                    </Select>
                  </Form.Item>

                  <Form.Item label={t('pages.settings.compactMode')}>
                    <Switch />
                  </Form.Item>

                  <Form.Item>
                    <Button type="primary" icon={<SaveOutlined />} loading={loading}>
                      {t('common.save')}
                    </Button>
                  </Form.Item>
                </Form>
              </Card>
            ),
          },
          {
            key: 'notifications',
            label: <span><BellOutlined /> {t('pages.settings.notifications')}</span>,
            children: (
              <Card>
                <Form layout="vertical" onFinish={handleSave}>
                  <Title level={5}>{t('pages.settings.emailNotifications')}</Title>
                  
                  <Form.Item label={t('pages.settings.newCommentNotification')}>
                    <Switch defaultChecked />
                  </Form.Item>

                  <Form.Item label={t('pages.settings.mentionNotification')}>
                    <Switch defaultChecked />
                  </Form.Item>

                  <Form.Item label={t('pages.settings.documentUpdateNotification')}>
                    <Switch />
                  </Form.Item>

                  <Form.Item label={t('pages.settings.qaReplyNotification')}>
                    <Switch defaultChecked />
                  </Form.Item>

                  <Divider />

                  <Title level={5}>{t('pages.settings.systemNotifications')}</Title>
                  
                  <Form.Item label={t('pages.settings.maintenanceNotification')}>
                    <Switch defaultChecked />
                  </Form.Item>

                  <Form.Item label={t('pages.settings.featureUpdateNotification')}>
                    <Switch defaultChecked />
                  </Form.Item>

                  <Form.Item label={t('pages.settings.securityReminder')}>
                    <Switch defaultChecked />
                  </Form.Item>

                  <Divider />

                  <Title level={5}>{t('pages.settings.notificationFrequency')}</Title>
                  
                  <Form.Item label={t('pages.settings.emailDigest')}>
                    <Select defaultValue="daily">
                      <Option value="immediate">{t('pages.settings.immediate')}</Option>
                      <Option value="hourly">{t('pages.settings.hourly')}</Option>
                      <Option value="daily">{t('pages.settings.daily')}</Option>
                      <Option value="weekly">{t('pages.settings.weekly')}</Option>
                    </Select>
                  </Form.Item>

                  <Form.Item>
                    <Button type="primary" icon={<SaveOutlined />} loading={loading}>
                      {t('common.save')}
                    </Button>
                  </Form.Item>
                </Form>
              </Card>
            ),
          },
          {
            key: 'security',
            label: <span><SecurityScanOutlined /> {t('pages.settings.security')}</span>,
            children: (
              <Card>
                <Form layout="vertical" onFinish={handleSave}>
                  <Title level={5}>{t('pages.settings.passwordSettings')}</Title>
                  
                  <Form.Item
                    name="currentPassword"
                    label={t('pages.settings.currentPassword')}
                    rules={[{ required: true, message: t('pages.settings.pleaseEnterCurrentPassword') }]}
                  >
                    <Input.Password />
                  </Form.Item>

                  <Form.Item
                    name="newPassword"
                    label={t('pages.settings.newPassword')}
                    rules={[
                      { required: true, message: t('pages.settings.pleaseEnterNewPassword') },
                      { min: 8, message: t('pages.settings.passwordMinLength') }
                    ]}
                  >
                    <Input.Password />
                  </Form.Item>

                  <Form.Item
                    name="confirmPassword"
                    label={t('pages.settings.confirmNewPassword')}
                    rules={[
                      { required: true, message: t('pages.settings.pleaseConfirmNewPassword') },
                      ({ getFieldValue }) => ({
                        validator(_, value) {
                          if (!value || getFieldValue('newPassword') === value) {
                            return Promise.resolve();
                          }
                          return Promise.reject(new Error(t('pages.settings.passwordsDoNotMatch')));
                        },
                      }),
                    ]}
                  >
                    <Input.Password />
                  </Form.Item>

                  <Divider />

                  <Title level={5}>{t('pages.settings.loginSecurity')}</Title>
                  
                  <Form.Item label={t('pages.settings.twoFactorAuth')}>
                    <Switch />
                  </Form.Item>

                  <Form.Item label={t('pages.settings.deviceManagement')}>
                    <Button>{t('pages.settings.viewDevices')}</Button>
                  </Form.Item>

                  <Form.Item label={t('pages.settings.loginHistory')}>
                    <Button>{t('pages.settings.viewHistory')}</Button>
                  </Form.Item>

                  <Divider />

                  <Title level={5}>{t('pages.settings.dataExport')}</Title>
                  
                  <Form.Item label={t('pages.settings.exportPersonalData')}>
                    <Button>{t('pages.settings.exportData')}</Button>
                  </Form.Item>

                  <Form.Item>
                    <Button type="primary" icon={<SaveOutlined />} loading={loading}>
                      {t('common.save')}
                    </Button>
                  </Form.Item>
                </Form>
              </Card>
            ),
          },
        ]}
      />
    </div>
  );
};

export default Settings;
