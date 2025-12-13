import React, { useRef } from 'react';
import { theme } from 'antd';
import { useEffectOnActive } from 'keepalive-for-react';
import Tabs, { TabKey } from './Tabs';
import SettingsTab from './SettingsTab';
import DocumentsTab from './DocumentsTab';
import RetrievalTab from './RetrievalTab';
import GraphTab from './GraphTab';

const KnowledgePortedPage: React.FC = () => {
  const { token } = theme.useToken();
  const backgroundColor = token.colorBgLayout;
  const containerRef = useRef<HTMLDivElement>(null);
  const savedScrollPositionRef = useRef<number>(0);

  
  // 使用 useEffectOnActive 在组件激活时恢复滚动位置并触发内部 tab 的 restore
  useEffectOnActive(
    () => {
      console.log('[KnowledgePage] Page activated');
      
      const container = containerRef.current;
      if (container && savedScrollPositionRef.current > 0) {
        requestAnimationFrame(() => {
          container.scrollTop = savedScrollPositionRef.current;
        });
      }
      
      // 触发当前 active tab 的 restore
      const storagePrefix = 'lightrag-ported:tabs';
      const raw = sessionStorage.getItem(`${storagePrefix}:active`);
      const active = (raw as TabKey | null) || 'documents';
      
      const emit = (type: 'activate' | 'deactivate') => {
        console.log('[KnowledgePage] Emitting', type, 'for tab:', active);
        window.dispatchEvent(new CustomEvent(`lightrag-tab-${type}`, { detail: { key: active } }));
      };
      
      // 多次延迟触发以适配异步渲染
      emit('activate');
      const t1 = window.setTimeout(() => emit('activate'), 150);
      const t2 = window.setTimeout(() => emit('activate'), 600);
      const t3 = window.setTimeout(() => emit('activate'), 1500);
      
      return () => {
        console.log('[KnowledgePage] Page deactivating');
        window.clearTimeout(t1);
        window.clearTimeout(t2);
        window.clearTimeout(t3);
        
        const container = containerRef.current;
        if (container) {
          savedScrollPositionRef.current = container.scrollTop;
        }
        
        emit('deactivate');
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
      <Tabs defaultActive="documents" renderTab={renderTab} />
    </div>
  );
};

export default KnowledgePortedPage;
