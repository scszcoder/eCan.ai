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
  /**
   * Managed mode hides the provider dropdown. The provider is owned by
   * System Settings (default_llm / default_embedding / default_rerank);
   * we display the active provider's name and a deep-link button so the
   * user can change it there. Only non-provider-specific tuning fields
   * remain editable.
   */
  managed?: boolean;
  /** Provider type the managed banner should reference (display only). */
  managedKind?: 'llm' | 'embedding' | 'rerank';
  navigateToSettings?: () => void;
  token?: any;
  t?: (key: string, options?: any) => string;
}

const ProviderSelector: React.FC<ProviderSelectorProps> = ({
  bindingKey,
  providers,
  commonFields = [],
  settings,
  onSettingChange,
  onTestProvider,
  managed = false,
  managedKind,
  navigateToSettings,
  token: tokenProp,
  t: tProp,
}) => {
  const { t: tHook } = useTranslation();
  const { token: tokenHook } = theme.useToken();
  const t = tProp || tHook;
  const token = tokenProp || tokenHook;
  
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

  const handleNavigateToSettings = (kind: 'llm' | 'embedding' | 'rerank') => {
    // Navigate within the app using hash routing (same as onboarding).
    // Each model type deep-links to its matching tab in System Settings so
    // the user lands exactly where they can change the provider.
    const tabMap: Record<'llm' | 'embedding' | 'rerank', string> = {
      llm: 'llm',
      embedding: 'embedding',
      rerank: 'rerank',
    };
    window.location.hash = `#/settings?tab=${tabMap[kind]}`;
  };

  const renderField = (field: ProviderFieldConfig) => {
    const value = settings[field.key] || field.defaultValue || '';
    // The backend marks the eCanAI-managed key/endpoint as
    // ``isSystemManaged`` at load time, but the user can switch the
    // provider mode without re-fetching the engine definitions. Compute
    // the managed flag from the *current* settings so the System badge
    // follows the active mode and disappears once the user picks local
    // or official.
    const mineruMode = settings.MINERU_API_MODE || 'ecanai';
    const doclingMode = settings.DOCLING_PROVIDER || 'ecanai';
    const isMineruEcanai = currentProvider?.id === 'mineru' && mineruMode === 'ecanai';
    const isDoclingEcanai = currentProvider?.id === 'docling' && doclingMode === 'ecanai';
    const isEcanaiManagedKey =
      (field.key === 'MINERU_API_TOKEN' || field.key === 'MINERU_ECANAI_ENDPOINT') && isMineruEcanai;
    const isEcanaiManagedDoclingKey =
      (field.key === 'DOCLING_API_KEY' || field.key === 'DOCLING_ECANAI_ENDPOINT') && isDoclingEcanai;
    const managed = field.isSystemManaged || isEcanaiManagedKey || isEcanaiManagedDoclingKey;
    
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
          <Tooltip title={t('pages.knowledge.settings.systemManaged')} placement="top">
            <span style={{
              fontSize: 10,
              background: token.colorFillSecondary,
              color: token.colorTextSecondary,
              padding: '1px 6px',
              borderRadius: 4,
              marginLeft: 4
            }}>
              {t('pages.knowledge.settings.badgeSystem', { defaultValue: 'System' })}
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
              <Button
                type="text"
                icon={<ReloadOutlined spin={ollamaLoading} />}
                size="small"
                onClick={currentProvider.hasDynamicModels ? fetchProviderModels : fetchOllamaModels}
                style={{ flexShrink: 0 }}
              />
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
                    type="text"
                    icon={<SettingOutlined />}
                    size="small"
                    onClick={() => handleNavigateToSettings(managedKind || 'llm')}
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
    if (currentProvider.id === 'mineru') {
      // Default to ``ecanai`` to match the schema's defaultValue; an empty
      // settings map should render the recommended provider, not silently
      // show local-only fields.
      const mineruMode = settings.MINERU_API_MODE || 'ecanai';
      const isOfficial = mineruMode === 'official';
      const isEcanai = mineruMode === 'ecanai';
      const localBackend = settings.MINERU_LOCAL_BACKEND || 'hybrid-auto-engine';

      // Each provider mode owns a dedicated endpoint env var so switching
      // modes never clobbers the value the user typed into the inactive
      // mode's box. Only the *endpoint* is mode-specific — every other
      // MinerU parameter is shown for all three modes so the user sees
      // the same options as on the official mineru.net console and
      // doesn't have to flip modes to discover what each knob does.
      // Per-mode API key fields: each mode owns its own key env var so a
      // user-typed credential is preserved across mode switches. Only the
      // active key field (matching the current mode) is shown so the user
      // always sees the right input for the current service.
      if (field.key === 'MINERU_API_TOKEN') return isEcanai;
      if (field.key === 'MINERU_LOCAL_API_KEY') return !isOfficial && !isEcanai;
      if (field.key === 'MINERU_OFFICIAL_API_KEY') return isOfficial;
      // Per-mode endpoints (one box per mode, switched by MINERU_API_MODE).
      if (field.key === 'MINERU_OFFICIAL_ENDPOINT') return isOfficial;
      if (field.key === 'MINERU_LOCAL_ENDPOINT_SETTING') return !isOfficial && !isEcanai;
      if (field.key === 'MINERU_ECANAI_ENDPOINT') return isEcanai;
      // MINERU_MODEL_VERSION / MINERU_IS_OCR / MINERU_PAGE_RANGES describe
      // official mineru.net API task parameters. LightRAG 1.5.6 also reads
      // MINERU_PAGE_RANGES in local mode (mapped to start/end_page_id via
      // local_page_bounds) but MINERU_MODEL_VERSION / MINERU_IS_OCR are
      // ignored by the local mineru-api service. Hide them in local mode
      // so the user does not configure knobs the service silently drops.
      if (field.key === 'MINERU_MODEL_VERSION') return isOfficial;
      if (field.key === 'MINERU_IS_OCR') return isOfficial;
      if (field.key === 'MINERU_PAGE_RANGES') return isOfficial;
      // MINERU_LOCAL_BACKEND / MINERU_LOCAL_PARSE_METHOD /
      // MINERU_LOCAL_IMAGE_ANALYSIS / MINERU_LOCAL_START_PAGE_ID /
      // MINERU_LOCAL_END_PAGE_ID describe the self-hosted MinerU service;
      // they are only meaningful in local and ecanai mode (ecanai is an
      // alias for local that talks to the proxy at ``/tasks``). Keep
      // them hidden in official mode so the user does not see fields
      // that the official API ignores.
      if (field.key === 'MINERU_LOCAL_BACKEND') {
        return !isOfficial;
      }
      if (field.key === 'MINERU_LOCAL_PARSE_METHOD') {
        return !isOfficial && !localBackend.startsWith('vlm');
      }
      if (field.key === 'MINERU_LOCAL_IMAGE_ANALYSIS') {
        return !isOfficial && (localBackend.startsWith('vlm') || localBackend.startsWith('hybrid'));
      }
      if (field.key === 'MINERU_LOCAL_START_PAGE_ID') return !isOfficial;
      if (field.key === 'MINERU_LOCAL_END_PAGE_ID') return !isOfficial;
      return true;
    }

    if (currentProvider.id === 'docling') {
      // Docling follows the same three-way provider model as MinerU. Each
      // mode owns its own endpoint and API key env var so user-typed
      // credentials are preserved across mode switches. Only the active
      // key field (matching the current mode) is shown.
      const doclingMode = settings.DOCLING_PROVIDER || 'ecanai';
      if (field.key === 'DOCLING_OFFICIAL_ENDPOINT') return doclingMode === 'official';
      if (field.key === 'DOCLING_LOCAL_ENDPOINT') return doclingMode === 'local';
      if (field.key === 'DOCLING_ECANAI_ENDPOINT') return doclingMode === 'ecanai';
      // Per-mode API key fields: same logic as MinerU above.
      if (field.key === 'DOCLING_API_KEY') return doclingMode === 'ecanai';
      if (field.key === 'DOCLING_LOCAL_API_KEY') return doclingMode === 'local';
      if (field.key === 'DOCLING_OFFICIAL_API_KEY') return doclingMode === 'official';
    }

    return true;
  }) || [];

  const parserFieldGroups = isParserSelector ? [
    {
      key: 'connection',
      title: t('pages.knowledge.settings.parserLayout.connection'),
      // Per-mode key/endpoint fields are conditionally shown by mode,
      // so include all of them in the group key list.
      keys: [
        'MINERU_API_MODE',
        'MINERU_OFFICIAL_ENDPOINT', 'MINERU_LOCAL_ENDPOINT_SETTING', 'MINERU_ECANAI_ENDPOINT',
        'MINERU_API_TOKEN', 'MINERU_LOCAL_API_KEY', 'MINERU_OFFICIAL_API_KEY',
        'DOCLING_PROVIDER',
        'DOCLING_OFFICIAL_ENDPOINT', 'DOCLING_LOCAL_ENDPOINT', 'DOCLING_ECANAI_ENDPOINT',
        'DOCLING_API_KEY', 'DOCLING_LOCAL_API_KEY', 'DOCLING_OFFICIAL_API_KEY',
      ]
    },
    {
      key: 'options',
      title: t('pages.knowledge.settings.parserLayout.options'),
      keys: ['PARSER_IMAGE_ANALYSIS', 'MINERU_MODEL_VERSION', 'MINERU_IS_OCR', 'MINERU_LANGUAGE', 'MINERU_ENABLE_TABLE', 'MINERU_ENABLE_FORMULA', 'MINERU_LOCAL_BACKEND', 'MINERU_LOCAL_PARSE_METHOD']
    },
    {
      key: 'advanced',
      title: t('pages.knowledge.settings.parserLayout.advanced'),
      keys: ['MINERU_LOCAL_IMAGE_ANALYSIS', 'MINERU_LOCAL_START_PAGE_ID', 'MINERU_LOCAL_END_PAGE_ID', 'MINERU_PAGE_RANGES', 'MINERU_ADDITIONAL_SUFFIXES', 'DOCLING_ADDITIONAL_SUFFIXES', 'MAX_PARALLEL_PARSE_MINERU', 'MAX_PARALLEL_PARSE_DOCLING', 'LIGHTRAG_PARSER']
    }
  ].map(group => ({ ...group, fields: visibleFields.filter(field => group.keys.includes(field.key)) }))
    .filter(group => group.fields.length > 0) : [];

  // In managed mode, fields whose values come from the System Settings
  // provider configuration (model, host, api_key) are hidden. The
  // provider object still knows about them — we just don't render the
  // inputs. Other tuning parameters (timeout, temperature, scoring
  // thresholds, etc.) stay editable.
  const managedFieldKeys = new Set([
    'LLM_MODEL', 'LLM_BINDING_HOST', 'LLM_BINDING_API_KEY',
    'EMBEDDING_MODEL', 'EMBEDDING_BINDING_HOST', 'EMBEDDING_BINDING_API_KEY',
    'EMBEDDING_DIM', 'EMBEDDING_TOKEN_LIMIT', 'EMBEDDING_SEND_DIM',
    'RERANK_MODEL', 'RERANK_BINDING_HOST', 'RERANK_BINDING_API_KEY',
  ]);
  const fieldsForDisplay = managed && currentProvider
    ? currentProvider.fields.filter(field => !managedFieldKeys.has(field.key))
    : visibleFields;

  return (
    <div style={{ padding: '8px 0' }}>
      {managed ? (
        // ── Managed banner ────────────────────────────────────────────
        // The provider dropdown is owned by System Settings. Show the
        // active provider as a read-only tag with its current status and
        // offer a deep link to the matching Settings tab. This banner
        // renders independently of provider fields — it must appear even
        // when all provider fields are managed (e.g. eCanAI reranking where
        // every field is stripped by managedFieldKeys and fieldsForDisplay
        // is empty).
        <div
          style={{
            marginBottom: 12,
            padding: '10px 12px',
            border: `1px solid ${token.colorBorder}`,
            borderRadius: 8,
            background: token.colorFillQuaternary,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            flexWrap: 'wrap',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flex: '1 1 auto', minWidth: 0 }}>
            <Tooltip title={t('pages.knowledge.settings.provider.managedHint', { defaultValue: 'This provider is configured in System Settings' })}>
              <span style={{
                fontSize: 10,
                background: token.colorFillSecondary,
                color: token.colorTextSecondary,
                padding: '1px 6px',
                borderRadius: 4,
              }}>
                {t('pages.knowledge.settings.badgeSystem', { defaultValue: 'System' })}
              </span>
            </Tooltip>
            <span style={{ color: token.colorTextSecondary, fontSize: 13 }}>
              {t(`pages.knowledge.settings.provider.managedBy_${managedKind || 'llm'}`, {
                provider: currentProvider
                  ? (currentProvider.name.includes('.') ? t(`pages.knowledge.settings.${currentProvider.name}`) : currentProvider.name)
                  : '—',
                defaultValue: 'Provider: {{provider}} (managed by System Settings)'
              })}
            </span>
          </div>

          {/* Test button + provider status — always visible in managed mode */}
          {onTestProvider && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Tooltip title={providerStatus === 'unavailable' ? (
                <div>
                  <div>{t(`pages.knowledge.settings.parserProbe.errors.${providerError.category || 'unknown'}.reason`)}</div>
                  {providerError.technical && <div style={{ marginTop: 4, wordBreak: 'break-word' }}>{providerError.technical}</div>}
                </div>
              ) : undefined}>
                <Badge
                  status={providerStatus === 'testing' ? 'processing' : providerStatus === 'available' ? 'success' : providerStatus === 'unavailable' ? 'error' : 'default'}
                  text={t(`pages.knowledge.settings.serviceStatus.${providerStatus}`)}
                  style={{ color: token.colorTextSecondary, fontSize: 12 }}
                />
              </Tooltip>
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
            </div>
          )}

          {navigateToSettings && (
            <Button
              type="link"
              size="small"
              icon={<SettingOutlined />}
              onClick={() => handleNavigateToSettings(managedKind || 'llm')}
              style={{ padding: '0 4px' }}
            >
              {t('pages.knowledge.settings.provider.goToSettings', { defaultValue: 'Go to System Settings' })}
            </Button>
          )}
        </div>
      ) : (
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
      )}

      {/* In managed mode the banner (above) is always visible.
          The Card only renders when there are managed-field tuning parameters
          to show (fieldsForDisplay non-empty). When all fields are owned by
          System Settings (e.g. eCanAI reranking) the Card is omitted so the
          user does not see an empty "Configuration" card. The common-fields
          Card below still shows any global tuning fields. */}
      {currentProvider && fieldsForDisplay.length > 0 && (
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
              {fieldsForDisplay.map(field => renderField(field))}
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
