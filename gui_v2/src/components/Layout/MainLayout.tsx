import React, { useState, useEffect } from 'react';
import { Layout, Menu, Button, Avatar, Dropdown, Space, Badge, Typography } from 'antd';
import type { MenuProps } from 'antd';
import {
    MenuFoldOutlined,
    MenuUnfoldOutlined,
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
    BellOutlined,
    UserOutlined,
    OrderedListOutlined,
    LogoutOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation } from 'react-router-dom';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';

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
    height: 32px;
    margin: 16px;
    background: rgba(255, 255, 255, 0.2);
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-size: 18px;
    font-weight: bold;
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

    return (
        <StyledLayout>
            <Sider trigger={null} collapsible collapsed={collapsed}>
                <Logo>ECBOT</Logo>
                <Menu
                    theme="dark"
                    mode="inline"
                    selectedKeys={[location.pathname]}
                    items={menuItems}
                    onClick={({ key }) => navigate(key)}
                />
            </Sider>
            <Layout>
                <StyledHeader>
                    <Button
                        type="text"
                        icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                        onClick={() => setCollapsed(!collapsed)}
                        style={{
                            fontSize: '16px',
                            width: 64,
                            height: 64,
                        }}
                    />
                    <HeaderRight>
                        <Badge count={5}>
                            <Button
                                type="text"
                                icon={<BellOutlined />}
                                style={{ fontSize: '16px' }}
                            />
                        </Badge>
                        <Dropdown
                            menu={{
                                items: userMenuItems,
                            }}
                        >
                            <Space style={{ cursor: 'pointer' }}>
                                <Avatar icon={<UserOutlined />} />
                                <span>{t('common.username')}</span>
                            </Space>
                        </Dropdown>
                    </HeaderRight>
                </StyledHeader>
                <StyledContent>{children}</StyledContent>
            </Layout>
        </StyledLayout>
    );
};

export default MainLayout; 