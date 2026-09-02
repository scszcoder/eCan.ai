import React, { useState, useEffect, useRef } from 'react';
import { theme, App, Tabs, Tooltip, Input, InputNumber, Select, Switch, Modal } from 'antd';
import { useTranslation } from 'react-i18next';
import { get_ipc_api } from '@/services/ipc_api';
import { 
  FolderOpenOutlined, 
  CheckOutlined,
  DatabaseOutlined, 
  ApiOutlined, 
  CloudServerOutlined,
  RobotOutlined,
  BlockOutlined,
  SortAscendingOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  QuestionCircleOutlined,
  ExclamationCircleOutlined
} from '@ant-design/icons';
import { useTheme } from '@/contexts/ThemeContext';
import { FIELDS_BY_TAB, FieldConfig, PROVIDER_BASED_TABS } from './settingsConfig';
import WorkspaceSelector from './WorkspaceSelector';
import ProviderSelector from './ProviderSelector';
import {
  STORAGE_KV_PROVIDERS, STORAGE_VECTOR_PROVIDERS, STORAGE_GRAPH_PROVIDERS,
  STORAGE_DOC_STATUS_PROVIDERS, STORAGE_COMMON_POSTGRES,
  RERANKING_COMMON_FIELDS,
  LLM_COMMON_FIELDS,
  EMBEDDING_COMMON_FIELDS,
  PARSER_PROVIDERS,
  ProviderConfig, getProvidersByRegion
} from './providerConfig';
import { buildProviderConfig, type RawProvider } from './buildProviderFields';
import { buildParserProviders, type ParserEngineDefinition } from './buildParserProviders';
import { useIsCN } from '@/contexts/AppConfigContext';
import { Card } from 'antd';
import HelpDialog from './HelpDialog';
import { useLightRAGSettingsStore } from '@/stores/ragStore';
import { useWorkspace } from './useWorkspace';

// Helper to build ProviderConfig from raw backend data
// (defined in buildProviderFields.ts)

interface Workspace {
  name: string;
  path: string;
  is_valid: boolean;
  created_at: number;
}

interface StartupStatus {
  running: boolean;
  ok: boolean;
  message: string;
  error_type: string;
  timestamp: number;
}

const parserImageAnalysisEnabled = (routing = ''): boolean => {
  const firstActiveRule = routing.split(',').find(rule => /:(native|mineru|docling)(?:\([^)]*\))?-/i.test(rule));
  const modifiers = firstActiveRule?.match(/:(?:native|mineru|docling)(?:\([^)]*\))?-([A-Za-z]+)/i)?.[1] || '';
  return modifiers.includes('i');
};

const setParserImageAnalysis = (routing: string, enabled: boolean): string =>
  routing.replace(
    /:(native|mineru|docling)(\([^)]*\))?-([A-Za-z]+)/gi,
    (_match, engine: string, args: string = '', modifiers: string) => {
      const withoutImages = modifiers.replace(/i/g, '');
      return `:${engine}${args || ''}-${enabled ? `i${withoutImages}` : withoutImages}`;
    }
  );

