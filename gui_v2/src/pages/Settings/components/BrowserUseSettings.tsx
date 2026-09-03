/**
 * Browser Use Settings Component
 * Manages browser-use agent parameters, browser session parameters, and browser profiles
 */
import React, { useState, useEffect, useCallback, forwardRef, useImperativeHandle } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Card,
  Form,
  Input,
  InputNumber,
  Switch,
  Select,
  Button,
  Space,
  Modal,
  Tooltip,
  Tabs,
  Row,
  Col,
  App,
  Divider,
  Tag,
  Popconfirm,
} from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
  SaveOutlined,
  StarOutlined,
  StarFilled,
  ReloadOutlined,
  GlobalOutlined,
  SettingOutlined,
  UserOutlined,
} from '@ant-design/icons';
import styled from '@emotion/styled';
import { get_ipc_api } from '@/services/ipc_api';
import PluginsSummaryCard from './PluginsSummaryCard';

// Removed Panel destructuring - using items prop instead

// Styled components
const SettingsContainer = styled.div`
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
`;

const ScrollableContent = styled.div`
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px 16px;
`;

const HeaderBar = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  min-height: 48px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  flex-shrink: 0;

  .browser-header-action,
  .browser-header-action:hover,
  .browser-header-action:focus,
  .browser-header-action:active {
    border-color: transparent !important;
    background: transparent !important;
    box-shadow: none !important;
  }

  .browser-header-action-primary {
    color: var(--ant-color-primary) !important;
    font-weight: 500;
  }
`;

const HeaderTitle = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  font-size: 14px;
  font-weight: 600;
`;

const StyledCard = styled(Card)`
  border-radius: 10px;
  
  .ant-card-body {
    padding: 14px 16px 6px;
  }

  .ant-form-item {
    margin-bottom: 10px;
  }

  .ant-form-item-label {
    padding-bottom: 3px;
  }

  .ant-form-item-label > label {
    height: 20px;
    font-size: 12px;
  }
`;

const ProfileCard = styled(Card)`
  margin-bottom: 6px;
  border-radius: 8px;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;

  &:hover {
    border-color: var(--ant-color-primary-border);
    box-shadow: var(--ant-box-shadow-tertiary);
  }
  
  .ant-card-body {
    padding: 9px 12px;
  }
`;

const BrowserTabs = styled(Tabs)`
  height: auto !important;

  > .ant-tabs-nav {
    min-height: 38px !important;
    margin: 0 0 10px !important;
    padding: 0 4px !important;
    background: transparent !important;
  }

  > .ant-tabs-nav .ant-tabs-tab {
    margin: 0 !important;
    padding: 8px 12px !important;
    font-size: 13px !important;
  }

  > .ant-tabs-content-holder,
  > .ant-tabs-content-holder > .ant-tabs-content,
  > .ant-tabs-content-holder > .ant-tabs-content > .ant-tabs-tabpane {
    height: auto !important;
    overflow: visible !important;
  }
`;

const ProfileModal = styled(Modal)`
  .ant-modal-header {
    margin-bottom: 10px;
  }

  .ant-modal-content {
    padding: 16px 18px 12px;
  }

  .ant-form-item {
    margin-bottom: 10px;
  }

  .ant-form-item-label {
    padding-bottom: 3px;
  }

  .ant-form-item-label > label {
    height: 20px;
    font-size: 12px;
  }

  .ant-divider {
    margin: 10px 0 8px !important;
    font-size: 13px;
  }
`;

// Types
export interface AgentSettings {
  use_vision: boolean | 'auto';
  vision_detail_level: 'auto' | 'low' | 'high';
  max_failures: number;
  max_steps: number;
  max_actions_per_step: number;
  use_thinking: boolean;
  flash_mode: boolean;
  use_judge: boolean;
  max_history_items: number | null;
  calculate_cost: boolean;
  include_tool_call_examples: boolean;
  llm_timeout: number;
  step_timeout: number;
  final_response_after_failure: boolean;
}

export interface BrowserSessionSettings {
  headless: boolean;
  minimum_wait_page_load_time: number;
  wait_for_network_idle_page_load_time: number;
  wait_between_actions: number;
  auto_download_pdfs: boolean;
  highlight_elements: boolean;
  dom_highlight_elements: boolean;
  max_iframes: number;
  max_iframe_depth: number;
  keep_alive: boolean;
}

