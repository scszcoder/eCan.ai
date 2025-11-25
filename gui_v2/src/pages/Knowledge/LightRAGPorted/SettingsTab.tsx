import React, { useState, useEffect } from 'react';
import { theme, message, Tabs, Modal, Tooltip, Input, Select, Checkbox } from 'antd';
import { useTranslation } from 'react-i18next';
import { get_ipc_api } from '@/services/ipc_api';
import { 
  FolderOpenOutlined, 
  SaveOutlined, 
  DatabaseOutlined, 
  ApiOutlined, 
  CloudServerOutlined,
  RobotOutlined,
  BlockOutlined,
  SortAscendingOutlined,
  ExperimentOutlined,
  QuestionCircleOutlined
} from '@ant-design/icons';
import { useTheme } from '@/contexts/ThemeContext';
import { FIELDS_BY_TAB, FieldConfig, PROVIDER_BASED_TABS } from './settingsConfig';
import ProviderSelector from './ProviderSelector';
import {
  RERANKING_PROVIDERS, RERANKING_COMMON_FIELDS,
  LLM_PROVIDERS, LLM_COMMON_FIELDS,
  EMBEDDING_PROVIDERS, EMBEDDING_COMMON_FIELDS,
  STORAGE_KV_PROVIDERS, STORAGE_VECTOR_PROVIDERS, STORAGE_GRAPH_PROVIDERS, 
  STORAGE_DOC_STATUS_PROVIDERS, STORAGE_COMMON_POSTGRES
} from './providerConfig';
import { Card } from 'antd';

