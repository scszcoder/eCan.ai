import React from 'react';
import { theme } from 'antd';
import WorkspacePicker from './WorkspacePicker';
import { useWorkspace } from './useWorkspace';

// Minimal header without branding, login/version/lang, github, etc.
// Scoped styles via inline classes to avoid leaking globals.
//
// The right-hand side hosts the GLOBAL workspace (tenant) selector. It is
// backed by useWorkspace(), which is a sessionStorage-backed singleton
// shared with the per-tab pickers in DocumentsTab / RetrievalTab — so all
// three stay in sync regardless of which one the user touched last.

const Header: React.FC = () => {
  const { token } = theme.useToken();
  const [workspace, setWorkspace] = useWorkspace();

  // 使用主题 token 的背景色
  const headerBg = token.colorBgContainer;

  return (
    <header
      style={{
        background: headerBg,
        padding: '8px 48px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}
      data-ec-scope="lightrag-ported"
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {/* Intentionally no logo/name per requirements */}
      </div>
      <div style={{ display: 'flex', alignItems: 'center' }}>
        {/* Tabs are rendered by parent; keep center clean */}
      </div>
      <nav style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <WorkspacePicker
          value={workspace}
          onChange={setWorkspace}
          label="Workspace"
          placeholder="(server default)"
        />
      </nav>
    </header>
  );
};

export default Header;
