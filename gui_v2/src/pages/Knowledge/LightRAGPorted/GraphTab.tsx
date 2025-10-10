import React from 'react';
import GraphViewer from './graph/GraphViewer';

const GraphTab: React.FC = () => {
  return (
    <div style={{ padding: 16, height: '100%', display: 'flex', flexDirection: 'column' }} data-ec-scope="lightrag-ported">
      <h3 style={{ marginBottom: 12 }}>Knowledge Graph</h3>
      <div style={{ height: '60vh', border: '1px solid var(--ant-color-border, #d9d9d9)', borderRadius: 8, overflow: 'hidden' }}>
        <GraphViewer />
      </div>
    </div>
  );
};

export default GraphTab;
