import React, { useRef, useState } from 'react';
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

const KnowledgePortedPage: React.FC = () => {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const backgroundColor = token.colorBgLayout;
  const containerRef = useRef<HTMLDivElement>(null);
  const savedScrollPositionRef = useRef<number>(0);
  const [activeTab, setActiveTab] = useState<TabKey>('documents');
  const hasValidatedRef = useRef<boolean>(false);

  
  // Validate LightRAG configuration on page activation
  const validateConfiguration = async () => {
    if (hasValidatedRef.current) return;
    
    try {
      const ipcApi = get_ipc_api();
      const response = await ipcApi.lightragApi.getSettings();
      
      if (response.success && response.data) {
        const validation = validateLightRAGConfig(response.data);
        
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
        defaultActive={activeTab} 
        onChange={(key) => setActiveTab(key)}
        renderTab={renderTab} 
      />
    </div>
  );
};

export default KnowledgePortedPage;
