import React, { useState, useEffect } from 'react';
import { theme, message, Tabs, Modal, Tooltip, Input, Select, Switch } from 'antd';
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
  STORAGE_DOC_STATUS_PROVIDERS, STORAGE_COMMON_POSTGRES,
  ProviderConfig
} from './providerConfig';
import { Card } from 'antd';

// Helper to merge static providers with system providers
// Preserves static config (rich UI) for known providers, adds new ones from system, removes missing ones
const mergeProviders = (staticList: ProviderConfig[], systemList: ProviderConfig[]) => {
  if (!systemList || !Array.isArray(systemList)) return staticList;
  
  const systemMap = new Map(systemList.map(p => [p.id.toLowerCase(), p]));
  const result: ProviderConfig[] = [];

  // Process static list first to preserve order and rich fields
  for (const staticP of staticList) {
    if (systemMap.has(staticP.id.toLowerCase())) {
      // Keep static config for known providers as it has better UI definitions
      // BUT we must merge dynamic data (options, defaults, system status) from the system provider
      const systemP = systemMap.get(staticP.id.toLowerCase())!;
      
      // Clone static provider to avoid mutation
      const mergedP = { ...staticP, fields: [...staticP.fields] };
      
      // Merge modelMetadata from system provider (for embedding providers)
      if (systemP.modelMetadata) {
        mergedP.modelMetadata = systemP.modelMetadata;
      }
      
      // Update fields with system data
      mergedP.fields = mergedP.fields.map(staticField => {
        const systemField = systemP.fields.find(f => f.key === staticField.key);
        if (systemField) {
          return {
            ...staticField,
            // Merge dynamic properties if they exist in system field
            options: systemField.options || staticField.options,
            defaultValue: systemField.defaultValue !== undefined ? systemField.defaultValue : staticField.defaultValue,
            isSystemManaged: systemField.isSystemManaged,
            disabled: systemField.disabled !== undefined ? systemField.disabled : staticField.disabled,
            // If system field changed type (e.g. text -> select), accept it
            type: (systemField.type === 'select' && staticField.type === 'text') ? 'select' : staticField.type
          };
        }
        return staticField;
      });

      result.push(mergedP);
      systemMap.delete(staticP.id.toLowerCase());
    }
  }

  // Add remaining new providers from system
  for (const p of systemMap.values()) {
    result.push(p);
  }
  
  return result;
};

