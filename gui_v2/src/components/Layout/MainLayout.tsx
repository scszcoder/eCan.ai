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
    const [searchQuery, setSearchQuery] = useState('');
    const navigate = useNavigate();
    const location = useLocation();
    const { t, i18n } = useTranslation();
    
    // 记住最后访问的 agents 路径（用于从其他页面返回时恢复）
    const lastAgentsPathRef = React.useRef<string>('/agents');
    
    // 监听路径变化，记录最后访问的 agents 路径
    useEffect(() => {
        if (location.pathname.startsWith('/agents')) {
            lastAgentsPathRef.current = location.pathname;
        }
    }, [location.pathname]);
    
    // 从 window 对象获取搜索状态（由 OrgNavigator 设置）
    // 优化：移除依赖项避免重复创建定时器，增加轮询间隔减少 CPU 占用
    useEffect(() => {
        const interval = setInterval(() => {
            const query = (window as any).__agentsSearchQuery;
            if (query !== undefined && query !== searchQuery) {
                setSearchQuery(query);
            }
        }, 300); // 从 100ms 增加到 300ms，减少 CPU 占用
        return () => clearInterval(interval);
    }, []); // 移除 searchQuery 依赖，避免每次状态变化都重新创建定时器
    
    // 处理搜索变化
    const handleSearchChange = (query: string) => {
        setSearchQuery(query);
        if ((window as any).__setAgentsSearchQuery) {
            (window as any).__setAgentsSearchQuery(query);
        }
    };

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
        { key: '/knowledge-ported', icon: <ReadOutlined />, label: t('menu.knowledge') },
        { key: '/orgs', icon: <ApartmentOutlined />, label: t('menu.organizations') },
        { key: '/settings', icon: <SettingOutlined />, label: t('menu.settings') },
        { key: '/dashboard', icon: <DashboardOutlined />, label: t('menu.dashboard') },
        { key: '/console', icon: <AlignLeftOutlined />, label: t('menu.console') },
        { key: '/tests', icon: <ExperimentOutlined />, label: t('menu.tests') },
    ], [t]);

    const userMenuItems = React.useMemo<MenuProps['items']>(() => [
        { key: 'profile', icon: <UserOutlined />, label: t('common.profile') },
    ], [t]) as NonNullable<MenuProps['items']>;

    const onMenuClick = ({ key }: { key: string }) => {
        // 如果点击 Agents 菜单，恢复到最后访问的 agents 路径
        if (key === '/agents') {
            navigate(lastAgentsPathRef.current);
        } else {
            navigate(key);
        }
    };

    const isSkillEditor = location.pathname.startsWith('/skill_editor');
    // 检查是否在 agents 相关页面，只有这些页面才显示右侧快速操作菜单
    const isAgentsPage = location.pathname.startsWith('/agents');

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
                    {!isSkillEditor && isAgentsPage && (
                        <div style={{ 
                            display: 'flex', 
                            alignItems: 'center', 
                            justifyContent: 'space-between',
                            position: 'absolute', 
                            top: 0, 
                            left: 0, 
                            right: 0,
                            zIndex: 10,
                            padding: '10px 24px',
                            background: 'rgba(30, 41, 59, 0.95)',
                            borderBottom: '1px solid rgba(255, 255, 255, 0.06)',
                            boxShadow: '0 4px 12px rgba(0, 0, 0, 0.2)'
                        }}>
                            <PageBackBreadcrumb 
                                searchQuery={searchQuery}
                                onSearchChange={handleSearchChange}
                            />
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