export interface BrowserProfile {
  id: string;
  name: string;
  isDefault: boolean;
  // Connection settings
  cdp_url: string;
  is_local: boolean;
  use_cloud: boolean;
  // Browser settings
  headless: boolean;
  user_data_dir: string;
  profile_directory: string;
  downloads_path: string;
  disable_security: boolean;
  deterministic_rendering: boolean;
  args: string[];
  user_agent: string;
  // Domain restrictions
  allowed_domains: string[];
  prohibited_domains: string[];
  block_ip_addresses: boolean;
  // Session settings
  keep_alive: boolean;
  enable_default_extensions: boolean;
  demo_mode: boolean;
  cookie_whitelist_domains: string[];
  // Window settings
  window_width: number;
  window_height: number;
  window_position_x: number;
  window_position_y: number;
  viewport_width: number;
  viewport_height: number;
  // iFrame settings
  cross_origin_iframes: boolean;
  max_iframes: number;
  max_iframe_depth: number;
  // Timing settings
  minimum_wait_page_load_time: number;
  wait_for_network_idle_page_load_time: number;
  wait_between_actions: number;
  // UI/DOM settings
  highlight_elements: boolean;
  dom_highlight_elements: boolean;
  filter_highlight_ids: boolean;
  paint_order_filtering: boolean;
  interaction_highlight_color: string;
  interaction_highlight_duration: number;
  // Downloads
  auto_download_pdfs: boolean;
  // Recording
  record_video_dir: string;
  record_video_framerate: number;
  // Fingerprint / Stealth
  enableStealth: boolean;
  timezone: string;
  locale: string;
  platform: string;
  languages: string[];
  canvasNoiseSeed: string;
  webglVendor: string;
  webglRenderer: string;
  hardwareConcurrency: number;
  deviceMemory: number;
  deviceScaleFactor: number;
  webrtcPolicy: string;
  fingerprintProxy: {
    server: string;
    username: string;
    password: string;
    bypass: string;
  } | null;
  // Geolocation
  geoLocationMode: string;  // 'based_on_ip' | 'custom' | 'block' | ''
  geolocation: { latitude: number; longitude: number; accuracy: number } | null;
  // Display language
  displayLanguage: string;
  // Do Not Track
  doNotTrack: string;  // '1' | '0' | ''
  // Hardware noise toggles
  noiseWebGLImage: boolean;
  noiseClientRects: boolean;
  noiseSpeechVoices: boolean;
  noiseMediaDevices: boolean;
  // Font protection
  fontProtection: boolean;
  customFonts: string[];
  // Port scan protection
  portScanProtection: boolean;
  portScanAllowedPorts: string;  // comma-separated port numbers
  // WebGPU
  webgpuMode: string;  // 'based_on_webgl' | 'real' | 'disabled'
  // Hardware acceleration
  hardwareAcceleration: string;  // 'default' | 'on' | 'off'
}

export interface BrowserUseSettingsData {
  agentSettings: AgentSettings;
  browserSessionSettings: BrowserSessionSettings;
  profiles: BrowserProfile[];
}

// Default values
const defaultAgentSettings: AgentSettings = {
  use_vision: true,
  vision_detail_level: 'auto',
  max_failures: 3,
  max_steps: 100,
  max_actions_per_step: 3,
  use_thinking: true,
  flash_mode: false,
  use_judge: true,
  max_history_items: null,
  calculate_cost: false,
  include_tool_call_examples: false,
  llm_timeout: 60,
  step_timeout: 180,
  final_response_after_failure: true,
};

const defaultBrowserSessionSettings: BrowserSessionSettings = {
  headless: false,
  minimum_wait_page_load_time: 0.5,
  wait_for_network_idle_page_load_time: 1.0,
  wait_between_actions: 0.5,
  auto_download_pdfs: true,
  highlight_elements: true,
  dom_highlight_elements: true,
  max_iframes: 3,
  max_iframe_depth: 3,
  keep_alive: false,
};

const createDefaultProfile = (id: string, name: string, isDefault: boolean = false): BrowserProfile => ({
  id,
  name,
  isDefault,
  // Connection settings
  cdp_url: '',
  is_local: false,
  use_cloud: false,
  // Browser settings
  headless: false,
  user_data_dir: '',
  profile_directory: 'Default',
  downloads_path: '',
  disable_security: false,
  deterministic_rendering: false,
  args: [],
  user_agent: '',
  // Domain restrictions
  allowed_domains: [],
  prohibited_domains: [],
  block_ip_addresses: false,
  // Session settings
  keep_alive: false,
  enable_default_extensions: true,
  demo_mode: false,
  cookie_whitelist_domains: ['nature.com', 'qatarairways.com'],
  // Window settings
  window_width: 1280,
  window_height: 720,
  window_position_x: 0,
  window_position_y: 0,
  viewport_width: 1280,
  viewport_height: 720,
  // iFrame settings
  cross_origin_iframes: true,
  max_iframes: 100,
  max_iframe_depth: 5,
  // Timing settings
  minimum_wait_page_load_time: 0.25,
  wait_for_network_idle_page_load_time: 0.5,
  wait_between_actions: 0.1,
  // UI/DOM settings
  highlight_elements: true,
  dom_highlight_elements: false,
  filter_highlight_ids: true,
  paint_order_filtering: true,
  interaction_highlight_color: 'rgb(255, 127, 39)',
  interaction_highlight_duration: 1.0,
  // Downloads
  auto_download_pdfs: true,
  // Recording
  record_video_dir: '',
  record_video_framerate: 30,
  // Fingerprint / Stealth
  enableStealth: false,
  timezone: '',
  locale: '',
  platform: '',
  languages: [],
  canvasNoiseSeed: '',
  webglVendor: '',
  webglRenderer: '',
  hardwareConcurrency: 0,
  deviceMemory: 0,
  deviceScaleFactor: 0,
  webrtcPolicy: 'block',
  fingerprintProxy: null,
  // Geolocation
  geoLocationMode: '',
  geolocation: null,
  // Display & tracking
  displayLanguage: '',
  doNotTrack: '',
  // Hardware noise toggles
  noiseWebGLImage: true,
  noiseClientRects: true,
  noiseSpeechVoices: true,
  noiseMediaDevices: true,
  // Font protection
  fontProtection: true,
  customFonts: [],
  // Port scan protection
  portScanProtection: true,
  portScanAllowedPorts: '80,443',
  // WebGPU
  webgpuMode: 'based_on_webgl',
  // Hardware acceleration
  hardwareAcceleration: 'default',
});

