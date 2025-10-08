import React, { useState, useCallback, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, Form, Select, Switch, Button, App, Input, Row, Col } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';

import { useUserStore } from '../../stores/userStore';
import { get_ipc_api } from '@/services/ipc_api';

import type { Settings } from './types';
import { LLMManagement } from './components';
import { StyledFormItem, StyledCard, FormContainer, ButtonContainer, buttonStyle } from '@/components/Common/StyledForm';

const SettingsContainer = styled.div`
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
`;

const SettingsContent = styled.div`
  flex: 1;
  overflow-y: auto;
  padding: 20px;
`;

const initialSettings: Settings = {
  schedule_mode: 'auto',
  debug_mode: false,
  default_wifi: '',
  default_printer: '',
  display_resolution: '',
  default_webdriver_path: '',
  build_dom_tree_script_path: '',
  new_orders_dir: 'c:/ding_dan/',
  local_user_db_host: '127.0.0.1',
  local_user_db_port: '5080',
  local_agent_db_host: '192.168.0.16',
  local_agent_db_port: '6668',
  lan_api_endpoint: '',
  wan_api_endpoint: '',
  ws_api_endpoint: '',
  img_engine: 'lan',
  schedule_engine: 'wan',
  local_agent_ports: [3600, 3800],
  browser_use_file_system_path: '',
  local_server_port: '4668',
  gui_flowgram_schema: '',
  wan_api_key: '',
  last_bots_file: '',
  last_bots_file_time: 0,
  last_order_file: '',
  last_order_file_time: 0,
  new_bots_file_path: '',
  new_orders_path: '',
  mids_forced_to_run: [],
  default_llm: ''  // Default LLM provider to use
};