const SettingsTab: React.FC = () => {
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  
  const { t, ready } = useTranslation();
  const { token } = theme.useToken();
  const { theme: currentTheme } = useTheme();
  const isDark = currentTheme === 'dark' || (currentTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);

  useEffect(() => {
    loadSettings();
  }, []);

  // Helper function to get field value (defaultValue or current value)
  const getFieldValue = (field: FieldConfig): string => {
    const currentValue = settings[field.key];
    // If has current value, use it
    if (currentValue !== undefined && currentValue !== '') {
      return currentValue;
    }
    // Otherwise use defaultValue if exists
    return field.defaultValue || '';
  };

  // Helper function to get placeholder
  const getPlaceholder = (field: FieldConfig): string => {
    return field.placeholder || '';
  };

  const loadSettings = async () => {
    try {
      const response = await get_ipc_api().lightragApi.getSettings();
      if (response.success && response.data) {
        setSettings(response.data as Record<string, string>);
      }
    } catch (e) {
      console.error('Failed to load settings:', e);
      message.error(t('pages.knowledge.settings.loadError'));
    }
  };

  const updateSetting = (key: string, value: string) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  const openFolderDialog = async (key: string) => {
    try {
      const response = await get_ipc_api().executeRequest<any>('fs.selectDirectory', {}, 300000);
      if (response.success && response.data?.path) {
        updateSetting(key, response.data.path);
      }
    } catch (e) {
      console.error('Failed to select directory:', e);
    }
  };

  const handleSave = async () => {
    try {
      setLoading(true);
      const response = await get_ipc_api().lightragApi.saveSettings(settings);
      if (response.success) {
        message.success(t('pages.knowledge.settings.saveSuccess'));
        
        // Prompt user to restart server
        Modal.confirm({
          title: t('pages.knowledge.settings.restartServer'),
          content: t('pages.knowledge.settings.restartPrompt'),
          okText: t('pages.knowledge.settings.restartServer'),
          cancelText: t('pages.knowledge.settings.restartLater'),
          onOk: async () => {
            await handleRestartServer();
          }
        });
      } else {
        throw new Error(response.error?.message || 'Unknown error');
      }
    } catch (e: any) {
      message.error(t('pages.knowledge.settings.saveError') + ': ' + (e.message || String(e)));
    } finally {
      setLoading(false);
    }
  };

  const handleRestartServer = async () => {
    try {
      const hideLoading = message.loading(t('pages.knowledge.settings.restarting'), 0);
      const response = await get_ipc_api().executeRequest<any>('lightrag.restartServer', {});
      hideLoading();
      
      if (response.success) {
        message.success(t('pages.knowledge.settings.restartSuccess'));
      } else {
        throw new Error(response.error?.message || 'Unknown error');
      }
    } catch (e: any) {
      message.error(t('pages.knowledge.settings.restartError') + ': ' + (e.message || String(e)));
    }
  };

  // Render field with tooltip support
  const renderField = (field: FieldConfig & { label?: string }) => {
    const value = getFieldValue(field);
    const placeholder = getPlaceholder(field);
    const hasTooltip = !!field.tooltip;
    
    // Use label if available (and translate if it's a key), otherwise use key
    const displayLabel = field.label 
      ? (field.label.includes('.') ? t(`pages.knowledge.settings.${field.label}`) : field.label)
      : field.key;

    const label = (
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 6 }}>
        <span style={{ fontWeight: 500, fontSize: 13, color: token.colorText }}>{displayLabel}</span>
        {hasTooltip && (
          <Tooltip title={t(`pages.knowledge.settings.${field.tooltip}`)} placement="top">
            <QuestionCircleOutlined style={{ fontSize: 12, color: token.colorTextSecondary, cursor: 'help' }} />
          </Tooltip>
        )}
      </div>
    );

    const commonStyle = { width: '100%' };

    switch (field.type) {
      case 'text':
      case 'password':
        return (
          <div key={field.key} style={{ marginBottom: 12 }}>
            {label}
            <Input
              type={field.type === 'password' ? 'password' : 'text'}
              value={value}
              placeholder={placeholder}
              onChange={(e) => updateSetting(field.key, e.target.value)}
              style={commonStyle}
              size="small"
              disabled={field.disabled}
            />
          </div>
        );
      
      case 'number':
        return (
          <div key={field.key} style={{ marginBottom: 12 }}>
            {label}
            <Input
              type="number"
              value={value}
              placeholder={placeholder}
              onChange={(e) => updateSetting(field.key, e.target.value)}
              style={commonStyle}
              size="small"
              disabled={field.disabled}
            />
          </div>
        );
      
      case 'textarea':
        return (
          <div key={field.key} style={{ marginBottom: 12 }}>
            {label}
            <Input.TextArea
              value={value}
              placeholder={placeholder}
              onChange={(e) => updateSetting(field.key, e.target.value)}
              rows={2}
              style={commonStyle}
              size="small"
              disabled={field.disabled}
            />
          </div>
        );
      
      case 'select':
        // Translate options if needed
        const options = field.options?.map(opt => ({
          ...opt,
          label: opt.label.includes('.') ? t(`pages.knowledge.settings.${opt.label}`) : opt.label
        }));

        return (
          <div key={field.key} style={{ marginBottom: 12 }}>
            {label}
            <Select
              value={value || undefined}
              placeholder={placeholder}
              onChange={(val) => updateSetting(field.key, val)}
              style={commonStyle}
              options={options}
              size="small"
              disabled={field.disabled}
            />
          </div>
        );
      
      case 'boolean':
        return (
          <div key={field.key} style={{ marginBottom: 12 }}>
            <Checkbox
              checked={value === 'true' || value === 'True'}
              onChange={(e) => updateSetting(field.key, e.target.checked ? 'true' : 'false')}
              disabled={field.disabled}
            >
              <span style={{ marginLeft: 8, fontSize: 13 }}>{displayLabel}</span>
              {hasTooltip && (
                <Tooltip title={t(`pages.knowledge.settings.${field.tooltip}`)} placement="top">
                  <QuestionCircleOutlined style={{ marginLeft: 4, color: token.colorTextSecondary, cursor: 'help' }} />
                </Tooltip>
              )}
            </Checkbox>
          </div>
        );
      
      case 'directory':
        return (
          <div key={field.key} style={{ marginBottom: 12 }}>
            {label}
            <Input
              value={value}
              placeholder={placeholder}
              onChange={(e) => updateSetting(field.key, e.target.value)}
              style={commonStyle}
              size="small"
              disabled={field.disabled}
              suffix={
                !field.disabled && (
                  <FolderOpenOutlined 
                    style={{ cursor: 'pointer', color: token.colorPrimary }} 
                    onClick={() => openFolderDialog(field.key)}
                  />
                )
              }
            />
          </div>
        );
      
      default:
        return null;
    }
  };

  // Helper function to group fields by section and render them
  const renderFieldsBySection = (fields: FieldConfig[]) => {
    // Group fields by section
    const sections: Record<string, FieldConfig[]> = {};
    fields.forEach(field => {
      const section = field.section || 'default';
      if (!sections[section]) {
        sections[section] = [];
      }
      sections[section].push(field);
    });

    return (
      <div style={{ padding: '16px 0' }}>
        {Object.entries(sections).map(([sectionName, sectionFields]) => (
          <div key={sectionName} style={{ marginBottom: 20 }}>
            {sectionName !== 'default' && (
              <h3 style={{ 
                marginBottom: 12, 
                fontSize: 14, 
                fontWeight: 600, 
                color: token.colorText,
                borderBottom: `1px solid ${token.colorBorder}`,
                paddingBottom: 6
              }}>
                {t(`pages.knowledge.settings.sections.${sectionName}`) || sectionName.charAt(0).toUpperCase() + sectionName.slice(1)}
              </h3>
            )}
            <div style={{ 
              display: 'grid', 
              gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', 
              gap: 12 
            }}>
              {sectionFields.map(field => renderField(field))}
            </div>
          </div>
        ))}
      </div>
    );
  };

  // Icon mapping
  const getTabIcon = (key: string) => {
    const icons: Record<string, React.ReactNode> = {
      basic: <CloudServerOutlined />,
      rag: <ApiOutlined />,
      reranking: <SortAscendingOutlined />,
      llm: <RobotOutlined />,
      embedding: <BlockOutlined />,
      storage: <DatabaseOutlined />,
      evaluation: <ExperimentOutlined />
    };
    return icons[key] || <ApiOutlined />;
  };

  // Render provider-based configuration tabs
  const renderProviderTab = (tabKey: string) => {
    switch (tabKey) {
      case 'reranking':
        return (
          <ProviderSelector
            bindingKey="RERANK_BINDING"
            providers={RERANKING_PROVIDERS}
            commonFields={RERANKING_COMMON_FIELDS}
            settings={settings}
            onSettingChange={updateSetting}
          />
        );
      case 'llm':
        return (
          <ProviderSelector
            bindingKey="LLM_BINDING"
            providers={LLM_PROVIDERS}
            commonFields={LLM_COMMON_FIELDS}
            settings={settings}
            onSettingChange={updateSetting}
          />
        );
      case 'embedding':
        return (
          <ProviderSelector
            bindingKey="EMBEDDING_BINDING"
            providers={EMBEDDING_PROVIDERS}
            commonFields={EMBEDDING_COMMON_FIELDS}
            settings={settings}
            onSettingChange={updateSetting}
          />
        );
      case 'storage':
        // Check if any PostgreSQL provider is selected
        const isPostgresSelected = [
          settings['LIGHTRAG_KV_STORAGE'],
          settings['LIGHTRAG_VECTOR_STORAGE'],
          settings['LIGHTRAG_GRAPH_STORAGE'],
          settings['LIGHTRAG_DOC_STATUS_STORAGE']
        ].some(id => id && id.startsWith('PG'));

        return (
          <div style={{ padding: '16px 0' }}>
            <div style={{ marginBottom: 24 }}>
              <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: token.colorText }}>
                {t('pages.knowledge.settings.provider.kvStorage')}
              </h3>
              <ProviderSelector
                bindingKey="LIGHTRAG_KV_STORAGE"
                providers={STORAGE_KV_PROVIDERS}
                settings={settings}
                onSettingChange={updateSetting}
              />
            </div>
            <div style={{ marginBottom: 24 }}>
              <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: token.colorText }}>
                {t('pages.knowledge.settings.provider.vectorStorage')}
              </h3>
              <ProviderSelector
                bindingKey="LIGHTRAG_VECTOR_STORAGE"
                providers={STORAGE_VECTOR_PROVIDERS}
                settings={settings}
                onSettingChange={updateSetting}
              />
            </div>
            <div style={{ marginBottom: 24 }}>
              <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: token.colorText }}>
                {t('pages.knowledge.settings.provider.graphStorage')}
              </h3>
              <ProviderSelector
                bindingKey="LIGHTRAG_GRAPH_STORAGE"
                providers={STORAGE_GRAPH_PROVIDERS}
                settings={settings}
                onSettingChange={updateSetting}
              />
            </div>
            <div style={{ marginBottom: 24 }}>
              <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: token.colorText }}>
                {t('pages.knowledge.settings.provider.docStatusStorage')}
              </h3>
              <ProviderSelector
                bindingKey="LIGHTRAG_DOC_STATUS_STORAGE"
                providers={STORAGE_DOC_STATUS_PROVIDERS}
                settings={settings}
                onSettingChange={updateSetting}
              />
            </div>

            {/* Common PostgreSQL Settings */}
            {isPostgresSelected && (
              <Card
                size="small"
                title={t('pages.knowledge.settings.provider.commonPostgresSettings')}
                style={{
                  marginTop: 24,
                  borderColor: token.colorBorder
                }}
              >
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                  gap: 12
                }}>
                  {STORAGE_COMMON_POSTGRES.map(field => renderField(field as any))}
                </div>
              </Card>
            )}
          </div>
        );
      default:
        return null;
    }
  };

  // Build tab items dynamically from configuration
  const tabItems = Object.entries(FIELDS_BY_TAB).map(([tabKey, fields]) => ({
    key: tabKey,
    label: (
      <span>
        {getTabIcon(tabKey)} {t(`pages.knowledge.settings.tabs.${tabKey}`)}
      </span>
    ),
    children: PROVIDER_BASED_TABS.includes(tabKey) 
      ? renderProviderTab(tabKey)
      : renderFieldsBySection(fields)
  }));

  // Don't render until i18n is ready
  if (!ready) {
    return <div style={{ padding: 32 }}>Loading...</div>;
  }


  return (
    <div style={{ 
      height: '100%', 
      display: 'flex', 
      flexDirection: 'column',
      background: token.colorBgLayout
    }} data-ec-scope="lightrag-ported">
      {/* Fixed Header */}
      <div style={{
        padding: '20px 24px 0 24px',
        background: token.colorBgLayout
      }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 0',
          marginBottom: 16
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ 
              width: 36, 
              height: 36, 
              borderRadius: 8, 
              background: `linear-gradient(135deg, ${token.colorPrimary} 0%, ${token.colorPrimaryHover} 100%)`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              <DatabaseOutlined style={{ fontSize: 18, color: '#ffffff' }} />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: token.colorText, lineHeight: 1.2 }}>
                {t('pages.knowledge.settings.title')}
              </h3>
              <p style={{ margin: '4px 0 0 0', fontSize: 13, color: token.colorTextSecondary }}>
                {t('pages.knowledge.settings.subtitle')}
              </p>
            </div>
          </div>
          <button className="ec-btn ec-btn-primary" onClick={handleSave} disabled={loading}>
            <SaveOutlined /> {loading ? t('pages.knowledge.settings.saving') : t('pages.knowledge.settings.saveSettings')}
          </button>
        </div>
      </div>

      {/* Tabs Container with Fixed Header */}
      <div style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        padding: '0 24px 20px 24px',
        overflow: 'hidden'
      }}>
        <div style={{
          background: token.colorBgContainer,
          borderRadius: 16,
          border: `1px solid ${token.colorBorder}`,
          boxShadow: isDark ? '0 4px 16px rgba(0, 0, 0, 0.15)' : '0 4px 16px rgba(0, 0, 0, 0.06)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          flex: 1
        }}>
          <Tabs
            defaultActiveKey="basic"
            items={tabItems}
            style={{ 
              height: '100%',
              display: 'flex',
              flexDirection: 'column'
            }}
            className="lightrag-settings-tabs"
          />
        </div>
      </div>

      {/* Scoped styles */}
      <style>{`
        /* Tabs fixed header and scrollable content */
        .lightrag-settings-tabs .ant-tabs-nav {
          margin: 0 !important;
          padding: 0 20px !important;
          flex-shrink: 0;
        }
        .lightrag-settings-tabs .ant-tabs-content-holder {
          overflow-y: auto !important;
          flex: 1;
        }
        .lightrag-settings-tabs .ant-tabs-content {
          height: 100%;
        }
        .lightrag-settings-tabs .ant-tabs-tabpane {
          padding: 0 20px 16px 20px;
        }
        
        [data-ec-scope="lightrag-ported"] .ec-input {
          background: ${token.colorBgContainer};
          color: ${token.colorText};
          border: 1px solid ${token.colorBorder};
          border-radius: 8px;
          padding: 6px 10px;
          font-size: 13px;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          width: 100%;
        }
        [data-ec-scope="lightrag-ported"] .ec-input:focus {
          outline: none;
          border-color: ${token.colorPrimary};
          box-shadow: 0 0 0 2px ${token.colorPrimaryBg};
        }
        [data-ec-scope="lightrag-ported"] .ec-btn {
          background: ${token.colorBgContainer};
          color: ${token.colorText};
          border: 1px solid ${token.colorBorder};
          border-radius: 8px;
          padding: 6px 14px;
          font-size: 13px;
          cursor: pointer;
          display: inline-flex;
          align-items: center;
          gap: 6px;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          font-weight: 500;
          white-space: nowrap;
          box-shadow: ${isDark ? '0 2px 8px rgba(0, 0, 0, 0.15)' : '0 2px 8px rgba(0, 0, 0, 0.05)'};
        }
        [data-ec-scope="lightrag-ported"] .ec-btn:hover {
          border-color: ${token.colorPrimary};
          color: ${token.colorPrimary};
          transform: translateY(-2px);
          box-shadow: ${isDark ? '0 4px 12px rgba(24, 144, 255, 0.3)' : '0 4px 12px rgba(24, 144, 255, 0.2)'};
        }
        [data-ec-scope="lightrag-ported"] .ec-btn-primary {
          background: ${token.colorPrimary};
          color: #ffffff;
          border-color: ${token.colorPrimary};
        }
        [data-ec-scope="lightrag-ported"] .ec-btn-primary:hover {
          background: ${token.colorPrimaryHover};
          border-color: ${token.colorPrimaryHover};
          color: #ffffff;
          transform: translateY(-2px);
          box-shadow: 0 6px 16px rgba(24, 144, 255, 0.4);
        }
        [data-ec-scope="lightrag-ported"] .setting-row {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        [data-ec-scope="lightrag-ported"] .setting-row > label {
          font-size: 13px;
          font-weight: 600;
          color: ${token.colorTextSecondary};
        }
        [data-ec-scope="lightrag-ported"] .setting-row > .ec-input,
        [data-ec-scope="lightrag-ported"] .setting-row > select.ec-input,
        [data-ec-scope="lightrag-ported"] .setting-row > div {
          width: 100%;
        }
        [data-ec-scope="lightrag-ported"] .ec-select {
          cursor: pointer;
        }
      `}</style>
    </div>
  );
};

export default SettingsTab;
