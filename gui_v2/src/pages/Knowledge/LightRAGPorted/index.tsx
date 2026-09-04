import React, { useRef, useState, useEffect } from 'react';
import { theme, Modal } from 'antd';
import { ExclamationCircleOutlined } from '@ant-design/icons';
import { useEffectOnActive } from 'keepalive-for-react';
import { useTranslation } from 'react-i18next';
import Tabs, { TabKey } from './Tabs';
import SettingsTab from './SettingsTab';
import DocumentsTab from './DocumentsTab';
import RetrievalTab from './RetrievalTab';
import GraphTab from './GraphTab';
import { validateLightRAGConfig } from './configValidator';
import { get_ipc_api } from '@/services/ipc_api';
import { useLightRAGSettingsStore } from '@/stores/ragStore';
import { eventBus } from '@/utils/eventBus';

const KnowledgePortedPage: React.FC = () => {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const backgroundColor = token.colorBgLayout;
  const containerRef = useRef<HTMLDivElement>(null);
  const savedScrollPositionRef = useRef<number>(0);
  const [activeTab, setActiveTab] = useState<TabKey>('documents');
  const hasValidatedRef = useRef<boolean>(false);
  const { bumpProviderVersion } = useLightRAGSettingsStore();

  // Listen for backend provider-update push and bump store version
  // so SettingsTab's useEffect re-loads settings + providers automatically.
  useEffect(() => {
    const handler = () => bumpProviderVersion();
    eventBus.on('localws:lightrag.providersUpdated', handler);
    return () => { eventBus.off('localws:lightrag.providersUpdated', handler); };
  }, [bumpProviderVersion]);

  
  // Validate LightRAG configuration on page activation
  const validateConfiguration = async () => {
    if (hasValidatedRef.current) return;

    try {
      const ipcApi = get_ipc_api();
      const response = await ipcApi.lightragApi.getSettings();

      if (response.success && response.data) {
        const settings: Record<string, any> = { ...response.data };

        // Global fallback: if the current workspace doesn't carry an LLM/Embedding
        // API key but the user already configured the same provider globally, treat
        // it as system-managed so the warning modal doesn't fire. This mirrors the
        // expected behavior users have after configuring RyoAIS in global Settings.
        try {
          const [llmResp, embedResp] = await Promise.all([
            ipcApi.getLLMProviders<{ providers: Array<{ name?: string; provider?: string; api_key_configured?: boolean }> }>(),
            ipcApi.getEmbeddingProviders<{ providers: Array<{ name?: string; provider?: string; api_key_configured?: boolean }> }>(),
          ]);

          const llmProvider = settings.LLM_BINDING || settings.LLM_PROVIDER;
          if (llmProvider && !settings.LLM_BINDING_API_KEY && !settings._SYSTEM_LLM_KEY_SOURCE) {
            const globalLlm = (llmResp.success && llmResp.data?.providers || []).find(
              (p) => (p.provider || p.name || '').toLowerCase() === llmProvider.toLowerCase()
            );
            if (globalLlm?.api_key_configured) {
              settings._SYSTEM_LLM_KEY_SOURCE = true;
            }
          }

          const embedProvider = settings.EMBEDDING_BINDING || settings.EMBEDDING_PROVIDER;
          if (embedProvider && !settings.EMBEDDING_BINDING_API_KEY && !settings._SYSTEM_EMBED_KEY_SOURCE) {
            const globalEmbed = (embedResp.success && embedResp.data?.providers || []).find(
              (p) => (p.provider || p.name || '').toLowerCase() === embedProvider.toLowerCase()
            );
            if (globalEmbed?.api_key_configured) {
              settings._SYSTEM_EMBED_KEY_SOURCE = true;
            }
          }
        } catch (e) {
          console.warn('[Knowledge] Failed to load global providers config for validation fallback:', e);
        }

        const validation = validateLightRAGConfig(settings);
        
        if (!validation.isValid) {
          // Show configuration warning modal
          const issueMessages = validation.issues.map(issue => t(issue.translationKey)).join('\n');
          
          Modal.warning({
            title: t('pages.knowledge.configurationRequired'),
            icon: <ExclamationCircleOutlined style={{ color: '#faad14' }} />,
            content: (
              <div style={{ color: '#ffffff' }}>
                <p style={{ marginBottom: '12px', color: '#ffffff' }}>
                  {t('pages.knowledge.configurationIncompleteMessage')}
                </p>
                <div style={{ 
                  whiteSpace: 'pre-line', 
                  fontSize: '14px', 
                  color: '#ffffff',
                  marginBottom: '12px',
                  lineHeight: '1.6'
                }}>
                  {issueMessages}
                </div>
              </div>
            ),
            okText: t('pages.knowledge.goToSettings'),
            cancelText: t('pages.knowledge.continueAnyway'),
            okCancel: true,
            width: 520,
            onOk: () => {
              // Switch to settings tab
              setActiveTab('settings');
            },
            onCancel: () => {
              // User chose to continue anyway
              hasValidatedRef.current = true;
            }
          });
        } else {
          hasValidatedRef.current = true;
        }
      }
    } catch (error) {
      console.error('Failed to validate LightRAG configuration:', error);
      // Don't block the user if validation fails
      hasValidatedRef.current = true;
    }
  };
  
  // 使用 useEffectOnActive 在组件激活时恢复滚动位置和验证配置
  // 注意：减少不必要的事件触发，避免激活/停用循环
  useEffectOnActive(
    () => {
      // Validate configuration on first activation
      validateConfiguration();
      
      // 恢复滚动位置
      const container = containerRef.current;
      if (container && savedScrollPositionRef.current > 0) {
        requestAnimationFrame(() => {
          container.scrollTop = savedScrollPositionRef.current;
        });
      }
      
      return () => {
        // 保存滚动位置
        const container = containerRef.current;
        if (container) {
          savedScrollPositionRef.current = container.scrollTop;
        }
      };
    },
    []
  );
  
  const renderTab = (key: TabKey) => {
    switch (key) {
      case 'documents':
        return <DocumentsTab />;
      case 'knowledge-graph':
        return <GraphTab />;
      case 'retrieval':
        return <RetrievalTab />;
      case 'settings':
        return <SettingsTab />;
      case 'api':
        return null; // hidden
      default:
        return null;
    }
  };

  return (
    <div 
      ref={containerRef}
      style={{ height: '100%', width: '100%', background: backgroundColor, overflow: 'auto' }}
    >
      <Tabs 
        active={activeTab}
        onChange={(key) => setActiveTab(key)}
        renderTab={renderTab} 
      />
    </div>
  );
};

export default KnowledgePortedPage;
