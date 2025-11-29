import React, { useState, useCallback, useEffect } from 'react';
import { Header } from 'antd/es/layout/layout';
import { Button, Badge, Dropdown, Space, Avatar, MenuProps } from 'antd';
import { MenuFoldOutlined, MenuUnfoldOutlined, BellOutlined, UserOutlined, SettingOutlined, GlobalOutlined, SkinOutlined, LogoutOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '../../stores/userStore';
import { useTheme } from '../../contexts/ThemeContext';
import { useLanguage } from '../../contexts/LanguageContext';
import { App } from 'antd';
import { useNavigate } from 'react-router-dom';
import { get_ipc_api } from '../../services/ipc_api';
import { messageManager } from '../../pages/Chat/managers/MessageManager';

const StyledHeader = styled(Header)`
    padding: 0 24px;
    background: rgba(30, 41, 59, 0.98) !important;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    position: relative;
    z-index: 10;
    
    /* AddBottom微光效果 */
    &::after {
        content: '';
        position: absolute;
        bottom: 0;
        left: 0;
        right: 0;
        height: 1px;
        background: linear-gradient(
            90deg,
            transparent,
            rgba(59, 130, 246, 0.4) 30%,
            rgba(139, 92, 246, 0.4) 70%,
            transparent
        );
    }
`;

const HeaderRight = styled.div`
    display: flex;
    align-items: center;
    gap: 20px;
`;

const StyledButton = styled(Button)`
    &.ant-btn-text {
        color: rgba(203, 213, 225, 0.9) !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        border-radius: 8px !important;
        
        &:hover {
            color: rgba(248, 250, 252, 1) !important;
            background: rgba(255, 255, 255, 0.1) !important;
        }
        
        &:active {
            opacity: 0.8;
        }
        
        .anticon {
            transition: color 0.3s ease;
        }
    }
`;

const StyledBadge = styled(Badge)`
    .ant-badge-count {
        background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
        box-shadow: 0 2px 8px rgba(239, 68, 68, 0.4);
        font-weight: 600;
        border: 2px solid rgba(15, 23, 42, 1);
    }
`;

const UserSection = styled(Space)`
    cursor: pointer;
    padding: 6px 12px;
    border-radius: 8px;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    background: transparent;
    border: 1px solid transparent;
    max-width: 220px;
    height: 40px;
    display: inline-flex;
    align-items: center;
    
    &:hover {
        background: rgba(255, 255, 255, 0.1);
        border-color: rgba(59, 130, 246, 0.3);
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.2);
    }
    
    &:active {
        background: rgba(255, 255, 255, 0.05);
        opacity: 0.9;
    }
    
    .ant-space-item:last-child {
        overflow: hidden;
        max-width: 150px;
        line-height: 1;
    }
    
    span {
        color: rgba(248, 250, 252, 0.95);
        font-weight: 500;
        font-size: 14px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        display: block;
        line-height: 1.5;
    }
`;

const StyledAvatar = styled(Avatar)`
    background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
    border: 2px solid rgba(255, 255, 255, 0.2);
    box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
    flex-shrink: 0;
    width: 32px;
    height: 32px;
    line-height: 32px;
    
    .anticon {
        font-size: 16px;
    }
`;

interface AppHeaderProps {
    collapsed: boolean;
    onCollapse: () => void;
    userMenuItems: any[];
    onLogout: () => void;
}

const AppHeader: React.FC<AppHeaderProps> = ({ collapsed, onCollapse, userMenuItems, onLogout }) => {
    const { t, i18n } = useTranslation();
    const { changeTheme } = useTheme();
    const { changeLanguage } = useLanguage();
    const { message, modal } = App.useApp();
    const username = useUserStore((state) => state.username);
    const navigate = useNavigate();

    // 控制下拉Menu的DisplayStatus
    const [dropdownVisible, setDropdownVisible] = useState(false);
    
    // CRITICAL: Track total unread count from all chats
    const [totalUnreadCount, setTotalUnreadCount] = useState(0);
    
    // Subscribe to MessageManager updates to get real-time unread counts
    useEffect(() => {
        // Calculate total unread count from all chats
        const calculateTotalUnread = () => {
            const allUnreadCounts = messageManager.getAllUnreadCounts();
            let total = 0;
            allUnreadCounts.forEach((count) => {
                total += count;
            });
            return total;
        };
        
        // Initial calculation
        setTotalUnreadCount(calculateTotalUnread());
        
        // Subscribe to MessageManager updates
        // MessageManager notifies listeners when messages/unreadCounts change
        const unsubscribe = messageManager.subscribe(() => {
            const newTotal = calculateTotalUnread();
            setTotalUnreadCount(newTotal);
        });
        
        return unsubscribe;
    }, []);

    // Process主题Toggle
    const handleThemeChange = useCallback((value: 'light' | 'dark' | 'system') => {
        changeTheme(value);
        message.success(t('pages.settings.themeChanged'));
        // Close下拉Menu
        setDropdownVisible(false);
    }, [changeTheme, message, t]);

    // Process语言Toggle
    const handleLanguageChange = useCallback(async (value: string) => {
        try {
            await i18n.changeLanguage(value);
            changeLanguage(value);
            
            // Save language preference to uli.json via IPC
            try {
                const api = get_ipc_api();
                if (api) {
                    const response = await api.updateUserPreferences(value);
                    if (response?.success) {
                        console.log('[AppHeader] Language preference saved to uli.json:', value);
                    } else {
                        console.warn('[AppHeader] Failed to save language preference:', response?.error);
                    }
                }
            } catch (ipcError) {
                console.error('[AppHeader] Error saving language preference:', ipcError);
            }
            
            message.success(t('pages.settings.languageChanged'));
            console.log('When前语言已Toggle为:', i18n.language);
        } catch (e) {
            message.error(t('pages.settings.languageChangeError'));
            console.error('语言ToggleFailed:', e);
        }
        // Close下拉Menu
        setDropdownVisible(false);
    }, [i18n, changeLanguage, message, t]);

    // ProcessMenu项Click
    const handleMenuClick = useCallback((key: string) => {
        switch (key) {
            case 'settings':
                navigate('/settings');
                break;
            case 'logout':
                // Show confirmation modal before logout
                modal.confirm({
                    title: t('common.logout_confirm_title') || '确认退出',
                    content: t('common.logout_confirm_message') || '您确定要退出登录吗？',
                    okText: t('common.confirm') || '确认',
                    cancelText: t('common.cancel') || '取消',
                    onOk: () => {
                        onLogout();
                    },
                    centered: true,
                    zIndex: 1000,
                    className: 'logout-confirm-modal',
                    styles: {
                        body: {
                            color: '#ffffff !important',
                        },
                        header: {
                            color: '#ffffff !important',
                        },
                        content: {
                            color: '#ffffff !important',
                        },
                    },
                });
                break;
            default:
                // ProcessUserCustomMenu项
                const userMenuItem = userMenuItems.find(item => item?.key === key);
                if (userMenuItem && userMenuItem.onClick) {
                    userMenuItem.onClick();
                }
                break;
        }
        // Close下拉Menu
        setDropdownVisible(false);
    }, [navigate, onLogout, userMenuItems, t, modal]);

    // 合并UserMenu和SettingsMenu
    const combinedMenuItems: MenuProps['items'] = [
        ...userMenuItems.map(item => ({
            ...item,
            onClick: () => handleMenuClick(item?.key as string),
        })),
        { type: 'divider' },
        {
            key: 'settings',
            icon: <SettingOutlined />,
            label: t('common.settings'),
            onClick: () => handleMenuClick('settings'),
        },
        {
            key: 'theme',
            icon: <SkinOutlined />,
            label: t('pages.settings.theme'),
            children: [
                {
                    key: 'theme-light',
                    label: t('pages.settings.themeLight'),
                    onClick: () => handleThemeChange('light'),
                },
                {
                    key: 'theme-dark',
                    label: t('pages.settings.themeDark'),
                    onClick: () => handleThemeChange('dark'),
                },
                {
                    key: 'theme-system',
                    label: t('pages.settings.themeSystem'),
                    onClick: () => handleThemeChange('system'),
                },
            ],
        },
        {
            key: 'language',
            icon: <GlobalOutlined />,
            label: t('pages.settings.language'),
            children: [
                {
                    key: 'language-zh-CN',
                    label: t('languages.zh-CN'),
                    onClick: () => handleLanguageChange('zh-CN'),
                },
                {
                    key: 'language-en-US',
                    label: t('languages.en-US'),
                    onClick: () => handleLanguageChange('en-US'),
                },
            ],
        },
        { type: 'divider' },
        {
            key: 'logout',
            icon: <LogoutOutlined />,
            label: t('common.logout'),
            onClick: () => handleMenuClick('logout'),
        },
    ];
    
    return (
        <StyledHeader>
            <StyledButton
                type="text"
                icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                onClick={onCollapse}
                style={{ fontSize: '18px', width: 64, height: 64 }}
            />
            <HeaderRight>
                <StyledBadge count={totalUnreadCount > 0 ? totalUnreadCount : 0} overflowCount={99}>
                    <StyledButton
                        type="text"
                        icon={<BellOutlined />}
                        style={{ fontSize: '18px' }}
                        onClick={() => navigate('/chat')}
                    />
                </StyledBadge>
                <Dropdown
                    menu={{ items: combinedMenuItems }}
                    trigger={['click']}
                    open={dropdownVisible}
                    onOpenChange={setDropdownVisible}
                    placement="bottomRight"
                    overlayClassName="user-profile-dropdown"
                    overlayStyle={{
                        zIndex: 1050,
                        minWidth: 200,
                    }}
                    getPopupContainer={() => document.body}
                >
                    <UserSection
                        onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            setDropdownVisible(!dropdownVisible);
                        }}
                    >
                        <StyledAvatar icon={<UserOutlined />} />
                        <span>{username || t('common.username')}</span>
                    </UserSection>
                </Dropdown>
            </HeaderRight>
        </StyledHeader>
    );
};

export default AppHeader; 