const Settings: React.FC = () => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [settingsData, setSettingsData] = useState<Settings | null>(null);
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const username = useUserStore((state) => state.username);

  const isMountedRef = useRef(false);

  useEffect(() => {
    isMountedRef.current = true;
    return () => { isMountedRef.current = false; };
  }, []);

  // Listen for username changes
  useEffect(() => {
    console.log('👤 Username changed:', username);
    if (username) {
      console.log('✅ Username available, will trigger loadSettings');
      // Reset settings loading state
      setSettingsLoaded(false);
    } else {
      console.log('❌ No username available');
      setSettingsLoaded(false);
      form.resetFields();
    }
  }, [username, form]);

  // Load settings
  const loadSettings = useCallback(async () => {
    console.log('🔄 loadSettings called, username:', username);
    if (!username) {
      console.log('❌ No username, skipping loadSettings');
      return;
    }
    try {
      setLoading(true);
      console.log('📡 Step 1: Calling getSettings API first (before LLM providers)');
      console.log('📡 Calling getSettings API with username:', username);
      const response = await get_ipc_api().getSettings<{ settings: any }>(username);
      console.log('Settings response:', response);
      console.log('Settings data:', response?.data);
      if (response && response.success && response.data) {
        const settings = response.data.settings;
        console.log('Settings object:', settings);

        if (isMountedRef.current) {
          // Save complete settings data
          setSettingsData(settings);

          // Set form data
          const formData = { ...settings };

          form.setFieldsValue(formData);
          console.log('✅ Form values set successfully');
          console.log('✅ Settings data saved, default_llm:', settings.default_llm);

          // Mark settings as loaded
          setSettingsLoaded(true);
          console.log('✅ Settings loaded, LLM components can now load');
        }
      } else {
        console.error('❌ Failed to load settings:', response);
        message.error('Failed to load settings');
      }
    } catch (error) {
      console.error('❌ Error loading settings:', error);
      message.error('Failed to load settings');
    } finally {
      setLoading(false);
    }
  }, [username, form, message]);

  // Handle default LLM change from LLMManagement component
  const handleDefaultLLMChange = useCallback((newDefaultLLM: string) => {
    // Update local settings data
    setSettingsData(prevSettings => {
      if (prevSettings) {
        return { ...prevSettings, default_llm: newDefaultLLM };
      }
      return prevSettings;
    });
  }, []);

  // Generate a key for form to force re-render when default_llm changes
  const formKey = `settings-form-${settingsData?.default_llm || 'none'}`;

  // Save settings
  const handleSave = async (values: Settings) => {
    if (!username) {
      message.error('Please log in first');
      return;
    }

    try {
      setLoading(true);
      console.log('💾 Saving settings:', values);
      
      const response = await get_ipc_api().saveSettings({ username, ...values });
      if (response && response.success) {
        message.success('Settings saved successfully');
        console.log('✅ Settings saved successfully');
      } else {
        console.error('❌ Failed to save settings:', response);
        message.error('Failed to save settings');
      }
    } catch (error) {
      console.error('❌ Error saving settings:', error);
      message.error('Failed to save settings');
    } finally {
      setLoading(false);
    }
  };

  // Reload settings
  const handleReload = () => {
    loadSettings();
  };

  // Initial loading
  useEffect(() => {
    if (username) {
      loadSettings();
    }
  }, [username, loadSettings]);

  return (
    <SettingsContainer>
      <SettingsContent>
        <Card
          title={t('common.settings')}
          extra={
            <Button
              icon={<ReloadOutlined />}
              onClick={handleReload}
              loading={loading}
            >
              {t('common.reload')}
            </Button>
          }
        >
        <Form
          key={formKey}
          form={form}
          layout="vertical"
          onFinish={handleSave}
          preserve={true}
          initialValues={settingsData || initialSettings}
        >
          {/* 基础模式设置 */}
          <Card
            title={t('pages.settings.basic_mode_settings')}
            size="small"
            style={{ marginBottom: '8px' }}
            styles={{ body: { padding: '12px 16px 8px 16px' } }}
          >
            <Row gutter={[16, 4]}>
              <Col span={12}>
                <StyledFormItem
                  name="debug_mode"
                  label={t('pages.settings.debug_mode')}
                  valuePropName="checked"
                  style={{ marginBottom: '8px' }}
                >
                  <Switch size="small" />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="schedule_mode"
                  label={t('pages.settings.schedule_mode')}
                  style={{ marginBottom: '8px' }}
                >
                  <Select size="small">
                    <Select.Option value="auto">Auto</Select.Option>
                    <Select.Option value="manual">Manual</Select.Option>
                    <Select.Option value="test">Test</Select.Option>
                  </Select>
                </StyledFormItem>
              </Col>
            </Row>
          </Card>

          {/* 硬件设置 */}
          <Card
            title={t('pages.settings.hardware_settings')}
            size="small"
            style={{ marginBottom: '8px' }}
            styles={{ body: { padding: '12px 16px 8px 16px' } }}
          >
            <Row gutter={[16, 4]}>
              <Col span={8}>
                <StyledFormItem
                  name="default_wifi"
                  label={t('pages.settings.default_wifi')}
                  style={{ marginBottom: '8px' }}
                >
                  <Input size="small" placeholder="Enter default WiFi" />
                </StyledFormItem>
              </Col>
              <Col span={8}>
                <StyledFormItem
                  name="default_printer"
                  label={t('pages.settings.default_printer')}
                  style={{ marginBottom: '8px' }}
                >
                  <Input size="small" placeholder="Enter default printer" />
                </StyledFormItem>
              </Col>
              <Col span={8}>
                <StyledFormItem
                  name="display_resolution"
                  label={t('pages.settings.display_resolution')}
                  style={{ marginBottom: '8px' }}
                >
                  <Select size="small">
                    <Select.Option value="D1920X1080">1920x1080</Select.Option>
                    <Select.Option value="D2560X1440">2560x1440</Select.Option>
                    <Select.Option value="D3840X2160">3840x2160</Select.Option>
                  </Select>
                </StyledFormItem>
              </Col>
            </Row>
          </Card>

          {/* 引擎和端口设置 */}
          <Card
            title={t('pages.settings.engine_port_settings')}
            size="small"
            style={{ marginBottom: '8px' }}
            styles={{ body: { padding: '12px 16px 8px 16px' } }}
          >
            <Row gutter={[16, 4]}>
              <Col span={8}>
                <StyledFormItem
                  name="img_engine"
                  label={t('pages.settings.img_engine')}
                  style={{ marginBottom: '8px' }}
                >
                  <Select size="small">
                    <Select.Option value="lan">LAN</Select.Option>
                    <Select.Option value="wan">WAN</Select.Option>
                  </Select>
                </StyledFormItem>
              </Col>
              <Col span={8}>
                <StyledFormItem
                  name="schedule_engine"
                  label={t('pages.settings.schedule_engine')}
                  style={{ marginBottom: '8px' }}
                >
                  <Select size="small">
                    <Select.Option value="lan">LAN</Select.Option>
                    <Select.Option value="wan">WAN</Select.Option>
                  </Select>
                </StyledFormItem>
              </Col>
              <Col span={8}>
                <StyledFormItem
                  name="local_server_port"
                  label={t('pages.settings.local_server_port')}
                  style={{ marginBottom: '8px' }}
                >
                  <Input size="small" placeholder="Enter local server port" />
                </StyledFormItem>
              </Col>
            </Row>
          </Card>

          {/* 路径设置 */}
          <Card
            title={t('pages.settings.path_settings')}
            size="small"
            style={{ marginBottom: '8px' }}
            styles={{ body: { padding: '12px 16px 8px 16px' } }}
          >
            <Row gutter={[16, 4]}>
              <Col span={12}>
                <StyledFormItem
                  name="default_webdriver_path"
                  label={t('pages.settings.default_webdriver_path')}
                  style={{ marginBottom: '6px' }}
                >
                  <Input size="small" placeholder="Enter webdriver path" />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="build_dom_tree_script_path"
                  label={t('pages.settings.build_dom_tree_script_path')}
                  style={{ marginBottom: '6px' }}
                >
                  <Input size="small" placeholder="Enter DOM tree script path" />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="browser_use_file_system_path"
                  label={t('pages.settings.browser_use_file_system_path')}
                  style={{ marginBottom: '6px' }}
                >
                  <Input size="small" placeholder="Enter browser file system path" />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="new_orders_dir"
                  label={t('pages.settings.new_orders_dir')}
                  style={{ marginBottom: '6px' }}
                >
                  <Input size="small" placeholder="Enter new orders directory" />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="new_orders_path"
                  label={t('pages.settings.new_orders_path')}
                  style={{ marginBottom: '6px' }}
                >
                  <Input size="small" placeholder="Enter new orders path" />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="new_bots_file_path"
                  label={t('pages.settings.new_bots_file_path')}
                  style={{ marginBottom: '6px' }}
                >
                  <Input size="small" placeholder="Enter new bots file path" />
                </StyledFormItem>
              </Col>
            </Row>
          </Card>

          {/* 数据库设置 */}
          <Card
            title={t('pages.settings.database_settings')}
            size="small"
            style={{ marginBottom: '8px' }}
            styles={{ body: { padding: '12px 16px 8px 16px' } }}
          >
            <Row gutter={[16, 4]}>
              <Col span={12}>
                <StyledFormItem
                  name="local_user_db_host"
                  label={t('pages.settings.local_user_db_host')}
                  style={{ marginBottom: '8px' }}
                >
                  <Input size="small" placeholder="Enter user DB host" />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="local_user_db_port"
                  label={t('pages.settings.local_user_db_port')}
                  style={{ marginBottom: '8px' }}
                >
                  <Input size="small" placeholder="Enter user DB port" />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="local_agent_db_host"
                  label={t('pages.settings.local_agent_db_host')}
                  style={{ marginBottom: '8px' }}
                >
                  <Input size="small" placeholder="Enter agent DB host" />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="local_agent_db_port"
                  label={t('pages.settings.local_agent_db_port')}
                  style={{ marginBottom: '8px' }}
                >
                  <Input size="small" placeholder="Enter agent DB port" />
                </StyledFormItem>
              </Col>
            </Row>
          </Card>

          {/* API端点设置 */}
          <Card
            title={t('pages.settings.api_endpoint_settings')}
            size="small"
            style={{ marginBottom: '8px' }}
            styles={{ body: { padding: '12px 16px 8px 16px' } }}
          >
            <Row gutter={[16, 4]}>
              <Col span={12}>
                <StyledFormItem
                  name="lan_api_endpoint"
                  label={t('pages.settings.lan_api_endpoint')}
                  style={{ marginBottom: '8px' }}
                >
                  <Input size="small" placeholder="Enter LAN API endpoint" />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="wan_api_endpoint"
                  label={t('pages.settings.wan_api_endpoint')}
                  style={{ marginBottom: '8px' }}
                >
                  <Input size="small" placeholder="Enter WAN API endpoint" />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="ws_api_endpoint"
                  label={t('pages.settings.ws_api_endpoint')}
                  style={{ marginBottom: '8px' }}
                >
                  <Input size="small" placeholder="Enter WebSocket API endpoint" />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="wan_api_key"
                  label={t('pages.settings.wan_api_key')}
                  style={{ marginBottom: '8px' }}
                >
                  <Input.Password size="small" placeholder="Enter WAN API key" />
                </StyledFormItem>
              </Col>
            </Row>
          </Card>

          {/* 文件跟踪和其他设置 */}
          <Card
            title={t('pages.settings.file_tracking_other_settings')}
            size="small"
            style={{ marginBottom: '8px' }}
            styles={{ body: { padding: '12px 16px 8px 16px' } }}
          >
            <Row gutter={[16, 4]}>
              <Col span={12}>
                <StyledFormItem
                  name="last_bots_file"
                  label={t('pages.settings.last_bots_file')}
                  style={{ marginBottom: '8px' }}
                >
                  <Input size="small" placeholder="Enter last bots file" />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="last_order_file"
                  label={t('pages.settings.last_order_file')}
                  style={{ marginBottom: '8px' }}
                >
                  <Input size="small" placeholder="Enter last order file" />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="gui_flowgram_schema"
                  label={t('pages.settings.gui_flowgram_schema')}
                  style={{ marginBottom: '8px' }}
                >
                  <Input size="small" placeholder="Enter GUI flowgram schema" />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="default_llm"
                  label={t('pages.settings.default_llm')}
                  style={{ marginBottom: '8px' }}
                >
                  <Input size="small" placeholder="Default LLM (managed by LLM Management below)" disabled />
                </StyledFormItem>
              </Col>
            </Row>
          </Card>

          {/* Advanced Settings Section */}
          <Row gutter={16}>
            <Col span={24}>
              <h3 style={{ marginTop: '20px', marginBottom: '16px', borderBottom: '1px solid #d9d9d9', paddingBottom: '8px' }}>
                {t('pages.settings.advanced_settings')}
              </h3>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <StyledFormItem
                name="local_agent_ports"
                label={t('pages.settings.local_agent_ports')}
                tooltip="Comma-separated port numbers (e.g., 3600,3800)"
              >
                <Input
                  placeholder="Enter ports (e.g., 3600,3800)"
                  onChange={(e) => {
                    const value = e.target.value;
                    const ports = value.split(',').map(p => parseInt(p.trim())).filter(p => !isNaN(p));
                    form.setFieldValue('local_agent_ports', ports);
                  }}
                />
              </StyledFormItem>
            </Col>
            <Col span={12}>
              <StyledFormItem
                name="last_bots_file_time"
                label={t('pages.settings.last_bots_file_time')}
              >
                <Input type="number" placeholder="Last bots file timestamp" />
              </StyledFormItem>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <StyledFormItem
                name="last_order_file_time"
                label={t('pages.settings.last_order_file_time')}
              >
                <Input type="number" placeholder="Last order file timestamp" />
              </StyledFormItem>
            </Col>
            <Col span={12}>
              <StyledFormItem
                name="mids_forced_to_run"
                label={t('pages.settings.mids_forced_to_run')}
                tooltip="JSON array format (e.g., [1,2,3])"
              >
                <Input.TextArea
                  placeholder='Enter JSON array (e.g., [1,2,3])'
                  rows={2}
                  onChange={(e) => {
                    try {
                      const value = e.target.value.trim();
                      if (value) {
                        const parsed = JSON.parse(value);
                        if (Array.isArray(parsed)) {
                          form.setFieldValue('mids_forced_to_run', parsed);
                        }
                      } else {
                        form.setFieldValue('mids_forced_to_run', []);
                      }
                    } catch (error) {
                      // Invalid JSON, keep current value
                    }
                  }}
                />
              </StyledFormItem>
            </Col>
          </Row>

          <StyledFormItem>
            <Button type="primary" htmlType="submit" loading={loading}>
              {t('common.save')}
            </Button>
          </StyledFormItem>
        </Form>
      </Card>

        {/* 🎯 New independent LLM management component */}
        <LLMManagement
          username={username}
          defaultLLM={settingsData?.default_llm || ''}
          settingsLoaded={settingsLoaded}
          onDefaultLLMChange={handleDefaultLLMChange}
        />
      </SettingsContent>
    </SettingsContainer>
  );
};

export default Settings;
