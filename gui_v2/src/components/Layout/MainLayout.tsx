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
    ApartmentOutlined
} from '@ant-design/icons';
import { useNavigate, useLocation } from 'react-router-dom';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import AppSider from './AppSider';
import AppHeader from './AppHeader';
import AppContent from './AppContent';
import BackgroundInitIndicator from '../BackgroundInitIndicator';
import PageBackBreadcrumb from './PageBackBreadcrumb';
import QuickActionMenu from './QuickActionMenu';
import A11yFocusGuard from '../Common/A11yFocusGuard';
import { logoutManager } from '../../services/LogoutManager';


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
        try {
            // 使用新的LogoutManager进行统一的logout处理
            await logoutManager.logout();

            // 跳转到登录页面
            window.location.replace('/login');
        } catch (error) {
            console.error('Logout error:', error);
            // 即使logout过程中出现错误，也要跳转到登录页面
            window.location.replace('/login');
        }
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
        { key: '/orgs', icon: <ApartmentOutlined />, label: t('menu.organizations') },
        { key: '/settings', icon: <SettingOutlined />, label: t('menu.settings') },
        { key: '/dashboard', icon: <DashboardOutlined />, label: t('menu.dashboard') },
        { key: '/console', icon: <AlignLeftOutlined />, label: t('menu.console') },
        { key: '/tests', icon: <ExperimentOutlined />, label: t('menu.tests') },
    ], [t]);

    const userMenuItems = React.useMemo<MenuProps['items']>(() => [
        { key: 'profile', icon: <UserOutlined />, label: t('common.profile') },
    ], [t]) as NonNullable<MenuProps['items']>;

    const onMenuClick = ({ key }: { key: string }) => navigate(key);

    const isSkillEditor = location.pathname.startsWith('/skill_editor');

    return (
        <StyledLayout>
            <A11yFocusGuard />
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
                    {!isSkillEditor && (
                        <div style={{ 
                            display: 'flex', 
                            alignItems: 'center', 
                            justifyContent: 'space-between',
                            position: 'absolute', 
                            top: 0, 
                            left: 0, 
                            right: 0,
                            zIndex: 10,
                            padding: '12px 24px',
                            background: 'var(--bg-secondary, rgba(15, 23, 42, 0.8))',
                            backdropFilter: 'blur(12px)',
                            borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
                            boxShadow: '0 2px 8px rgba(0, 0, 0, 0.15)'
                        }}>
                            <PageBackBreadcrumb />
                            <QuickActionMenu />
                        </div>
                    )}
                    <AppContent>{children}</AppContent>
                </div>
            </StyledInnerLayout>
            {/* Background initialization indicator */}
            <BackgroundInitIndicator />
        </StyledLayout>
    );
};

export default MainLayout; 