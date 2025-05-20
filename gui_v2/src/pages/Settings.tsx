import React from 'react';
import { useTranslation } from 'react-i18next';
import { Card, Form, Select, Switch, Button, App } from 'antd';
import { useTheme } from '../contexts/ThemeContext';
import { useLanguage } from '../contexts/LanguageContext';
import { useIPC } from '../hooks/useIPC';

const { Option } = Select;

type Theme = 'light' | 'dark' | 'system';

interface SettingsFormData {
  theme: string;
  language: string;
  notifications: boolean;
  autoUpdate: boolean;
  [key: string]: string | boolean;
}

const Settings: React.FC = () => {
  const { t, i18n } = useTranslation();
  const { theme, changeTheme } = useTheme();
  const { changeLanguage } = useLanguage();
  const [form] = Form.useForm();
  const { sendCommand } = useIPC();
  const { message } = App.useApp();

  React.useEffect(() => {
    // 初始化表单值
    form.setFieldsValue({
      theme: theme,
      language: localStorage.getItem('language') || 'en-US',
      notifications: localStorage.getItem('notifications') === 'true',
      autoUpdate: localStorage.getItem('autoUpdate') === 'true'
    });
  }, [form, theme]);

  // 语言切换处理
  const handleLanguageChange = async (value: string) => {
    try {
      localStorage.setItem('i18nextLng', value);
      await i18n.changeLanguage(value);
      changeLanguage(value);
      message.success(t('settings.languageChanged'));
    } catch {
      message.error(t('settings.languageChangeError'));
    }
  };

  // 主题切换处理
  const handleThemeChange = (value: Theme) => {
    changeTheme(value);
    localStorage.setItem('theme', value);
    message.success(t('settings.themeChanged'));
  };

  // 通知设置切换处理
  const handleNotificationChange = (checked: boolean) => {
    localStorage.setItem('notifications', String(checked));
    form.setFieldsValue({ notifications: checked });
  };

  // 自动更新设置切换处理
  const handleAutoUpdateChange = (checked: boolean) => {
    localStorage.setItem('autoUpdate', String(checked));
    form.setFieldsValue({ autoUpdate: checked });
  };

  const onFinish = async (values: SettingsFormData) => {
    try {
      // 发送设置到后端
      await sendCommand('save_settings', values);
      
      // 更新本地设置
      localStorage.setItem('language', values.language);
      localStorage.setItem('notifications', String(values.notifications));
      localStorage.setItem('autoUpdate', String(values.autoUpdate));
      
      // 更新主题
      changeTheme(values.theme as 'light' | 'dark' | 'system');
      
      message.success(t('settings.saved'));
    } catch (error) {
      console.error('Failed to save settings:', error);
      message.error(t('settings.saveError', { error: String(error) }));
    }
  };

  return (
    <div className="settings-container">
      <Card title={t('settings.title')} className="settings-card">
        <Form
          form={form}
          layout="vertical"
          onFinish={onFinish}
          initialValues={{
            theme: theme,
            language: localStorage.getItem('language') || 'en-US',
            notifications: localStorage.getItem('notifications') === 'true',
            autoUpdate: localStorage.getItem('autoUpdate') === 'true'
          }}
        >
          <Form.Item
            label={t('settings.language')}
            name="language"
          >
            <Select onChange={handleLanguageChange}>
              <Option value="en-US">{t('languages.en-US')}</Option>
              <Option value="zh-CN">{t('languages.zh-CN')}</Option>
            </Select>
          </Form.Item>

          <Form.Item
            label={t('settings.theme')}
            name="theme"
          >
            <Select onChange={handleThemeChange}>
              <Option value="light">{t('settings.theme.light')}</Option>
              <Option value="dark">{t('settings.theme.dark')}</Option>
              <Option value="system">{t('settings.theme.system')}</Option>
            </Select>
          </Form.Item>

          <Form.Item
            label={t('settings.notifications')}
            name="notifications"
            valuePropName="checked"
          >
            <Switch onChange={handleNotificationChange} />
          </Form.Item>

          <Form.Item
            label={t('settings.autoUpdate')}
            name="autoUpdate"
            valuePropName="checked"
          >
            <Switch onChange={handleAutoUpdateChange} />
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit">
              {t('common.save')}
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
};

export default Settings; 