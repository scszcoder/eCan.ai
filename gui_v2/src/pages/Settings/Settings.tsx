import React, { useState, useCallback, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, Form, Select, Switch, Button, App, Input, Row, Col, Tooltip, Divider, Tabs, theme } from 'antd';
import { ReloadOutlined, FolderOpenOutlined, GlobalOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { useEffectOnActive } from 'keepalive-for-react';
import { useLocation } from 'react-router-dom';

import { useUserStore } from '../../stores/userStore';
import { get_ipc_api } from '@/services/ipc_api';

import type { Settings } from './types';
import { LLMManagement, EmbeddingManagement } from './components';

// Suppress Ant Design useForm warning (form is properly connected in Tab children)
const originalError = console.error;
const originalWarn = console.warn;
console.error = (...args: any[]) => {
  const message = String(args[0] || '');
  if (message.includes('Instance created by `useForm`') || 
      message.includes('not connected to any Form element')) {
    return;
  }
  originalError(...args);
};
console.warn = (...args: any[]) => {
  const message = String(args[0] || '');
  if (message.includes('Instance created by `useForm`') || 
      message.includes('not connected to any Form element')) {
    return;
  }
  originalWarn(...args);
};
import { StyledFormItem } from '@/components/Common/StyledForm';

const SettingsContainer = styled.div`
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
`;

const SettingsContent = styled.div`
  height: 100%;
  display: flex;
  flex-direction: column;
  
  .ant-tabs {
    display: flex;
    flex-direction: column;
    height: 100%;
    
    .ant-tabs-nav {
      margin: 0;
      padding: 0 24px;
      min-height: 52px;
      
      .ant-tabs-tab {
        padding: 16px 24px;
        font-size: 15px;
        font-weight: 500;
        border-radius: 0;
        margin: 0;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        border-bottom: 3px solid transparent;
        letter-spacing: 0.3px;
        
        &.ant-tabs-tab-active {
          font-weight: 600;
          border-bottom-width: 3px;
        }
      }
      
      .ant-tabs-ink-bar {
        display: none;
      }
    }
    
    .ant-tabs-content-holder {
      flex: 1;
      overflow: hidden;
    }
    
    .ant-tabs-content {
      height: 100%;
      
      .ant-tabs-tabpane {
        height: 100%;
        overflow-y: auto;
        padding: 20px 24px;
        
        &::-webkit-scrollbar {
          width: 8px;
        }
        
        &::-webkit-scrollbar-track {
          border-radius: 4px;
        }
        
        &::-webkit-scrollbar-thumb {
          border-radius: 4px;
        }
      }
    }
  }
`;

const StyledCard = styled(Card)`
  /* Card styles will use theme tokens dynamically */
`;

const StyledRefreshButton = styled(Button)`
  /* Button styles will use theme tokens dynamically */
`;

// OCR 配置预设
const OCR_PRESETS = {
  lan: {
    ocr_api_endpoint: 'http://52.204.81.197:8848/graphql/reqScreenTxtRead',
    ocr_api_key: ''
  },
  wan: {
    ocr_api_endpoint: '',  // WAN endpoint 需要用户配置
    ocr_api_key: ''
  }
};

const initialSettings: Settings = {
  // General
  schedule_mode: 'auto',
  debug_mode: false,
  
  // Hardware
  default_wifi: '',
  default_printer: '',
  display_resolution: 'D1920X1080',
  
  // Paths
  default_webdriver_path: '',
  build_dom_tree_script_path: 'agent/ec_skills/dom/buildDomTree.js',
  new_orders_dir: '',
  new_bots_file_path: '',
  new_orders_path: '',
  browser_use_file_system_path: '',
  browser_use_download_dir: '',
  browser_use_user_data_dir: '',
  gui_flowgram_schema: 'myskills/node_schemas.json',
  
  // Local DB
  local_user_db_host: '127.0.0.1',
  local_user_db_port: '5080',
  local_agent_db_host: '',
  local_agent_db_port: '6668',
  local_agent_ports: [3600, 3800],
  local_server_port: '4668',
  
  // API Endpoints
  lan_api_endpoint: '',
  wan_api_endpoint: 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql',
  ws_api_endpoint: 'wss://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-realtime-api.us-east-1.amazonaws.com/graphql',
  ws_api_host: '3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com',
  ecan_cloud_searcher_url: 'http://52.204.81.197:5808/search_components',
  
  // API Keys
  wan_api_key: '',
  ocr_api_key: '',
  
  // Engines
  network_api_engine: 'lan',
  schedule_engine: 'wan',
  
  // OCR
  ocr_api_endpoint: 'http://52.204.81.197:8848/graphql/reqScreenTxtRead',
  
  // LLM
  default_llm: 'ChatOpenAI',
  default_llm_model: '',
  
  // Embedding
  default_embedding: 'OpenAI',
  default_embedding_model: 'text-embedding-3-small',
  
  // Skill
  skill_use_git: false,
  
  // Internal
  last_bots_file: '',
  last_bots_file_time: 0,
  last_order_file: '',
  last_order_file_time: 0,
  mids_forced_to_run: []
};

const Settings: React.FC = () => {
  const { t } = useTranslation();
  const location = useLocation();
  const { token } = theme.useToken();
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [settingsData, setSettingsData] = useState<Settings | null>(null);
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const [activeTab, setActiveTab] = useState<string>('general');
  const username = useUserStore((state) => state.username);

  const isMountedRef = useRef(false);
  const settingsContentRef = useRef<HTMLDivElement | null>(null);
  const savedScrollPositionRef = useRef<number>(0);
  
  // Parse tab from URL on mount
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const tabParam = params.get('tab');
    if (tabParam === 'llm') {
      setActiveTab('llm');
    } else if (tabParam === 'embedding') {
      setActiveTab('embedding');
    } else {
      setActiveTab('general');
    }
  }, [location.search]);

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

  // Sync form values when settingsData changes (e.g., from LLM/Embedding management updates)
  useEffect(() => {
    if (settingsData && form) {
      // Only update specific fields that changed
      const currentValues = form.getFieldsValue();
      const updates: any = {};
      
      if (currentValues.default_llm !== settingsData.default_llm || 
          currentValues.default_llm_model !== settingsData.default_llm_model) {
        updates.default_llm = settingsData.default_llm;
        updates.default_llm_model = settingsData.default_llm_model;
      }
      
      if (currentValues.default_embedding !== settingsData.default_embedding || 
          currentValues.default_embedding_model !== settingsData.default_embedding_model) {
        updates.default_embedding = settingsData.default_embedding;
        updates.default_embedding_model = settingsData.default_embedding_model;
      }
      
      if (Object.keys(updates).length > 0) {
        console.log('🔄 Syncing form with updated settingsData:', updates);
        form.setFieldsValue(updates);
      }
    }
  }, [settingsData?.default_llm, settingsData?.default_llm_model, 
      settingsData?.default_embedding, settingsData?.default_embedding_model, form]);

  // Handle tab change
  const handleTabChange = (key: string) => {
    setActiveTab(key);
    // Update URL parameter
    const newUrl = new URL(window.location.href);
    if (key === 'llm') {
      newUrl.searchParams.set('tab', 'llm');
    } else if (key === 'embedding') {
      newUrl.searchParams.set('tab', 'embedding');
    } else {
      newUrl.searchParams.delete('tab');
    }
    if (newUrl.href !== window.location.href) {
      window.history.replaceState(null, '', newUrl);
    }
  };

  // Handle default LLM change from LLMManagement component
  const handleDefaultLLMChange = useCallback(async (newDefaultLLM: string, newDefaultModel?: string) => {
    console.log('🔔 [Settings] handleDefaultLLMChange called:', { newDefaultLLM, newDefaultModel });
    
    if (!username) {
      console.warn('⚠️ No username, skipping settings save');
      return;
    }

    // Update local settings data
    setSettingsData(prevSettings => {
      console.log('🔄 [Settings] Previous settings:', { default_llm: prevSettings?.default_llm, default_llm_model: prevSettings?.default_llm_model });
      
      if (prevSettings) {
        const updates: any = { default_llm: newDefaultLLM };
        // Also update default_llm_model if provided
        if (newDefaultModel !== undefined) {
          updates.default_llm_model = newDefaultModel;
        }
        console.log('🔄 Updating settings in parent:', updates);
        
        // Save updated settings to backend
        const updatedSettings = { ...prevSettings, ...updates };
        console.log('✅ [Settings] New settings created:', { default_llm: updatedSettings.default_llm, default_llm_model: updatedSettings.default_llm_model });
        
        // Async save to backend (don't await to avoid blocking UI)
        get_ipc_api().saveSettings({ username, ...updatedSettings })
          .then(response => {
            if (response && response.success) {
              console.log('✅ Default LLM settings saved to backend:', { default_llm: newDefaultLLM, default_llm_model: newDefaultModel });
            } else {
              console.error('❌ Failed to save default LLM settings:', response);
            }
          })
          .catch(error => {
            console.error('❌ Error saving default LLM settings:', error);
          });
        
        return updatedSettings;
      }
      return prevSettings;
    });
  }, [username]);

  // Refs to manage cross-component refresh for shared providers
  const llmManagementRef = React.useRef<{ loadProviders: () => Promise<void> } | null>(null);
  const embeddingManagementRef = React.useRef<{ loadProviders: () => Promise<void> } | null>(null);

  // Callback to refresh the other component when shared providers are updated
  const handleSharedProviderUpdate = useCallback((sharedProviders: Array<{ name: string; type: string }>) => {
    console.log('🔄 [Settings] Shared providers updated:', sharedProviders);
    
    // Refresh the other component based on shared provider type
    sharedProviders.forEach((provider) => {
      if (provider.type === 'embedding' && embeddingManagementRef.current) {
        console.log('🔄 [Settings] Refreshing EmbeddingManagement due to shared provider:', provider.name);
        embeddingManagementRef.current.loadProviders();
      } else if (provider.type === 'llm' && llmManagementRef.current) {
        console.log('🔄 [Settings] Refreshing LLMManagement due to shared provider:', provider.name);
        llmManagementRef.current.loadProviders();
      }
    });
  }, []);

  // Handle default Embedding change from EmbeddingManagement component
  const handleDefaultEmbeddingChange = useCallback(async (newDefaultEmbedding: string, newDefaultModel?: string) => {
    console.log('🔔 [Settings] handleDefaultEmbeddingChange called:', { newDefaultEmbedding, newDefaultModel });
    
    if (!username) {
      console.warn('⚠️ No username, skipping settings save');
      return;
    }

    // Update local settings data
    setSettingsData(prevSettings => {
      console.log('🔄 [Settings] Previous settings:', { default_embedding: prevSettings?.default_embedding, default_embedding_model: prevSettings?.default_embedding_model });
      
      if (prevSettings) {
        const updates: any = { default_embedding: newDefaultEmbedding };
        // Also update default_embedding_model if provided
        if (newDefaultModel !== undefined) {
          updates.default_embedding_model = newDefaultModel;
        }
        console.log('🔄 Updating settings in parent:', updates);
        
        // Save updated settings to backend
        const updatedSettings = { ...prevSettings, ...updates };
        console.log('✅ [Settings] New settings created:', { default_embedding: updatedSettings.default_embedding, default_embedding_model: updatedSettings.default_embedding_model });
        
        // Async save to backend (don't await to avoid blocking UI)
        get_ipc_api().saveSettings({ username, ...updatedSettings })
          .then(response => {
            if (response && response.success) {
              console.log('✅ Default Embedding settings saved to backend:', { default_embedding: newDefaultEmbedding, default_embedding_model: newDefaultModel });
            } else {
              console.error('❌ Failed to save default Embedding settings:', response);
            }
          })
          .catch(error => {
            console.error('❌ Error saving default Embedding settings:', error);
          });
        
        return updatedSettings;
      }
      return prevSettings;
    });
  }, [username]);

  // Handle network_api_engine change - also update OCR settings
  const handleNetworkApiEngineChange = useCallback((value: 'lan' | 'wan') => {
    console.log('🔄 Network API engine changed to:', value);
    const preset = OCR_PRESETS[value];
    
    // 获取当前表单的所有值
    const currentValues = form.getFieldsValue();
    
    // 只在当前值为空或使用默认值时才应用预设
    const shouldApplyPreset = (
      !currentValues.ocr_api_endpoint || 
      currentValues.ocr_api_endpoint === OCR_PRESETS.lan.ocr_api_endpoint ||
      currentValues.ocr_api_endpoint === OCR_PRESETS.wan.ocr_api_endpoint
    );
    
    if (shouldApplyPreset) {
      // 应用预设配置
      form.setFieldsValue({
        ocr_api_endpoint: preset.ocr_api_endpoint,
        ocr_api_key: preset.ocr_api_key
      });
      
      message.info(t('pages.settings.ocr_preset_applied', { engine: value.toUpperCase() }));
    } else {
      // 用户有自定义配置，保持不变
      console.log('ℹ️ User has custom OCR config, keeping it');
    }
  }, [form, message, t]);

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

  // Open path in file explorer (using IPC to call backend)
  const handleOpenPath = async (fieldName: string) => {
    const path = form.getFieldValue(fieldName);
    if (!path || path.trim() === '') {
      message.warning(t('pages.settings.path_empty_warning'));
      return;
    }

    try {
      // Use IPC to call backend to open folder
      const response = await get_ipc_api().executeRequest<{ success: boolean }>('open_folder', { path });
      if (response && response.success) {
        message.success(t('pages.settings.path_opened_success'));
      } else {
        // 根据错误类型显示不同的提示
        const errorCode = response?.error?.code;
        if (errorCode === 'PATH_NOT_FOUND') {
          message.error(t('pages.settings.path_not_found', { path }));
        } else {
          message.error(t('pages.settings.path_open_error'));
        }
      }
    } catch (error) {
      console.error('Error opening path:', error);
      message.error(t('pages.settings.path_open_error'));
    }
  };

  // Open URL in browser (using window.open)
  const handleOpenUrl = (fieldName: string) => {
    const url = form.getFieldValue(fieldName);
    if (!url || url.trim() === '') {
      message.warning(t('pages.settings.url_empty_warning'));
      return;
    }

    try {
      // Open URL in new tab
      window.open(url, '_blank', 'noopener,noreferrer');
      message.success(t('pages.settings.url_opened_success'));
    } catch (error) {
      console.error('Error opening URL:', error);
      message.error(t('pages.settings.url_open_error'));
    }
  };

  // Initial loading
  useEffect(() => {
    if (username) {
      loadSettings();
    }
  }, [username, loadSettings]);

  // 使用 useEffectOnActive 在ComponentActive时RestoreScrollPosition
  useEffectOnActive(
    () => {
      // ComponentActive时：RestoreScrollPosition
      const container = settingsContentRef.current;
      if (container && savedScrollPositionRef.current > 0) {
        requestAnimationFrame(() => {
          container.scrollTop = savedScrollPositionRef.current;
          // console.log('[Settings] Restored scroll position:', savedScrollPositionRef.current);
        });
      }
      
      // 返回CleanupFunction，在Component失活前SaveScrollPosition
      return () => {
        const container = settingsContentRef.current;
        if (container) {
          savedScrollPositionRef.current = container.scrollTop;
          //console.log('[Settings] Saved scroll position:', savedScrollPositionRef.current);
        }
      };
    },
    []
  );

  return (
    <SettingsContainer style={{ background: token.colorBgLayout }}>
      <SettingsContent ref={settingsContentRef}>
        <style>{`
          .ant-tabs-nav {
            background: ${token.colorBgContainer} !important;
            border-bottom: 1px solid ${token.colorBorderSecondary} !important;
          }
          .ant-tabs-tab {
            color: ${token.colorTextSecondary} !important;
          }
          .ant-tabs-tab:hover {
            color: ${token.colorPrimary} !important;
            background: ${token.colorPrimaryBg} !important;
          }
          .ant-tabs-tab-active {
            color: ${token.colorPrimary} !important;
            border-bottom-color: ${token.colorPrimary} !important;
          }
          .ant-tabs-content-holder {
            background: ${token.colorBgLayout} !important;
          }
          .ant-tabs-tabpane::-webkit-scrollbar-track {
            background: ${token.colorBgContainer};
          }
          .ant-tabs-tabpane::-webkit-scrollbar-thumb {
            background: ${token.colorBorder};
          }
          .ant-tabs-tabpane::-webkit-scrollbar-thumb:hover {
            background: ${token.colorBorderSecondary};
          }
        `}</style>
        <Tabs
          activeKey={activeTab}
          onChange={handleTabChange}
          items={[
            {
              key: 'general',
              label: t('pages.settings.general_tab_title') || 'General',
              children: (
                <StyledCard
                  title={t('common.settings')}
                  extra={
                    <Tooltip title={t('common.reload')}>
                      <StyledRefreshButton
                        shape="circle"
                        icon={<ReloadOutlined />}
                        onClick={handleReload}
                        loading={loading}
                      />
                    </Tooltip>
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
          {/* Base模式Settings */}
          <StyledCard
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
                </StyledCard>

          {/* 硬件Settings */}
          <StyledCard
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
                </StyledCard>

          {/* 引擎和端口Settings */}
          <StyledCard
            title={t('pages.settings.engine_port_settings')}
            size="small"
            style={{ marginBottom: '8px' }}
            styles={{ body: { padding: '12px 16px 8px 16px' } }}
          >
            <Row gutter={[16, 4]}>
              <Col span={8}>
                <StyledFormItem
                  name="network_api_engine"
                  label={t('pages.settings.network_api_engine')}
                  style={{ marginBottom: '8px' }}
                  tooltip={t('pages.settings.network_api_engine_tooltip')}
                >
                  <Select 
                    size="small"
                    onChange={handleNetworkApiEngineChange}
                  >
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
                </StyledCard>

          {/* API Configuration Settings - Group related endpoint+key pairs */}
          <StyledCard
            title={t('pages.settings.api_configuration')}
            size="small"
            style={{ marginBottom: '8px' }}
            styles={{ body: { padding: '12px 16px 8px 16px' } }}
          >
            {/* OCR API Configuration */}
            <Divider orientation="left" style={{ margin: '8px 0 12px 0', fontSize: '13px', fontWeight: 600 }}>
              {t('pages.settings.ocr_api_config')}
            </Divider>
            <Row gutter={[16, 4]}>
              <Col span={18}>
                <StyledFormItem
                  name="ocr_api_endpoint"
                  label={t('pages.settings.ocr_api_endpoint')}
                  style={{ marginBottom: '8px' }}
                  tooltip={t('pages.settings.ocr_api_endpoint_tooltip')}
                >
                  <Input 
                    size="small" 
                    placeholder={form.getFieldValue('network_api_engine') === 'lan' 
                      ? 'http://52.204.81.197:8848/graphql/reqScreenTxtRead' 
                      : 'Enter WAN OCR endpoint'
                    }
                    suffix={
                      <Tooltip title={t('pages.settings.open_in_browser')}>
                        <Button 
                          type="text" 
                          size="small" 
                          icon={<GlobalOutlined />}
                          onClick={() => handleOpenUrl('ocr_api_endpoint')}
                          style={{ 
                            cursor: 'pointer',
                            color: 'rgba(203, 213, 225, 0.7)',
                            fontSize: '14px',
                            transition: 'color 0.2s'
                          }}
                          onMouseEnter={(e) => e.currentTarget.style.color = 'rgba(255, 255, 255, 0.9)'}
                          onMouseLeave={(e) => e.currentTarget.style.color = 'rgba(203, 213, 225, 0.7)'}
                        />
                      </Tooltip>
                    }
                    style={{
                      border: 'none'
                    }}
                  />
                </StyledFormItem>
              </Col>
              <Col span={6}>
                <StyledFormItem
                  name="ocr_api_key"
                  label={t('pages.settings.ocr_api_key')}
                  style={{ marginBottom: '8px' }}
                  tooltip={t('pages.settings.ocr_api_key_tooltip')}
                >
                  <Input.Password 
                    size="small" 
                    placeholder={form.getFieldValue('network_api_engine') === 'lan' ? 'xxxxxxxxxxxxxx' : 'Enter API key'}
                  />
                </StyledFormItem>
              </Col>
            </Row>

            {/* WAN API Configuration */}
            <Divider orientation="left" style={{ margin: '16px 0 12px 0', fontSize: '13px', fontWeight: 600 }}>
              {t('pages.settings.wan_api_config')}
            </Divider>
            <Row gutter={[16, 4]}>
              <Col span={18}>
                <StyledFormItem
                  name="wan_api_endpoint"
                  label={t('pages.settings.wan_api_endpoint')}
                  style={{ marginBottom: '8px' }}
                >
                  <Input 
                    size="small" 
                    placeholder="Enter WAN API endpoint"
                    suffix={
                      <Tooltip title={t('pages.settings.open_in_browser')}>
                        <Button 
                          type="text" 
                          size="small" 
                          icon={<GlobalOutlined />}
                          onClick={() => handleOpenUrl('wan_api_endpoint')}
                          style={{ 
                            cursor: 'pointer',
                            color: 'rgba(203, 213, 225, 0.7)',
                            fontSize: '14px',
                            transition: 'color 0.2s'
                          }}
                          onMouseEnter={(e) => e.currentTarget.style.color = 'rgba(255, 255, 255, 0.9)'}
                          onMouseLeave={(e) => e.currentTarget.style.color = 'rgba(203, 213, 225, 0.7)'}
                        />
                      </Tooltip>
                    }
                    style={{
                      border: 'none'
                    }}
                  />
                </StyledFormItem>
              </Col>
              <Col span={6}>
                <StyledFormItem
                  name="wan_api_key"
                  label={t('pages.settings.wan_api_key')}
                  style={{ marginBottom: '8px' }}
                >
                  <Input.Password size="small" placeholder="Enter WAN API key" />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="ws_api_endpoint"
                  label={t('pages.settings.ws_api_endpoint')}
                  style={{ marginBottom: '8px' }}
                >
                  <Input 
                    size="small" 
                    placeholder="Enter WebSocket API endpoint"
                    suffix={
                      <Tooltip title={t('pages.settings.open_in_browser')}>
                        <Button 
                          type="text" 
                          size="small" 
                          icon={<GlobalOutlined />}
                          onClick={() => handleOpenUrl('ws_api_endpoint')}
                          style={{ 
                            cursor: 'pointer',
                            color: 'rgba(203, 213, 225, 0.7)',
                            fontSize: '14px',
                            transition: 'color 0.2s'
                          }}
                          onMouseEnter={(e) => e.currentTarget.style.color = 'rgba(255, 255, 255, 0.9)'}
                          onMouseLeave={(e) => e.currentTarget.style.color = 'rgba(203, 213, 225, 0.7)'}
                        />
                      </Tooltip>
                    }
                    style={{
                      border: 'none'
                    }}
                  />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="ws_api_host"
                  label={t('pages.settings.ws_api_host')}
                  style={{ marginBottom: '8px' }}
                >
                  <Input size="small" placeholder="Enter WebSocket API host" />
                </StyledFormItem>
              </Col>
            </Row>

            {/* LAN API Configuration */}
            <Divider orientation="left" style={{ margin: '16px 0 12px 0', fontSize: '13px', fontWeight: 600 }}>
              {t('pages.settings.lan_api_config')}
            </Divider>
            <Row gutter={[16, 4]}>
              <Col span={24}>
                <StyledFormItem
                  name="lan_api_endpoint"
                  label={t('pages.settings.lan_api_endpoint')}
                  style={{ marginBottom: '8px' }}
                  tooltip={t('pages.settings.lan_api_endpoint_tooltip')}
                >
                  <Input 
                    size="small" 
                    placeholder="Enter LAN API endpoint"
                    suffix={
                      <Tooltip title={t('pages.settings.open_in_browser')}>
                        <Button 
                          type="text" 
                          size="small" 
                          icon={<GlobalOutlined />}
                          onClick={() => handleOpenUrl('lan_api_endpoint')}
                          style={{ 
                            cursor: 'pointer',
                            color: 'rgba(203, 213, 225, 0.7)',
                            fontSize: '14px',
                            transition: 'color 0.2s'
                          }}
                          onMouseEnter={(e) => e.currentTarget.style.color = 'rgba(255, 255, 255, 0.9)'}
                          onMouseLeave={(e) => e.currentTarget.style.color = 'rgba(203, 213, 225, 0.7)'}
                        />
                      </Tooltip>
                    }
                    style={{
                      border: 'none'
                    }}
                  />
                </StyledFormItem>
              </Col>
              <Col span={24}>
                <StyledFormItem
                  name="ecan_cloud_searcher_url"
                  label={t('pages.settings.ecan_cloud_searcher_url')}
                  style={{ marginBottom: '8px' }}
                >
                  <Input 
                    size="small" 
                    placeholder="Enter eCan Cloud Searcher URL"
                    suffix={
                      <Tooltip title={t('pages.settings.open_in_browser')}>
                        <Button 
                          type="text" 
                          size="small" 
                          icon={<GlobalOutlined />}
                          onClick={() => handleOpenUrl('ecan_cloud_searcher_url')}
                          style={{ 
                            cursor: 'pointer',
                            color: 'rgba(203, 213, 225, 0.7)',
                            fontSize: '14px',
                            transition: 'color 0.2s'
                          }}
                          onMouseEnter={(e) => e.currentTarget.style.color = 'rgba(255, 255, 255, 0.9)'}
                          onMouseLeave={(e) => e.currentTarget.style.color = 'rgba(203, 213, 225, 0.7)'}
                        />
                      </Tooltip>
                    }
                    style={{
                      border: 'none'
                    }}
                  />
                </StyledFormItem>
              </Col>
            </Row>
                </StyledCard>

          {/* PathSettings */}
          <StyledCard
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
                  <Input 
                    size="small" 
                    placeholder="Enter webdriver path"
                    suffix={
                      <Tooltip title={t('pages.settings.open_folder')}>
                        <FolderOpenOutlined 
                          onClick={() => handleOpenPath('default_webdriver_path')}
                          style={{ 
                            cursor: 'pointer',
                            color: 'rgba(203, 213, 225, 0.7)',
                            fontSize: '14px',
                            transition: 'color 0.2s'
                          }}
                          onMouseEnter={(e) => e.currentTarget.style.color = 'rgba(255, 255, 255, 0.9)'}
                          onMouseLeave={(e) => e.currentTarget.style.color = 'rgba(203, 213, 225, 0.7)'}
                        />
                      </Tooltip>
                    }
                    style={{
                      border: 'none'
                    }}
                  />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="build_dom_tree_script_path"
                  label={t('pages.settings.build_dom_tree_script_path')}
                  style={{ marginBottom: '6px' }}
                >
                  <Input 
                    size="small" 
                    placeholder="Enter DOM tree script path"
                    suffix={
                      <Tooltip title={t('pages.settings.open_folder')}>
                        <FolderOpenOutlined 
                          onClick={() => handleOpenPath('build_dom_tree_script_path')}
                          style={{ 
                            cursor: 'pointer',
                            color: 'rgba(203, 213, 225, 0.7)',
                            fontSize: '14px',
                            transition: 'color 0.2s'
                          }}
                          onMouseEnter={(e) => e.currentTarget.style.color = 'rgba(255, 255, 255, 0.9)'}
                          onMouseLeave={(e) => e.currentTarget.style.color = 'rgba(203, 213, 225, 0.7)'}
                        />
                      </Tooltip>
                    }
                    style={{
                      border: 'none'
                    }}
                  />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="browser_use_file_system_path"
                  label={t('pages.settings.browser_use_file_system_path')}
                  style={{ marginBottom: '6px' }}
                >
                  <Input 
                    size="small" 
                    placeholder="Enter browser file system path"
                    suffix={
                      <Tooltip title={t('pages.settings.open_folder')}>
                        <FolderOpenOutlined 
                          onClick={() => handleOpenPath('browser_use_file_system_path')}
                          style={{ 
                            cursor: 'pointer',
                            color: 'rgba(203, 213, 225, 0.7)',
                            fontSize: '14px',
                            transition: 'color 0.2s'
                          }}
                          onMouseEnter={(e) => e.currentTarget.style.color = 'rgba(255, 255, 255, 0.9)'}
                          onMouseLeave={(e) => e.currentTarget.style.color = 'rgba(203, 213, 225, 0.7)'}
                        />
                      </Tooltip>
                    }
                    style={{
                      border: 'none'
                    }}
                  />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="new_orders_dir"
                  label={t('pages.settings.new_orders_dir')}
                  style={{ marginBottom: '6px' }}
                >
                  <Input 
                    size="small" 
                    placeholder="Enter new orders directory"
                    suffix={
                      <Tooltip title={t('pages.settings.open_folder')}>
                        <FolderOpenOutlined 
                          onClick={() => handleOpenPath('new_orders_dir')}
                          style={{ 
                            cursor: 'pointer',
                            color: 'rgba(203, 213, 225, 0.7)',
                            fontSize: '14px',
                            transition: 'color 0.2s'
                          }}
                          onMouseEnter={(e) => e.currentTarget.style.color = 'rgba(255, 255, 255, 0.9)'}
                          onMouseLeave={(e) => e.currentTarget.style.color = 'rgba(203, 213, 225, 0.7)'}
                        />
                      </Tooltip>
                    }
                    style={{
                      border: 'none'
                    }}
                  />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="new_orders_path"
                  label={t('pages.settings.new_orders_path')}
                  style={{ marginBottom: '6px' }}
                >
                  <Input 
                    size="small" 
                    placeholder="Enter new orders path"
                    suffix={
                      <Tooltip title={t('pages.settings.open_folder')}>
                        <FolderOpenOutlined 
                          onClick={() => handleOpenPath('new_orders_path')}
                          style={{ 
                            cursor: 'pointer',
                            color: 'rgba(203, 213, 225, 0.7)',
                            fontSize: '14px',
                            transition: 'color 0.2s'
                          }}
                          onMouseEnter={(e) => e.currentTarget.style.color = 'rgba(255, 255, 255, 0.9)'}
                          onMouseLeave={(e) => e.currentTarget.style.color = 'rgba(203, 213, 225, 0.7)'}
                        />
                      </Tooltip>
                    }
                    style={{
                      border: 'none'
                    }}
                  />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="new_bots_file_path"
                  label={t('pages.settings.new_bots_file_path')}
                  style={{ marginBottom: '6px' }}
                >
                  <Input 
                    size="small" 
                    placeholder="Enter new bots file path"
                    suffix={
                      <Tooltip title={t('pages.settings.open_folder')}>
                        <FolderOpenOutlined 
                          onClick={() => handleOpenPath('new_bots_file_path')}
                          style={{ 
                            cursor: 'pointer',
                            color: 'rgba(203, 213, 225, 0.7)',
                            fontSize: '14px',
                            transition: 'color 0.2s'
                          }}
                          onMouseEnter={(e) => e.currentTarget.style.color = 'rgba(255, 255, 255, 0.9)'}
                          onMouseLeave={(e) => e.currentTarget.style.color = 'rgba(203, 213, 225, 0.7)'}
                        />
                      </Tooltip>
                    }
                    style={{
                      border: 'none'
                    }}
                  />
                </StyledFormItem>
              </Col>
            </Row>
                </StyledCard>

          {/* Database Settings - Group host+port pairs */}
          <StyledCard
            title={t('pages.settings.database_settings')}
            size="small"
            style={{ marginBottom: '8px' }}
            styles={{ body: { padding: '12px 16px 8px 16px' } }}
          >
            {/* User Database Configuration */}
            <Divider orientation="left" style={{ margin: '8px 0 12px 0', fontSize: '13px', fontWeight: 600 }}>
              {t('pages.settings.user_database_config')}
            </Divider>
            <Row gutter={[16, 4]}>
              <Col span={18}>
                <StyledFormItem
                  name="local_user_db_host"
                  label={t('pages.settings.local_user_db_host')}
                  style={{ marginBottom: '8px' }}
                >
                  <Input size="small" placeholder="Enter user DB host (e.g., localhost)" />
                </StyledFormItem>
              </Col>
              <Col span={6}>
                <StyledFormItem
                  name="local_user_db_port"
                  label={t('pages.settings.local_user_db_port')}
                  style={{ marginBottom: '8px' }}
                >
                  <Input size="small" placeholder="Port" />
                </StyledFormItem>
              </Col>
            </Row>

            {/* Agent Database Configuration */}
            <Divider orientation="left" style={{ margin: '16px 0 12px 0', fontSize: '13px', fontWeight: 600 }}>
              {t('pages.settings.agent_database_config')}
            </Divider>
            <Row gutter={[16, 4]}>
              <Col span={18}>
                <StyledFormItem
                  name="local_agent_db_host"
                  label={t('pages.settings.local_agent_db_host')}
                  style={{ marginBottom: '8px' }}
                >
                  <Input size="small" placeholder="Enter agent DB host (e.g., localhost)" />
                </StyledFormItem>
              </Col>
              <Col span={6}>
                <StyledFormItem
                  name="local_agent_db_port"
                  label={t('pages.settings.local_agent_db_port')}
                  style={{ marginBottom: '8px' }}
                >
                  <Input size="small" placeholder="Port" />
                </StyledFormItem>
              </Col>
            </Row>

                </StyledCard>

          {/* 文件跟踪和其他Settings */}
          <StyledCard
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
                  <Input 
                    size="small" 
                    placeholder="Enter GUI flowgram schema"
                    suffix={
                      <Tooltip title={t('pages.settings.open_folder')}>
                        <FolderOpenOutlined 
                          onClick={() => handleOpenPath('gui_flowgram_schema')}
                          style={{ 
                            cursor: 'pointer',
                            color: 'rgba(203, 213, 225, 0.7)',
                            fontSize: '14px',
                            transition: 'color 0.2s'
                          }}
                          onMouseEnter={(e) => e.currentTarget.style.color = 'rgba(255, 255, 255, 0.9)'}
                          onMouseLeave={(e) => e.currentTarget.style.color = 'rgba(203, 213, 225, 0.7)'}
                        />
                      </Tooltip>
                    }
                    style={{
                      border: 'none'
                    }}
                  />
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
                </StyledCard>

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
                </StyledCard>
              ),
            },
            {
              key: 'llm',
              label: t('pages.settings.llm_tab_title') || 'LLM',
              children: (
                <LLMManagement
                  ref={llmManagementRef}
                  username={username}
                  defaultLLM={settingsData?.default_llm || ''}
                  settingsLoaded={settingsLoaded}
                  onDefaultLLMChange={handleDefaultLLMChange}
                  onSharedProviderUpdate={handleSharedProviderUpdate}
                />
              ),
            },
            {
              key: 'embedding',
              label: t('pages.settings.embedding_tab_title') || 'Embedding',
              children: (
                <EmbeddingManagement
                  ref={embeddingManagementRef}
                  username={username}
                  defaultEmbedding={settingsData?.default_embedding || ''}
                  settingsLoaded={settingsLoaded}
                  onDefaultEmbeddingChange={handleDefaultEmbeddingChange}
                  onSharedProviderUpdate={handleSharedProviderUpdate}
                />
              ),
            },
          ]}
        />
      </SettingsContent>
    </SettingsContainer>
  );
};

export default Settings;