const SettingsTab: React.FC = () => {
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [llmProviders, setLlmProviders] = useState<ProviderConfig[]>(LLM_PROVIDERS);
  const [embeddingProviders, setEmbeddingProviders] = useState<ProviderConfig[]>(EMBEDDING_PROVIDERS);
  
  const { t, ready } = useTranslation();
  const { token } = theme.useToken();
  const { theme: currentTheme } = useTheme();
  const isDark = currentTheme === 'dark' || (currentTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);

  useEffect(() => {
    const initializeSettings = async () => {
      await loadSettings();
      await loadProviders();
    };
    initializeSettings();
  }, []);

  // Validate and clean up mismatched provider fields after providers are loaded
  useEffect(() => {
    if (llmProviders.length === 0 || embeddingProviders.length === 0) {
      return; // Wait until providers are loaded
    }

    setSettings(prev => {
      if (Object.keys(prev).length === 0) {
        return prev; // Settings not loaded yet
      }

      const updates: Record<string, string> = {};
      let hasChanges = false;

      // Check LLM provider fields
      const llmProviderId = prev['LLM_BINDING'];
      if (llmProviderId) {
        const llmProvider = llmProviders.find(p => p.id === llmProviderId);
        if (llmProvider) {
          // Check if current field values match the provider
          llmProvider.fields.forEach(field => {
            const currentValue = prev[field.key];
            
            // For model field, validate it's in the provider's options
            if (field.key === 'LLM_MODEL' && currentValue) {
              if (field.options && field.options.length > 0) {
                const isValidModel = field.options.some(opt => opt.value === currentValue);
                if (!isValidModel) {
                  // Model not in this provider's list, reset to default
                  const targetValue = field.defaultValue || '';
                  if (currentValue !== targetValue) {
                    updates[field.key] = targetValue;
                    hasChanges = true;
                  }
                }
              }
            }
            // For disabled fields (like API host), always use provider's default if it exists
            else if (field.disabled && field.defaultValue !== undefined) {
              const currentValue = prev[field.key] || '';
              const targetValue = field.defaultValue;
              if (currentValue !== targetValue) {
                updates[field.key] = targetValue;
                hasChanges = true;
              }
            }
          });

          // Validate system key flag
          const apiKeyField = llmProvider.fields.find(f => f.key === 'LLM_BINDING_API_KEY');
          if (prev['_SYSTEM_LLM_KEY_SOURCE']) {
              if (!apiKeyField || !apiKeyField.isSystemManaged) {
                  updates['_SYSTEM_LLM_KEY_SOURCE'] = '';
                  if (prev['LLM_BINDING_API_KEY']) {
                      updates['LLM_BINDING_API_KEY'] = '';
                  }
                  hasChanges = true;
              } else {
                  // Valid system key. Ensure settings has the masked value if currently empty
                  const currentKey = prev['LLM_BINDING_API_KEY'];
                  const defaultKey = apiKeyField.defaultValue;
                  if (!currentKey && defaultKey) {
                      updates['LLM_BINDING_API_KEY'] = defaultKey;
                      hasChanges = true;
                  }
              }
          }
        }
      }

      // Check Embedding provider fields
      const embeddingProviderId = prev['EMBEDDING_BINDING'];
      if (embeddingProviderId) {
        const embeddingProvider = embeddingProviders.find(p => p.id === embeddingProviderId);
        if (embeddingProvider) {
          embeddingProvider.fields.forEach(field => {
            const currentValue = prev[field.key];
            
            // For model field, validate it's in the provider's options
            if (field.key === 'EMBEDDING_MODEL' && currentValue) {
              if (field.options && field.options.length > 0) {
                const isValidModel = field.options.some(opt => opt.value === currentValue);
                if (!isValidModel) {
                  // Model not in this provider's list, reset to default
                  const targetValue = field.defaultValue || '';
                  if (currentValue !== targetValue) {
                    updates[field.key] = targetValue;
                    hasChanges = true;
                  }
                }
              }
            }
            // For disabled fields (like API host, dimensions, token limit), always use provider's default if it exists
            else if (field.disabled && field.defaultValue !== undefined) {
              const currentValue = prev[field.key] || '';
              const targetValue = field.defaultValue;
              if (currentValue !== targetValue) {
                updates[field.key] = targetValue;
                hasChanges = true;
              }
            }
          });

          // Sync dimensions/token limit from metadata if available
          if (embeddingProvider.modelMetadata) {
             const currentModel = updates['EMBEDDING_MODEL'] || prev['EMBEDDING_MODEL'] || 
                                  embeddingProvider.fields.find(f => f.key === 'EMBEDDING_MODEL')?.defaultValue;
             if (currentModel && embeddingProvider.modelMetadata[currentModel]) {
                 const meta = embeddingProvider.modelMetadata[currentModel];
                 if (meta.dimensions && prev['EMBEDDING_DIM'] !== meta.dimensions.toString()) {
                     updates['EMBEDDING_DIM'] = meta.dimensions.toString();
                     hasChanges = true;
                 }
                 if (meta.max_tokens && prev['EMBEDDING_TOKEN_LIMIT'] !== meta.max_tokens.toString()) {
                     updates['EMBEDDING_TOKEN_LIMIT'] = meta.max_tokens.toString();
                     hasChanges = true;
                 }
             }
          }

          // Validate system key flag
          const apiKeyField = embeddingProvider.fields.find(f => f.key === 'EMBEDDING_BINDING_API_KEY');
          if (prev['_SYSTEM_EMBED_KEY_SOURCE']) {
              if (!apiKeyField || !apiKeyField.isSystemManaged) {
                  updates['_SYSTEM_EMBED_KEY_SOURCE'] = '';
                  // If we are removing the system flag, we should also clear the key if it looks like a masked value or if we want to force re-entry
                  if (prev['EMBEDDING_BINDING_API_KEY']) {
                      updates['EMBEDDING_BINDING_API_KEY'] = '';
                  }
                  hasChanges = true;
              } else {
                  // Valid system key. Ensure settings has the masked value if currently empty
                  const currentKey = prev['EMBEDDING_BINDING_API_KEY'];
                  const defaultKey = apiKeyField.defaultValue;
                  if (!currentKey && defaultKey) {
                      updates['EMBEDDING_BINDING_API_KEY'] = defaultKey;
                      hasChanges = true;
                  }
              }
          }
        }
      }

      // Return updated settings if there are changes, otherwise return prev to avoid re-render
      if (hasChanges) {
        return { ...prev, ...updates };
      }
      return prev;
    });
  }, [llmProviders, embeddingProviders]);

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

  const loadProviders = async () => {
    try {
      const response = await get_ipc_api().executeRequest<any>('lightrag.getSystemProviders', {});
      if (response.success && response.data) {
        const systemLlm = response.data.llm_providers as ProviderConfig[];
        const systemEmbed = response.data.embedding_providers as ProviderConfig[];

        setLlmProviders(mergeProviders(LLM_PROVIDERS, systemLlm));
        setEmbeddingProviders(mergeProviders(EMBEDDING_PROVIDERS, systemEmbed));
      }
    } catch (e) {
      console.error('Failed to load system providers:', e);
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
          content: (
            <div style={{ color: token.colorText }}>
              {t('pages.knowledge.settings.restartPrompt')}
            </div>
          ),
          okText: t('pages.knowledge.settings.applyNow'),
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
    let value = getFieldValue(field);
    let placeholder = getPlaceholder(field);
    const hasTooltip = !!field.tooltip;
    
    // Check for system managed keys
    const isSystemManaged = (field.key === 'LLM_BINDING_API_KEY' && !!settings['_SYSTEM_LLM_KEY_SOURCE']) ||
                           (field.key === 'EMBEDDING_BINDING_API_KEY' && !!settings['_SYSTEM_EMBED_KEY_SOURCE']);
    
    const disabled = field.disabled || isSystemManaged;

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
        {isSystemManaged && (
          <Tooltip title={t('pages.knowledge.settings.systemManaged', { defaultValue: 'Managed by System Settings' })} placement="top">
            <span style={{ 
              fontSize: 10, 
              background: token.colorFillSecondary, 
              color: token.colorTextSecondary, 
              padding: '1px 6px', 
              borderRadius: 4,
              marginLeft: 4
            }}>
              System
            </span>
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
              disabled={disabled}
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
            {label}
            <div style={{ height: 24, display: 'flex', alignItems: 'center' }}>
              <Switch
                checked={value === 'true' || value === 'True'}
                onChange={(checked) => updateSetting(field.key, checked ? 'true' : 'false')}
                size="small"
                disabled={disabled}
              />
            </div>
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

  // Helper to handle setting changes, including auto-filling defaults when provider changes
  const createSettingChangeHandler = (bindingKey: string, providers: ProviderConfig[]) => {
    return (key: string, value: string) => {
      updateSetting(key, value);

      // If the changed key matches the binding key, it means the provider selection changed
      if (key === bindingKey) {
        const oldProviderId = settings[bindingKey];
        const oldProvider = providers.find(p => p.id === oldProviderId);
        const newProvider = providers.find(p => p.id === value);
        
        // Determine the API key field name based on binding type
        let apiKeyField = '';
        let systemFlagKey = '';
        if (bindingKey === 'LLM_BINDING') {
          apiKeyField = 'LLM_BINDING_API_KEY';
          systemFlagKey = '_SYSTEM_LLM_KEY_SOURCE';
        } else if (bindingKey === 'EMBEDDING_BINDING') {
          apiKeyField = 'EMBEDDING_BINDING_API_KEY';
          systemFlagKey = '_SYSTEM_EMBED_KEY_SOURCE';
        } else if (bindingKey === 'RERANK_BINDING') {
          apiKeyField = 'RERANK_BINDING_API_KEY';
        }

        // Clear all old provider-specific fields first
        if (oldProvider && oldProvider.fields) {
          oldProvider.fields.forEach(field => {
            updateSetting(field.key, '');
          });
        }

        // Check if new provider has system-managed API key
        const apiKeyFieldConfig = newProvider?.fields.find(f => f.key === apiKeyField);
        const isNewProviderSystemManaged = apiKeyFieldConfig?.isSystemManaged;

        // Update system managed flag and API key based on new provider
        if (systemFlagKey) {
          if (isNewProviderSystemManaged) {
            updateSetting(systemFlagKey, 'true');
            // Set the masked default value if available
            if (apiKeyFieldConfig?.defaultValue !== undefined) {
              updateSetting(apiKeyField, apiKeyFieldConfig.defaultValue);
            }
          } else {
            // New provider is not system managed, clear the flag
            updateSetting(systemFlagKey, '');
          }
        }

        // Auto-fill all fields with defaults from the new provider
        if (newProvider && newProvider.fields) {
          newProvider.fields.forEach(field => {
             // Skip API key field if it's system managed (already handled above)
             if (field.key === apiKeyField && isNewProviderSystemManaged) return;
             
             // Set to default value or empty string
             updateSetting(field.key, field.defaultValue || '');
          });
        }

        // For embedding provider change, also update dimensions and token limit based on default model
        if (bindingKey === 'EMBEDDING_BINDING' && newProvider) {
          const defaultModel = newProvider.fields.find(f => f.key === 'EMBEDDING_MODEL')?.defaultValue;
          if (defaultModel && newProvider.modelMetadata && newProvider.modelMetadata[defaultModel]) {
            const meta = newProvider.modelMetadata[defaultModel];
            if (meta.dimensions) {
              updateSetting('EMBEDDING_DIM', meta.dimensions.toString());
            }
            if (meta.max_tokens) {
              updateSetting('EMBEDDING_TOKEN_LIMIT', meta.max_tokens.toString());
            }
          }
        }
      }

      // Handle Embedding Model change to update dimensions/tokens based on metadata
      if (bindingKey === 'EMBEDDING_BINDING' && key === 'EMBEDDING_MODEL') {
          // We need to find the current provider to look up metadata
          // Use the current settings or the first provider as fallback (logic from ProviderSelector)
          const currentProviderId = settings[bindingKey] || providers[0]?.id;
          const provider = providers.find(p => p.id === currentProviderId);
          
          if (provider && provider.modelMetadata && provider.modelMetadata[value]) {
              const meta = provider.modelMetadata[value];
              if (meta.dimensions) {
                  updateSetting('EMBEDDING_DIM', meta.dimensions.toString());
              }
              if (meta.max_tokens) {
                  updateSetting('EMBEDDING_TOKEN_LIMIT', meta.max_tokens.toString());
              }
          }
      }
    };
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
            onSettingChange={createSettingChangeHandler("RERANK_BINDING", RERANKING_PROVIDERS)}
          />
        );
      case 'llm':
        return (
          <ProviderSelector
            bindingKey="LLM_BINDING"
            providers={llmProviders}
            commonFields={LLM_COMMON_FIELDS}
            settings={settings}
            onSettingChange={createSettingChangeHandler("LLM_BINDING", llmProviders)}
          />
        );
      case 'embedding':
        return (
          <ProviderSelector
            bindingKey="EMBEDDING_BINDING"
            providers={embeddingProviders}
            commonFields={EMBEDDING_COMMON_FIELDS}
            settings={settings}
            onSettingChange={createSettingChangeHandler("EMBEDDING_BINDING", embeddingProviders)}
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
