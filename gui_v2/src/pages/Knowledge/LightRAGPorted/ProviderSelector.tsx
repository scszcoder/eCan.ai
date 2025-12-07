import React, { useState, useEffect, useCallback } from 'react';
import { Select, Input, Switch, Card, theme, Tooltip, Button } from 'antd';
import { QuestionCircleOutlined, SettingOutlined, ReloadOutlined, GlobalOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { ProviderConfig, ProviderFieldConfig } from './providerConfig';
import { IPCAPI } from '../../../services/ipc/api';

interface OllamaModel {
  name: string;
  size: number;
  modified_at: string;
  digest: string;
  details: Record<string, any>;
}

interface ProviderSelectorProps {
  bindingKey: string;
  providers: ProviderConfig[];
  commonFields?: ProviderFieldConfig[];
  settings: Record<string, string>;
  onSettingChange: (key: string, value: string) => void;
}

const ProviderSelector: React.FC<ProviderSelectorProps> = ({
  bindingKey,
  providers,
  commonFields = [],
  settings,
  onSettingChange
}) => {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  
  const currentProviderId = settings[bindingKey] || providers[0]?.id || '';
  const currentProvider = providers.find(p => p.id === currentProviderId);
  
  // Ollama models state
  const [ollamaModels, setOllamaModels] = useState<OllamaModel[]>([]);
  const [ollamaLoading, setOllamaLoading] = useState(false);
  const [ollamaError, setOllamaError] = useState<string | null>(null);

  // Get the Ollama host from settings based on binding type
  const getOllamaHost = useCallback(() => {
    if (bindingKey === 'LLM_BINDING') {
      return settings['LLM_BINDING_HOST'] || 'http://127.0.0.1:11434';
    } else if (bindingKey === 'EMBEDDING_BINDING') {
      return settings['EMBEDDING_BINDING_HOST'] || 'http://127.0.0.1:11434';
    } else if (bindingKey === 'RERANK_BINDING') {
      return settings['RERANK_BINDING_HOST'] || 'http://127.0.0.1:11434';
    }
    return 'http://127.0.0.1:11434';
  }, [bindingKey, settings]);

  // Fetch Ollama models
  const fetchOllamaModels = useCallback(async () => {
    if (!currentProvider?.isOllama) return;
    
    setOllamaLoading(true);
    setOllamaError(null);
    
    try {
      const api = IPCAPI.getInstance();
      const host = getOllamaHost();
      const response = await api.getOllamaModels<{ models: OllamaModel[]; host: string }>(host);
      
      if (response.success && response.data) {
        setOllamaModels(response.data.models || []);
        if (response.data.models.length === 0) {
          setOllamaError(t('pages.knowledge.settings.ollama.noModels', { defaultValue: 'No models found' }));
        }
      } else {
        setOllamaError(response.error?.message || t('pages.knowledge.settings.ollama.fetchError', { defaultValue: 'Failed to fetch models' }));
        setOllamaModels([]);
      }
    } catch (error: any) {
      setOllamaError(error.message || t('pages.knowledge.settings.ollama.fetchError', { defaultValue: 'Failed to fetch models' }));
      setOllamaModels([]);
    } finally {
      setOllamaLoading(false);
    }
  }, [currentProvider?.isOllama, getOllamaHost, t]);

  // Fetch Ollama models when provider changes to Ollama
  useEffect(() => {
    if (currentProvider?.isOllama) {
      fetchOllamaModels();
    } else {
      setOllamaModels([]);
      setOllamaError(null);
    }
  }, [currentProvider?.isOllama, fetchOllamaModels]);

  // Open Ollama website (configured host)
  const handleOpenOllamaWebsite = () => {
    const host = getOllamaHost();
    // Open the configured Ollama host in browser
    window.open(host, '_blank');
  };

  const handleNavigateToSettings = (fieldKey: string) => {
    // Navigate within the app using hash routing (same as onboarding)
    if (fieldKey === 'LLM_BINDING_API_KEY') {
      window.location.hash = '#/settings?tab=llm';
    } else if (fieldKey === 'EMBEDDING_BINDING_API_KEY') {
      window.location.hash = '#/settings?tab=embedding';
    } else if (fieldKey === 'RERANK_BINDING_API_KEY') {
      window.location.hash = '#/settings?tab=rerank';
    }
  };

  const renderField = (field: ProviderFieldConfig) => {
    const value = settings[field.key] || field.defaultValue || '';
    // Use field.isSystemManaged property directly from backend data
    const managed = field.isSystemManaged || false;
    
    // Translate placeholder only for select type with matching option values
    const placeholder = field.placeholder 
      ? (field.type === 'select' && field.options?.some(opt => opt.value === field.placeholder)
          ? t(`pages.knowledge.settings.placeholders.${field.placeholder}`)
          : field.placeholder)
      : '';
    const hasTooltip = !!field.tooltip;
    
    // Try to translate label if it looks like an i18n key (contains '.')
    const labelText = field.label 
      ? (field.label.includes('.') ? t(`pages.knowledge.settings.${field.label}`) : field.label)
      : field.key;
    
    const label = (
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 6 }}>
        <span style={{ fontWeight: 500, fontSize: 13, color: token.colorText }}>
          {labelText}
          {field.required && <span style={{ color: token.colorError, marginLeft: 2 }}>*</span>}
        </span>
        {hasTooltip && (
          <Tooltip title={t(`pages.knowledge.settings.${field.tooltip}`)} placement="top">
            <QuestionCircleOutlined style={{ fontSize: 12, color: token.colorTextSecondary, cursor: 'help' }} />
          </Tooltip>
        )}
        {managed && (
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

    // Handle Ollama dynamic model field
    if (field.isDynamicOllamaModel && currentProvider?.isOllama) {
      const modelOptions = ollamaModels.map(m => ({ value: m.name, label: m.name }));
      
      return (
        <div key={field.key} style={{ marginBottom: 12 }}>
          {label}
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <Select
              value={value || undefined}
              placeholder={ollamaLoading ? t('pages.knowledge.settings.ollama.loading', { defaultValue: 'Loading...' }) : (ollamaError || placeholder)}
              onChange={(val) => onSettingChange(field.key, val)}
              style={{ flex: 1 }}
              options={modelOptions}
              size="small"
              loading={ollamaLoading}
              disabled={managed}
              showSearch
              allowClear
              notFoundContent={ollamaError || t('pages.knowledge.settings.ollama.noModels', { defaultValue: 'No models' })}
            />
            <Tooltip title={t('pages.knowledge.settings.ollama.refresh', { defaultValue: 'Refresh' })}>
              <Button icon={<ReloadOutlined spin={ollamaLoading} />} size="small" onClick={fetchOllamaModels} style={{ flexShrink: 0 }} />
            </Tooltip>
          </div>
        </div>
      );
    }

    // Handle text fields with options as Select (e.g. Model list)
    if (field.type === 'text' && field.options && field.options.length > 0) {
        const translatedModelOptions = field.options.map(opt => {
          const isI18nKey = opt.label.startsWith('fields.') || opt.label.startsWith('providers.');
          return { value: opt.value, label: isI18nKey ? t(`pages.knowledge.settings.${opt.label}`) : opt.label };
        });
        
        return (
          <div key={field.key} style={{ marginBottom: 12 }}>
            {label}
            <Select
              value={value || undefined}
              placeholder={placeholder}
              onChange={(val) => onSettingChange(field.key, val)}
              style={commonStyle}
              options={translatedModelOptions}
              size="small"
              disabled={managed}
            />
          </div>
        );
    }

    switch (field.type) {
      case 'text':
        return (
          <div key={field.key} style={{ marginBottom: 12 }}>
            {label}
            <Input
              type="text"
              value={value}
              placeholder={placeholder}
              onChange={(e) => onSettingChange(field.key, e.target.value)}
              style={commonStyle}
              size="small"
              disabled={managed || field.disabled}
            />
          </div>
        );
        
      case 'password':
        // Check if this is an API key field that should have a settings button
        const isApiKeyField = field.key === 'LLM_BINDING_API_KEY' || 
                             field.key === 'EMBEDDING_BINDING_API_KEY' ||
                             field.key === 'RERANK_BINDING_API_KEY';
        
        return (
          <div key={field.key} style={{ marginBottom: 12 }}>
            {label}
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <Input.Password
                value={value}
                placeholder={placeholder}
                onChange={(e) => onSettingChange(field.key, e.target.value)}
                style={{ 
                  flex: 1,
                  ...(managed ? { backgroundColor: token.colorBgContainerDisabled, cursor: 'not-allowed' } : {})
                }}
                size="small"
                readOnly={managed} // ReadOnly for system managed keys - allows viewing but not editing
                visibilityToggle={true} // Always show toggle so users can view the value (even if masked)
              />
              {isApiKeyField && (
                <Tooltip title={t('pages.knowledge.settings.goToSettings', { defaultValue: 'Go to System Settings' })}>
                  <Button
                    icon={<SettingOutlined />}
                    size="small"
                    onClick={() => handleNavigateToSettings(field.key)}
                    style={{ flexShrink: 0 }}
                  />
                </Tooltip>
              )}
            </div>
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
              onChange={(e) => onSettingChange(field.key, e.target.value)}
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
              onChange={(e) => onSettingChange(field.key, e.target.value)}
              rows={2}
              style={commonStyle}
              size="small"
              disabled={field.disabled}
            />
          </div>
        );
      
      case 'select':
        // Translate option labels only if they look like i18n keys (start with 'fields.' or 'providers.')
        const translatedOptions = field.options?.map(opt => {
          const isI18nKey = opt.label.startsWith('fields.') || opt.label.startsWith('providers.');
          return {
            value: opt.value,
            label: isI18nKey ? t(`pages.knowledge.settings.${opt.label}`) : opt.label
          };
        });
        
        return (
          <div key={field.key} style={{ marginBottom: 12 }}>
            {label}
            <Select
              value={value || undefined}
              placeholder={placeholder}
              onChange={(val) => onSettingChange(field.key, val)}
              style={commonStyle}
              options={translatedOptions}
              size="small"
              disabled={field.disabled}
            />
          </div>
        );
      
      case 'boolean':
        return (
          <div key={field.key} style={{ marginBottom: 12 }}>
            {label}
            <Switch
              checked={value === 'true' || value === 'True'}
              onChange={(checked) => onSettingChange(field.key, checked ? 'true' : 'false')}
              size="small"
              disabled={field.disabled}
            />
          </div>
        );
      
      default:
        return null;
    }
  };

  return (
    <div style={{ padding: '16px 0' }}>
      <div style={{ marginBottom: 20 }}>
        <div style={{ marginBottom: 6 }}>
          <span style={{ fontWeight: 600, fontSize: 14, color: token.colorText }}>
            {t('pages.knowledge.settings.provider.selectProvider')}
          </span>
        </div>
        <Select
          value={currentProviderId}
          onChange={(val) => onSettingChange(bindingKey, val)}
          style={{ width: '100%' }}
          size="middle"
          optionLabelProp="label"
        >
          {providers.map(p => {
            // Translate provider name if it's an i18n key
            const providerName = p.name.includes('.') 
              ? t(`pages.knowledge.settings.${p.name}`)
              : p.name;
            
            return (
              <Select.Option key={p.id} value={p.id} label={providerName}>
                <div>
                  <div style={{ fontWeight: 500 }}>{providerName}</div>
                  {p.description && (
                    <div style={{ fontSize: 12, color: token.colorTextSecondary }}>{p.description}</div>
                  )}
                </div>
              </Select.Option>
            );
          })}
        </Select>
      </div>

      {currentProvider && currentProvider.fields.length > 0 && (
        <Card
          size="small"
          title={
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span>{`${currentProvider.name.includes('.') ? t(`pages.knowledge.settings.${currentProvider.name}`) : currentProvider.name} ${t('pages.knowledge.settings.provider.configuration')}`}</span>
              {currentProvider.isOllama && (
                <Tooltip title={t('pages.knowledge.settings.ollama.openWebsite', { defaultValue: 'Open Ollama' })}>
                  <Button
                    type="link"
                    size="small"
                    icon={<GlobalOutlined />}
                    onClick={handleOpenOllamaWebsite}
                    style={{ padding: '0 4px' }}
                  />
                </Tooltip>
              )}
            </div>
          }
          style={{
            marginBottom: 20,
            borderColor: token.colorBorder
          }}
        >
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: 12
          }}>
            {currentProvider.fields.map(field => renderField(field))}
          </div>
        </Card>
      )}

      {commonFields.length > 0 && (
        <Card
          size="small"
          title={t('pages.knowledge.settings.provider.commonSettings')}
          style={{
            borderColor: token.colorBorder
          }}
        >
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: 12
          }}>
            {commonFields.map(field => renderField(field))}
          </div>
        </Card>
      )}
    </div>
  );
};

export default ProviderSelector;
