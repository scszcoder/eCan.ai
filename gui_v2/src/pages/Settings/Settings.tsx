import React, { useState, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, Form, Select, Switch, Button, App, Space } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useTheme } from '../../contexts/ThemeContext';
import { useLanguage } from '../../contexts/LanguageContext';
import { logger } from '../../utils/logger';
import { IPCAPI } from '@/services/ipc/api';
import { useUserStore } from '../../stores/userStore';

type Theme = 'light' | 'dark' | 'system';

interface SettingsFormData {
  theme: string;
  language: string;
  notifications: boolean;
  autoUpdate: boolean;
  [key: string]: string | boolean;
}

const settingsEventBus = {
    listeners: new Set<(data: SettingsFormData) => void>(),
    subscribe(listener: (data: SettingsFormData) => void) {
        this.listeners.add(listener);
        return () => this.listeners.delete(listener);
    },
    emit(data: SettingsFormData) {
        this.listeners.forEach(listener => listener(data));
    }
};

// 导出更新数据的函数
export const updateSettingsGUI = (data: SettingsFormData) => {
    settingsEventBus.emit(data);
};

const Settings: React.FC = () => {
  const { t, i18n } = useTranslation();
  const { theme, changeTheme } = useTheme();
  const { changeLanguage } = useLanguage();
  const [form] = Form.useForm<SettingsFormData>();
  const { message } = App.useApp();
  const [loading, setLoading] = useState(false);
  const username = useUserStore((state) => state.username);

  // 加载设置
  const loadSettings = useCallback(async () => {
    try {
      setLoading(true);
      const response = await IPCAPI.getInstance().getSettings(username);
      if (response && response.success && response.data) {
        const settings = response.data;
        form.setFieldsValue({
          theme: settings.theme || theme,
          language: settings.language || localStorage.getItem('language') || 'en-US',
          notifications: settings.notifications || localStorage.getItem('notifications') === 'true',
          autoUpdate: settings.autoUpdate || localStorage.getItem('autoUpdate') === 'true'
        });
      } else {
        // Handle case where response is not successful
        logger.warn('Settings response was not successful:', response);
        // Set default values from localStorage
        form.setFieldsValue({
          theme: localStorage.getItem('theme') || theme,
          language: localStorage.getItem('language') || 'en-US',
          notifications: localStorage.getItem('notifications') === 'true',
          autoUpdate: localStorage.getItem('autoUpdate') === 'true'
        });
      }
    } catch (error) {
      logger.error('Failed to load settings:', error instanceof Error ? error.message : 'Unknown error');
      // Set default values from localStorage on error
      form.setFieldsValue({
        theme: localStorage.getItem('theme') || theme,
        language: localStorage.getItem('language') || 'en-US',
        notifications: localStorage.getItem('notifications') === 'true',
        autoUpdate: localStorage.getItem('autoUpdate') === 'true'
      });
      message.error(t('settings.loadError'));
    } finally {
      setLoading(false);
    }
  }, [form, theme, t, message]);

  // 初始化加载设置
  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  // 处理刷新
  const handleRefresh = useCallback(async () => {
    await loadSettings();
    message.success(t('settings.refreshed'));
  }, [loadSettings, message, t]);

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
    message.success(t('settings.notificationsChanged'));
  };

  // 自动更新设置切换处理
  const handleAutoUpdateChange = (checked: boolean) => {
    localStorage.setItem('autoUpdate', String(checked));
    form.setFieldsValue({ autoUpdate: checked });
    message.success(t('settings.autoUpdateChanged'));
  };

  const handleSave = async (values: SettingsFormData) => {
    try {
      setLoading(true);
      // 保存设置到后端
      const response = await IPCAPI.getInstance().saveSettings(values);

      if (response && response.success) {
        // 更新本地设置
        localStorage.setItem('language', values.language);
        localStorage.setItem('notifications', String(values.notifications));
        localStorage.setItem('autoUpdate', String(values.autoUpdate));

        // 更新主题
        changeTheme(values.theme as 'light' | 'dark' | 'system');

        message.success(t('settings.saved'));
      } else {
        throw new Error(response?.message || 'Failed to save settings');
      }
    } catch (error) {
      logger.error('Failed to save settings:', error);
      message.error(t('settings.saveError'));
    } finally {
      setLoading(false);
    }
  };

  const cardTitle = (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span>{t('settings.title')}</span>
      <Button
        type="text"
        icon={<ReloadOutlined style={{ color: 'white' }} />}
        onClick={handleRefresh}
        loading={loading}
        title={t('settings.refresh')}
      />
    </div>
  );

  return (
    <div className="settings-container">
      <Card
        title={cardTitle}
        className="settings-card"
        loading={loading}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSave}
          preserve={false}
        >
          <Form.Item
            label={t('settings.language')}
            name="language"
          >
            <Select onChange={handleLanguageChange} disabled={loading}>
              <Select.Option value="en-US">{t('languages.en-US')}</Select.Option>
              <Select.Option value="zh-CN">{t('languages.zh-CN')}</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item
            label={t('settings.theme')}
            name="theme"
          >
            <Select onChange={handleThemeChange} disabled={loading}>
              <Select.Option value="light">{t('settings.theme.light')}</Select.Option>
              <Select.Option value="dark">{t('settings.theme.dark')}</Select.Option>
              <Select.Option value="system">{t('settings.theme.system')}</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item
            label={t('settings.notifications')}
            name="notifications"
            valuePropName="checked"
          >
            <Switch
              onChange={handleNotificationChange}
              disabled={loading}
            />
          </Form.Item>

          <Form.Item
            label={t('settings.autoUpdate')}
            name="autoUpdate"
            valuePropName="checked"
          >
            <Switch
              onChange={handleAutoUpdateChange}
              disabled={loading}
            />
          </Form.Item>

          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
            >
              {t('common.save')}
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
};

export default Settings;