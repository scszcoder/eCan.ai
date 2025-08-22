import React, { useState, useCallback, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, Form, Select, Switch, Button, App, Input, Row, Col } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useTheme } from '../../contexts/ThemeContext';
import { useLanguage } from '../../contexts/LanguageContext';
import { logger } from '../../utils/logger';
import type { Settings } from './types';
import { useUserStore } from '../../stores/userStore';
import { get_ipc_api } from '@/services/ipc_api';
import { useLocation } from 'react-router-dom';

// type Theme = 'light' | 'dark' | 'system';

const initialSettings: Settings = {
  api_api_port: '',
  debug_mode: false,
  default_wifi: '',
  default_printer: '',
  display_resolution: '',
  default_webdriver: '',
  img_engine: '',
  localUserDB_host: '',
  localUserDB_port: '',
  localAgentDB_host: '',
  localAgentDB_port: '',
  localAgent_ports: [],
  local_server_port: '',
  lan_api_endpoint: '',
  lan_api_host: '',
  last_bots_file: '',
  last_bots_file_time: '',
  mids_forced_to_run: [],
  new_orders_dir: '',
  new_bots_file_path: '',
  wan_api_endpoint: '',
  ws_api_endpoint: '',
  schedule_engine: '',
  schedule_mode: '',
};

