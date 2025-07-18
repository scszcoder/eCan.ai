import React from 'react';
import { Layout, Menu } from 'antd';
import styled from '@emotion/styled';
import type { MenuProps } from 'antd';
import HLogo1Dark from '@/assets/HLogo1Dark.png';

const { Sider } = Layout;

const Logo = styled.div`
    height: 64px;
    padding: 0; /* 去除左右 padding 让 logo 区域更大 */
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0;
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
        width: 100%;
        height: 64px;
        display: flex;
        align-items: center; /* 垂直居中 */
        justify-content: center; /* 水平居中 */
        background: none;
        border-radius: 0px;
        border: 0px solid rgba(24, 144, 255, 0.18);
        box-sizing: border-box;
        margin: 0;
        padding: 8px; /* 增加内边距让图片与边缘有距离 */
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

const MenuWrapper = styled.div`
    flex: 1;
    overflow: auto;
    height: calc(100vh - 64px);
`;

const StyledSider = styled(Sider)`
    height: 100vh;
    display: flex;
    flex-direction: column;
`;

interface AppSiderProps {
    collapsed: boolean;
    onLogoClick: () => void;
    menuItems: MenuProps['items'];
    selectedKey: string;
    onMenuClick: ({ key }: { key: string }) => void;
}

const AppSider: React.FC<AppSiderProps> = ({ collapsed, onLogoClick, menuItems, selectedKey, onMenuClick }) => (
    <StyledSider trigger={null} collapsible collapsed={collapsed} theme="dark">
        <Logo onClick={onLogoClick}>
            <div className="logo-icon">
                <img src={HLogo1Dark} alt="Logo" style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain', borderRadius: 8, display: 'block' }} />
            </div>
        </Logo>
        <MenuWrapper>
            <Menu
                theme="dark"
                mode="inline"
                selectedKeys={[selectedKey]}
                items={menuItems}
                onClick={onMenuClick}
            />
        </MenuWrapper>
    </StyledSider>
);

export default AppSider;
