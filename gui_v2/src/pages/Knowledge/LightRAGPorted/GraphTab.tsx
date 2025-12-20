import React from 'react';
import { theme } from 'antd';
import GraphViewer from './graph/GraphViewer';

const GraphTab: React.FC = () => {
  const { token } = theme.useToken();

  return (
    <div style={{ 
      height: '100%', 
      width: '100%',
      background: token.colorBgLayout
    }} data-ec-scope="lightrag-ported">
      <GraphViewer />
    </div>
  );
};

export default GraphTab;
