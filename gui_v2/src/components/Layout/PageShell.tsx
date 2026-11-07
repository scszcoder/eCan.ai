import React from 'react';

interface PageShellProps {
    children: React.ReactNode;
    /**
     * Use for pages that own their internal scrolling (list/detail two-panel
     * layouts). Suppresses the page-level scrollbar so the inner panels can
     * manage their own overflow.
     */
    fill?: boolean;
    className?: string;
    style?: React.CSSProperties;
}

/**
 * The single page-root wrapper for every routed page.
 *
 * Its only job is to apply the shared page rhythm (`--page-padding`) and the
 * shared page title/section roles, so sub-pages stop inventing their own
 * 4/8/12/14/16/18/20/22/24px root padding. Styling lives in global.css
 * (`.page-shell`, `.page-title`, `.section-title`, `.caption-text`) to keep the
 * theme contract: CSS owns colour and scale, TSX only picks the role.
 */
const PageShell: React.FC<PageShellProps> = ({ children, fill = false, className, style }) => (
    <div
        className={`page-shell${fill ? ' page-shell--fill' : ''}${className ? ` ${className}` : ''}`}
        style={style}
    >
        {children}
    </div>
);

export default PageShell;
