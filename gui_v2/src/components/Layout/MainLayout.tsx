import React, { useState, useEffect } from 'react';
import { Layout, Menu, Button, Avatar, Dropdown, Space, Badge, Typography } from 'antd';
import type { MenuProps } from 'antd';
import {
    MenuFoldOutlined,
    MenuUnfoldOutlined,
    LeftSquareFilled,
    RightSquareFilled,
    DashboardOutlined,
    CarOutlined,
    ClusterOutlined,
    CalendarOutlined,
    MessageOutlined,
    RobotOutlined,
    ReadOutlined,
    EditOutlined,
    TeamOutlined,
    BarChartOutlined,
    AppstoreOutlined,
    ToolOutlined,
    SettingOutlined,
    BellOutlined,
    UserOutlined,
    OrderedListOutlined,
    LogoutOutlined,
    AlignLeftOutlined,
    SafetyCertificateOutlined,
    ExperimentOutlined
} from '@ant-design/icons';
import { useNavigate, useLocation } from 'react-router-dom';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import AppSider from './AppSider';
import AppHeader from './AppHeader';
import AppContent from './AppContent';

const { Header, Sider, Content } = Layout;
const { Title } = Typography;

const StyledLayout = styled(Layout)`
    min-height: 100vh;
`;

const StyledHeader = styled(Header)`
    padding: 0 24px;
    background: #fff;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
`;

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

const StyledContent = styled(Content)`
    margin: 24px 16px;
    padding: 24px;
    background: #fff;
    min-height: 280px;
    border-radius: 8px;
`;

const HeaderRight = styled.div`
    display: flex;
    align-items: center;
    gap: 16px;
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
        localStorage.removeItem('isAuthenticated');
        localStorage.removeItem('userRole');
        
        window.location.replace('/login');
    };

    const handleLogoClick = () => {
        navigate('/');
    };

    const menuItems = React.useMemo<MenuProps['items']>(() => [
        {
            key: '/',
            icon: <DashboardOutlined />,
            label: t('menu.dashboard'),
        },
        {
            key: '/vehicles',
            icon: <CarOutlined />,
            label: t('menu.vehicles'),
        },
        {
            key: '/schedule',
            icon: <CalendarOutlined />,
            label: t('menu.schedule'),
        },
        {
            key: '/chat',
            icon: <MessageOutlined />,
            label: t('menu.chat'),
        },
        {
            key: '/skills',
            icon: <RobotOutlined />,
            label: t('menu.skills'),
        },
        {
            key: '/skill_editor',
            icon: <EditOutlined />,
            label: t('menu.skill_editor'),
        },
        {
            key: '/agents',
            icon: <TeamOutlined />,
            label: t('menu.agents'),
        },
        {
            key: '/analytics',
            icon: <BarChartOutlined />,
            label: t('menu.analytics'),
        },
        {
            key: '/apps',
            icon: <AppstoreOutlined />,
            label: t('menu.apps'),
        },
        {
            key: '/tasks',
            icon: <OrderedListOutlined />,
            label: t('menu.tasks'),
        },
        {
            key: '/tools',
            icon: <ToolOutlined />,
            label: t('menu.tools'),
        },
        {
            key: '/settings',
            icon: <SettingOutlined />,
            label: t('menu.settings'),
        },
        {
            key: '/console',
            icon: <AlignLeftOutlined />,
            label: t('menu.console'),
        },
        {
            key: '/knowledge',
            icon: <ReadOutlined />,
            label: t('menu.knowledge'),
        },
        {
            key: '/tests',
            icon: <ExperimentOutlined />,
            label: t('menu.tests'),
        },
    ], [t]);

    const userMenuItems = React.useMemo<MenuProps['items']>(() => [
        {
            key: 'profile',
            icon: <UserOutlined />,
            label: t('common.profile'),
        },
        {
            key: 'settings',
            icon: <SettingOutlined />,
            label: t('common.settings'),
        },
        {
            type: 'divider',
        },
        {
            key: 'logout',
            icon: <LogoutOutlined />,
            label: t('common.logout'),
            onClick: handleLogout,
        },
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
            <Layout>
                <AppHeader
                    collapsed={collapsed}
                    onCollapse={() => setCollapsed(!collapsed)}
                    userMenuItems={userMenuItems}
                    onLogout={handleLogout}
                />
                <AppContent>{children}</AppContent>
            </Layout>
        </StyledLayout>
    );
};

export default MainLayout; 