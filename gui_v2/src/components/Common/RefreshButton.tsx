import React from 'react';
import { Button } from 'antd';
import styled from '@emotion/styled';
import { ReloadOutlined } from '@ant-design/icons';

/**
 * The one icon-only refresh button used across pages.
 *
 * This replaces four copy-pasted `styled(Button)` blocks (Tools, Settings,
 * GeneralTabContent, PageBackBreadcrumb) that had drifted into four different
 * looks — some 36px with a hover tint, some fully transparent, some with a
 * border. Sizing comes from `--control-*` tokens so it sits on the shared
 * control ladder instead of inventing its own height.
 */
const RefreshButtonRoot = styled(Button)`
    &.ant-btn {
        width: var(--control-height-md);
        height: var(--control-height-md);
        min-width: var(--control-height-md);
        padding: 0 !important;
        border: none !important;
        border-radius: var(--control-radius) !important;
        background: transparent !important;
        box-shadow: none !important;
        color: var(--text-secondary) !important;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: var(--font-size-md) !important;
        transition: background-color var(--transition-fast), color var(--transition-fast) !important;

        &:hover:not(:disabled) {
            background: var(--control-bg-hover) !important;
            color: var(--text-primary) !important;
        }

        &:active:not(:disabled) {
            background: var(--control-bg-focus) !important;
        }

        &:disabled {
            opacity: 0.5 !important;
        }
    }
`;

interface RefreshButtonProps {
    onClick?: () => void;
    loading?: boolean;
    disabled?: boolean;
    /** Localised tooltip/label text. */
    title?: string;
    className?: string;
}

const RefreshButton: React.FC<RefreshButtonProps> = ({ onClick, loading, disabled, title, className }) => (
    <RefreshButtonRoot
        type="text"
        className={className}
        icon={<ReloadOutlined />}
        onClick={onClick}
        loading={loading}
        disabled={disabled}
        title={title}
        aria-label={title}
    />
);

export default RefreshButton;
