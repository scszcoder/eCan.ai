import React from 'react';
import { Layout, Menu } from 'antd';
import styled from '@emotion/styled';
import type { MenuProps } from 'antd';
import HLogo1Dark from '@/assets/HLogo1Dark2.png';
import { useTheme, resolveTheme } from '@/contexts/ThemeContext';

const { Sider } = Layout;

const Logo = styled.div`
    height: var(--header-height);
    padding: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0;
    cursor: pointer;
    transition: background var(--transition-slow);
    margin: 0;
    position: relative;
    background: linear-gradient(
        135deg,
        rgba(var(--primary-color-rgb), 0.15) 0%,
        rgba(139, 92, 246, 0.08) 100%
    );
    border-bottom: var(--border-width) solid var(--border-color);

    /* 顶部高光 */
    &::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 1px;
        background: linear-gradient(
            90deg,
            transparent,
            rgba(var(--primary-color-rgb), 0.3),
            transparent
        );
    }

    &:hover {
        background: linear-gradient(
            135deg,
            rgba(var(--primary-color-rgb), 0.25) 0%,
            rgba(139, 92, 246, 0.15) 100%
        );
    }

    &:active {
        opacity: 0.9;
    }

    .logo-icon {
        width: 100%;
        height: var(--header-height);
        display: flex;
        align-items: center;
        justify-content: center;
        background: none;
        border-radius: 0;
        box-sizing: border-box;
        margin: 0;
        padding: 10px;
        transition: transform var(--transition-slow);

        .anticon {
            font-size: 20px;
            color: var(--text-primary);
        }
    }

    .logo-text {
        color: var(--text-primary);
        font-size: var(--font-size-lg);
        font-weight: var(--font-weight-semibold);
        letter-spacing: 0.5px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        transition: color var(--transition-normal);
    }
`;

const MenuWrapper = styled.div`
    flex: 1;
    overflow: auto;
    height: calc(100vh - var(--header-height));
    padding: var(--space-sm) 0;

    /* 自动隐藏滚动条 */
    scrollbar-width: thin;
    scrollbar-color: transparent transparent;

    &::-webkit-scrollbar {
        width: 6px;
    }

    &::-webkit-scrollbar-track {
        background: var(--scrollbar-track);
        border-radius: 3px;
        margin: 4px 0;
    }

    &::-webkit-scrollbar-thumb {
        background: transparent;
        border-radius: 3px;
        transition: background var(--transition-normal);
    }

    /* hover 时显示滚动条 */
    &:hover {
        scrollbar-color: var(--scrollbar-thumb) transparent;

        &::-webkit-scrollbar-thumb {
            background: var(--scrollbar-thumb);
        }
    }

    /* 滚动条 hover 时加深 */
    &::-webkit-scrollbar-thumb:hover {
        background: var(--scrollbar-thumb-hover);
    }
`;

const StyledSider = styled(Sider)`
    height: 100vh;
    display: flex;
    flex-direction: column;
    background: linear-gradient(
        180deg,
        var(--sider-bg-from) 0%,
        var(--sider-bg-to) 100%
    ) !important;
    border-right: var(--border-width) solid var(--border-color) !important;
    box-shadow: var(--shadow-md);
    position: relative;

    /* 右侧微光 */
    &::after {
        content: '';
        position: absolute;
        top: 0;
        right: 0;
        width: 1px;
        height: 100%;
        background: linear-gradient(
            180deg,
            transparent,
            rgba(var(--primary-color-rgb), 0.3) 30%,
            rgba(139, 92, 246, 0.3) 70%,
            transparent
        );
        opacity: 0.5;
    }
`;

const StyledMenu = styled(Menu)`
    background: transparent !important;
    border: none !important;

    .ant-menu-item {
        margin: 6px 12px !important;
        padding: 0 16px !important;
        height: var(--control-height-lg) !important;
        line-height: 44px !important;
        border-radius: var(--radius-sm) !important;
        color: var(--sider-text) !important;
        font-weight: var(--font-weight-medium) !important;
        font-size: 15px !important;
        transition: background var(--transition-normal), color var(--transition-normal) !important;
        position: relative;
        overflow: hidden;

        /* 微妙的背景纹理 */
        &::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: radial-gradient(
                circle at 50% 50%,
                rgba(255, 255, 255, 0.03) 0%,
                transparent 70%
            );
            opacity: 0;
            transition: opacity var(--transition-normal);
        }

        &:hover {
            color: var(--sider-text-hover) !important;
            background: var(--sider-item-hover-bg) !important;

            &::before {
                opacity: 1;
            }

            /* 悬停时左侧发光条 */
            &::after {
                content: '';
                position: absolute;
                left: 0;
                top: 50%;
                transform: translateY(-50%);
                width: 3px;
                height: 60%;
                background: linear-gradient(
                    180deg,
                    transparent,
                    rgba(var(--primary-color-rgb), 0.8),
                    transparent
                );
                border-radius: 0 2px 2px 0;
            }
        }

        &:active {
            opacity: 0.8;
        }
    }

    .ant-menu-item-selected {
        background: var(--sider-item-active-bg) !important;
        color: var(--sider-text-hover) !important;
        font-weight: var(--font-weight-semibold) !important;
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06);
        border: var(--border-width) solid rgba(var(--primary-color-rgb), 0.3);

        /* 选中态左侧彩色条 */
        &::before {
            content: '';
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            width: 4px;
            background: linear-gradient(
                180deg,
                var(--primary-color) 0%,
                var(--accent-color) 100%
            );
            border-radius: 0 2px 2px 0;
            opacity: 1;
        }

        &:hover {
            background: var(--bg-active) !important;
        }
    }

    .ant-menu-item-icon {
        color: inherit !important;
        font-size: 18px !important;
        transition: color var(--transition-normal) !important;
    }

    .ant-menu-item:hover .ant-menu-item-icon {
        color: inherit !important;
    }

    .ant-menu-item-selected .ant-menu-item-icon {
        color: var(--primary-text) !important;
    }
`;

interface AppSiderProps {
    collapsed: boolean;
    menuItems: MenuProps['items'];
    selectedKey: string;
    onMenuClick: ({ key }: { key: string }) => void;
}

const AppSider: React.FC<AppSiderProps> = ({ collapsed, menuItems, selectedKey, onMenuClick }) => {
    // antd's own dark/light menu algorithm must follow the app theme, otherwise
    // `theme="dark"` keeps painting dark item colours over our light tokens.
    const { theme } = useTheme();
    const isDark = resolveTheme(theme) === 'dark';

    const handleLogoClick = () => {
        // Open official website
        window.open('https://www.ecan.ai', '_blank');
    };

    return (
        <StyledSider trigger={null} collapsible collapsed={collapsed} theme={isDark ? 'dark' : 'light'}>
            <Logo onClick={handleLogoClick}>
                <div className="logo-icon">
                    <img
                        src={HLogo1Dark}
                        alt="Logo"
                        style={{
                            maxWidth: '100%',
                            maxHeight: '100%',
                            objectFit: 'contain',
                            borderRadius: 0,
                            display: 'block',
                        }}
                    />
                </div>
            </Logo>
        <MenuWrapper>
            <StyledMenu
                theme={isDark ? 'dark' : 'light'}
                mode="inline"
                selectedKeys={[selectedKey]}
                items={menuItems}
                onClick={onMenuClick}
            />
        </MenuWrapper>
    </StyledSider>
    );
};

export default AppSider;
