import React, { useState } from 'react';
import Header from './Header';

// Minimal tabs component for the ported LightRAG UI.
// Does not depend on Radix or Tailwind; no routing changes.

export type TabKey = 'documents' | 'knowledge-graph' | 'retrieval' | 'settings' | 'api';

interface TabsProps {
  defaultActive?: TabKey;
  onChange?: (key: TabKey) => void;
  renderTab: (key: TabKey) => React.ReactNode;
}

const TAB_ORDER: TabKey[] = ['documents', 'knowledge-graph', 'retrieval', 'settings', 'api'];

const Tabs: React.FC<TabsProps> = ({ defaultActive = 'documents', onChange, renderTab }) => {
  const [active, setActive] = useState<TabKey>(defaultActive);

  const handleClick = (key: TabKey) => {
    setActive(key);
    onChange?.(key);
  };

  return (
    <div data-ec-scope="lightrag-ported" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Header />
      <div className="px-12 py-2 border-b border-solid border-[var(--ant-color-border)] flex items-center gap-8">
        <button className={`ec-tab ${active === 'documents' ? 'ec-tab-active' : ''}`} onClick={() => handleClick('documents')}>Documents</button>
        <button className={`ec-tab ${active === 'knowledge-graph' ? 'ec-tab-active' : ''}`} onClick={() => handleClick('knowledge-graph')}>Knowledge Graph</button>
        <button className={`ec-tab ${active === 'retrieval' ? 'ec-tab-active' : ''}`} onClick={() => handleClick('retrieval')}>Retrieval</button>
        <button className={`ec-tab ${active === 'settings' ? 'ec-tab-active' : ''}`} onClick={() => handleClick('settings')}>Settings</button>
        {/* API tab is present but invisible per requirement */}
        <button className={`ec-tab ${active === 'api' ? 'ec-tab-active' : ''}`} onClick={() => handleClick('api')} style={{ visibility: 'hidden' }}>API</button>
      </div>
      <div style={{ flex: 1, overflow: 'auto' }}>
        {renderTab(active)}
      </div>
      <style>{`
        [data-ec-scope="lightrag-ported"] .ec-tab { background: transparent; border: none; cursor: pointer; padding: 6px 8px; border-radius: 6px; }
        [data-ec-scope="lightrag-ported"] .ec-tab-active { background: var(--ant-color-primary-bg); color: var(--ant-color-primary); }
      `}</style>
    </div>
  );
};

export default Tabs;