const Settings: React.FC = () => {
  const { t, i18n } = useTranslation();
  const { theme, changeTheme } = useTheme();
  const { changeLanguage } = useLanguage();
  const [form] = Form.useForm<Settings>();
  const { message } = App.useApp();
  const [loading, setLoading] = useState(false);
  const username = useUserStore((state) => state.username);
  const [pageForm] = Form.useForm<{ language: string; theme: 'light' | 'dark' | 'system' }>();
  const location = useLocation();
  // 优先使用当前操作系统/浏览器语言
  const getDefaultLanguage = () => {
    const browserLang = navigator.language;
    if (browserLang === 'zh-CN' || browserLang === 'en-US') return browserLang;
    return 'zh-CN';
  };

  const isMountedRef = useRef(false);

  useEffect(() => {
    isMountedRef.current = true;
    return () => { isMountedRef.current = false; };
  }, []);

  // 加载设置
  const loadSettings = useCallback(async () => {
    if (!username) return;
    try {
      setLoading(true);
      const response = await get_ipc_api().getSettings<{ settings: Settings }>(username);
      console.log(response.data);
      if (response && response.success && response.data) {
        const settings = response.data.settings;
        if (isMountedRef.current) {
          form.setFieldsValue({
            ...settings
          });
        }
      } else {
        logger.warn('Settings response was not successful:', response);
        if (isMountedRef.current) {
          form.setFieldsValue({});
        }
      }
    } catch (error) {
      logger.error('Failed to load settings:', error instanceof Error ? error.message : 'Unknown error');
      if (isMountedRef.current) {
        form.setFieldsValue({});
      }
      message.error('Failed to load settings');
    } finally {
      setLoading(false);
    }
  }, [form, username]);

  // 初始化加载设置
  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  // 处理刷新
  const handleRefresh = useCallback(async () => {
    await loadSettings();
    message.success(t('pages.settings.refreshed'));
  }, [loadSettings, message, t]);

  // 页面设置保存
  const handlePageThemeChange = (value: 'light' | 'dark' | 'system') => {
    saveScroll();
    changeTheme(value);
    message.success(t('pages.settings.themeChanged'));
    setTimeout(restoreScroll, 0);
  };
  const handlePageLanguageChange = async (value: string) => {
    saveScroll();
    try {
      await i18n.changeLanguage(value);
      changeLanguage(value);
      message.success(t('pages.settings.languageChanged'));
      setTimeout(restoreScroll, 0);
      console.log('当前语言已切换为:', i18n.language);
    } catch (e) {
      message.error(t('pages.settings.languageChangeError'));
      console.error('语言切换失败:', e);
    }
  };

  const handleSave = async (values: Settings) => {
    try {
      setLoading(true);
      const response = await get_ipc_api().saveSettings(values);
      if (response && response.success) {
        message.success(t('pages.settings.saved'));
      } else {
        throw new Error(response?.error?.message || 'Failed to save settings');
      }
    } catch (error) {
      logger.error('Failed to save settings:', error);
      message.error(t('pages.settings.saveError'));
    } finally {
      setLoading(false);
    }
  };

  // 统一 label 国际化函数
  const getLabel = (key: string) =>
    t(`pages.settings.${key}`) ||
    t(`settings.${key}`) ||
    t(`settingsForm.${key}`) ||
    key;

  const cardTitle = (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span>{t('pages.settings.title')}</span>
      <Button
        type="text"
        icon={<ReloadOutlined style={{ color: 'white' }} />}
        onClick={handleRefresh}
        loading={loading}
        title={t('pages.settings.refresh')}
      />
    </div>
  );

  const containerRef = useRef<HTMLDivElement>(null);
  const saveScroll = () => {
    const container = containerRef.current;
    if (container) {
      localStorage.setItem('settingsScrollTop', String(container.scrollTop));
    }
  };
  const restoreScroll = () => {
    const container = containerRef.current;
    if (container) {
      const saved = localStorage.getItem('settingsScrollTop');
      if (saved) {
        container.scrollTop = Number(saved);
      }
    }
  };

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const handleScroll = () => {
      localStorage.setItem('settingsScrollTop', String(container.scrollTop));
    };
    container.addEventListener('scroll', handleScroll);
    // 页面加载时恢复滚动
    const saved = localStorage.getItem('settingsScrollTop');
    if (saved) {
      container.scrollTop = Number(saved);
    }
    return () => {
      container.removeEventListener('scroll', handleScroll);
    };
  }, []);

  return (
    <div
      className="settings-container"
      ref={containerRef}
      style={{ height: '100%', maxHeight: 'calc(100vh - 64px)', overflowY: 'auto' }}
    >
      <Card
        title={cardTitle}
        className="settings-card"
        loading={loading}
        styles={{ body: { padding: 16 } }}
        style={{ maxWidth: 1200, margin: '0 auto' }}
      >
        {/* 其余设置分组 */}
        <Form
          key={location.pathname + '-main'}
          form={form}
          layout="vertical"
          onFinish={handleSave}
          initialValues={initialSettings}
          preserve={false}
        >
          {/* 基础设置（去除语言和主题） */}
          <Card title={getLabel('basic')} style={{ marginBottom: 8 }} styles={{ body: { padding: 12 } }}>
            <Row gutter={12}>
              <Col span={12}><Form.Item label={getLabel('display_resolution')} name="display_resolution"><Input size="small" placeholder={getLabel('display_resolution')} /></Form.Item></Col>
              <Col span={12}><Form.Item label={getLabel('debug_mode')} name="debug_mode" valuePropName="checked"><Switch size="small" /></Form.Item></Col>
              <Col span={12}><Form.Item label={getLabel('default_wifi')} name="default_wifi"><Input size="small" placeholder={getLabel('default_wifi')} /></Form.Item></Col>
              <Col span={12}><Form.Item label={getLabel('default_webdriver')} name="default_webdriver"><Input size="small" placeholder={getLabel('default_webdriver')} /></Form.Item></Col>
            </Row>
          </Card>
          {/* 网络与端口 */}
          <Card title={getLabel('network')} style={{ marginBottom: 8 }} styles={{ body: { padding: 12 } }}>
            <Row gutter={12}>
              <Col span={12}><Form.Item label={getLabel('api_api_port')} name="api_api_port"><Input size="small" placeholder={getLabel('api_api_port')} /></Form.Item></Col>
              <Col span={12}><Form.Item label={getLabel('localUserDB_host')} name="localUserDB_host"><Input size="small" placeholder={getLabel('localUserDB_host')} /></Form.Item></Col>
              <Col span={12}><Form.Item label={getLabel('localUserDB_port')} name="localUserDB_port"><Input size="small" placeholder={getLabel('localUserDB_port')} /></Form.Item></Col>
              <Col span={12}><Form.Item label={getLabel('localAgentDB_host')} name="localAgentDB_host"><Input size="small" placeholder={getLabel('localAgentDB_host')} /></Form.Item></Col>
              <Col span={12}><Form.Item label={getLabel('localAgentDB_port')} name="localAgentDB_port"><Input size="small" placeholder={getLabel('localAgentDB_port')} /></Form.Item></Col>
              <Col span={12}><Form.Item label={getLabel('localAgent_ports')} name="localAgent_ports" getValueFromEvent={(vals: any[]) => (vals || []).map((v: any) => Number(v))}>
                <Select
                  mode="tags"
                  style={{ width: '100%' }}
                  tokenSeparators={[',']}
                  placeholder={getLabel('localAgent_ports')}
                  size="small"
                />
              </Form.Item></Col>
              <Col span={12}><Form.Item label={getLabel('local_server_port')} name="local_server_port"><Input size="small" placeholder={getLabel('local_server_port')} /></Form.Item></Col>
              <Col span={12}><Form.Item label={getLabel('lan_api_endpoint')} name="lan_api_endpoint"><Input size="small" placeholder={getLabel('lan_api_endpoint')} /></Form.Item></Col>
              <Col span={12}><Form.Item label={getLabel('lan_api_host')} name="lan_api_host"><Input size="small" placeholder={getLabel('lan_api_host')} /></Form.Item></Col>
              <Col span={12}><Form.Item label={getLabel('wan_api_endpoint')} name="wan_api_endpoint"><Input size="small" placeholder={getLabel('wan_api_endpoint')} /></Form.Item></Col>
              <Col span={12}><Form.Item label={getLabel('ws_api_endpoint')} name="ws_api_endpoint"><Input size="small" placeholder={getLabel('ws_api_endpoint')} /></Form.Item></Col>
            </Row>
          </Card>
          {/* 打印与文件 */}
          <Card title={getLabel('print_file')} style={{ marginBottom: 8 }} styles={{ body: { padding: 12 } }}>
            <Row gutter={12}>
              <Col span={12}><Form.Item label={getLabel('default_printer')} name="default_printer"><Input size="small" placeholder={getLabel('default_printer')} /></Form.Item></Col>
              <Col span={12}><Form.Item label={getLabel('new_orders_dir')} name="new_orders_dir"><Input size="small" placeholder={getLabel('new_orders_dir')} /></Form.Item></Col>
              <Col span={12}><Form.Item label={getLabel('new_bots_file_path')} name="new_bots_file_path"><Input size="small" placeholder={getLabel('new_bots_file_path')} /></Form.Item></Col>
              <Col span={12}><Form.Item label={getLabel('last_bots_file')} name="last_bots_file"><Input size="small" placeholder={getLabel('last_bots_file')} /></Form.Item></Col>
              <Col span={12}><Form.Item label={getLabel('last_bots_file_time')} name="last_bots_file_time"><Input size="small" placeholder={getLabel('last_bots_file_time')} /></Form.Item></Col>
            </Row>
          </Card>
          {/* 调度与引擎 */}
          <Card title={getLabel('engine')} style={{ marginBottom: 8 }} styles={{ body: { padding: 12 } }}>
            <Row gutter={12}>
              <Col span={12}><Form.Item label={getLabel('img_engine')} name="img_engine"><Input size="small" placeholder={getLabel('img_engine')} /></Form.Item></Col>
              <Col span={12}><Form.Item label={getLabel('schedule_engine')} name="schedule_engine"><Input size="small" placeholder={getLabel('schedule_engine')} /></Form.Item></Col>
              <Col span={12}><Form.Item label={getLabel('schedule_mode')} name="schedule_mode"><Input size="small" placeholder={getLabel('schedule_mode')} /></Form.Item></Col>
            </Row>
          </Card>
          {/* 高级设置 */}
          <Card title={getLabel('advanced')} style={{ marginBottom: 8 }} styles={{ body: { padding: 12 } }}>
            <Row gutter={12}>
              <Col span={24}><Form.Item label={getLabel('mids_forced_to_run')} name="mids_forced_to_run">
                <Select
                  mode="tags"
                  style={{ width: '100%' }}
                  tokenSeparators={[',']}
                  placeholder={getLabel('mids_forced_to_run')}
                  size="small"
                />
              </Form.Item></Col>
            </Row>
          </Card>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} size="small">{t('common.save')}</Button>
          </Form.Item>
        </Form>
        {/* 页面设置分组放在底部，无保存按钮，切换即生效 */}
        <Card title={t('pages.settings.page_settings')} style={{ marginTop: 32 }}>
          <Form
            key={location.pathname + '-page'}
            form={pageForm}
            layout="vertical"
            initialValues={{ language: getDefaultLanguage(), theme: (theme === 'light' || theme === 'dark' || theme === 'system') ? theme : 'light' }}
          >
            <Form.Item label={getLabel('language')} name="language">
              <Select onChange={handlePageLanguageChange}>
                <Select.Option value="en-US">{t('languages.en-US')}</Select.Option>
                <Select.Option value="zh-CN">{t('languages.zh-CN')}</Select.Option>
              </Select>
            </Form.Item>
            <Form.Item label={getLabel('theme')} name="theme">
              <Select onChange={handlePageThemeChange}>
                <Select.Option value="light">{getLabel('theme.light')}</Select.Option>
                <Select.Option value="dark">{getLabel('theme.dark')}</Select.Option>
                <Select.Option value="system">{getLabel('theme.system')}</Select.Option>
              </Select>
            </Form.Item>
          </Form>
        </Card>
      </Card>
    </div>
  );
};

export default Settings;