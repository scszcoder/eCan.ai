import React, { useState, useCallback } from 'react';
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

const StyledHeader = styled(Header)`
    padding: 0 24px;
    background: #fff;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
`;

const HeaderRight = styled.div`
    display: flex;
    align-items: center;
    gap: 16px;
`;

interface AppHeaderProps {
    collapsed: boolean;
    onCollapse: () => void;
    userMenuItems: any[];
    onLogout: () => void;
}

const AppHeader: React.FC<AppHeaderProps> = ({ collapsed, onCollapse, userMenuItems, onLogout }) => {
    const { t, i18n } = useTranslation();
    const { theme, changeTheme } = useTheme();
    const { changeLanguage } = useLanguage();
    const { message } = App.useApp();
    const username = useUserStore((state) => state.username);
    const navigate = useNavigate();

    // 控制下拉菜单的显示状态
    const [dropdownVisible, setDropdownVisible] = useState(false);

    // 处理主题切换
    const handleThemeChange = useCallback((value: 'light' | 'dark' | 'system') => {
        changeTheme(value);
        message.success(t('pages.settings.themeChanged'));
        // 关闭下拉菜单
        setDropdownVisible(false);
    }, [changeTheme, message, t]);

    // 处理语言切换
    const handleLanguageChange = useCallback(async (value: string) => {
        try {
            await i18n.changeLanguage(value);
            changeLanguage(value);
            message.success(t('pages.settings.languageChanged'));
            console.log('当前语言已切换为:', i18n.language);
        } catch (e) {
            message.error(t('pages.settings.languageChangeError'));
            console.error('语言切换失败:', e);
        }
        // 关闭下拉菜单
        setDropdownVisible(false);
    }, [i18n, changeLanguage, message, t]);

    // 处理菜单项点击
    const handleMenuClick = useCallback((key: string) => {
        switch (key) {
            case 'settings':
                navigate('/settings');
                break;
            case 'logout':
                onLogout();
                break;
            default:
                // 处理用户自定义菜单项
                const userMenuItem = userMenuItems.find(item => item?.key === key);
                if (userMenuItem && userMenuItem.onClick) {
                    userMenuItem.onClick();
                }
                break;
        }
        // 关闭下拉菜单
        setDropdownVisible(false);
    }, [navigate, onLogout, userMenuItems]);

    // 合并用户菜单和设置菜单
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
            <Button
                type="text"
                icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                onClick={onCollapse}
                style={{ fontSize: '16px', width: 64, height: 64 }}
            />
            <HeaderRight>
                <Badge count={5}>
                    <Button
                        type="text"
                        icon={<BellOutlined />}
                        style={{ fontSize: '16px', color: 'white' }}
                    />
                </Badge>
                <Dropdown
                    menu={{ items: combinedMenuItems }}
                    trigger={['click']}
                    open={dropdownVisible}
                    onOpenChange={setDropdownVisible}
                    placement="bottomRight"
                    overlayClassName="user-profile-dropdown"
                    overlayStyle={{
                        zIndex: 1060, // 使用合理的 zIndex，避免 Ant Design 警告
                        minWidth: 200,
                    }}
                    getPopupContainer={(triggerNode) => triggerNode.parentElement || document.body}
                >
                    <Space
                        style={{ cursor: 'pointer' }}
                        onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            setDropdownVisible(!dropdownVisible);
                        }}
                    >
                        <Avatar icon={<UserOutlined />} />
                        <span>{username || t('common.username')}</span>
                    </Space>
                </Dropdown>
            </HeaderRight>
        </StyledHeader>
    );
};

export default AppHeader; 