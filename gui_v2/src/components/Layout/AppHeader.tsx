import React from 'react';
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

    // 处理主题切换
    const handleThemeChange = (value: 'light' | 'dark' | 'system') => {
        changeTheme(value);
        message.success(t('pages.settings.themeChanged'));
    };

    // 处理语言切换
    const handleLanguageChange = async (value: string) => {
        try {
            await i18n.changeLanguage(value);
            changeLanguage(value);
            message.success(t('pages.settings.languageChanged'));
            console.log('当前语言已切换为:', i18n.language);
        } catch (e) {
            message.error(t('pages.settings.languageChangeError'));
            console.error('语言切换失败:', e);
        }
    };

    // 合并用户菜单和设置菜单
    const combinedMenuItems: MenuProps['items'] = [
        ...userMenuItems,
        { type: 'divider' },
        {
            key: 'settings',
            icon: <SettingOutlined />,
            label: t('common.settings'),
            onClick: () => navigate('/settings'),
        },
        {
            key: 'theme',
            icon: <SkinOutlined />,
            label: t('pages.settings.theme'),
            children: [
                {
                    key: 'theme-light',
                    label: t('pages.settings.theme.light'),
                    onClick: () => handleThemeChange('light'),
                },
                {
                    key: 'theme-dark',
                    label: t('pages.settings.theme.dark'),
                    onClick: () => handleThemeChange('dark'),
                },
                {
                    key: 'theme-system',
                    label: t('pages.settings.theme.system'),
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
            onClick: onLogout,
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
                >
                    <Space style={{ cursor: 'pointer' }}>
                        <Avatar icon={<UserOutlined />} />
                        <span>{username || t('common.username')}</span>
                    </Space>
                </Dropdown>
            </HeaderRight>
        </StyledHeader>
    );
};

export default AppHeader; 