const SettingsTab: React.FC = () => {
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceLoading, setWorkspaceLoading] = useState(false);
  const [startupStatus, setStartupStatus] = useState<StartupStatus | null>(null);
  const [activeWorkspace, setActiveWorkspace] = useWorkspace();
  const [helpDialogVisible, setHelpDialogVisible] = useState(false);
  const savedScrollPosition = useRef<number>(0);
  const restoringRef = useRef(false);
  const initialLoadRef = useRef(true);
  const lastCheckedDimRef = useRef<number | null>(null);
  const pendingSettingsRef = useRef<Record<string, string>>({});

  const storagePrefix = 'lightrag-ported:tabs';
  const settingsScrollKey = `${storagePrefix}:innerScroll:settings`;

  // Check embedding dimension conflict with existing vector database
  const checkDimensionConflict = async (newDimension: number, pendingSettings?: Record<string, string>) => {
    // Store pending settings to apply after workspace switch
    if (pendingSettings) {
      console.log('[DimensionCheck] Storing pending settings:', pendingSettings);
      pendingSettingsRef.current = pendingSettings;
    } else {
      console.log('[DimensionCheck] No pending settings provided');
    }
    try {
      // Use WORKSPACE config instead of extracting from WORKING_DIR path
      const currentWorkspace = settings['WORKSPACE'] || 'default';
      const api = get_ipc_api();
      const result = await api.executeRequest<{
        hasConflict: boolean;
        currentDimension: number | null;
        newDimension: number;
        vectorStorage: string;
        workspaceName: string;
        workspaces: Workspace[];
      }>('lightrag.checkEmbeddingDimension', {
        newDimension,
        workspaceName: currentWorkspace
      });

      // Debug log - raw response
      console.log('[DimensionCheck] Raw API response:', result);
      
      // Debug log - parsed data
      console.log('[DimensionCheck] API result:', {
        success: result.success,
        hasConflict: result.data?.hasConflict,
        currentDimension: result.data?.currentDimension,
        newDimension: result.data?.newDimension,
        vectorStorage: result.data?.vectorStorage,
        workspaceName: result.data?.workspaceName
      });

      if (result.success && result.data?.hasConflict) {
        const { currentDimension, vectorStorage, workspaces } = result.data;
        
        Modal.confirm({
          title: t('pages.knowledge.lightrag.dimension_conflict_title'),
          icon: <ExclamationCircleOutlined style={{ color: '#faad14' }} />,
          width: 600,
          content: (
            <div style={{ fontSize: '15px', lineHeight: '1.6', color: isDark ? '#fff' : 'inherit' }}>
              <p style={{ fontSize: '15px', marginBottom: '12px', color: isDark ? '#fff' : 'inherit' }}>
                {t('pages.knowledge.lightrag.dimension_conflict_message', { 
                  current: currentDimension, 
                  new: newDimension 
                })}
              </p>
              <p style={{ 
                marginTop: '12px', 
                padding: '10px', 
                backgroundColor: isDark ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.02)',
                borderRadius: '4px',
                fontSize: '14px',
                color: isDark ? '#fff' : 'inherit'
              }}>
                {t('pages.knowledge.lightrag.vector_storage_type')}: <strong style={{ fontSize: '15px', color: isDark ? '#fff' : 'inherit' }}>{vectorStorage}</strong>
              </p>
              <p style={{ marginTop: '16px', fontWeight: 'bold', fontSize: '15px', color: isDark ? '#fff' : 'inherit' }}>
                {t('pages.knowledge.lightrag.dimension_conflict_options')}:
              </p>
              <ul style={{ 
                marginTop: '10px', 
                paddingLeft: '24px',
                fontSize: '14px',
                lineHeight: '1.8',
                color: isDark ? '#fff' : 'inherit'
              }}>
                <li style={{ marginBottom: '6px' }}>{t('pages.knowledge.lightrag.dimension_conflict_option1')}</li>
                <li>{t('pages.knowledge.lightrag.dimension_conflict_option2')}</li>
              </ul>
            </div>
          ),
          okText: t('pages.knowledge.lightrag.switch_workspace'),
          cancelText: t('common.cancel'),
          onOk: () => {
            // Show workspace selection
            showWorkspaceSelection(workspaces, newDimension);
          }
        });
      }
    } catch (error) {
      console.error('Failed to check dimension conflict:', error);
    }
  };

  // Show workspace selection modal
  const showWorkspaceSelection = (availableWorkspaces: Workspace[], newDimension: number) => {
    const workspaceOptions = availableWorkspaces.map(ws => ({
      label: `${ws.name} (${ws.is_valid ? t('common.valid') : t('common.invalid')})`,
      value: ws.name
    }));

    // Add option to create new workspace
    workspaceOptions.push({
      label: t('pages.knowledge.lightrag.create_new_workspace'),
      value: '__new__'
    });

    let selectedWorkspace = workspaceOptions[0]?.value;

    Modal.confirm({
      title: t('pages.knowledge.lightrag.select_workspace'),
      width: 550,
      className: isDark ? 'dark-theme-modal' : '',
      content: (
        <div style={{ fontSize: '15px', lineHeight: '1.6', color: isDark ? '#fff' : 'inherit' }}>
          <p style={{ fontSize: '15px', marginBottom: '16px', lineHeight: '1.6', color: isDark ? '#fff' : 'inherit' }}>
            {t('pages.knowledge.lightrag.select_workspace_message', { dimension: newDimension })}
          </p>
          <Select
            style={{ width: '100%', fontSize: '15px' }}
            size="large"
            defaultValue={selectedWorkspace}
            options={workspaceOptions}
            onChange={(value) => { selectedWorkspace = value; }}
            getPopupContainer={(trigger) => trigger.parentElement || document.body}
            className={isDark ? 'dark-select' : ''}
          />
        </div>
      ),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      onOk: async () => {
        if (selectedWorkspace === '__new__') {
          // Show custom modal for new workspace name
          showCreateWorkspaceModal(newDimension);
        } else {
          await switchToWorkspace(selectedWorkspace);
        }
      }
    });
  };

  const testParserConfig = async (
    engine: string,
    silent = false,
  ): Promise<{ ok: boolean; category?: string; technical?: string }> => {
    const provider = parserProviders.find(item => item.id === engine);
    const providerName = provider
      ? (provider.name.includes('.') ? t(`pages.knowledge.settings.${provider.name}`) : provider.name)
      : engine;
    try {
      const parserSettings = Object.fromEntries(
        (provider?.fields || []).map(field => [
          field.key,
          settings[field.key] ?? field.defaultValue ?? '',
        ])
      );
      parserSettings.SSL_VERIFY = settings.SSL_VERIFY ?? 'false';
      const response = await get_ipc_api().lightragApi.testParserConfig<{
        available?: boolean;
        category?: string;
        technical_detail?: string;
        message?: string;
        url?: string;
        status_code?: number;
      }>({ engine, settings: parserSettings });
      const probeResult = response.data || {};
      if (!response.success || probeResult.available === false) {
        const details = (response.error?.details || {}) as {
          category?: string;
          technical_detail?: string;
        };
        const category = probeResult.category || details.category || 'unknown';
        const technicalDetail = probeResult.technical_detail || details.technical_detail;
        if (!silent) modal.error({
          title: t('pages.knowledge.settings.parserProbe.failedTitle', { provider: providerName }),
          width: 520,
          okText: t('common.confirm'),
          content: (
            <div style={{ lineHeight: 1.65 }}>
              <div style={{ marginTop: 12 }}>
                <strong>{t('pages.knowledge.settings.parserProbe.reasonLabel')}</strong>
                <div>{t(`pages.knowledge.settings.parserProbe.errors.${category}.reason`)}</div>
              </div>
              <div style={{ marginTop: 12 }}>
                <strong>{t('pages.knowledge.settings.parserProbe.suggestionLabel')}</strong>
                <div>{t(`pages.knowledge.settings.parserProbe.errors.${category}.suggestion`)}</div>
              </div>
              {technicalDetail && (
                <details style={{ marginTop: 14, color: token.colorTextSecondary }}>
                  <summary style={{ cursor: 'pointer' }}>
                    {t('pages.knowledge.settings.parserProbe.technicalDetails')}
                  </summary>
                  <div style={{ marginTop: 8, padding: 10, borderRadius: 6, background: token.colorFillTertiary, wordBreak: 'break-word' }}>
                    {technicalDetail}
                  </div>
                </details>
              )}
            </div>
          ),
        });
        return { ok: false, category, technical: technicalDetail };
      }
      if (!silent) modal.success({
        title: t('pages.knowledge.settings.parserProbe.successTitle', { provider: providerName }),
        okText: t('common.confirm'),
        content: (
          <div style={{ lineHeight: 1.65 }}>
            <div>{t('pages.knowledge.settings.parserProbe.success')}</div>
            {response.data?.url && <div style={{ marginTop: 8, color: token.colorTextSecondary, wordBreak: 'break-all' }}>{response.data.url}</div>}
          </div>
        ),
      });
      return { ok: true };
    } catch (error: any) {
      if (!silent) modal.error({
        title: t('pages.knowledge.settings.parserProbe.failedTitle', { provider: providerName }),
        width: 520,
        okText: t('common.confirm'),
        content: (
          <div style={{ lineHeight: 1.65 }}>
            <div>{t('pages.knowledge.settings.parserProbe.errors.unknown.reason')}</div>
            <div style={{ marginTop: 8 }}>{t('pages.knowledge.settings.parserProbe.errors.unknown.suggestion')}</div>
            <details style={{ marginTop: 14, color: token.colorTextSecondary }}>
              <summary style={{ cursor: 'pointer' }}>{t('pages.knowledge.settings.parserProbe.technicalDetails')}</summary>
              <div style={{ marginTop: 8, wordBreak: 'break-word' }}>{error?.message || String(error)}</div>
            </details>
          </div>
        ),
      });
      return { ok: false, category: 'unknown', technical: error?.message || String(error) };
    }
  };

  const testModelServiceConfig = async (
    kind: 'llm' | 'embedding' | 'rerank',
    providerId: string,
    silent = false,
  ): Promise<{ ok: boolean; category?: string; technical?: string }> => {
    const providerList = kind === 'llm' ? llmProviders : kind === 'embedding' ? embeddingProviders : rerankingProviders;
    const provider = providerList.find(item => item.id === providerId);
    const providerName = provider
      ? (provider.name.includes('.') ? t(`pages.knowledge.settings.${provider.name}`) : provider.name)
      : providerId;
    try {
      const response = await get_ipc_api().lightragApi.testModelServiceConfig({ kind, settings });
      const probeResult = (response.data || {}) as { available?: boolean; category?: string; technical_detail?: string };
      if (!response.success || probeResult.available === false) {
        const details = (response.error?.details || {}) as { category?: string; technical_detail?: string };
        const category = probeResult.category || details.category || 'unknown';
        const technicalDetail = probeResult.technical_detail || details.technical_detail;
        if (!silent) modal.error({
          title: t('pages.knowledge.settings.serviceStatus.failedTitle', { provider: providerName }),
          width: 520,
          okText: t('common.confirm'),
          content: (
            <div style={{ lineHeight: 1.65 }}>
              <strong>{t('pages.knowledge.settings.parserProbe.reasonLabel')}</strong>
              <div>{t(`pages.knowledge.settings.parserProbe.errors.${category}.reason`)}</div>
              <div style={{ marginTop: 12 }}><strong>{t('pages.knowledge.settings.parserProbe.suggestionLabel')}</strong></div>
              <div>{t(`pages.knowledge.settings.parserProbe.errors.${category}.suggestion`)}</div>
              {technicalDetail && <><div style={{ marginTop: 12 }}><strong>{t('pages.knowledge.settings.parserProbe.technicalDetails')}</strong></div><div style={{ marginTop: 6, padding: 10, borderRadius: 6, background: token.colorFillTertiary, wordBreak: 'break-word' }}>{technicalDetail}</div></>}
            </div>
          ),
        });
        return { ok: false, category, technical: technicalDetail };
      }
      if (!silent) modal.success({
        title: t('pages.knowledge.settings.serviceStatus.successTitle', { provider: providerName }),
        okText: t('common.confirm'),
        content: t('pages.knowledge.settings.serviceStatus.available'),
      });
      return { ok: true };
    } catch (error: any) {
      if (!silent) modal.error({
        title: t('pages.knowledge.settings.serviceStatus.failedTitle', { provider: providerName }),
        content: t('pages.knowledge.settings.parserProbe.errors.unknown.suggestion'),
      });
      return { ok: false, category: 'unknown', technical: error?.message || String(error) };
    }
  };

  // Show create new workspace modal
  const showCreateWorkspaceModal = (newDimension: number) => {
    let workspaceName = '';
    
    Modal.confirm({
      title: t('pages.knowledge.lightrag.create_new_workspace'),
      width: 500,
      className: isDark ? 'dark-theme-modal' : '',
      content: (
        <div style={{ fontSize: '15px', lineHeight: '1.6', color: isDark ? '#fff' : 'inherit' }}>
          <p style={{ fontSize: '15px', marginBottom: '16px', lineHeight: '1.6', color: isDark ? '#fff' : 'inherit' }}>
            {t('pages.knowledge.lightrag.enter_workspace_name')}
          </p>
          <Input
            size="large"
            placeholder={t('pages.knowledge.lightrag.workspace_name_placeholder')}
            defaultValue=""
            onChange={(e) => { workspaceName = e.target.value; }}
            style={{ fontSize: '15px' }}
            className={isDark ? 'dark-input' : ''}
          />
          <p style={{ 
            marginTop: '12px', 
            fontSize: '13px', 
            color: isDark ? 'rgba(255, 255, 255, 0.65)' : '#999',
            lineHeight: '1.5'
          }}>
            {t('pages.knowledge.lightrag.workspace_name_hint', { dimension: newDimension })}
          </p>
        </div>
      ),
      okText: t('common.create'),
      cancelText: t('common.cancel'),
      onOk: async () => {
        if (workspaceName && workspaceName.trim()) {
          await switchToWorkspace(workspaceName.trim());
        } else {
          message.error(t('pages.knowledge.lightrag.workspace_name_required'));
          return Promise.reject();
        }
      }
    });
  };

  // Switch to a different workspace
  const switchToWorkspace = async (workspaceName: string) => {
    try {
      setLoading(true);
      
      // Update both WORKSPACE and WORKING_DIR settings
      // Ensure we get the rag_storage directory path
      let baseWorkingDir = settings['WORKING_DIR'] || '';
      
      // If WORKING_DIR contains 'rag_storage', extract up to and including 'rag_storage'
      if (baseWorkingDir.includes('rag_storage')) {
        const parts = baseWorkingDir.split('/');
        const ragStorageIndex = parts.findIndex(p => p === 'rag_storage');
        if (ragStorageIndex >= 0) {
          baseWorkingDir = parts.slice(0, ragStorageIndex + 1).join('/');
        } else {
          // Fallback: remove last component
          baseWorkingDir = baseWorkingDir.replace(/\/[^/]+$/, '');
        }
      } else {
        // Fallback: remove last component
        baseWorkingDir = baseWorkingDir.replace(/\/[^/]+$/, '');
      }
      
      // IMPORTANT: WORKING_DIR should only point to rag_storage directory
      // LightRAG will append workspace name automatically: working_dir/workspace
      // So we should NOT include workspace name in WORKING_DIR
      const newWorkingDir = baseWorkingDir;  // Fixed: Don't append workspace name
      
      console.log('[Workspace Switch] Switching to workspace:', workspaceName);
      console.log('[Workspace Switch] Original WORKING_DIR:', settings['WORKING_DIR']);
      console.log('[Workspace Switch] Base working dir:', baseWorkingDir);
      console.log('[Workspace Switch] New working dir (rag_storage only):', newWorkingDir);
      console.log('[Workspace Switch] LightRAG will create:', `${newWorkingDir}/${workspaceName}`);
      console.log('[Workspace Switch] Pending settings:', pendingSettingsRef.current);
      
      // Build new settings object
      const newSettings = {
        ...settings,
        'WORKSPACE': workspaceName,
        'WORKING_DIR': newWorkingDir  // Only rag_storage path, no workspace name
      };
      
      // Apply pending settings if any
      if (Object.keys(pendingSettingsRef.current).length > 0) {
        console.log('[Workspace Switch] Applying pending settings:', pendingSettingsRef.current);
        Object.assign(newSettings, pendingSettingsRef.current);
        // Clear pending settings
        pendingSettingsRef.current = {};
      }
      
      console.log('[Workspace Switch] Saving settings:', newSettings);
      
      // Save all settings to backend
      const response = await get_ipc_api().lightragApi.saveSettings(newSettings);
      
      if (!response.success) {
        throw new Error(response.error?.message || 'Failed to save settings');
      }
      
      console.log('[Workspace Switch] Settings saved successfully');
      
      // Update local state
      setSettings(newSettings);
      // Keep the header, document list and retrieval tab in sync with the
      // workspace selected here. Previously only the env file changed, so
      // the rest of the page continued displaying and querying the old one.
      setActiveWorkspace(workspaceName);
      
      // Restart LightRAG server to apply new workspace settings
      console.log('[Workspace Switch] Restarting LightRAG server...');
      try {
        const restartResponse = await get_ipc_api().lightragApi.restartServer({});
        if (restartResponse.success) {
          console.log('[Workspace Switch] ✅ LightRAG server restarted successfully');
        } else {
          throw new Error(restartResponse.error?.message || 'LightRAG server restart failed');
        }
      } catch (restartError) {
        console.error('[Workspace Switch] ❌ Error restarting server:', restartError);
        throw restartError;
      }
      
      // Reload workspaces list
      await loadWorkspaces();
      
      // Close all open modals after all operations complete
      setTimeout(() => {
        Modal.destroyAll();
      }, 100);
      
      message.success(t('pages.knowledge.lightrag.workspace_switched', { name: workspaceName }));
      
      // Reset dimension check state
      lastCheckedDimRef.current = null;
      initialLoadRef.current = true;
      
    } catch (error) {
      console.error('[Workspace Switch] Failed to switch workspace:', error);
      message.error(t('pages.knowledge.lightrag.workspace_switch_failed'));
    } finally {
      setLoading(false);
    }
  };

  const readSaved = () => {
    const raw = sessionStorage.getItem(settingsScrollKey);
    const num = raw ? Number(raw) : 0;
    return Number.isFinite(num) ? num : 0;
  };

  const saveScroll = () => {
    const tabsContent = document.querySelector('.lightrag-settings-tabs .ant-tabs-content-holder') as HTMLElement | null;
    if (tabsContent) {
      const v = tabsContent.scrollTop;
      const saved = readSaved();
      // 避免在“刚返回页面/刚挂载”的 0 把已有的非 0 保存覆盖掉
      if (restoringRef.current && v === 0 && saved > 0) return;
      savedScrollPosition.current = v;
      if (v > 0 || saved === 0) {
        sessionStorage.setItem(settingsScrollKey, String(savedScrollPosition.current));
      }
    }
  };

  const restoreScrollWithRetry = (attempts = 0) => {
    const tabsContent = document.querySelector('.lightrag-settings-tabs .ant-tabs-content-holder') as HTMLElement | null;
    const saved = readSaved();
    if (saved <= 0) return;

    restoringRef.current = true;

    // 外层 page 切回时，content-holder 可能还没挂载出来，必须重试
    if (!tabsContent) {
      if (attempts < 80) {
        setTimeout(() => restoreScrollWithRetry(attempts + 1), 50);
      }
      return;
    }

    tabsContent.scrollTop = saved;
    if (tabsContent.scrollTop !== saved && attempts < 80) {
      setTimeout(() => restoreScrollWithRetry(attempts + 1), 50);
      return;
    }

    restoringRef.current = false;
  };

  useEffect(() => {
    const activeTab = sessionStorage.getItem(`${storagePrefix}:active`);
    if (activeTab === 'settings') {
      requestAnimationFrame(() => restoreScrollWithRetry());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    let currentEl: HTMLElement | null = null;
    const onScroll = () => {
      if (currentEl) {
        const v = currentEl.scrollTop;
        const saved = readSaved();
        if (restoringRef.current && v === 0 && saved > 0) return;
        if (v > 0 || saved === 0) {
          sessionStorage.setItem(settingsScrollKey, String(v));
        }
      }
    };

    const bindWithRetry = (attempts = 0) => {
      const el = document.querySelector('.lightrag-settings-tabs .ant-tabs-content-holder') as HTMLElement | null;
      if (el) {
        if (currentEl !== el) {
          if (currentEl) currentEl.removeEventListener('scroll', onScroll);
          currentEl = el;
          currentEl.addEventListener('scroll', onScroll, { passive: true });
        }
        return;
      }
      if (attempts < 80) {
        setTimeout(() => bindWithRetry(attempts + 1), 50);
      }
    };

    bindWithRetry();

    return () => {
      // 卸载时也保存一次，避免外层 page 切换时没来得及触发事件
      saveScroll();
      if (currentEl) {
        currentEl.removeEventListener('scroll', onScroll);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onActivate = (e: Event) => {
      const ce = e as CustomEvent<{ key?: string }>;
      if (ce.detail?.key === 'settings') {
        requestAnimationFrame(() => restoreScrollWithRetry());
      }
    };

    const onDeactivate = (e: Event) => {
      const ce = e as CustomEvent<{ key?: string }>;
      if (ce.detail?.key === 'settings') {
        saveScroll();
      }
    };

    window.addEventListener('lightrag-tab-activate', onActivate);
    window.addEventListener('lightrag-tab-deactivate', onDeactivate);
    return () => {
      window.removeEventListener('lightrag-tab-activate', onActivate);
      window.removeEventListener('lightrag-tab-deactivate', onDeactivate);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  
  // Get current region for provider filtering
  const isCN = useIsCN();
  const currentRegion = isCN ? 'cn' : 'intl';
  
  // Use ref to always get the latest region value in async callbacks
  const regionRef = useRef(currentRegion);
  useEffect(() => {
    regionRef.current = currentRegion;
  }, [currentRegion]);
  
  const [llmProviders, setLlmProviders] = useState<ProviderConfig[]>([]);
  const [embeddingProviders, setEmbeddingProviders] = useState<ProviderConfig[]>([]);
  const [rerankingProviders, setRerankingProviders] = useState<ProviderConfig[]>([]);
  const [parserProviders, setParserProviders] = useState<ProviderConfig[]>(PARSER_PROVIDERS);
  
  const { t, ready } = useTranslation();
  const { token } = theme.useToken();
  const { theme: currentTheme } = useTheme();
  const isDark = currentTheme === 'dark' || (currentTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  const { message, modal } = App.useApp();

  // ── Provider sync ────────────────────────────────────────────────────────
  // Bump signal from Settings page (via WebSocket push → eventBus → Zustand).
  // When a provider is saved in Settings, KnowledgePortedPage bumps the store
  // version and this useEffect re-loads settings + provider list automatically.
  const { providerVersion } = useLightRAGSettingsStore();

  // Reload on provider version change (skip on initial mount — the other useEffect handles it)
  useEffect(() => {
    if (providerVersion === 0) return; // skip initial mount
    const reload = async () => {
      await Promise.all([loadSettings(), loadProviders()]);
    };
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [providerVersion]); // intentionally omitting loadSettings/loadProviders to avoid stale closure

  useEffect(() => {
    const initializeSettings = async () => {
      await loadSettings();
      await loadProviders();
    };
    initializeSettings();
  }, [isCN]);

  // Auto-check dimension conflict when user manually changes dimension
  useEffect(() => {
    const checkDimensionChange = async () => {
      const embeddingDim = settings['EMBEDDING_DIM'];
      if (!embeddingDim) return;
      
      const dimension = parseInt(embeddingDim);
      if (isNaN(dimension) || dimension <= 0) return;
      
      console.log('[DimensionCheck] useEffect triggered:', {
        dimension,
        initialLoad: initialLoadRef.current,
        lastChecked: lastCheckedDimRef.current,
        workspace: settings['WORKING_DIR']
      });
      
      // Skip initial load
      if (initialLoadRef.current) {
        console.log('[DimensionCheck] Skipping initial load, setting initialLoadRef to false');
        initialLoadRef.current = false;
        lastCheckedDimRef.current = dimension;
        return;
      }
      
      // Skip if dimension hasn't changed
      if (lastCheckedDimRef.current === dimension) {
        console.log('[DimensionCheck] Dimension unchanged, skipping check');
        return;
      }
      
      // Update last checked dimension
      lastCheckedDimRef.current = dimension;
      
      console.log('[DimensionCheck] Triggering conflict check from useEffect for dimension:', dimension);
      // Check for conflict
      await checkDimensionConflict(dimension);
    };
    
    // Only check if settings are loaded
    if (Object.keys(settings).length > 0) {
      checkDimensionChange();
    }
  }, [settings['EMBEDDING_DIM'], settings['WORKING_DIR']]);

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
                     const newDim = meta.dimensions.toString();
                     updates['EMBEDDING_DIM'] = newDim;
                     hasChanges = true;
                     
                     console.log('[DimensionCheck] Auto-sync detected dimension change:', {
                       oldDim: prev['EMBEDDING_DIM'],
                       newDim: newDim,
                       model: currentModel,
                       initialLoad: initialLoadRef.current,
                       lastChecked: lastCheckedDimRef.current
                     });
                     
                     // Don't trigger dimension conflict check here
                     // It will be triggered by createSettingChangeHandler when provider changes
                     console.log('[DimensionCheck] Auto-sync dimension change, will be checked by provider change handler');
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
        const loadedSettings = response.data as Record<string, string>;
        
        // Auto-set RERANK_BY_DEFAULT based on RERANK_BINDING
        if (!loadedSettings['RERANK_BY_DEFAULT']) {
          const rerankBinding = loadedSettings['RERANK_BINDING'];
          loadedSettings['RERANK_BY_DEFAULT'] = (rerankBinding && rerankBinding !== 'null') ? 'true' : 'false';
        }

        // Derive the UI-only parsing engine selection from LIGHTRAG_PARSER
        const parserValue = (loadedSettings['LIGHTRAG_PARSER'] || '').toLowerCase();
        if (parserValue.includes('mineru')) {
          loadedSettings['PARSING_ENGINE'] = 'mineru';
        } else if (parserValue.includes('docling')) {
          loadedSettings['PARSING_ENGINE'] = 'docling';
        } else {
          loadedSettings['PARSING_ENGINE'] = 'native';
        }
        loadedSettings['PARSER_IMAGE_ANALYSIS'] = parserImageAnalysisEnabled(parserValue) ? 'true' : 'false';
        
        setSettings(loadedSettings);
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
        const rawLlm = (response.data.llm_providers || []) as RawProvider[];
        const rawEmbed = (response.data.embedding_providers || []) as RawProvider[];
        const rawRerank = (response.data.rerank_providers || []) as RawProvider[];

        const builtLlm = rawLlm.map(p => buildProviderConfig(p, 'llm'));
        const builtEmbed = rawEmbed.map(p => buildProviderConfig(p, 'embedding'));
        const builtRerank = rawRerank.map(p => buildProviderConfig(p, 'rerank'));

        setLlmProviders(getProvidersByRegion(builtLlm, regionRef.current as 'cn' | 'intl'));
        setEmbeddingProviders(getProvidersByRegion(builtEmbed, regionRef.current as 'cn' | 'intl'));
        setRerankingProviders(getProvidersByRegion(builtRerank, regionRef.current as 'cn' | 'intl'));
      }
    } catch (e) {
      console.error('Failed to load system providers:', e);
    }

    // Document parsing engines are defined and served by the backend
    // (knowledge/lightrag_parser_config.py); fall back to the static list
    // when the handler is unavailable (older backend).
    try {
      const parserResponse = await get_ipc_api().lightragApi.getParserEngines<{
        engines?: ParserEngineDefinition[];
        current?: Record<string, string>;
        engine?: string;
      }>();
      if (parserResponse.success && parserResponse.data) {
        const parserData = parserResponse.data;
        setParserProviders(buildParserProviders(parserData.engines));
        if (parserData.current) {
          // Older running backends can omit newly introduced parser keys or
          // serialize them as null. Do not let that partial response erase a
          // value already loaded from lightrag.getSettings (notably parser
          // API keys) when both requests finish concurrently.
          const current = Object.fromEntries(
            Object.entries(parserData.current).filter(([, value]) => value !== null && value !== undefined)
          ) as Record<string, string>;
          setSettings(prev => ({
            ...prev,
            ...current,
            // The engine selection is UI-only (never persisted); it is
            // derived from LIGHTRAG_PARSER on the backend.
            PARSING_ENGINE: parserData.engine || prev.PARSING_ENGINE || 'native'
          }));
        }
      }
    } catch (e) {
      console.error('Failed to load parser engines:', e);
    }
  };

  const updateSetting = (key: string, value: string) => {
    setSettings(prev => {
      const newSettings = { ...prev, [key]: value };

      if (key === 'PARSER_IMAGE_ANALYSIS') {
        newSettings.LIGHTRAG_PARSER = setParserImageAnalysis(
          prev.LIGHTRAG_PARSER || '',
          value === 'true'
        );
      }
      
      // Rerank linkage logic
      if (key === 'RERANK_BINDING') {
        if (value && value !== 'null') {
          // Selecting a provider -> Enable rerank by default
          newSettings['RERANK_BY_DEFAULT'] = 'true';
        } else {
          // Deselecting provider -> Disable rerank by default
          newSettings['RERANK_BY_DEFAULT'] = 'false';
        }
      } else if (key === 'RERANK_BY_DEFAULT') {
        if (value === 'false') {
          // Disabling default rerank -> Clear provider
          newSettings['RERANK_BINDING'] = 'null';
        }
      } else if (key === 'MINERU_API_MODE') {
        if (value === 'official') {
          newSettings['MINERU_OFFICIAL_ENDPOINT'] ||= 'https://mineru.net';
        }
      }
      
      // Check dimension conflict when EMBEDDING_BINDING or EMBEDDING_MODEL changes
      if (key === 'EMBEDDING_BINDING' || key === 'EMBEDDING_MODEL') {
        // Get the new dimension from provider metadata
        const embeddingProvider = embeddingProviders.find(p => p.id === (key === 'EMBEDDING_BINDING' ? value : newSettings['EMBEDDING_BINDING']));
        if (embeddingProvider && embeddingProvider.modelMetadata) {
          const modelId = key === 'EMBEDDING_MODEL' ? value : newSettings['EMBEDDING_MODEL'];
          const modelMeta = embeddingProvider.modelMetadata[modelId];
          if (modelMeta && modelMeta.dimensions) {
            const newDim = modelMeta.dimensions;
            const currentDim = parseInt(prev['EMBEDDING_DIM'] || '0');
            
            // Only check if dimension actually changed and not initial load
            if (!initialLoadRef.current && newDim !== currentDim && lastCheckedDimRef.current !== newDim) {
              lastCheckedDimRef.current = newDim;
              // Store the new settings to apply after workspace switch
              const pendingChanges = { ...newSettings, 'EMBEDDING_DIM': newDim.toString() };
              // Use setTimeout to avoid blocking the state update
              setTimeout(() => {
                checkDimensionConflict(newDim, pendingChanges);
              }, 100);
            }
          }
        }
      }
      
      // Check dimension conflict when EMBEDDING_DIM changes directly
      if (key === 'EMBEDDING_DIM') {
        const newDim = parseInt(value);
        if (!isNaN(newDim) && newDim > 0) {
          // Skip initial load
          if (!initialLoadRef.current && lastCheckedDimRef.current !== newDim) {
            lastCheckedDimRef.current = newDim;
            // Use setTimeout to avoid blocking the state update
            setTimeout(() => {
              checkDimensionConflict(newDim, newSettings);
            }, 100);
          }
        }
      }
      
      return newSettings;
    });
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

  const loadWorkspaces = async () => {
    try {
      setWorkspaceLoading(true);
      const response = await get_ipc_api().lightragApi.getWorkspaces<{ workspaces: Workspace[]; current: string }>();
      if (response.success && response.data) {
        setWorkspaces(response.data.workspaces || []);
      }
    } catch (e: any) {
      console.error('Failed to load workspaces:', e);
      message.error(t('pages.knowledge.settings.workspace.loadError'));
    } finally {
      setWorkspaceLoading(false);
    }
  };

  const loadStartupStatus = async () => {
    try {
      const response = await get_ipc_api().lightragApi.getStartupStatus<StartupStatus>();
      if (response.success && response.data) {
        console.log('[SettingsTab] Startup status received:', response.data);
        setStartupStatus(response.data);
      }
    } catch (e) {
      console.error('Failed to load startup status:', e);
    }
  };

  const handleDeleteWorkspace = async (workspaceName: string) => {
    modal.confirm({
      title: t('pages.knowledge.settings.workspace.deleteTitle'),
      content: t('pages.knowledge.settings.workspace.deleteConfirm', { name: workspaceName }),
      okText: t('common.delete'),
      okButtonProps: { danger: true },
      cancelText: t('common.cancel'),
      onOk: async () => {
        try {
          const response = await get_ipc_api().lightragApi.deleteWorkspace<any>({
            workspace_name: workspaceName
          });

          if (response.success) {
            message.success(t('pages.knowledge.settings.workspace.deleteSuccess'));
            await loadWorkspaces();
            // If deleted workspace was selected, clear the field
            if (settings['WORKSPACE'] === workspaceName) {
              updateSetting('WORKSPACE', '');
            }
          } else {
            throw new Error(response.error?.message || 'Unknown error');
          }
        } catch (e: any) {
          message.error(t('pages.knowledge.settings.workspace.deleteError') + ': ' + (e.message || String(e)));
        }
      }
    });
  };

  useEffect(() => {
    loadWorkspaces();
    loadStartupStatus();
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      loadStartupStatus();
    }, 5000);

    return () => window.clearInterval(timer);
  }, []);

  const handleSave = async () => {
    try {
      setLoading(true);
      
      // Check for embedding dimension conflict before saving
      const embeddingDim = settings['EMBEDDING_DIM'];
      if (embeddingDim) {
        const newDim = parseInt(embeddingDim);
        if (!isNaN(newDim) && newDim > 0) {
          const currentWorkspace = settings['WORKSPACE'] || 'default';
          const api = get_ipc_api();
          
          try {
            const result = await api.executeRequest<{
              hasConflict: boolean;
              currentDimension: number | null;
              newDimension: number;
              vectorStorage: string;
              workspaceName: string;
              workspaces: Workspace[];
            }>('lightrag.checkEmbeddingDimension', {
              newDimension: newDim,
              workspaceName: currentWorkspace
            });
            
            if (result.success && result.data?.hasConflict) {
              // Has conflict, show warning and ask user to switch workspace
              setLoading(false);
              await checkDimensionConflict(newDim, settings);
              return; // Don't save yet, wait for user to switch workspace
            }
          } catch (error) {
            console.error('Failed to check dimension conflict:', error);
            // Continue with save even if check fails
          }
        }
      }
      
      // Strip the UI-only engine selection from the payload — the engine is
      // persisted through LIGHTRAG_PARSER itself and must never be written
      // to lightrag.env as a fake variable.
      const savePayload = { ...settings };
      delete savePayload.PARSING_ENGINE;
      delete savePayload.PARSER_IMAGE_ANALYSIS;

      const response = await get_ipc_api().lightragApi.saveSettings(savePayload);
      if (response.success) {
        message.success(t('pages.knowledge.settings.saveSuccess'));
        
        // Prompt user to restart server
        modal.confirm({
          title: t('pages.knowledge.settings.restartPrompt'),
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
      const response = await get_ipc_api().lightragApi.restartServer({});
      hideLoading();
      
      if (response.success) {
        message.success(t('pages.knowledge.settings.restartSuccess'));
        await loadStartupStatus();
      } else {
        throw new Error(response.error?.message || 'Unknown error');
      }
    } catch (e: any) {
      message.error(t('pages.knowledge.settings.restartError') + ': ' + (e.message || String(e)));
      await loadStartupStatus();
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
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}>
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
        return (
          <div key={field.key} style={{ marginBottom: 8 }}>
            {label}
            <Input
              value={value}
              placeholder={placeholder}
              onChange={(e) => updateSetting(field.key, e.target.value)}
              style={commonStyle}
              disabled={disabled}
            />
          </div>
        );

      case 'password':
        return (
          <div key={field.key} style={{ marginBottom: 8 }}>
            {label}
            <Input.Password
              value={value}
              placeholder={placeholder}
              onChange={(e) => updateSetting(field.key, e.target.value)}
              style={commonStyle}
              disabled={disabled}
              visibilityToggle={!disabled}
            />
          </div>
        );

      case 'number':
        return (
          <div key={field.key} style={{ marginBottom: 8 }}>
            {label}
            <InputNumber
              value={value ? Number(value) : undefined}
              placeholder={placeholder}
              onChange={(val) => updateSetting(field.key, val?.toString() || '')}
              style={commonStyle}
              disabled={disabled}
              min={0}
              step={field.key.includes('TEMPERATURE') || field.key.includes('SCORE') ? 0.1 : 1}
              precision={field.key.includes('TEMPERATURE') || field.key.includes('THRESHOLD') || field.key.includes('SCORE') ? 2 : 0}
            />
          </div>
        );

      case 'textarea':
        return (
          <div key={field.key} style={{ marginBottom: 8 }}>
            {label}
            <Input.TextArea
              value={value}
              placeholder={placeholder}
              onChange={(e) => updateSetting(field.key, e.target.value)}
              rows={2}
              style={commonStyle}
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
          <div key={field.key} style={{ marginBottom: 8 }}>
            {label}
            <Select
              value={value || undefined}
              placeholder={placeholder}
              onChange={(val) => updateSetting(field.key, val)}
              style={commonStyle}
              options={options}
              disabled={field.disabled}
            />
          </div>
        );

      case 'boolean':
        return (
          <div key={field.key} style={{ marginBottom: 8, minHeight: 30, display: 'flex', alignItems: 'center' }}>
            <Switch
              checked={value === 'true' || value === 'True'}
              onChange={(checked) => updateSetting(field.key, checked ? 'true' : 'false')}
              disabled={disabled}
            />
          </div>
        );

      case 'directory':
        return (
          <div key={field.key} style={{ marginBottom: 8 }}>
            {label}
            <Input
              value={value}
              placeholder={placeholder}
              onChange={(e) => updateSetting(field.key, e.target.value)}
              style={commonStyle}
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
  const renderFieldsBySection = (fields: FieldConfig[], isBasicTab: boolean = false) => {
    const sections: Record<string, FieldConfig[]> = {};
    
    fields.forEach(field => {
      const section = field.section || 'default';
      if (!sections[section]) {
        sections[section] = [];
      }
      sections[section].push(field);
    });

    return (
      <div style={{ padding: '8px 0' }}>
        {/* Workspace Module - Only show in basic tab */}
        {isBasicTab && (
          <div style={{ marginBottom: 16 }}>
            <h3 style={{
              marginBottom: 8,
              fontSize: 14,
              fontWeight: 600,
              color: token.colorText,
              borderBottom: `1px solid ${token.colorBorder}`,
              paddingBottom: 4,
              display: 'flex',
              alignItems: 'center',
              gap: 8
            }}>
              <BlockOutlined style={{ fontSize: 14, color: token.colorPrimary }} />
              {t('pages.knowledge.settings.workspace.tooltip')}
            </h3>
            <WorkspaceSelector
              workspaces={workspaces}
              currentWorkspace={activeWorkspace || (() => {
                const val = settings['WORKSPACE'];
                if (Array.isArray(val)) {
                  return val[0] || 'default';
                }
                return val || 'default';
              })()}
              loading={workspaceLoading || loading}
              onSwitch={async (workspaceName: string) => {
                await switchToWorkspace(workspaceName);
              }}
              onCreate={async (workspaceName: string) => {
                await switchToWorkspace(workspaceName);
              }}
              onDelete={handleDeleteWorkspace}
              onRefresh={loadWorkspaces}
              token={token}
              t={t}
            />
          </div>
        )}

        {Object.entries(sections).map(([sectionName, sectionFields]) => (
          <div key={sectionName} style={{ marginBottom: 12 }}>
            {sectionName !== 'default' && (
              <h3 style={{
                marginBottom: 8,
                fontSize: 14,
                fontWeight: 600,
                color: token.colorText,
                borderBottom: `1px solid ${token.colorBorder}`,
                paddingBottom: 4
              }}>
                {t(`pages.knowledge.settings.sections.${sectionName}`) || sectionName.charAt(0).toUpperCase() + sectionName.slice(1)}
              </h3>
            )}
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
              gap: 12,
              maxWidth: '100%'
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
      parsing: <FileTextOutlined />,
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
      // Parser engines own separate env keys (MINERU_* and DOCLING_*).
      // Switching the visible engine must preserve both configurations so a
      // user can compare/test them and switch back without re-entering URLs
      // or secrets. Only the UI selection and active routing rule change.
      if (key === bindingKey && bindingKey === 'PARSING_ENGINE') {
        const newProvider = providers.find(provider => provider.id === value);
        setSettings(prev => {
          const next: Record<string, string> = { ...prev, [bindingKey]: value };
          for (const field of newProvider?.fields || []) {
            if (field.key === 'LIGHTRAG_PARSER') {
              next[field.key] = field.defaultValue || '';
            } else if (!(field.key in next) && field.defaultValue !== undefined) {
              next[field.key] = field.defaultValue;
            }
          }
          next.PARSER_IMAGE_ANALYSIS = 'false';
          return next;
        });
        return;
      }

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
          systemFlagKey = '_SYSTEM_RERANK_KEY_SOURCE';
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
              const newDimension = parseInt(meta.dimensions.toString());
              const pendingSettings: Record<string, string> = {
                'EMBEDDING_BINDING': value,
                'EMBEDDING_MODEL': defaultModel,
                'EMBEDDING_DIM': meta.dimensions.toString()
              };
              if (meta.max_tokens) {
                pendingSettings['EMBEDDING_TOKEN_LIMIT'] = meta.max_tokens.toString();
              }
              updateSetting('EMBEDDING_DIM', meta.dimensions.toString());
              // Check dimension conflict with pending settings
              checkDimensionConflict(newDimension, pendingSettings);
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
          
          console.log('[Model Change] Embedding model changed to:', value);
          console.log('[Model Change] Current provider ID:', currentProviderId);
          console.log('[Model Change] Provider found:', provider?.name);
          console.log('[Model Change] Has modelMetadata:', !!provider?.modelMetadata);
          console.log('[Model Change] Metadata for this model:', provider?.modelMetadata?.[value]);
          
          if (provider && provider.modelMetadata && provider.modelMetadata[value]) {
              const meta = provider.modelMetadata[value];
              console.log('[Model Change] ✅ Found metadata:', meta);
              if (meta.dimensions) {
                  const newDimension = parseInt(meta.dimensions.toString());
                  const pendingSettings: Record<string, string> = {
                    'EMBEDDING_MODEL': value,
                    'EMBEDDING_DIM': meta.dimensions.toString()
                  };
                  if (meta.max_tokens) {
                    pendingSettings['EMBEDDING_TOKEN_LIMIT'] = meta.max_tokens.toString();
                  }
                  console.log('[Model Change] ✅ Updating EMBEDDING_DIM to:', meta.dimensions);
                  updateSetting('EMBEDDING_DIM', meta.dimensions.toString());
                  // Check dimension conflict with pending settings
                  checkDimensionConflict(newDimension, pendingSettings);
              } else {
                  console.warn('[Model Change] ⚠️ No dimensions in metadata');
              }
              if (meta.max_tokens) {
                  console.log('[Model Change] ✅ Updating EMBEDDING_TOKEN_LIMIT to:', meta.max_tokens);
                  updateSetting('EMBEDDING_TOKEN_LIMIT', meta.max_tokens.toString());
              }
          } else {
              console.warn('[Model Change] ⚠️ No metadata found for model:', value);
              console.warn('[Model Change] Available metadata keys:', Object.keys(provider?.modelMetadata || {}));
          }
      }
      
      // Handle direct EMBEDDING_DIM change
      if (key === 'EMBEDDING_DIM' && value) {
          const newDimension = parseInt(value);
          if (!isNaN(newDimension) && newDimension > 0) {
              checkDimensionConflict(newDimension);
          }
      }
    };
  };

  // Render provider-based configuration tabs
  const renderProviderTab = (tabKey: string) => {
    switch (tabKey) {
      case 'parsing':
        return (
          <ProviderSelector
            bindingKey="PARSING_ENGINE"
            providers={parserProviders}
            settings={settings}
            onSettingChange={createSettingChangeHandler("PARSING_ENGINE", parserProviders)}
            onTestProvider={settings.PARSING_ENGINE === 'mineru' || settings.PARSING_ENGINE === 'docling' ? testParserConfig : undefined}
          />
        );
      case 'reranking':
        return (
          <ProviderSelector
            bindingKey="RERANK_BINDING"
            providers={rerankingProviders}
            commonFields={RERANKING_COMMON_FIELDS}
            settings={settings}
            onSettingChange={createSettingChangeHandler("RERANK_BINDING", rerankingProviders)}
            onTestProvider={(providerId, silent) => testModelServiceConfig('rerank', providerId, silent)}
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
            onTestProvider={(providerId, silent) => testModelServiceConfig('llm', providerId, silent)}
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
            onTestProvider={(providerId, silent) => testModelServiceConfig('embedding', providerId, silent)}
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
          <div style={{ padding: '8px 0' }}>
            <div style={{ marginBottom: 12 }}>
              <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, color: token.colorText }}>
                {t('pages.knowledge.settings.provider.kvStorage')}
              </h3>
              <ProviderSelector
                bindingKey="LIGHTRAG_KV_STORAGE"
                providers={STORAGE_KV_PROVIDERS}
                settings={settings}
                onSettingChange={updateSetting}
              />
            </div>
            <div style={{ marginBottom: 12 }}>
              <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, color: token.colorText }}>
                {t('pages.knowledge.settings.provider.vectorStorage')}
              </h3>
              <ProviderSelector
                bindingKey="LIGHTRAG_VECTOR_STORAGE"
                providers={STORAGE_VECTOR_PROVIDERS}
                settings={settings}
                onSettingChange={updateSetting}
              />
            </div>
            <div style={{ marginBottom: 12 }}>
              <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, color: token.colorText }}>
                {t('pages.knowledge.settings.provider.graphStorage')}
              </h3>
              <ProviderSelector
                bindingKey="LIGHTRAG_GRAPH_STORAGE"
                providers={STORAGE_GRAPH_PROVIDERS}
                settings={settings}
                onSettingChange={updateSetting}
              />
            </div>
            <div style={{ marginBottom: 12 }}>
              <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, color: token.colorText }}>
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
                  marginTop: 12,
                  borderColor: token.colorBorder
                }}
              >
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                  gap: 12,
                  maxWidth: '100%'
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
      : renderFieldsBySection(fields, tabKey === 'basic')
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
        padding: '12px 16px 0 16px',
        background: token.colorBgLayout
      }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '8px 0',
          marginBottom: 8,
          gap: 12,
          flexWrap: 'wrap'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flex: '1 1 auto', minWidth: 0 }}>
            <div style={{ 
              width: 36, 
              height: 36, 
              borderRadius: 8, 
              background: `linear-gradient(135deg, ${token.colorPrimary} 0%, ${token.colorPrimaryHover} 100%)`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0
            }}>
              <DatabaseOutlined style={{ fontSize: 18, color: '#ffffff' }} />
            </div>
            <div style={{ minWidth: 0, flex: 1 }}>
              <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: token.colorText, lineHeight: 1.2, whiteSpace: 'nowrap' }}>
                {t('pages.knowledge.settings.title')}
              </h3>
              <p style={{ margin: '4px 0 0 0', fontSize: 13, color: token.colorTextSecondary, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {t('pages.knowledge.settings.subtitle')}
              </p>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '12px', flexShrink: 0, flexWrap: 'wrap' }}>
            <Tooltip title={t('pages.knowledge.help.tooltip')}>
              <button 
                className="ec-btn ec-btn-default" 
                onClick={() => setHelpDialogVisible(true)}
                style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
              >
                <QuestionCircleOutlined /> {t('pages.knowledge.help.button')}
              </button>
            </Tooltip>
            <button className="ec-btn ec-btn-primary" onClick={handleSave} disabled={loading}>
              <CheckOutlined /> {loading ? t('pages.knowledge.settings.saving') : t('pages.knowledge.settings.saveSettings')}
            </button>
          </div>
        </div>
      </div>

      {/* Tabs Container with Fixed Header */}
      <div style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        padding: '0 16px 12px 16px',
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
          flex: 1,
          minHeight: 0
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

      {/* Help Dialog */}
      <HelpDialog 
        visible={helpDialogVisible}
        onClose={() => setHelpDialogVisible(false)}
      />

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
          padding: 0 16px 8px 16px;
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