interface BrowserUseSettingsProps {
  username?: string;
  settingsLoaded?: boolean;
}

export interface BrowserUseSettingsRef {
  save: () => Promise<boolean>;
  reload: () => Promise<void>;
}

const BrowserUseSettings = forwardRef<BrowserUseSettingsRef, BrowserUseSettingsProps>(
  ({ username, settingsLoaded }, ref) => {
    const { t } = useTranslation();
    const { message } = App.useApp();
    
    // Translation helper for browser_use settings
    const tb = (key: string) => t(`pages.settings.browser_use.${key}`);
    
    const [agentForm] = Form.useForm();
    const [sessionForm] = Form.useForm();
    const [profileForm] = Form.useForm();
    
    const [loading, setLoading] = useState(false);
    const [profiles, setProfiles] = useState<BrowserProfile[]>([]);
    const [editingProfile, setEditingProfile] = useState<BrowserProfile | null>(null);
    const [profileModalVisible, setProfileModalVisible] = useState(false);
    const [hasChanges, setHasChanges] = useState(false);

    // Load settings from backend
    const loadSettings = useCallback(async () => {
      setLoading(true);
      try {
        const response = await get_ipc_api().getBrowserUseSettings<BrowserUseSettingsData>();
        if (response.success && response.data) {
          const data = response.data;
          agentForm.setFieldsValue(data.agentSettings || defaultAgentSettings);
          sessionForm.setFieldsValue(data.browserSessionSettings || defaultBrowserSessionSettings);
          setProfiles(data.profiles || [createDefaultProfile('default', tb('profiles.default_profile_name'), true)]);
        } else {
          // Initialize with defaults
          agentForm.setFieldsValue(defaultAgentSettings);
          sessionForm.setFieldsValue(defaultBrowserSessionSettings);
          setProfiles([createDefaultProfile('default', tb('profiles.default_profile_name'), true)]);
        }
        setHasChanges(false);
      } catch (error) {
        console.error('Failed to load browser-use settings:', error);
        message.error('Failed to load browser-use settings');
        // Initialize with defaults on error
        agentForm.setFieldsValue(defaultAgentSettings);
        sessionForm.setFieldsValue(defaultBrowserSessionSettings);
        setProfiles([createDefaultProfile('default', tb('profiles.default_profile_name'), true)]);
      } finally {
        setLoading(false);
      }
    }, [agentForm, sessionForm, message]);

    // Save settings to backend
    const saveSettings = useCallback(async (): Promise<boolean> => {
      setLoading(true);
      try {
        const agentSettings = agentForm.getFieldsValue();
        const browserSessionSettings = sessionForm.getFieldsValue();
        
        const settingsData: BrowserUseSettingsData = {
          agentSettings,
          browserSessionSettings,
          profiles,
        };
        
        const response = await get_ipc_api().saveBrowserUseSettings(settingsData);
        if (response.success) {
          message.success('Browser-use settings saved successfully');
          setHasChanges(false);
          return true;
        } else {
          message.error(response.error || 'Failed to save settings');
          return false;
        }
      } catch (error) {
        console.error('Failed to save browser-use settings:', error);
        message.error('Failed to save browser-use settings');
        return false;
      } finally {
        setLoading(false);
      }
    }, [agentForm, sessionForm, profiles, message]);

    // Expose methods via ref
    useImperativeHandle(ref, () => ({
      save: saveSettings,
      reload: loadSettings,
    }));

    // Load settings on mount
    useEffect(() => {
      if (settingsLoaded !== false) {
        loadSettings();
      }
    }, [loadSettings, settingsLoaded]);

    // Profile management functions
    const handleAddProfile = () => {
      const newProfile = createDefaultProfile(
        `profile_${Date.now()}`,
        `Profile ${profiles.length + 1}`,
        profiles.length === 0
      );
      setEditingProfile(newProfile);
      profileForm.setFieldsValue(newProfile);
      setProfileModalVisible(true);
    };

    const handleEditProfile = (profile: BrowserProfile) => {
      setEditingProfile(profile);
      profileForm.setFieldsValue({
        ...profile,
        args: profile.args?.join('\n') || '',
        allowed_domains: profile.allowed_domains?.join('\n') || '',
        prohibited_domains: profile.prohibited_domains?.join('\n') || '',
        cookie_whitelist_domains: profile.cookie_whitelist_domains?.join('\n') || '',
      });
      setProfileModalVisible(true);
    };

    const handleDeleteProfile = (profileId: string) => {
      const profile = profiles.find(p => p.id === profileId);
      if (profile?.isDefault && profiles.length > 1) {
        message.warning(tb('profiles.cannot_delete_default'));
        return;
      }
      
      const newProfiles = profiles.filter(p => p.id !== profileId);
      
      // If we deleted the default and there are remaining profiles, make the first one default
      if (profile?.isDefault && newProfiles.length > 0) {
        newProfiles[0].isDefault = true;
      }
      
      setProfiles(newProfiles);
      setHasChanges(true);
    };

    const handleSetDefaultProfile = (profileId: string) => {
      const newProfiles = profiles.map(p => ({
        ...p,
        isDefault: p.id === profileId,
      }));
      setProfiles(newProfiles);
      setHasChanges(true);
    };

    const handleSaveProfile = async () => {
      try {
        const values = await profileForm.validateFields();
        
        // Convert newline-separated strings back to arrays
        const parseTextareaToArray = (text: string | undefined): string[] => {
          if (!text) return [];
          return text.split('\n').map((s: string) => s.trim()).filter((s: string) => s);
        };
        
        const updatedProfile: BrowserProfile = {
          ...editingProfile!,
          ...values,
          args: parseTextareaToArray(values.args),
          allowed_domains: parseTextareaToArray(values.allowed_domains),
          prohibited_domains: parseTextareaToArray(values.prohibited_domains),
          cookie_whitelist_domains: parseTextareaToArray(values.cookie_whitelist_domains),
        };
        
        const existingIndex = profiles.findIndex(p => p.id === updatedProfile.id);
        let newProfiles: BrowserProfile[];
        
        if (existingIndex >= 0) {
          newProfiles = [...profiles];
          newProfiles[existingIndex] = updatedProfile;
        } else {
          newProfiles = [...profiles, updatedProfile];
        }
        
        setProfiles(newProfiles);
        setProfileModalVisible(false);
        setEditingProfile(null);
        setHasChanges(true);
        message.success('Profile saved');
      } catch (error) {
        console.error('Profile validation failed:', error);
      }
    };

    const handleFormChange = () => {
      setHasChanges(true);
    };

    return (
      <SettingsContainer>
        <HeaderBar>
          <HeaderTitle>
            <GlobalOutlined />
            <span>{t('pages.settings.browser_use.tab_title')}</span>
            {hasChanges && <Tag color="warning">{tb('unsaved_changes')}</Tag>}
          </HeaderTitle>
          <Space size={6}>
            <Button
              type="text"
              size="small"
              className="browser-header-action browser-header-action-primary"
              icon={<SaveOutlined />}
              onClick={saveSettings}
              loading={loading}
            >
              {tb('save_all')}
            </Button>
            <Tooltip title={tb('reload')}>
              <Button
                type="text"
                size="small"
                className="browser-header-action"
                icon={<ReloadOutlined />}
                onClick={loadSettings}
                loading={loading}
              />
            </Tooltip>
          </Space>
        </HeaderBar>
        
        <ScrollableContent>
          <PluginsSummaryCard />
          <BrowserTabs
            className="browser-settings-tabs"
            defaultActiveKey="agent"
            size="small"
            items={[
              {
                key: 'agent',
                label: (
                  <span>
                    <SettingOutlined style={{ marginRight: 8 }} />
                    {tb('agent_settings.title')}
                  </span>
                ),
                children: (
                  <StyledCard size="small">
                <Form
                  form={agentForm}
                  layout="vertical"
                  size="small"
                  initialValues={defaultAgentSettings}
                  onValuesChange={handleFormChange}
                >
                  <Row gutter={[16, 8]}>
                    <Col span={8}>
                      <Form.Item name="use_vision" label={tb('agent_settings.use_vision')} valuePropName="checked">
                        <Switch />
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item name="vision_detail_level" label={tb('agent_settings.vision_detail_level')}>
                        <Select>
                          <Select.Option value="auto">Auto</Select.Option>
                          <Select.Option value="low">Low</Select.Option>
                          <Select.Option value="high">High</Select.Option>
                        </Select>
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item name="max_failures" label={tb('agent_settings.max_failures')}>
                        <InputNumber min={1} max={10} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                  </Row>
                  
                  <Row gutter={[16, 8]}>
                    <Col span={8}>
                      <Form.Item name="max_steps" label={tb('agent_settings.max_steps')}>
                        <InputNumber min={1} max={500} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item name="max_actions_per_step" label={tb('agent_settings.max_actions_per_step')}>
                        <InputNumber min={1} max={20} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item name="use_thinking" label={tb('agent_settings.use_thinking')} valuePropName="checked">
                        <Switch />
                      </Form.Item>
                    </Col>
                  </Row>
                  
                  <Row gutter={[16, 8]}>
                    <Col span={8}>
                      <Form.Item name="flash_mode" label={tb('agent_settings.flash_mode')} valuePropName="checked">
                        <Switch />
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item name="use_judge" label={tb('agent_settings.use_judge')} valuePropName="checked">
                        <Switch />
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item name="calculate_cost" label={tb('agent_settings.calculate_cost')} valuePropName="checked">
                        <Switch />
                      </Form.Item>
                    </Col>
                  </Row>
                  
                  <Row gutter={[16, 8]}>
                    <Col span={8}>
                      <Form.Item name="final_response_after_failure" label={tb('agent_settings.final_response_after_failure')} valuePropName="checked">
                        <Switch />
                      </Form.Item>
                    </Col>
                  </Row>
                  
                  <Divider style={{ margin: '12px 0' }} />
                  
                  <Row gutter={[16, 8]}>
                    <Col span={8}>
                      <Form.Item name="llm_timeout" label={tb('agent_settings.llm_timeout')}>
                        <InputNumber min={10} max={300} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item name="step_timeout" label={tb('agent_settings.step_timeout')}>
                        <InputNumber min={30} max={600} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item name="max_history_items" label={tb('agent_settings.max_history_items')}>
                        <InputNumber min={0} max={100} style={{ width: '100%' }} placeholder="null = unlimited" />
                      </Form.Item>
                    </Col>
                  </Row>
                </Form>
              </StyledCard>
                )
              },
              {
                key: 'session',
                label: (
                  <span>
                    <GlobalOutlined style={{ marginRight: 8 }} />
                    {tb('session_settings.title')}
                  </span>
                ),
                children: (
                  <StyledCard size="small">
                <Form
                  form={sessionForm}
                  layout="vertical"
                  size="small"
                  initialValues={defaultBrowserSessionSettings}
                  onValuesChange={handleFormChange}
                >
                  <Row gutter={[16, 8]}>
                    <Col span={8}>
                      <Form.Item name="headless" label={tb('session_settings.headless')} valuePropName="checked">
                        <Switch />
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item name="keep_alive" label={tb('session_settings.keep_alive')} valuePropName="checked">
                        <Switch />
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item name="auto_download_pdfs" label={tb('session_settings.auto_download_pdfs')} valuePropName="checked">
                        <Switch />
                      </Form.Item>
                    </Col>
                  </Row>
                  
                  <Row gutter={[16, 8]}>
                    <Col span={8}>
                      <Form.Item name="highlight_elements" label={tb('session_settings.highlight_elements')} valuePropName="checked">
                        <Switch />
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item name="dom_highlight_elements" label={tb('session_settings.dom_highlight_elements')} valuePropName="checked">
                        <Switch />
                      </Form.Item>
                    </Col>
                  </Row>
                  
                  <Divider style={{ margin: '12px 0' }} />
                  
                  <Row gutter={[16, 8]}>
                    <Col span={8}>
                      <Form.Item name="minimum_wait_page_load_time" label={tb('session_settings.min_page_load_wait')}>
                        <InputNumber min={0} max={10} step={0.1} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item name="wait_for_network_idle_page_load_time" label={tb('session_settings.network_idle_wait')}>
                        <InputNumber min={0} max={30} step={0.1} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item name="wait_between_actions" label={tb('session_settings.wait_between_actions')}>
                        <InputNumber min={0} max={10} step={0.1} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                  </Row>
                  
                  <Row gutter={[16, 8]}>
                    <Col span={8}>
                      <Form.Item name="max_iframes" label={tb('session_settings.max_iframes')}>
                        <InputNumber min={0} max={20} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item name="max_iframe_depth" label={tb('session_settings.max_iframe_depth')}>
                        <InputNumber min={0} max={10} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                  </Row>
                </Form>
              </StyledCard>
                )
              },
              {
                key: 'profiles',
                label: (
                  <span>
                    <UserOutlined style={{ marginRight: 8 }} />
                    {tb('profiles.title')}
                  </span>
                ),
                children: (
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
                <Button size="small" type="primary" icon={<PlusOutlined />} onClick={handleAddProfile}>
                  {tb('profiles.add_profile')}
                </Button>
              </div>
              
              {profiles.map((profile) => (
                <ProfileCard key={profile.id} size="small">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontWeight: 500 }}>
                        {profile.name === 'Default Profile' ? tb('profiles.default_profile_name') : profile.name}
                      </span>
                      {profile.isDefault && (
                        <Tag color="gold" icon={<StarFilled />}>{t('common.default')}</Tag>
                      )}
                      {profile.headless && <Tag>{tb('profiles.fields.headless')}</Tag>}
                      {profile.profile_directory && profile.profile_directory !== 'Default' && (
                        <Tag color="blue">{profile.profile_directory}</Tag>
                      )}
                    </div>
                    <Space>
                      {!profile.isDefault && (
                        <Tooltip title={tb('profiles.set_default')}>
                          <Button
                            size="small"
                            icon={<StarOutlined />}
                            onClick={() => handleSetDefaultProfile(profile.id)}
                          />
                        </Tooltip>
                      )}
                      <Tooltip title={tb('profiles.edit_profile')}>
                        <Button
                          size="small"
                          icon={<EditOutlined />}
                          onClick={() => handleEditProfile(profile)}
                        />
                      </Tooltip>
                      <Popconfirm
                        title={tb('profiles.delete_profile')}
                        onConfirm={() => handleDeleteProfile(profile.id)}
                        okText={t('common.yes')}
                        cancelText={t('common.no')}
                      >
                        <Tooltip title={t('common.delete')}>
                          <Button
                            size="small"
                            danger
                            icon={<DeleteOutlined />}
                          />
                        </Tooltip>
                      </Popconfirm>
                    </Space>
                  </div>
                  {(profile.user_data_dir || profile.downloads_path) && (
                    <div style={{ marginTop: 8, fontSize: 12, color: '#888' }}>
                      {profile.user_data_dir && <div>{tb('profiles.fields.user_data_dir')}: {profile.user_data_dir}</div>}
                      {profile.downloads_path && <div>{tb('profiles.fields.downloads_path')}: {profile.downloads_path}</div>}
                    </div>
                  )}
                </ProfileCard>
              ))}
              
              {profiles.length === 0 && (
                <div style={{ textAlign: 'center', padding: 24, color: '#888' }}>
                  {tb('profiles.no_profiles')}
                </div>
              )}
                  </div>
                )
              }
            ]}
          />
        </ScrollableContent>

        {/* Profile Edit Modal */}
        <ProfileModal
          title={editingProfile?.id.startsWith('profile_') ? tb('profiles.add_profile') : tb('profiles.edit_profile')}
          open={profileModalVisible}
          onOk={handleSaveProfile}
          onCancel={() => {
            setProfileModalVisible(false);
            setEditingProfile(null);
          }}
          width={800}
          styles={{ body: { maxHeight: '70vh', overflowY: 'auto' } }}
        >
          <Form form={profileForm} layout="vertical" size="small">
            {/* Basic Settings */}
            <Divider orientation="left" style={{ margin: '8px 0' }}>{tb('profiles.basic_settings')}</Divider>
            <Row gutter={16}>
              <Col span={8}>
                <Form.Item
                  name="name"
                  label={tb('profiles.fields.name')}
                  rules={[{ required: true, message: t('common.please_input_name') }]}
                >
                  <Input placeholder="My Profile" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="profile_directory" label={tb('profiles.fields.profile_directory')}>
                  <Input placeholder="Default" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="headless" label={tb('profiles.fields.headless')} valuePropName="checked">
                  <Switch />
                </Form.Item>
              </Col>
            </Row>
            
            {/* Connection Settings */}
            <Divider orientation="left" style={{ margin: '8px 0' }}>{tb('profiles.connection_settings')}</Divider>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="cdp_url" label="CDP URL" tooltip="CDP URL for connecting to existing browser instance">
                  <Input placeholder="http://127.0.0.1:9222" />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="is_local" label="Is Local" valuePropName="checked" tooltip="Whether this is a local browser instance">
                  <Switch />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="use_cloud" label="Use Cloud" valuePropName="checked" tooltip="Use browser-use cloud browser service">
                  <Switch />
                </Form.Item>
              </Col>
            </Row>
            
            {/* Paths */}
            <Divider orientation="left" style={{ margin: '8px 0' }}>{tb('profiles.paths')}</Divider>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="user_data_dir" label="User Data Directory">
                  <Input placeholder="Path to user data directory" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="downloads_path" label="Downloads Path">
                  <Input placeholder="Path for downloads" />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="record_video_dir" label="Record Video Directory" tooltip="Directory to save video recordings">
                  <Input placeholder="Path to save video recordings" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="record_video_framerate" label="Video Framerate">
                  <InputNumber min={1} max={60} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
            </Row>
            
            {/* Window & Viewport */}
            <Divider orientation="left" style={{ margin: '8px 0' }}>{tb('profiles.window_viewport')}</Divider>
            <Row gutter={16}>
              <Col span={6}>
                <Form.Item name="window_width" label="Window Width">
                  <InputNumber min={320} max={3840} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="window_height" label="Window Height">
                  <InputNumber min={240} max={2160} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="window_position_x" label="Window X">
                  <InputNumber min={0} max={5000} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="window_position_y" label="Window Y">
                  <InputNumber min={0} max={5000} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="viewport_width" label="Viewport Width">
                  <InputNumber min={320} max={3840} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="viewport_height" label="Viewport Height">
                  <InputNumber min={240} max={2160} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
            </Row>
            
            {/* Timing Settings */}
            <Divider orientation="left" style={{ margin: '8px 0' }}>{tb('profiles.timing_settings')}</Divider>
            <Row gutter={16}>
              <Col span={8}>
                <Form.Item name="minimum_wait_page_load_time" label="Min Page Load Wait (s)">
                  <InputNumber min={0} max={10} step={0.05} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="wait_for_network_idle_page_load_time" label="Network Idle Wait (s)">
                  <InputNumber min={0} max={30} step={0.1} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="wait_between_actions" label="Wait Between Actions (s)">
                  <InputNumber min={0} max={10} step={0.05} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
            </Row>
            
            {/* iFrame Settings */}
            <Divider orientation="left" style={{ margin: '8px 0' }}>{tb('profiles.iframe_settings')}</Divider>
            <Row gutter={16}>
              <Col span={8}>
                <Form.Item name="cross_origin_iframes" label="Cross-Origin iFrames" valuePropName="checked" tooltip="Enable cross-origin iframe support">
                  <Switch />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="max_iframes" label="Max iFrames">
                  <InputNumber min={0} max={500} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="max_iframe_depth" label="Max iFrame Depth">
                  <InputNumber min={0} max={20} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
            </Row>
            
            {/* UI/DOM Settings */}
            <Divider orientation="left" style={{ margin: '8px 0' }}>{tb('profiles.ui_dom_settings')}</Divider>
            <Row gutter={16}>
              <Col span={6}>
                <Form.Item name="highlight_elements" label="Highlight Elements" valuePropName="checked">
                  <Switch />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="dom_highlight_elements" label="DOM Highlight" valuePropName="checked" tooltip="For debugging">
                  <Switch />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="filter_highlight_ids" label="Filter Highlight IDs" valuePropName="checked">
                  <Switch />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="paint_order_filtering" label="Paint Order Filter" valuePropName="checked">
                  <Switch />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="interaction_highlight_color" label="Highlight Color">
                  <Input placeholder="rgb(255, 127, 39)" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="interaction_highlight_duration" label="Highlight Duration (s)">
                  <InputNumber min={0.1} max={10} step={0.1} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
            </Row>
            
            {/* Domain Restrictions */}
            <Divider orientation="left" style={{ margin: '8px 0' }}>{tb('profiles.domain_restrictions')}</Divider>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="allowed_domains" label="Allowed Domains" tooltip="One domain per line (e.g., *.google.com)">
                  <Input.TextArea rows={2} placeholder="*.google.com&#10;https://example.com" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="prohibited_domains" label="Prohibited Domains" tooltip="One domain per line">
                  <Input.TextArea rows={2} placeholder="*.ads.com&#10;tracking.example.com" />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={24}>
                <Form.Item name="block_ip_addresses" label="Block IP Addresses" valuePropName="checked" tooltip="Block navigation to URLs containing IP addresses">
                  <Switch />
                </Form.Item>
              </Col>
            </Row>
            
            {/* Session & Extensions */}
            <Divider orientation="left" style={{ margin: '8px 0' }}>{tb('profiles.session_extensions')}</Divider>
            <Row gutter={16}>
              <Col span={6}>
                <Form.Item name="keep_alive" label="Keep Alive" valuePropName="checked" tooltip="Keep browser alive after agent run">
                  <Switch />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="enable_default_extensions" label="Default Extensions" valuePropName="checked" tooltip="Enable ad blocking, cookie handling extensions">
                  <Switch />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="demo_mode" label="Demo Mode" valuePropName="checked" tooltip="Enable demo mode side panel">
                  <Switch />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="auto_download_pdfs" label="Auto Download PDFs" valuePropName="checked">
                  <Switch />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={24}>
                <Form.Item name="cookie_whitelist_domains" label="Cookie Whitelist Domains" tooltip="Domains to whitelist for cookie handling (one per line)">
                  <Input.TextArea rows={2} placeholder="nature.com&#10;qatarairways.com" />
                </Form.Item>
              </Col>
            </Row>
            
            {/* Security & Rendering */}
            <Divider orientation="left" style={{ margin: '8px 0' }}>{tb('profiles.security_rendering')}</Divider>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="disable_security" label="Disable Security" valuePropName="checked" tooltip="Disable browser security features">
                  <Switch />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="deterministic_rendering" label="Deterministic Rendering" valuePropName="checked">
                  <Switch />
                </Form.Item>
              </Col>
            </Row>
            
            {/* User Agent & Args */}
            <Divider orientation="left" style={{ margin: '8px 0' }}>{tb('profiles.user_agent_args')}</Divider>
            <Form.Item name="user_agent" label="User Agent">
              <Input placeholder="Custom user agent (leave empty for default)" />
            </Form.Item>
            <Form.Item name="args" label="Browser Arguments" tooltip="One argument per line (e.g., --disable-gpu)">
              <Input.TextArea rows={3} placeholder="--disable-gpu&#10;--no-sandbox" />
            </Form.Item>

            {/* Fingerprint / Stealth */}
            <Divider orientation="left" style={{ margin: '8px 0' }}>{tb('profiles.fingerprint_stealth')}</Divider>
            <Row gutter={16}>
              <Col span={8}>
                <Form.Item name="enableStealth" label={tb('profiles.fields.enableStealth')} valuePropName="checked"
                  tooltip={tb('profiles.fields.enableStealthTooltip')}>
                  <Switch />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="platform" label={tb('profiles.fields.platform')}>
                  <Select allowClear placeholder="Auto">
                    <Select.Option value="Win32">Win32</Select.Option>
                    <Select.Option value="MacIntel">MacIntel</Select.Option>
                    <Select.Option value="Linux x86_64">Linux x86_64</Select.Option>
                    <Select.Option value="Linux armv8l">Linux armv8l (Android)</Select.Option>
                  </Select>
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="webrtcPolicy" label={tb('profiles.fields.webrtcPolicy')}>
                  <Select placeholder="block">
                    <Select.Option value="block">Block</Select.Option>
                    <Select.Option value="default">Default</Select.Option>
                    <Select.Option value="disable_non_proxied_udp">Disable Non-Proxied UDP</Select.Option>
                  </Select>
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={8}>
                <Form.Item name="timezone" label={tb('profiles.fields.timezone')}>
                  <Input placeholder="America/New_York" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="locale" label={tb('profiles.fields.locale')}>
                  <Input placeholder="en-US" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="canvasNoiseSeed" label={tb('profiles.fields.canvasNoiseSeed')}
                  tooltip={tb('profiles.fields.canvasNoiseSeedTooltip')}>
                  <Input placeholder="Auto-generated if empty" />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="webglVendor" label={tb('profiles.fields.webglVendor')}>
                  <Input placeholder="Intel Inc." />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="webglRenderer" label={tb('profiles.fields.webglRenderer')}>
                  <Input placeholder="Intel(R) UHD Graphics 630" />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={6}>
                <Form.Item name="hardwareConcurrency" label={tb('profiles.fields.hardwareConcurrency')}>
                  <InputNumber min={0} max={128} placeholder="0=auto" style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="deviceMemory" label={tb('profiles.fields.deviceMemory')}>
                  <InputNumber min={0} max={512} placeholder="0=auto" style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="deviceScaleFactor" label={tb('profiles.fields.deviceScaleFactor')}>
                  <InputNumber min={0} max={4} step={0.25} placeholder="0=auto" style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="languages" label={tb('profiles.fields.languages')}
                  tooltip={tb('profiles.fields.languagesTooltip')}>
                  <Select mode="tags" placeholder="en-US, en" />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={8}>
                <Form.Item name="displayLanguage" label={tb('profiles.fields.displayLanguage')}
                  tooltip={tb('profiles.fields.displayLanguageTooltip')}>
                  <Input placeholder="en-US" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="doNotTrack" label={tb('profiles.fields.doNotTrack')}>
                  <Select allowClear placeholder="Browser Default">
                    <Select.Option value="">Default</Select.Option>
                    <Select.Option value="1">On</Select.Option>
                    <Select.Option value="0">Off</Select.Option>
                  </Select>
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="hardwareAcceleration" label={tb('profiles.fields.hardwareAcceleration')}>
                  <Select placeholder="Default">
                    <Select.Option value="default">Default</Select.Option>
                    <Select.Option value="on">On</Select.Option>
                    <Select.Option value="off">Off</Select.Option>
                  </Select>
                </Form.Item>
              </Col>
            </Row>

            {/* Geolocation */}
            <Row gutter={16}>
              <Col span={8}>
                <Form.Item name="geoLocationMode" label={tb('profiles.fields.geoLocationMode')}>
                  <Select allowClear placeholder="Default">
                    <Select.Option value="">Default</Select.Option>
                    <Select.Option value="based_on_ip">Based on IP</Select.Option>
                    <Select.Option value="custom">Custom</Select.Option>
                    <Select.Option value="block">Block</Select.Option>
                  </Select>
                </Form.Item>
              </Col>
              <Col span={5}>
                <Form.Item name={['geolocation', 'latitude']} label={tb('profiles.fields.geoLatitude')}>
                  <InputNumber step={0.0001} placeholder="40.7128" style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={5}>
                <Form.Item name={['geolocation', 'longitude']} label={tb('profiles.fields.geoLongitude')}>
                  <InputNumber step={0.0001} placeholder="-74.0060" style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="webgpuMode" label={tb('profiles.fields.webgpuMode')}>
                  <Select placeholder="Based on WebGL">
                    <Select.Option value="based_on_webgl">Based on WebGL</Select.Option>
                    <Select.Option value="real">Real</Select.Option>
                    <Select.Option value="disabled">Disabled</Select.Option>
                  </Select>
                </Form.Item>
              </Col>
            </Row>

            {/* Hardware Noise Toggles */}
            <Divider orientation="left" style={{ margin: '8px 0', fontSize: '13px' }}>{tb('profiles.hardware_noise')}</Divider>
            <Row gutter={16}>
              <Col span={4}>
                <Form.Item name="noiseWebGLImage" label={tb('profiles.fields.noiseWebGLImage')} valuePropName="checked">
                  <Switch size="small" />
                </Form.Item>
              </Col>
              <Col span={4}>
                <Form.Item name="noiseClientRects" label={tb('profiles.fields.noiseClientRects')} valuePropName="checked">
                  <Switch size="small" />
                </Form.Item>
              </Col>
              <Col span={4}>
                <Form.Item name="noiseSpeechVoices" label={tb('profiles.fields.noiseSpeechVoices')} valuePropName="checked">
                  <Switch size="small" />
                </Form.Item>
              </Col>
              <Col span={4}>
                <Form.Item name="noiseMediaDevices" label={tb('profiles.fields.noiseMediaDevices')} valuePropName="checked">
                  <Switch size="small" />
                </Form.Item>
              </Col>
              <Col span={4}>
                <Form.Item name="fontProtection" label={tb('profiles.fields.fontProtection')} valuePropName="checked">
                  <Switch size="small" />
                </Form.Item>
              </Col>
              <Col span={4}>
                <Form.Item name="portScanProtection" label={tb('profiles.fields.portScanProtection')} valuePropName="checked">
                  <Switch size="small" />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="customFonts" label={tb('profiles.fields.customFonts')}
                  tooltip={tb('profiles.fields.customFontsTooltip')}>
                  <Select mode="tags" placeholder="Arial, Helvetica, Times New Roman" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="portScanAllowedPorts" label={tb('profiles.fields.portScanAllowedPorts')}
                  tooltip={tb('profiles.fields.portScanAllowedPortsTooltip')}>
                  <Input placeholder="80,443" />
                </Form.Item>
              </Col>
            </Row>
          </Form>
        </ProfileModal>
      </SettingsContainer>
    );
  }
);

BrowserUseSettings.displayName = 'BrowserUseSettings';

export default BrowserUseSettings;
