import React from 'react';
import { Layout, Menu } from 'antd';
import styled from '@emotion/styled';
import { SafetyCertificateOutlined } from '@ant-design/icons';
import type { MenuProps } from 'antd';

const { Sider } = Layout;

const Logo = styled.div`
    height: 64px;
    padding: 0 16px;
    display: flex;
    align-items: center;
    gap: 12px;
    cursor: pointer;
    transition: all 0.3s ease;
    margin: 0;
    background: linear-gradient(
        135deg,
        rgba(255, 255, 255, 0.08) 0%,
        rgba(255, 255, 255, 0.03) 100%
    );
    &:hover {
        background: linear-gradient(
            135deg,
            rgba(255, 255, 255, 0.12) 0%,
            rgba(255, 255, 255, 0.05) 100%
        );
    }
    .logo-icon {
        width: 32px;
        height: 32px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: linear-gradient(135deg, var(--primary-color) 0%, var(--primary-color-hover) 100%);
        border-radius: 6px;
        transition: all 0.3s ease;
        .anticon {
            font-size: 18px;
            color: #fff;
        }
    }
    .logo-text {
        color: rgba(255, 255, 255, 0.9);
        font-size: 18px;
        font-weight: 600;
        letter-spacing: 0.5px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        transition: all 0.3s ease;
    }
`;

interface AppSiderProps {
    collapsed: boolean;
    onLogoClick: () => void;
    menuItems: MenuProps['items'];
    selectedKey: string;
    onMenuClick: ({ key }: { key: string }) => void;
}

const AppSider: React.FC<AppSiderProps> = ({ collapsed, onLogoClick, menuItems, selectedKey, onMenuClick }) => (
    <Sider trigger={null} collapsible collapsed={collapsed} theme="dark">
        <Logo onClick={onLogoClick}>
            <div className="logo-icon">
                <SafetyCertificateOutlined />
            </div>
            <div className="logo-text">ECBot</div>
        </Logo>
        <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[selectedKey]}
            items={menuItems}
            onClick={onMenuClick}
        />
    </Sider>
);

export default AppSider; 