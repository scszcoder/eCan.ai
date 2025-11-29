import React from 'react';
import { Layout, Menu } from 'antd';
import styled from '@emotion/styled';
import type { MenuProps } from 'antd';
import HLogo1Dark from '@/assets/HLogo1Dark2.png';

const { Sider } = Layout;

const Logo = styled.div`
    height: 64px;
    padding: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0;
    cursor: pointer;
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    margin: 0;
    position: relative;
    background: linear-gradient(
        135deg,
        rgba(59, 130, 246, 0.15) 0%,
        rgba(139, 92, 246, 0.08) 100%
    );
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    
    /* AddTop高光效果 */
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
            rgba(59, 130, 246, 0.3),
            transparent
        );
    }
    
    &:hover {
        background: linear-gradient(
            135deg,
            rgba(59, 130, 246, 0.25) 0%,
            rgba(139, 92, 246, 0.15) 100%
        );
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.2);
    }
    
    &:active {
        opacity: 0.9;
    }
    
    .logo-icon {
        width: 100%;
        height: 64px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: none;
        border-radius: 0px;
        box-sizing: border-box;
        margin: 0;
        padding: 10px;
        transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        
        .anticon {
            font-size: 20px;
            color: #fff;
        }
    }
    
    .logo-text {
        color: rgba(255, 255, 255, 0.95);
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
    padding: 12px 0;
    
    /* OptimizeScroll条样式 */
    &::-webkit-scrollbar {
        width: 6px;
    }
    
    &::-webkit-scrollbar-track {
        background: rgba(255, 255, 255, 0.02);
        border-radius: 3px;
        margin: 4px 0;
    }
    
    &::-webkit-scrollbar-thumb {
        background: rgba(255, 255, 255, 0.1);
        border-radius: 3px;
        transition: background 0.3s ease;
        
        &:hover {
            background: rgba(255, 255, 255, 0.2);
        }
    }
`;

const StyledSider = styled(Sider)`
    height: 100vh;
    display: flex;
    flex-direction: column;
    background: linear-gradient(
        180deg,
        #0f172a 0%,
        #1e293b 100%
    ) !important;
    border-right: 1px solid rgba(255, 255, 255, 0.08) !important;
    box-shadow: 4px 0 24px rgba(0, 0, 0, 0.3);
    position: relative;
    
    /* AddRight微光效果 */
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
            rgba(59, 130, 246, 0.3) 30%,
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
        height: 44px !important;
        line-height: 44px !important;
        border-radius: 10px !important;
        color: rgba(203, 213, 225, 0.9) !important;
        font-weight: 500 !important;
        font-size: 14px !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        position: relative;
        overflow: hidden;
        
        /* Add微妙的背景纹理 */
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
            transition: opacity 0.3s ease;
        }
        
        &:hover {
            color: rgba(248, 250, 252, 1) !important;
            background: rgba(255, 255, 255, 0.08) !important;
            
            &::before {
                opacity: 1;
            }
            
            /* 悬停时Left发光条 */
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
                    rgba(59, 130, 246, 0.8),
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
        background: linear-gradient(
            90deg,
            rgba(59, 130, 246, 0.2) 0%,
            rgba(139, 92, 246, 0.15) 100%
        ) !important;
        color: rgba(248, 250, 252, 1) !important;
        font-weight: 600 !important;
        box-shadow: 
            0 2px 8px rgba(59, 130, 246, 0.2),
            inset 0 1px 0 rgba(255, 255, 255, 0.1);
        border: 1px solid rgba(59, 130, 246, 0.3);
        
        /* 选中Status的Left彩色条 */
        &::before {
            content: '';
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            width: 4px;
            background: linear-gradient(
                180deg,
                #3b82f6 0%,
                #8b5cf6 100%
            );
            border-radius: 0 2px 2px 0;
            box-shadow: 0 0 12px rgba(59, 130, 246, 0.6);
            opacity: 1;
        }
        
        &:hover {
            background: linear-gradient(
                90deg,
                rgba(59, 130, 246, 0.25) 0%,
                rgba(139, 92, 246, 0.2) 100%
            ) !important;
        }
    }
    
    .ant-menu-item-icon {
        color: inherit !important;
        font-size: 18px !important;
        transition: color 0.3s ease !important;
    }
    
    .ant-menu-item:hover .ant-menu-item-icon {
        color: inherit !important;
    }
    
    .ant-menu-item-selected .ant-menu-item-icon {
        color: #60a5fa !important;
        filter: drop-shadow(0 0 4px rgba(59, 130, 246, 0.5));
    }
`;

interface AppSiderProps {
    collapsed: boolean;
    menuItems: MenuProps['items'];
    selectedKey: string;
    onMenuClick: ({ key }: { key: string }) => void;
}

const AppSider: React.FC<AppSiderProps> = ({ collapsed, menuItems, selectedKey, onMenuClick }) => {
    const handleLogoClick = () => {
        // Open official website
        window.open('https://www.ecan.ai', '_blank');
    };

    return (
        <StyledSider trigger={null} collapsible collapsed={collapsed} theme="dark">
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
                            filter: 'drop-shadow(0 2px 8px rgba(59, 130, 246, 0.3))'
                        }} 
                    />
                </div>
            </Logo>
        <MenuWrapper>
            <StyledMenu
                theme="dark"
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
