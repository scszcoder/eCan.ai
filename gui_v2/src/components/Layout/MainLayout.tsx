import React, { useState, useEffect } from 'react';
import { Layout, Typography } from 'antd';
import type { MenuProps } from 'antd';
import {
    DashboardOutlined,
    CarOutlined,
    CalendarOutlined,
    MessageOutlined,
    RobotOutlined,
    EditOutlined,
    TeamOutlined,
    BarChartOutlined,
    AppstoreOutlined,
    ToolOutlined,
    SettingOutlined,
    OrderedListOutlined,
    AlignLeftOutlined,
    ReadOutlined,
    ExperimentOutlined,
    UserOutlined,
    LogoutOutlined
} from '@ant-design/icons';
import { useNavigate, useLocation } from 'react-router-dom';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { pageRefreshManager } from '../../services/events/PageRefreshManager';
import { useUserStore } from '../../stores/userStore';
import AppSider from './AppSider';
import AppHeader from './AppHeader';
import AppContent from './AppContent';

const { Title } = Typography;

const StyledLayout = styled(Layout)`
    min-height: 100vh;
`;

const StyledInnerLayout = styled(Layout)`
    height: 100vh;
    display: flex;
    flex-direction: column;
`;

const MainLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [collapsed, setCollapsed] = useState(false);
    const navigate = useNavigate();
    const location = useLocation();
    const { t, i18n } = useTranslation();

    useEffect(() => {
        const savedLanguage = localStorage.getItem('i18nextLng');
        if (savedLanguage && savedLanguage !== i18n.language) {
            i18n.changeLanguage(savedLanguage);
        }
    }, [i18n]);

    const handleLogout = () => {
        pageRefreshManager.disable();
        
        // 清理localStorage
        localStorage.removeItem('isAuthenticated');
        localStorage.removeItem('userRole');
        localStorage.removeItem('token');
        localStorage.removeItem('username');
        
        // 清理userStore
        useUserStore.getState().setUsername(null);
        
        window.location.replace('/login');
    };

    const handleLogoClick = () => {
        navigate('/');
    };

    const menuItems = React.useMemo<MenuProps['items']>(() => [
        {
            key: '/',
            icon: <DashboardOutlined />, label: t('menu.dashboard'),
        },
        { key: '/vehicles', icon: <CarOutlined />, label: t('menu.vehicles') },
        { key: '/schedule', icon: <CalendarOutlined />, label: t('menu.schedule') },
        { key: '/chat', icon: <MessageOutlined />, label: t('menu.chat') },
        { key: '/skills', icon: <RobotOutlined />, label: t('menu.skills') },
        { key: '/skill_editor', icon: <EditOutlined />, label: t('menu.skill_editor') },
        { key: '/agents', icon: <TeamOutlined />, label: t('menu.agents') },
        { key: '/analytics', icon: <BarChartOutlined />, label: t('menu.analytics') },
        { key: '/apps', icon: <AppstoreOutlined />, label: t('menu.apps') },
        { key: '/tasks', icon: <OrderedListOutlined />, label: t('menu.tasks') },
        { key: '/tools', icon: <ToolOutlined />, label: t('menu.tools') },
        { key: '/settings', icon: <SettingOutlined />, label: t('menu.settings') },
        { key: '/console', icon: <AlignLeftOutlined />, label: t('menu.console') },
        { key: '/knowledge', icon: <ReadOutlined />, label: t('menu.knowledge') },
        { key: '/tests', icon: <ExperimentOutlined />, label: t('menu.tests') },
    ], [t]);

    const userMenuItems = React.useMemo<MenuProps['items']>(() => [
        { key: 'profile', icon: <UserOutlined />, label: t('common.profile') },
        { key: 'settings', icon: <SettingOutlined />, label: t('common.settings') },
        { type: 'divider' },
        { key: 'logout', icon: <LogoutOutlined />, label: t('common.logout'), onClick: handleLogout },
    ], [t]);

    const onMenuClick = ({ key }: { key: string }) => navigate(key);

    return (
        <StyledLayout>
            <AppSider
                collapsed={collapsed}
                onLogoClick={handleLogoClick}
                menuItems={menuItems}
                selectedKey={location.pathname}
                onMenuClick={onMenuClick}
            />
            <StyledInnerLayout>
                <AppHeader
                    collapsed={collapsed}
                    onCollapse={() => setCollapsed(!collapsed)}
                    userMenuItems={userMenuItems}
                    onLogout={handleLogout}
                />
                <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
                    <AppContent>{children}</AppContent>
                </div>
            </StyledInnerLayout>
        </StyledLayout>
    );
};

export default MainLayout; 