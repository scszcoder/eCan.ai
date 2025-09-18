import React, { useState, useEffect } from 'react';
import { Card, Table, Button, Input, Radio, Space, Tooltip, App } from 'antd';
import { EditOutlined, DeleteOutlined, EyeOutlined, EyeInvisibleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { get_ipc_api } from '../../../services/ipc_api';
import type { LLMProvider } from '../types';

interface LLMManagementProps {
  username: string | null;
  defaultLLM?: string; // Default LLM passed from settings
  settingsLoaded?: boolean; // Flag indicating whether settings have been loaded
  onDefaultLLMChange?: (newDefaultLLM: string) => void; // Callback to notify parent of default LLM changes
}

const LLMManagement: React.FC<LLMManagementProps> = ({ username, defaultLLM: propDefaultLLM, settingsLoaded, onDefaultLLMChange }) => {
  const { t } = useTranslation();
  const { message } = App.useApp();

  // State management
  const [providers, setProviders] = useState<LLMProvider[]>([]);
  const [defaultLLM, setDefaultLLM] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [visibleApiKeys, setVisibleApiKeys] = useState<Set<string>>(new Set());
  const [apiKeyValues, setApiKeyValues] = useState<Map<string, string>>(new Map());
  const [editingProvider, setEditingProvider] = useState<string | null>(null);
  const [editingValue, setEditingValue] = useState<string>('');
  const [editingAzureEndpoint, setEditingAzureEndpoint] = useState<string>('');
  const [editingAwsAccessKeyId, setEditingAwsAccessKeyId] = useState<string>('');
  const [editingAwsSecretAccessKey, setEditingAwsSecretAccessKey] = useState<string>('');
  const [editingLoading, setEditingLoading] = useState<boolean>(false);



  // Load LLM providers
  const loadProviders = async () => {
    if (!username) return;

    setLoading(true);
    try {
      const response = await get_ipc_api().getLLMProviders<{ providers: LLMProvider[] }>();
      if (response.success && response.data) {
        setProviders(response.data.providers);
        console.log('✅ LLM providers loaded:', response.data.providers);
      } else {
        message.error(`${t('pages.settings.failed_to_load_providers')}: ${response.error?.message}`);
      }
    } catch (error) {
      console.error('Error loading LLM providers:', error);
      message.error(t('pages.settings.failed_to_load_providers'));
    } finally {
      setLoading(false);
    }
  };

  // loadDefaultLLM function removed, defaultLLM now passed from Settings page via props

  // Set default LLM
  const handleDefaultLLMChange = async (providerName: string) => {
    // Find the provider to check its configuration status
    const provider = providers.find(p => p.name === providerName);
    if (!provider) {
      message.error(`Provider ${providerName} not found`);
      return;
    }

    if (!provider.api_key_configured) {
      message.warning(`${providerName} ${t('pages.settings.provider_not_configured')}`);
      return;
    }

    try {
      const response = await get_ipc_api().setDefaultLLM<{ message: string }>(providerName, username || '');

      if (response.success) {
        setDefaultLLM(providerName);
        // Notify parent component to update settings
        onDefaultLLMChange?.(providerName);
        message.success(`${t('pages.settings.default_llm_set')}: ${providerName}`);
      } else {
        // If backend says provider is not configured, reload providers to sync
        if (response.error?.message?.includes('not configured')) {
          message.warning(`${providerName} ${t('pages.settings.provider_not_configured')}`);
          // Reload providers to sync with backend
          loadProviders();
        } else {
          message.error(`${t('pages.settings.failed_to_set_default')}: ${response.error?.message}`);
        }
      }
    } catch (error) {
      console.error('Error setting default LLM:', error);
      message.error(t('pages.settings.failed_to_set_default'));
    }
  };

  // Update provider configuration
  const updateProvider = async (name: string, apiKey: string, azureEndpoint?: string, awsAccessKeyId?: string, awsSecretAccessKey?: string) => {
    try {
      const response = await get_ipc_api().updateLLMProvider<{ message: string }>(name, apiKey, azureEndpoint, awsAccessKeyId, awsSecretAccessKey);

      if (response.success) {
        message.success(`${name} ${t('pages.settings.llm_updated_successfully')}`);
        await loadProviders(); // Reload data
        console.log('✅ Provider updated:', name);
      } else {
        message.error(`${t('pages.settings.failed_to_update_provider')} ${name}: ${response.error?.message}`);
      }
    } catch (error) {
      console.error('Error updating provider:', error);
      message.error(`${t('pages.settings.failed_to_update_provider')} ${name}`);
    }
  };

  // Delete provider configuration
  const deleteProviderConfig = async (name: string) => {
    try {
      const response = await get_ipc_api().deleteLLMProviderConfig<{ message: string }>(name, username || '');

      if (response.success) {
        message.success(`${name} ${t('pages.settings.llm_config_deleted')}`);

        // Update local state immediately for better UX
        setProviders(prevProviders =>
          prevProviders.map(provider =>
            provider.name === name
              ? { ...provider, api_key_configured: false }
              : provider
          )
        );

        // Clear any cached API key values for this provider
        setApiKeyValues(prevValues => {
          const newValues = new Map(prevValues);
          newValues.delete(name);
          return newValues;
        });

        // Remove from visible API keys
        setVisibleApiKeys(prevVisible => {
          const newVisible = new Set(prevVisible);
          newVisible.delete(name);
          return newVisible;
        });

        // If this was the default LLM, clear it
        if (defaultLLM === name) {
          setDefaultLLM('');
          // Notify parent component to clear default_llm in settings
          onDefaultLLMChange?.('');
        }

        // Reload providers from backend to verify the deletion
        setTimeout(() => {
          loadProviders();
        }, 500);
      } else {
        message.error(`${t('pages.settings.failed_to_delete_config')} ${name}: ${response.error?.message}`);
      }
    } catch (error) {
      console.error('Error deleting provider config:', error);
      message.error(`${t('pages.settings.failed_to_delete_config')} ${name}`);
    }
  };



  // API key editing related functions
  const startEditing = async (providerName: string) => {
    // Find the provider to check if it's configured
    const provider = providers.find(p => p.name === providerName);
    if (!provider) {
      message.error(`Provider ${providerName} not found`);
      return;
    }

    setEditingProvider(providerName);
    setEditingLoading(true);

    // If provider is configured, try to get the current credentials
    if (provider.api_key_configured) {
      try {
        const response = await get_ipc_api().getLLMProviderApiKey<{ api_key?: string, credentials?: any }>(providerName, true);
        if (response.success && response.data) {
          // Handle special cases with multiple credentials
          if (providerName === 'AzureOpenAI' && response.data.credentials) {
            setEditingValue(response.data.credentials.api_key || '');
            setEditingAzureEndpoint(response.data.credentials.azure_endpoint || '');
            setEditingAwsAccessKeyId('');
            setEditingAwsSecretAccessKey('');
          } else if (providerName === 'ChatBedrockConverse' && response.data.credentials) {
            setEditingValue('');
            setEditingAzureEndpoint('');
            setEditingAwsAccessKeyId(response.data.credentials.aws_access_key_id || '');
            setEditingAwsSecretAccessKey(response.data.credentials.aws_secret_access_key || '');
          } else {
            setEditingValue(response.data.api_key || '');
            setEditingAzureEndpoint('');
            setEditingAwsAccessKeyId('');
            setEditingAwsSecretAccessKey('');
          }
        } else {
          // If failed to get credentials, start with empty values
          setEditingValue('');
          setEditingAzureEndpoint('');
          setEditingAwsAccessKeyId('');
          setEditingAwsSecretAccessKey('');
        }
      } catch (error) {
        console.error('Error fetching credentials for editing:', error);
        setEditingValue('');
        setEditingAzureEndpoint('');
        setEditingAwsAccessKeyId('');
        setEditingAwsSecretAccessKey('');
      }
    } else {
      // If not configured, start with empty values
      setEditingValue('');
      setEditingAzureEndpoint('');
      setEditingAwsAccessKeyId('');
      setEditingAwsSecretAccessKey('');
    }

    setEditingLoading(false);
  };

  const saveApiKey = async () => {
    if (editingProvider) {
      await updateProvider(editingProvider, editingValue, editingAzureEndpoint, editingAwsAccessKeyId, editingAwsSecretAccessKey);
      setEditingProvider(null);
      setEditingValue('');
      setEditingAzureEndpoint('');
      setEditingAwsAccessKeyId('');
      setEditingAwsSecretAccessKey('');
    }
  };

  const cancelEditing = () => {
    setEditingProvider(null);
    setEditingValue('');
    setEditingAzureEndpoint('');
    setEditingAwsAccessKeyId('');
    setEditingAwsSecretAccessKey('');
    setEditingLoading(false);
  };

  const handleToggleApiKeyVisibility = async (providerName: string) => {
    // Find the provider to check if it's local
    const provider = providers.find(p => p.name === providerName);
    if (!provider) {
      message.error(`Provider ${providerName} not found`);
      return;
    }

    // For local providers, show a different message
    if (provider.is_local) {
      message.info(`${providerName} ${t('pages.settings.local_service_no_api_key')}`);
      return;
    }

    const isCurrentlyVisible = visibleApiKeys.has(providerName);

    if (isCurrentlyVisible) {
      // Hide the API key
      const newVisible = new Set(visibleApiKeys);
      newVisible.delete(providerName);
      setVisibleApiKeys(newVisible);

      // Remove from cache
      const newValues = new Map(apiKeyValues);
      newValues.delete(providerName);
      setApiKeyValues(newValues);
    } else {
      // Show the API key - fetch it from backend
      try {
        const response = await get_ipc_api().getLLMProviderApiKey<{ api_key: string }>(providerName, true);

        if (response.success && response.data) {
          // Add to visible set
          const newVisible = new Set(visibleApiKeys);
          newVisible.add(providerName);
          setVisibleApiKeys(newVisible);

          // Cache the API key value
          const newValues = new Map(apiKeyValues);
          newValues.set(providerName, response.data.api_key);
          setApiKeyValues(newValues);
        } else {
          message.error(`${t('pages.settings.failed_to_get_api_key')}: ${response.error?.message}`);
        }
      } catch (error) {
        console.error('Error fetching API key:', error);
        message.error(t('pages.settings.failed_to_get_api_key'));
      }
    }
  };

  // Update local state when passed defaultLLM changes
  useEffect(() => {
    if (propDefaultLLM !== undefined) {
      setDefaultLLM(propDefaultLLM);
    }
  }, [propDefaultLLM]);

  // Initialize loading - wait for settings to load before loading providers
  useEffect(() => {
    if (username && settingsLoaded) {
      loadProviders();
      // No longer call loadDefaultLLM() as defaultLLM is passed from Settings page
    }
  }, [username, settingsLoaded]);

  // If user is not logged in
  if (!username) {
    return (
      <Card title={t('pages.settings.llm_management')} style={{ marginTop: '20px' }}>
        <div style={{ textAlign: 'center', padding: '40px', color: '#999' }}>
          🔐 {t('pages.settings.login_to_view_llm')}
        </div>
      </Card>
    );
  }

  // Table column definitions
  const columns = [
    {
      title: t('pages.settings.llm_provider'),
      dataIndex: 'display_name',
      key: 'display_name',
      width: '20%',
    },
    {
      title: t('pages.settings.status'),
      dataIndex: 'api_key_configured',
      key: 'status',
      width: '15%',
      render: (isConfigured: boolean) => (
        <span style={{ color: isConfigured ? '#52c41a' : '#ff4d4f' }}>
          {isConfigured ? `✅ ${t('pages.settings.configured')}` : `❌ ${t('pages.settings.not_configured')}`}
        </span>
      ),
    },
    {
      title: t('pages.settings.api_key'),
      dataIndex: 'api_key',
      key: 'api_key',
      width: '35%',
      render: (_: any, record: LLMProvider) => {
        const isEditing = editingProvider === record.name;
        
        if (isEditing) {
          return (
            <Space direction="vertical" style={{ width: '100%' }}>
              {/* Azure OpenAI specific fields */}
              {record.name === 'AzureOpenAI' && (
                <>
                  <Input
                    value={editingAzureEndpoint}
                    onChange={(e) => setEditingAzureEndpoint(e.target.value)}
                    placeholder={editingLoading ? 'Loading current Azure endpoint...' : 'Enter Azure endpoint (https://your-resource.openai.azure.com)'}
                    style={{ width: '350px' }}
                    disabled={editingLoading}
                  />
                  <Input
                    value={editingValue}
                    onChange={(e) => setEditingValue(e.target.value)}
                    placeholder={editingLoading ? 'Loading current API key...' : 'Enter Azure OpenAI API key'}
                    style={{ width: '350px' }}
                    disabled={editingLoading}
                  />
                </>
              )}
              
              {/* AWS Bedrock specific fields */}
              {record.name === 'ChatBedrockConverse' && (
                <>
                  <Input
                    value={editingAwsAccessKeyId}
                    onChange={(e) => setEditingAwsAccessKeyId(e.target.value)}
                    placeholder={editingLoading ? 'Loading current AWS Access Key ID...' : 'Enter AWS Access Key ID'}
                    style={{ width: '350px' }}
                    disabled={editingLoading}
                  />
                  <Input
                    value={editingAwsSecretAccessKey}
                    onChange={(e) => setEditingAwsSecretAccessKey(e.target.value)}
                    placeholder={editingLoading ? 'Loading current AWS Secret Access Key...' : 'Enter AWS Secret Access Key'}
                    style={{ width: '350px' }}
                    disabled={editingLoading}
                    type="password"
                  />
                </>
              )}
              
              {/* Standard single API key field for other providers */}
              {record.name !== 'AzureOpenAI' && record.name !== 'ChatBedrockConverse' && (
                <Input
                  value={editingValue}
                  onChange={(e) => setEditingValue(e.target.value)}
                  placeholder={editingLoading ? 'Loading current API key...' : t('pages.settings.enter_api_key')}
                  style={{ width: '350px' }}
                  disabled={editingLoading}
                />
              )}
              
              <Space>
                <Button size="small" type="primary" onClick={saveApiKey} disabled={editingLoading}>
                  {t('common.save')}
                </Button>
                <Button size="small" onClick={cancelEditing} disabled={editingLoading}>
                  {t('common.cancel')}
                </Button>
              </Space>
            </Space>
          );
        }

        return (
          <Space>
            <span style={{ fontFamily: 'monospace' }}>
              {record.is_local ?
                '🏠 Local Service' :
                (record.api_key_configured ?
                  (visibleApiKeys.has(record.name) ?
                    apiKeyValues.get(record.name) || '••••••••••••••••' :
                    '••••••••••••••••'
                  ) :
                  t('pages.settings.not_configured')
                )
              }
            </span>
            {record.api_key_configured && !record.is_local && (
              <Tooltip title={visibleApiKeys.has(record.name) ? t('pages.settings.hide') : t('pages.settings.show')}>
                <Button
                  size="small"
                  type="text"
                  icon={visibleApiKeys.has(record.name) ? <EyeInvisibleOutlined /> : <EyeOutlined />}
                  onClick={() => handleToggleApiKeyVisibility(record.name)}
                />
              </Tooltip>
            )}
          </Space>
        );
      },
    },
    {
      title: t('pages.settings.default'),
      dataIndex: 'name',
      key: 'default',
      width: '15%',
      render: (name: string, record: LLMProvider) => (
        <Radio
          checked={defaultLLM === name}
          disabled={!record.api_key_configured}
          onClick={() => {
            if (record.api_key_configured && defaultLLM !== name) {
              handleDefaultLLMChange(name);
            }
          }}
        >
          {defaultLLM === name ? t('pages.settings.default') : ''}
        </Radio>
      ),
    },
    {
      title: t('pages.settings.actions'),
      key: 'actions',
      width: '15%',
      render: (_: any, record: LLMProvider) => (
        <Space>
          {!record.is_local && (
            <>
              <Tooltip title={t('common.edit')}>
                <Button
                  size="small"
                  type="text"
                  icon={<EditOutlined />}
                  onClick={() => startEditing(record.name)}
                />
              </Tooltip>
              <Tooltip title={t('common.delete')}>
                <Button
                  size="small"
                  type="text"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => deleteProviderConfig(record.name)}
                  disabled={!record.api_key_configured}
                />
              </Tooltip>
            </>
          )}
          {record.is_local && (
            <span style={{ color: '#999', fontSize: '12px' }}>Local Service</span>
          )}
        </Space>
      ),
    },
  ];

  return (
    <Card
      title={t('pages.settings.llm_management')}
      style={{ marginTop: '20px' }}
    >
      <Table
        columns={columns}
        dataSource={providers}
        rowKey="name"
        loading={loading}
        pagination={false}
        size="small"
      />

    </Card>
  );
};

export default LLMManagement;
