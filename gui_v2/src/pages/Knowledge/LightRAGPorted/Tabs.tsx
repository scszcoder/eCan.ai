import React, { useEffect, useState, useRef } from 'react';
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
  const storagePrefix = 'lightrag-ported:tabs';

  const readActiveFromStorage = (): TabKey => {
    const raw = sessionStorage.getItem(`${storagePrefix}:active`);
    const key = raw as TabKey | null;
    if (key === 'documents' || key === 'knowledge-graph' || key === 'retrieval' || key === 'settings' || key === 'api') {
      return key;
    }
    return defaultActive;
  };

  const readVisitedFromStorage = (activeKey: TabKey): Set<TabKey> => {
    try {
      const raw = sessionStorage.getItem(`${storagePrefix}:visited`);
      if (!raw) return new Set([activeKey]);
      const arr = JSON.parse(raw) as TabKey[];
      const valid = arr.filter((k) => k === 'documents' || k === 'knowledge-graph' || k === 'retrieval' || k === 'settings' || k === 'api');
      const set = new Set<TabKey>(valid);
      set.add(activeKey);
      return set;
    } catch {
      return new Set([activeKey]);
    }
  };

  const [active, setActive] = useState<TabKey>(() => readActiveFromStorage());
  // Keep track of visited tabs to lazy-load them but keep them alive afterwards
  const [visited, setVisited] = useState<Set<TabKey>>(() => readVisitedFromStorage(readActiveFromStorage()));
  
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const { theme: currentTheme } = useTheme();
  const isDark = currentTheme === 'dark' || (currentTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);

  const scrollPositions = useRef<Map<TabKey, number>>(new Map());
  const tabRefs = useRef<Map<TabKey, HTMLDivElement>>(new Map());

  const isOuterScrollable = (key: TabKey) => {
    return key === 'documents' || key === 'knowledge-graph' || key === 'api';
  };

  const saveScrollPosition = (key: TabKey, scrollTop: number) => {
    scrollPositions.current.set(key, scrollTop);
    sessionStorage.setItem(`${storagePrefix}:scroll:${key}`, String(scrollTop));
  };

  const readScrollPosition = (key: TabKey): number => {
    const inMemory = scrollPositions.current.get(key);
    if (typeof inMemory === 'number') return inMemory;
    const raw = sessionStorage.getItem(`${storagePrefix}:scroll:${key}`);
    const num = raw ? Number(raw) : 0;
    return Number.isFinite(num) ? num : 0;
  };

  const emitTabEvent = (type: 'activate' | 'deactivate', key: TabKey) => {
    window.dispatchEvent(new CustomEvent(`lightrag-tab-${type}`, { detail: { key } }));
  };

  const restoreScrollWithRetry = (key: TabKey, attempts = 0) => {
    if (!isOuterScrollable(key)) return;
    const el = tabRefs.current.get(key);
    const saved = readScrollPosition(key);
    if (!el || saved <= 0) return;

    if (el.scrollHeight <= el.clientHeight && attempts < 12) {
      setTimeout(() => restoreScrollWithRetry(key, attempts + 1), 50);
      return;
    }

    el.scrollTop = saved;
  };

  useEffect(() => {
    sessionStorage.setItem(`${storagePrefix}:active`, active);
    sessionStorage.setItem(`${storagePrefix}:visited`, JSON.stringify(Array.from(visited)));
  }, [active, visited]);

  // 使用 ref 保存最新的 active 值，避免闭包问题
  const activeRef = useRef(active);
  activeRef.current = active;

  // 组件挂载时恢复滚动位置，卸载时保存滚动位置
  useEffect(() => {
    // 延迟执行，确保 DOM 已经渲染完成
    const timer = setTimeout(() => {
      emitTabEvent('activate', activeRef.current);
      restoreScrollWithRetry(activeRef.current);
    }, 100);
    
    // 组件卸载时保存滚动位置
    return () => {
      clearTimeout(timer);
      // 使用 ref 获取最新的 active 值
      const currentActive = activeRef.current;
      if (isOuterScrollable(currentActive)) {
        const el = tabRefs.current.get(currentActive);
        if (el) {
          saveScrollPosition(currentActive, el.scrollTop);
        }
      }
      emitTabEvent('deactivate', currentActive);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    emitTabEvent('activate', active);
    requestAnimationFrame(() => restoreScrollWithRetry(active));
    return () => {
      emitTabEvent('deactivate', active);
    };
  }, [active]);

  const handleClick = (key: TabKey) => {
    // 保存当前标签页的滚动位置
    if (isOuterScrollable(active)) {
      const currentTabElement = tabRefs.current.get(active);
      if (currentTabElement) {
        saveScrollPosition(active, currentTabElement.scrollTop);
      }
    }
    
    setActive(key);
    setVisited(prev => {
      const next = new Set(prev);
      next.add(key);
      return next;
    });
    onChange?.(key);
  };
  
  // 设置 tab ref
  const setTabRef = (key: TabKey) => (el: HTMLDivElement | null) => {
    if (el) {
      tabRefs.current.set(key, el);
      if (key === active) {
        requestAnimationFrame(() => restoreScrollWithRetry(key));
      }
    } else {
      tabRefs.current.delete(key);
    }
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
              ref={setTabRef(key)}
              onScroll={(e) => {
                if (active === key && isOuterScrollable(key)) {
                  saveScrollPosition(key, e.currentTarget.scrollTop);
                }
              }}
              style={{ 
                position: 'absolute',
                top: 0,
                left: 0,
                height: '100%', 
                width: '100%', 
                visibility: active === key ? 'visible' : 'hidden',
                overflow: isOuterScrollable(key) ? 'auto' : 'hidden',
                pointerEvents: active === key ? 'auto' : 'none'
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
