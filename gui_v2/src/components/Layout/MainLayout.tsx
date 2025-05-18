import React from 'react';
import { Layout, Menu, theme } from 'antd';
import { Outlet, useNavigate } from 'react-router-dom';
import {
    DashboardOutlined,
    SettingOutlined,
    ToolOutlined,
} from '@ant-design/icons';

const { Header, Sider, Content } = Layout;

const MainLayout: React.FC = () => {
    const navigate = useNavigate();
    const {
        token: { colorBgContainer, borderRadiusLG },
    } = theme.useToken();

    const menuItems = [
        {
            key: 'dashboard',
            icon: <DashboardOutlined />,
            label: '仪表盘',
        },
        {
            key: 'tools',
            icon: <ToolOutlined />,
            label: '工具',
        },
        {
            key: 'settings',
            icon: <SettingOutlined />,
            label: '设置',
        },
    ];

    return (
        <Layout style={{ height: '100vh', width: '100vw' }}>
            <Sider
                theme="light"
                breakpoint="lg"
                collapsedWidth="0"
                style={{ height: '100vh' }}
            >
                <div style={{ height: 32, margin: 16, background: 'rgba(0, 0, 0, 0.2)' }} />
                <Menu
                    mode="inline"
                    defaultSelectedKeys={['dashboard']}
                    items={menuItems}
                    onClick={({ key }) => navigate(key)}
                />
            </Sider>
            <Layout style={{ height: '100vh' }}>
                <Header style={{ 
                    padding: 0, 
                    background: colorBgContainer,
                    height: '64px',
                    lineHeight: '64px'
                }} />
                <Content style={{ 
                    margin: '24px 16px',
                    padding: '24px',
                    background: colorBgContainer,
                    borderRadius: borderRadiusLG,
                    minHeight: 'calc(100vh - 112px)',
                    overflow: 'auto'
                }}>
                    <Outlet />
                </Content>
            </Layout>
        </Layout>
    );
};

export default MainLayout; 