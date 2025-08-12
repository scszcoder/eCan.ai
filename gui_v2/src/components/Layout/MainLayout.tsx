import React, { useState, useEffect } from 'react';
import { Layout } from 'antd';
import type { MenuProps } from 'antd';
import {
    DashboardOutlined,
    CarOutlined,
    CalendarOutlined,
    MessageOutlined,
    RobotOutlined,
    EditOutlined,
    TeamOutlined,
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
import PageBackBreadcrumb from './PageBackBreadcrumb';
import { get_ipc_api } from '@/services/ipc_api';


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

    const handleLogout = async () => {
        pageRefreshManager.disable();
        // 调用后端登出接口
        try {
            await get_ipc_api().logout();
        } catch (e) {
            // 可以根据需要处理错误
            console.error('Logout API error:', e);
        }
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
        { key: '/agents', icon: <TeamOutlined />, label: t('menu.agents') },
        { key: '/chat', icon: <MessageOutlined />, label: t('menu.chat') },
        { key: '/tasks', icon: <OrderedListOutlined />, label: t('menu.tasks') },
        { key: '/skills', icon: <RobotOutlined />, label: t('menu.skills') },
        { key: '/skill_editor', icon: <EditOutlined />, label: t('menu.skill_editor') },
        { key: '/schedule', icon: <CalendarOutlined />, label: t('menu.schedule') },
        { key: '/vehicles', icon: <CarOutlined />, label: t('menu.vehicles') },
        { key: '/tools', icon: <ToolOutlined />, label: t('menu.tools') },
        { key: '/knowledge', icon: <ReadOutlined />, label: t('menu.knowledge') },
        { key: '/settings', icon: <SettingOutlined />, label: t('menu.settings') },
        { key: '/dashboard', icon: <DashboardOutlined />, label: t('menu.dashboard') },
        { key: '/console', icon: <AlignLeftOutlined />, label: t('menu.console') },
        { key: '/tests', icon: <ExperimentOutlined />, label: t('menu.tests') },
    ], [t]);

    const userMenuItems = React.useMemo<MenuProps['items']>(() => [
        { key: 'profile', icon: <UserOutlined />, label: t('common.profile') },
        { key: 'settings', icon: <SettingOutlined />, label: t('common.settings') },
        { type: 'divider' },
        { key: 'logout', icon: <LogoutOutlined />, label: t('common.logout'), onClick: handleLogout },
    ], [t]) || [];

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
                <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', position: 'relative' }}>
                    <PageBackBreadcrumb />
                    <AppContent>{children}</AppContent>
                </div>
            </StyledInnerLayout>
        </StyledLayout>
    );
};

export default MainLayout; 