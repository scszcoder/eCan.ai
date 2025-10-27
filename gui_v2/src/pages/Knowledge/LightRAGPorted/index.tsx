import React from 'react';
import { theme } from 'antd';
import Tabs, { TabKey } from './Tabs';
import SettingsTab from './SettingsTab';
import DocumentsTab from './DocumentsTab';
import RetrievalTab from './RetrievalTab';
import GraphTab from './GraphTab';

const KnowledgePortedPage: React.FC = () => {
  const { token } = theme.useToken();
  
  // 调试：输出 token 值
  React.useEffect(() => {
    console.log('=== Knowledge Page Token Debug ===');
    console.log('colorBgLayout:', token.colorBgLayout);
    console.log('colorBgContainer:', token.colorBgContainer);
    console.log('colorBgElevated:', token.colorBgElevated);
  }, [token]);
  
  // 使用主题 token 的背景色
  const backgroundColor = token.colorBgLayout;
  
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
    <div style={{ height: '100%', width: '100%', background: backgroundColor }}>
      <Tabs defaultActive="documents" renderTab={renderTab} />
    </div>
  );
};

export default KnowledgePortedPage;
