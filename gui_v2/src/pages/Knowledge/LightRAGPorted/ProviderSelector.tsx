import React, { useState, useEffect, useCallback } from 'react';
import { theme, Select, Input, InputNumber, Switch, Card, Tooltip, Button, Badge } from 'antd';
import { QuestionCircleOutlined, SettingOutlined, ReloadOutlined, GlobalOutlined, ApiOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { ProviderConfig, ProviderFieldConfig } from './providerConfig';
import { IPCAPI } from '../../../services/ipc/api';

interface OllamaModel {
  name: string;
  size: number;
  modified_at: string;
  digest: string;
  details: Record<string, any>;
  dimensions?: number;
  dimension?: number;
  max_tokens?: number;
  context_length?: number;
}

interface ProviderSelectorProps {
  bindingKey: string;
  providers: ProviderConfig[];
  commonFields?: ProviderFieldConfig[];
  settings: Record<string, string>;
  onSettingChange: (key: string, value: string) => void;
  onTestProvider?: (providerId: string, silent?: boolean) => Promise<boolean | { ok: boolean; category?: string; technical?: string }>;
}

const ProviderSelector: React.FC<ProviderSelectorProps> = ({
  bindingKey,
  providers,
  commonFields = [],
  settings,
  onSettingChange,
  onTestProvider
}) => {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  
  const currentProviderId = settings[bindingKey] || '';
  // Only fall back to first provider if the saved setting is a valid provider in the current list.
  // If the setting is empty or references a provider not in the list (e.g., wrong region), show "none" state.
  const isCurrentProviderValid = providers.some(p => p.id === currentProviderId);
  const effectiveProviderId = currentProviderId && isCurrentProviderValid ? currentProviderId : undefined;
  const currentProvider = providers.find(p => p.id === (effectiveProviderId || currentProviderId));
  const isParserSelector = bindingKey === 'PARSING_ENGINE';
  
  // Ollama models state
  const [ollamaModels, setOllamaModels] = useState<OllamaModel[]>([]);
  const [ollamaLoading, setOllamaLoading] = useState(false);
  const [ollamaError, setOllamaError] = useState<string | null>(null);
  const [testingProvider, setTestingProvider] = useState(false);
  const [providerStatus, setProviderStatus] = useState<'unchecked' | 'testing' | 'available' | 'unavailable'>('unchecked');
  const [providerError, setProviderError] = useState<{ category?: string; technical?: string }>({});
  const lastAutoProbeRef = React.useRef('');
  const onSettingChangeRef = React.useRef(onSettingChange);
  useEffect(() => {
    onSettingChangeRef.current = onSettingChange;
  }, [onSettingChange]);

  const applyDynamicModelMetadata = useCallback((model?: OllamaModel) => {
    if (bindingKey !== 'EMBEDDING_BINDING' || !model) return;
    const dimensions = model.dimensions ?? model.dimension;
    const tokenLimit = model.max_tokens ?? model.context_length;
    if (dimensions) onSettingChangeRef.current('EMBEDDING_DIM', String(dimensions));
    if (tokenLimit) onSettingChangeRef.current('EMBEDDING_TOKEN_LIMIT', String(tokenLimit));
  }, [bindingKey]);

  const probeFingerprint = currentProvider
    ? JSON.stringify([currentProvider.id, ...currentProvider.fields.map(field => settings[field.key] ?? field.defaultValue ?? '')])
    : '';

  useEffect(() => {
    setProviderStatus('unchecked');
    setProviderError({});
    if (!currentProvider || !onTestProvider || !probeFingerprint || lastAutoProbeRef.current === probeFingerprint) return;
    lastAutoProbeRef.current = probeFingerprint;
    const timer = window.setTimeout(async () => {
      setProviderStatus('testing');
      try {
        const result = await onTestProvider(currentProvider.id, true);
        const ok = typeof result === 'boolean' ? result : result.ok;
        setProviderError(typeof result === 'boolean' ? {} : result);
        setProviderStatus(ok ? 'available' : 'unavailable');
      } catch (error: any) {
        setProviderError({ category: 'unknown', technical: error?.message || String(error) });
        setProviderStatus('unavailable');
      }
    }, 500);
    return () => window.clearTimeout(timer);
    // onTestProvider is intentionally excluded: callers create it during render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [probeFingerprint, currentProvider?.id]);

  const handleTestProvider = async () => {
    if (!currentProvider || !onTestProvider) return;
    setTestingProvider(true);
    setProviderStatus('testing');
    try {
      const result = await onTestProvider(currentProvider.id, false);
      const ok = typeof result === 'boolean' ? result : result.ok;
      setProviderError(typeof result === 'boolean' ? {} : result);
      setProviderStatus(ok ? 'available' : 'unavailable');
    } catch {
      setProviderStatus('unavailable');
    } finally {
      setTestingProvider(false);
    }
  };

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

  const fetchProviderModels = useCallback(async () => {
    if (!currentProvider?.hasDynamicModels) return;
    setOllamaLoading(true);
    setOllamaError(null);
    const prefix = bindingKey === 'LLM_BINDING' ? 'LLM' : bindingKey === 'EMBEDDING_BINDING' ? 'EMBEDDING' : 'RERANK';
    const modelType = prefix.toLowerCase();
    const host = settings[`${prefix}_BINDING_HOST`]
      || currentProvider.fields.find(field => field.key === `${prefix}_BINDING_HOST`)?.defaultValue
      || '';
    try {
      const response = await IPCAPI.getInstance().getProviderModels<{ models: OllamaModel[]; host: string }>(
        host,
        settings[`${prefix}_BINDING_API_KEY`],
        modelType,
        currentProvider.id
      );
      if (response.success && response.data) {
        const models = response.data.models || [];
        setOllamaModels(models);
        if (!models.length) {
          setOllamaError(t('pages.knowledge.settings.ollama.noModels', { defaultValue: 'No models found' }));
        } else if (!settings[`${prefix}_MODEL`]) {
          onSettingChange(`${prefix}_MODEL`, models[0].name);
          applyDynamicModelMetadata(models[0]);
        }
      } else {
        setOllamaModels([]);
        setOllamaError(response.error?.message || t('pages.knowledge.settings.ollama.fetchError', { defaultValue: 'Failed to fetch models' }));
      }
    } catch (error: any) {
      setOllamaModels([]);
      setOllamaError(error.message || t('pages.knowledge.settings.ollama.fetchError', { defaultValue: 'Failed to fetch models' }));
    } finally {
      setOllamaLoading(false);
    }
  // onSettingChange is intentionally excluded: callers create it during render.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applyDynamicModelMetadata, bindingKey, currentProvider?.hasDynamicModels, currentProvider?.fields, settings, t]);

  // Fetch Ollama models when provider changes to Ollama
  useEffect(() => {
    if (currentProvider?.hasDynamicModels) {
      fetchProviderModels();
    } else if (currentProvider?.isOllama) {
      fetchOllamaModels();
    } else {
      setOllamaModels([]);
      setOllamaError(null);
    }
  }, [currentProvider?.isOllama, currentProvider?.hasDynamicModels, fetchOllamaModels, fetchProviderModels]);

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
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}>
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
    if ((field.isDynamicOllamaModel && currentProvider?.isOllama) || (field.isDynamicProviderModel && currentProvider?.hasDynamicModels)) {
      const modelOptions = ollamaModels.map(m => ({ value: m.name, label: m.name }));
      
      return (
        <div key={field.key} style={{ marginBottom: 12 }}>
          {label}
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <Select
              value={value || undefined}
              placeholder={ollamaLoading ? t('pages.knowledge.settings.ollama.loading', { defaultValue: 'Loading...' }) : (ollamaError || placeholder)}
              onChange={(val) => {
                onSettingChange(field.key, val);
                applyDynamicModelMetadata(ollamaModels.find(model => model.name === val));
              }}
              style={{ flex: 1 }}
              options={modelOptions}
              loading={ollamaLoading}
              disabled={managed}
              showSearch
              allowClear
              notFoundContent={ollamaError || t('pages.knowledge.settings.ollama.noModels', { defaultValue: 'No models' })}
            />
            <Tooltip title={t('pages.knowledge.settings.ollama.refresh', { defaultValue: 'Refresh' })}>
              <Button icon={<ReloadOutlined spin={ollamaLoading} />} size="small" onClick={currentProvider.hasDynamicModels ? fetchProviderModels : fetchOllamaModels} style={{ flexShrink: 0 }} />
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
            <InputNumber
              value={value ? Number(value) : undefined}
              placeholder={placeholder}
              onChange={(val) => onSettingChange(field.key, val?.toString() || '')}
              style={commonStyle}
              disabled={field.disabled}
              min={0}
              step={field.key.includes('TEMPERATURE') || field.key.includes('SCORE') ? 0.1 : 1}
              precision={field.key.includes('TEMPERATURE') || field.key.includes('THRESHOLD') || field.key.includes('SCORE') ? 2 : 0}
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
              disabled={field.disabled}
            />
          </div>
        );
      
      case 'boolean':
        if (isParserSelector) {
          return (
            <div key={field.key} style={{
              minHeight: 44,
              padding: '6px 10px',
              border: `1px solid ${token.colorBorderSecondary}`,
              borderRadius: token.borderRadiusLG,
              background: token.colorFillQuaternary,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 12
            }}>
              <div style={{ minWidth: 0 }}>{label}</div>
              <Switch
                checked={value === 'true' || value === 'True'}
                onChange={(checked) => onSettingChange(field.key, checked ? 'true' : 'false')}
                size="small"
                disabled={field.disabled}
              />
            </div>
          );
        }
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

  const visibleFields = currentProvider?.fields.filter(field => {
    if (currentProvider.id !== 'mineru') return true;

    const mineruMode = settings.MINERU_API_MODE || 'local';
    const isOfficial = mineruMode === 'official';
    const localBackend = settings.MINERU_LOCAL_BACKEND || 'hybrid-auto-engine';

    // These are two different LightRAG protocols. Only expose fields that
    // are actually included in the active protocol's request payload.
    if (['MINERU_OFFICIAL_ENDPOINT', 'MINERU_MODEL_VERSION', 'MINERU_IS_OCR'].includes(field.key)) {
      return isOfficial;
    }
    if (field.key === 'MINERU_API_TOKEN') return true;
    if (['MINERU_LOCAL_ENDPOINT', 'MINERU_LOCAL_BACKEND'].includes(field.key)) {
      return !isOfficial;
    }
    if (field.key === 'MINERU_LOCAL_PARSE_METHOD') {
      return !isOfficial && !localBackend.startsWith('vlm');
    }
    if (field.key === 'MINERU_LOCAL_IMAGE_ANALYSIS') {
      return !isOfficial && (localBackend.startsWith('vlm') || localBackend.startsWith('hybrid'));
    }
    return true;
  }) || [];

  const parserFieldGroups = isParserSelector ? [
    {
      key: 'connection',
      title: t('pages.knowledge.settings.parserLayout.connection'),
      keys: ['MINERU_API_MODE', 'MINERU_OFFICIAL_ENDPOINT', 'MINERU_LOCAL_ENDPOINT', 'MINERU_API_TOKEN', 'DOCLING_ENDPOINT', 'DOCLING_API_KEY']
    },
    {
      key: 'options',
      title: t('pages.knowledge.settings.parserLayout.options'),
      keys: ['PARSER_IMAGE_ANALYSIS', 'MINERU_MODEL_VERSION', 'MINERU_IS_OCR', 'MINERU_LANGUAGE', 'MINERU_ENABLE_TABLE', 'MINERU_ENABLE_FORMULA', 'MINERU_LOCAL_BACKEND', 'MINERU_LOCAL_PARSE_METHOD']
    },
    {
      key: 'advanced',
      title: t('pages.knowledge.settings.parserLayout.advanced'),
      keys: ['MINERU_LOCAL_IMAGE_ANALYSIS', 'MINERU_ADDITIONAL_SUFFIXES', 'DOCLING_ADDITIONAL_SUFFIXES', 'MAX_PARALLEL_PARSE_MINERU', 'MAX_PARALLEL_PARSE_DOCLING', 'LIGHTRAG_PARSER']
    }
  ].map(group => ({ ...group, fields: visibleFields.filter(field => group.keys.includes(field.key)) }))
    .filter(group => group.fields.length > 0) : [];

  return (
    <div style={{ padding: '8px 0' }}>
      <div style={{ marginBottom: 12 }}>
        <div style={{ marginBottom: 4 }}>
          <span style={{ fontWeight: 600, fontSize: 14, color: token.colorText }}>
            {t('pages.knowledge.settings.provider.selectProvider')}
          </span>
        </div>
        <Select
          value={effectiveProviderId}
          placeholder={t('pages.knowledge.settings.provider.selectProviderPlaceholder')}
          onChange={(val) => onSettingChange(bindingKey, val)}
          style={{ width: '100%' }}
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

      {currentProvider && visibleFields.length > 0 && (
        <Card
          size="small"
          title={
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              {`${currentProvider.name.includes('.') ? t(`pages.knowledge.settings.${currentProvider.name}`) : currentProvider.name} ${t('pages.knowledge.settings.provider.configuration')}`}
              {bindingKey === 'RERANK_BINDING' && settings['_RERANK_USES_PROXY'] === 'true' && settings['_RERANK_RUNTIME_HOST'] && (
                <Tooltip
                  title={
                    <div style={{ lineHeight: 1.6 }}>
                      <div>{t('pages.knowledge.settings.rerankProxy.realAddress')}: {settings['RERANK_BINDING_HOST']}</div>
                      <div>{t('pages.knowledge.settings.rerankProxy.runtimeAddress')}: {settings['_RERANK_RUNTIME_HOST']}</div>
                      <div style={{ marginTop: 4 }}>{t('pages.knowledge.settings.rerankProxy.hint')}</div>
                    </div>
                  }
                >
                  <QuestionCircleOutlined style={{ color: token.colorTextSecondary, fontSize: 14 }} />
                </Tooltip>
              )}
            </span>
          }
          extra={
            <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              {onTestProvider && (
                <Tooltip title={providerStatus === 'unavailable' ? (
                  <div>
                    <div>{t(`pages.knowledge.settings.parserProbe.errors.${providerError.category || 'unknown'}.reason`)}</div>
                    {providerError.technical && <div style={{ marginTop: 4, wordBreak: 'break-word' }}>{providerError.technical}</div>}
                  </div>
                ) : undefined}>
                  <Badge
                    status={providerStatus === 'testing' ? 'processing' : providerStatus === 'available' ? 'success' : providerStatus === 'unavailable' ? 'error' : 'default'}
                    text={t(`pages.knowledge.settings.serviceStatus.${providerStatus}`)}
                    style={{ marginRight: 6, color: token.colorTextSecondary, fontSize: 12 }}
                  />
                </Tooltip>
              )}
              {onTestProvider && (
                <Tooltip title={t('pages.knowledge.settings.parserProbe.test')}>
                  <Button
                    type="text"
                    size="small"
                    icon={<ApiOutlined />}
                    loading={testingProvider}
                    onClick={handleTestProvider}
                    style={{ height: 28, padding: '0 8px', color: token.colorPrimary, fontWeight: 500 }}
                  >
                    {t('pages.knowledge.settings.parserProbe.testShort')}
                  </Button>
                </Tooltip>
              )}
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
            marginBottom: 12,
            borderColor: token.colorBorder,
            borderRadius: 12,
            boxShadow: '0 2px 8px rgba(0, 0, 0, 0.06)',
          }}
        >
          {isParserSelector ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {parserFieldGroups.map(group => (
                <section key={group.key}>
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12,
                    color: token.colorTextSecondary, fontSize: 12, fontWeight: 600
                  }}>
                    <span>{group.title}</span>
                    <span style={{ height: 1, flex: 1, background: token.colorBorderSecondary }} />
                  </div>
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                    gap: 8
                  }}>
                    {group.fields.map(field => (
                      <div key={field.key} style={{
                        minWidth: 0,
                        gridColumn: field.key === 'LIGHTRAG_PARSER' ? '1 / -1' : undefined
                      }}>
                        {renderField(field)}
                      </div>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          ) : (
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
              gap: 8
            }}>
              {visibleFields.map(field => renderField(field))}
            </div>
          )}
        </Card>
      )}

      {commonFields.length > 0 && (
        <Card
          size="small"
          title={t('pages.knowledge.settings.provider.commonSettings')}
          style={{
            borderColor: token.colorBorder,
            borderRadius: 12,
            boxShadow: '0 2px 8px rgba(0, 0, 0, 0.06)',
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
