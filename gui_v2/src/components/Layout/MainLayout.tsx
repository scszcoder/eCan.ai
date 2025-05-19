import React, { useState } from 'react';
import { Layout, Menu, Input, Button } from 'antd';
import {
    MenuFoldOutlined,
    MenuUnfoldOutlined,
    SearchOutlined,
    PlusOutlined,
    SyncOutlined,
    MessageOutlined,
    ScheduleOutlined,
    RobotOutlined,
    TeamOutlined,
    CarOutlined,
    SettingOutlined,
    BarChartOutlined,
    AppstoreOutlined,
    ToolOutlined,
    EditOutlined,
} from '@ant-design/icons';
import styled from '@emotion/styled';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';

const { Header, Sider, Content } = Layout;

const StyledLayout = styled(Layout)`
    min-height: 100vh;
    background: #f0f2f5;
`;

const StyledHeader = styled(Header)`
    padding: 0 16px;
    background: #fff;
    display: flex;
    align-items: center;
    gap: 16px;
    border-bottom: 1px solid #e8e8e8;
    height: 48px;
    line-height: 48px;
`;

const SearchInput = styled(Input)`
    width: 300px;
    border-radius: 4px;
    .ant-input {
        background: #f5f5f5;
        border: 1px solid #d9d9d9;
        &:hover, &:focus {
            background: #fff;
        }
    }
`;

const StyledSider = styled(Sider)`
    background: #fff;
    border-right: 1px solid #e8e8e8;
    .ant-menu {
        border-right: none;
    }
    .ant-menu-item {
        margin: 4px 8px;
        border-radius: 4px;
        &:hover {
            background: #f5f5f5;
        }
        &.ant-menu-item-selected {
            background: #e6f7ff;
            color: #1890ff;
        }
    }
`;

const StyledContent = styled(Content)`
    margin: 16px;
    padding: 16px;
    background: #fff;
    border-radius: 4px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
    min-height: calc(100vh - 80px);
`;

const menuItems = [
    {
        key: 'chat',
        icon: <MessageOutlined />,
        label: 'Chat',
    },
    {
        key: 'schedule',
        icon: <ScheduleOutlined />,
        label: 'Schedule',
    },
    {
        key: 'skills',
        icon: <RobotOutlined />,
        label: 'Skills',
    },
    {
        key: 'skill-editor',
        icon: <EditOutlined />,
        label: 'SkillEditor',
    },
    {
        key: 'agents',
        icon: <TeamOutlined />,
        label: 'Agents',
    },
    {
        key: 'vehicles',
        icon: <CarOutlined />,
        label: 'Vehicles',
    },
    {
        key: 'settings',
        icon: <SettingOutlined />,
        label: 'Settings',
    },
    {
        key: 'analytics',
        icon: <BarChartOutlined />,
        label: 'Analytics',
    },
    {
        key: 'apps',
        icon: <AppstoreOutlined />,
        label: 'Apps',
    },
    {
        key: 'tools',
        icon: <ToolOutlined />,
        label: 'Tools',
    },
];

const MainLayout: React.FC = () => {
    const [collapsed, setCollapsed] = useState(false);
    const navigate = useNavigate();
    const location = useLocation();

    const handleMenuClick = (key: string) => {
        navigate(`/main/${key}`);
    };

    return (
        <StyledLayout>
            <StyledHeader>
                <Button
                    type="text"
                    icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                    onClick={() => setCollapsed(!collapsed)}
                    style={{ fontSize: '16px' }}
                />
                <SearchInput
                    placeholder="Search..."
                    prefix={<SearchOutlined />}
                />
                <Button
                    type="text"
                    icon={<PlusOutlined />}
                    style={{ fontSize: '16px' }}
                />
                <Button
                    type="text"
                    icon={<SyncOutlined />}
                    style={{ fontSize: '16px' }}
                />
            </StyledHeader>
            <Layout>
                <StyledSider trigger={null} collapsible collapsed={collapsed} width={200}>
                    <Menu
                        theme="light"
                        mode="inline"
                        selectedKeys={[location.pathname.split('/')[2] || 'chat']}
                        items={menuItems}
                        onClick={({ key }) => handleMenuClick(key)}
                    />
                </StyledSider>
                <StyledContent>
                    <Outlet />
                </StyledContent>
            </Layout>
        </StyledLayout>
    );
};

export default MainLayout; 