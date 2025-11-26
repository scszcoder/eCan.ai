import React, { useState } from 'react';
import { theme } from 'antd';
import { FileTextOutlined, ShareAltOutlined, SearchOutlined, SettingOutlined } from '@ant-design/icons';
import { useTheme } from '@/contexts/ThemeContext';
import { useTranslation } from 'react-i18next';
import Header from './Header';

// Minimal tabs component for the ported LightRAG UI.
// Does not depend on Radix or Tailwind; no routing changes.

export type TabKey = 'documents' | 'knowledge-graph' | 'retrieval' | 'settings' | 'api';

interface TabsProps {
  defaultActive?: TabKey;
  onChange?: (key: TabKey) => void;
  renderTab: (key: TabKey) => React.ReactNode;
}

const Tabs: React.FC<TabsProps> = ({ defaultActive = 'documents', onChange, renderTab }) => {
  const [active, setActive] = useState<TabKey>(defaultActive);
  // Keep track of visited tabs to lazy-load them but keep them alive afterwards
  const [visited, setVisited] = useState<Set<TabKey>>(new Set([defaultActive]));
  
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const { theme: currentTheme } = useTheme();
  const isDark = currentTheme === 'dark' || (currentTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);

  const handleClick = (key: TabKey) => {
    setActive(key);
    setVisited(prev => {
      const next = new Set(prev);
      next.add(key);
      return next;
    });
    onChange?.(key);
  };

  // 使用主题 token 的背景色
  const tabBarBg = token.colorBgContainer;
  const contentBg = token.colorBgLayout;
  
  const tabKeys: TabKey[] = ['documents', 'knowledge-graph', 'retrieval', 'settings', 'api'];

  return (
    <div data-ec-scope="lightrag-ported" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Header />
      <div style={{
        padding: '0 32px',
        background: tabBarBg,
        display: 'flex',
        alignItems: 'center',
        gap: '4px',
        position: 'relative',
        minHeight: 52
      }}>
        <button className={`ec-tab ${active === 'documents' ? 'ec-tab-active' : ''}`} onClick={() => handleClick('documents')}>
          <FileTextOutlined style={{ marginRight: 8 }} />
          {t('pages.knowledge.tabs.documents')}
        </button>
        <button className={`ec-tab ${active === 'knowledge-graph' ? 'ec-tab-active' : ''}`} onClick={() => handleClick('knowledge-graph')}>
          <ShareAltOutlined style={{ marginRight: 8 }} />
          {t('pages.knowledge.tabs.knowledgeGraph')}
        </button>
        <button className={`ec-tab ${active === 'retrieval' ? 'ec-tab-active' : ''}`} onClick={() => handleClick('retrieval')}>
          <SearchOutlined style={{ marginRight: 8 }} />
          {t('pages.knowledge.tabs.retrieval')}
        </button>
        <button className={`ec-tab ${active === 'settings' ? 'ec-tab-active' : ''}`} onClick={() => handleClick('settings')}>
          <SettingOutlined style={{ marginRight: 8 }} />
          {t('pages.knowledge.tabs.settings')}
        </button>
        {/* API tab is present but invisible per requirement */}
        <button className={`ec-tab ${active === 'api' ? 'ec-tab-active' : ''}`} onClick={() => handleClick('api')} style={{ visibility: 'hidden' }}>API</button>
      </div>
      <div style={{ flex: 1, overflow: 'hidden', background: contentBg, position: 'relative' }}>
        {tabKeys.map(key => {
          if (!visited.has(key)) return null;
          return (
            <div 
              key={key} 
              style={{ 
                height: '100%', 
                width: '100%', 
                display: active === key ? 'block' : 'none',
                overflow: 'auto' // Inner scroll for each tab
              }}
            >
              {renderTab(key)}
            </div>
          );
        })}
      </div>
      <style>{`
        [data-ec-scope="lightrag-ported"] .ec-tab {
          background: transparent;
          border: none;
          cursor: pointer;
          padding: 16px 24px;
          font-size: 15px;
          font-weight: 500;
          color: ${token.colorTextSecondary};
          border-radius: 0;
          transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
          position: relative;
          border-bottom: 3px solid transparent;
          letter-spacing: 0.3px;
        }
        [data-ec-scope="lightrag-ported"] .ec-tab:hover {
          color: ${token.colorPrimary};
          background: ${isDark ? 'rgba(59, 130, 246, 0.1)' : 'rgba(59, 130, 246, 0.06)'};
        }
        [data-ec-scope="lightrag-ported"] .ec-tab-active {
          color: ${token.colorPrimary};
          font-weight: 600;
          border-bottom-color: ${token.colorPrimary};
          background: transparent;
        }
      `}</style>
    </div>
  );
};

export default Tabs;
