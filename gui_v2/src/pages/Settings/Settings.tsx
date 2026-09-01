import React, { useState, useCallback, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, Form, Select, Switch, Button, App, Input, Row, Col, Tooltip, Divider, Tabs, theme } from 'antd';
import { ReloadOutlined, FolderOpenOutlined, GlobalOutlined, SettingOutlined, RobotOutlined, BlockOutlined, SortAscendingOutlined, SaveOutlined, CloudServerOutlined, ChromeOutlined, MessageOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { useEffectOnActive } from 'keepalive-for-react';
import { useLocation } from 'react-router-dom';

import { useUserStore } from '../../stores/userStore';
import { get_ipc_api } from '@/services/ipc_api';

import type { Settings } from './types';
import { LLMManagement, EmbeddingManagement, RerankManagement, RyoaisManagement, BrowserUseSettings, GeneralTabContent, ChannelSettings } from './components';

// CN/Intl detection is now handled by backend at login time (see user_handler._apply_intl_endpoints)
// CN uses TCB, Intl uses AppSync - frontend receives populated endpoints from backend

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
      overflow: hidden;
      
      .ant-tabs-tabpane {
        height: 100%;
        overflow-y: auto;
        overflow-x: auto;
        padding: 0;
      }
      
      .ant-tabs-tabpane-active {
        display: flex;
        flex-direction: column;
      }
    }
    
    .ant-tabs-nav-wrap {
      flex-shrink: 0;
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

// Endpoints are now populated by backend at login time (see user_handler._apply_intl_endpoints)
// CN uses TCB (no endpoint config needed), Intl uses AppSync (filled from auth_config.yml)

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

  // API Endpoints (populated by backend at login time)
  lan_api_endpoint: '',
  wan_api_endpoint: '',
  ws_api_endpoint: '',
  ws_api_host: '',
  ecan_cloud_searcher_url: 'http://52.204.81.197:5808/search_components',
  
  // API Keys
  wan_api_key: '',
  
  // Engines
  network_api_engine: 'lan',
  schedule_engine: 'wan',
  
  // OCR
  ocr_api_endpoint: 'http://52.204.81.197:8848/graphql/reqScreenTxtRead',
  ocr_api_key: '',
  
  // Cloud LLM Proxy
  use_lambda_proxy: false,
  lambda_proxy_endpoint: '',
  
  // LLM
  default_llm: 'ecanai',
  default_llm_model: '',
  
  // Embedding
  default_embedding: 'ecanai',
  default_embedding_model: 'text-embedding-v3',
  
  // Rerank
  default_rerank: 'ecanai',
  default_rerank_model: 'gte-rerank',
  
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
  const [ryoaisDevices, setRyoaisDevices] = useState<any[]>([]);
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
    console.log('� [Settings] handleDefaultLLMChange called:', { newDefaultLLM, newDefaultModel });
    
    if (!username) {
      console.log('❌ No username, skipping save');
      return;
    }

    // Update local settings data
    setSettingsData(prevSettings => {
      console.log('🔄 [Settings] Previous settings:', { default_llm: prevSettings?.default_llm, default_llm_model: prevSettings?.default_llm_model });
      
      if (prevSettings) {
        const updates: Partial<Settings> = {
          default_llm: newDefaultLLM
        };
        if (newDefaultModel !== undefined) {
          updates.default_llm_model = newDefaultModel;
        }
        console.log('🔄 Updating settings in parent:', updates);
        
        // Save updated settings to backend
        const updatedSettings = { ...prevSettings, ...updates };
        console.log('✅ [Settings] New settings created:', { default_llm: updatedSettings.default_llm, default_llm_model: updatedSettings.default_llm_model });
        
        // IMPORTANT: Remove nested 'settings' field and old token before saving
        // The token in settingsData is from config file (old), not current session token
        const { settings: _, token: __, username: ___, ...cleanSettings } = updatedSettings as any;
        
        // Async save to backend (don't await to avoid blocking UI)
        get_ipc_api().saveSettings({ username, ...cleanSettings })
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
  const rerankManagementRef = React.useRef<{ loadProviders: () => Promise<void> } | null>(null);

  // Callback to refresh the other component when shared providers are updated
  const handleSharedProviderUpdate = useCallback((sharedProviders: Array<{ name: string; type: string }>) => {
    console.log('🔄 [Settings] Shared providers updated:', sharedProviders);
    
    // Refresh the other component based on shared provider type
    sharedProviders.forEach((provider) => {
      if (provider.type === 'embedding' && embeddingManagementRef.current) {
        console.log('🔄 [Settings] Refreshing EmbeddingManagement due to shared provider:', provider.name);
        embeddingManagementRef.current.loadProviders();
      } else if (provider.type === 'rerank' && rerankManagementRef.current) {
        console.log('🔄 [Settings] Refreshing RerankManagement due to shared provider:', provider.name);
        rerankManagementRef.current.loadProviders();
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
        
        // IMPORTANT: Remove nested 'settings' field and old token before saving
        // The token in settingsData is from config file (old), not current session token
        const { settings: _, token: __, username: ___, ...cleanSettings } = updatedSettings as any;
        
        // Async save to backend (don't await to avoid blocking UI)
        get_ipc_api().saveSettings({ username, ...cleanSettings })
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

  // Handle default Rerank change from RerankManagement component
  const handleDefaultRerankChange = useCallback(async (newDefaultRerank: string, newDefaultModel?: string) => {
    console.log('🔔 [Settings] handleDefaultRerankChange called:', { newDefaultRerank, newDefaultModel });
    
    if (!username) {
      console.warn('⚠️ No username, skipping settings save');
      return;
    }

    // Update local settings data
    setSettingsData(prevSettings => {
      console.log('🔄 [Settings] Previous settings:', { default_rerank: prevSettings?.default_rerank, default_rerank_model: prevSettings?.default_rerank_model });
      
      if (prevSettings) {
        const updates: any = { default_rerank: newDefaultRerank };
        // Also update default_rerank_model if provided
        if (newDefaultModel !== undefined) {
          updates.default_rerank_model = newDefaultModel;
        }
        console.log('🔄 Updating settings in parent:', updates);
        
        // Save updated settings to backend
        const updatedSettings = { ...prevSettings, ...updates };
        console.log('✅ [Settings] New settings created:', { default_rerank: updatedSettings.default_rerank, default_rerank_model: updatedSettings.default_rerank_model });
        
        // IMPORTANT: Remove nested 'settings' field and old token before saving
        // The token in settingsData is from config file (old), not current session token
        const { settings: _, token: __, username: ___, ...cleanSettings } = updatedSettings as any;
        
        // Async save to backend (don't await to avoid blocking UI)
        get_ipc_api().saveSettings({ username, ...cleanSettings })
          .then(response => {
            if (response && response.success) {
              console.log('✅ Default Rerank settings saved to backend:', { default_rerank: newDefaultRerank, default_rerank_model: newDefaultModel });
            } else {
              console.error('❌ Failed to save default Rerank settings:', response);
            }
          })
          .catch(error => {
            console.error('❌ Error saving default Rerank settings:', error);
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
      
      // IMPORTANT: Remove nested 'settings' field and old token before saving
      // The token in values is from config file (old), not current session token
      const { settings: _, token: __, username: ___, ...cleanValues } = values as any;
      
      const response = await get_ipc_api().saveSettings({ username, ...cleanValues });
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [username]);

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
          /* Auto-hide scrollbar - only show on hover/scroll */
          .ant-tabs-tabpane > div {
            scrollbar-width: thin;
            scrollbar-color: transparent transparent;
          }
          .ant-tabs-tabpane > div:hover {
            scrollbar-color: ${token.colorBorder} transparent;
          }
          /* Webkit scrollbar styles for direct children only */
          .ant-tabs-tabpane > div::-webkit-scrollbar {
            width: 6px;
          }
          .ant-tabs-tabpane > div::-webkit-scrollbar-track {
            background: transparent;
          }
          .ant-tabs-tabpane > div::-webkit-scrollbar-thumb {
            background: transparent;
            border-radius: 3px;
          }
          .ant-tabs-tabpane > div:hover::-webkit-scrollbar-thumb {
            background: ${token.colorBorder};
          }
          .ant-tabs-tabpane > div::-webkit-scrollbar-thumb:hover {
            background: ${token.colorTextSecondary};
          }
          /* Table body scrollbar */
          .ant-table-body {
            scrollbar-width: thin;
            scrollbar-color: transparent transparent;
          }
          .ant-table-body:hover {
            scrollbar-color: ${token.colorBorder} transparent;
          }
          .ant-table-body::-webkit-scrollbar {
            width: 6px;
          }
          .ant-table-body::-webkit-scrollbar-track {
            background: transparent;
          }
          .ant-table-body::-webkit-scrollbar-thumb {
            background: transparent;
            border-radius: 3px;
          }
          .ant-table-body:hover::-webkit-scrollbar-thumb {
            background: ${token.colorBorder};
          }
          /* Unified table header styles - match General Settings tabs */
          .ant-table-wrapper {
            padding-top: 0 !important;
            margin-top: 0 !important;
          }
          .ant-table {
            border-collapse: collapse !important;
            margin-top: 0 !important;
            border-spacing: 0 !important;
          }
          .ant-table-container {
            border-top: none !important;
            margin-top: 0 !important;
          }
          .ant-table-header {
            margin-bottom: 0 !important;
            padding-bottom: 0 !important;
          }
          .ant-table-thead {
            background: ${token.colorBgContainer} !important;
          }
          .ant-table-thead > tr {
            background: ${token.colorBgContainer} !important;
            height: auto !important;
            border: none !important;
          }
          .ant-table-thead > tr > th {
            background: ${token.colorBgContainer} !important;
            color: ${token.colorText} !important;
            font-weight: 500 !important;
            border: none !important;
            border-bottom: 1px solid ${token.colorBorderSecondary} !important;
            padding: 12px 16px !important;
            line-height: 1.5 !important;
            vertical-align: middle !important;
            height: auto !important;
          }
          .ant-table-thead > tr > th::before {
            display: none !important;
          }
          .ant-table-thead > tr > th::after {
            display: none !important;
          }
          .ant-table-tbody {
            border-top: none !important;
          }
          .ant-table-tbody > tr:first-child > td {
            border-top: none !important;
            padding-top: 12px !important;
          }
          .ant-table-tbody > tr > td {
            border-top: none !important;
          }
          /* Remove all gaps */
          .ant-table table {
            border-spacing: 0 !important;
            border-collapse: collapse !important;
          }
          /* Fix sticky header gap */
          .ant-table-sticky-holder {
            margin-top: 0 !important;
            padding-top: 0 !important;
          }
          .ant-table-sticky-scroll {
            display: none !important;
          }
          /* Remove padding from table parent containers */
          .ant-tabs-tabpane > div > div[style*="paddingTop"] {
            padding-top: 0 !important;
          }
        `}</style>
        <Tabs
          activeKey={activeTab}
          onChange={handleTabChange}
          destroyOnHidden={true}
          items={[
            {
              key: 'general',
              label: (
                <span>
                  <SettingOutlined style={{ marginRight: 8 }} />
                  {t('pages.settings.general_tab_title') || 'General'}
                </span>
              ),
              children: (
                <Form
                  key={formKey}
                  form={form}
                  layout="vertical"
                  onFinish={handleSave}
                  preserve={true}
                  initialValues={settingsData || initialSettings}
                >
                  <GeneralTabContent
                    form={form}
                    loading={loading}
                    handleReload={handleReload}
                    handleNetworkApiEngineChange={handleNetworkApiEngineChange}
                    handleOpenUrl={handleOpenUrl}
                  />
                </Form>
              ),
            },
            {
              key: 'llm',
              label: (
                <span>
                  <RobotOutlined style={{ marginRight: 8 }} />
                  {t('pages.settings.llm_tab_title') || 'LLM'}
                </span>
              ),
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
              label: (
                <span>
                  <BlockOutlined style={{ marginRight: 8 }} />
                  {t('pages.settings.embedding_tab_title') || 'Embedding'}
                </span>
              ),
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
            {
              key: 'rerank',
              label: (
                <span>
                  <SortAscendingOutlined style={{ marginRight: 8 }} />
                  {t('pages.settings.rerank_tab_title') || 'Rerank'}
                </span>
              ),
              children: (
                <RerankManagement
                  ref={rerankManagementRef}
                  username={username}
                  defaultRerank={settingsData?.default_rerank || ''}
                  settingsLoaded={settingsLoaded}
                  onDefaultRerankChange={handleDefaultRerankChange}
                  onSharedProviderUpdate={handleSharedProviderUpdate}
                />
              ),
            },
            {
              key: 'ryoais',
              label: (
                <span>
                  <CloudServerOutlined style={{ marginRight: 8 }} />
                  {t('pages.settings.ryoais.tab_title') || 'ryoais Discovery'}
                </span>
              ),
              children: (
                <RyoaisManagement
                  username={username || undefined}
                  devices={ryoaisDevices}
                  onDevicesChange={setRyoaisDevices}
                />
              ),
            },
            {
              key: 'browser-use',
              label: (
                <span>
                  <ChromeOutlined style={{ marginRight: 8 }} />
                  {t('pages.settings.browser_use.tab_title')}
                </span>
              ),
              children: (
                <BrowserUseSettings
                  username={username || undefined}
                  settingsLoaded={settingsLoaded}
                />
              ),
            },
            {
              key: 'channels',
              label: (
                <span>
                  <MessageOutlined style={{ marginRight: 8 }} />
                  {t('pages.settings.channels_tab_title')}
                </span>
              ),
              children: <ChannelSettings />,
            },
          ]}
        />
      </SettingsContent>
    </SettingsContainer>
  );
};

export default Settings;
