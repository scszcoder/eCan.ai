import React from 'react';
import { theme } from 'antd';

// Minimal header without branding, login/version/lang, github, etc.
// Scoped styles via inline classes to avoid leaking globals.

const Header: React.FC = () => {
  const { token } = theme.useToken();
  
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
      <nav style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {/* Intentionally empty per requirements */}
      </nav>
    </header>
  );
};

export default Header;
