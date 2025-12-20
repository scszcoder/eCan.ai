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

  
  // 使用 useEffectOnActive 在组件激活时恢复滚动位置
  // 注意：减少不必要的事件触发，避免激活/停用循环
  useEffectOnActive(
    () => {
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
      <Tabs defaultActive="documents" renderTab={renderTab} />
    </div>
  );
};

export default KnowledgePortedPage;
