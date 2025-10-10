import React from 'react';

// Minimal header without branding, login/version/lang, github, etc.
// Scoped styles via inline classes to avoid leaking globals.

const Header: React.FC = () => {
  return (
    <header className="border-b border-solid border-[var(--ant-color-border)] px-12 py-2 flex items-center justify-between" data-ec-scope="lightrag-ported">
      <div className="flex items-center gap-2">
        {/* Intentionally no logo/name per requirements */}
      </div>
      <div className="flex items-center">
        {/* Tabs are rendered by parent; keep center clean */}
      </div>
      <nav className="flex items-center gap-2">
        {/* Intentionally empty per requirements */}
      </nav>
    </header>
  );
};

export default Header;
