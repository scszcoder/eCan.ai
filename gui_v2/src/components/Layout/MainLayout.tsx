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
    ApartmentOutlined,
    ShopOutlined,
    ShoppingOutlined
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
    
    // 记住最后访问的 agents Path（Used for从其他Page返回时Restore）
    const lastAgentsPathRef = React.useRef<string>('/agents');

    // ListenPath变化，记录最后访问的 agents Path
    useEffect(() => {
        if (location.pathname.startsWith('/agents')) {
            lastAgentsPathRef.current = location.pathname;
        };
    }, [location.pathname]);
    
    // 从 window 对象GetSearchStatus（由 OrgNavigator Settings）
    // Optimize：RemoveDependency项避免重复Create定时器，增加轮询Interval减少 CPU 占用
    useEffect(() => {
        const interval = setInterval(() => {
            const query = (window as any).__agentsSearchQuery;
            if (query !== undefined && query !== searchQuery) {
                setSearchQuery(query);
            }
        }, 300); // 从 100ms 增加到 300ms，减少 CPU 占用
        return () => clearInterval(interval);
    }, []); // Remove searchQuery Dependency，避免每次Status变化都重新Create定时器
    
    // ProcessSearch变化
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
            // 使用新的LogoutManager进行统一的logoutProcess
            await logoutManager.logout();

            // 跳转到LoginPage - 使用navigate而不是window.location.replace
            // 这样可以避免在本地文件模式下尝试加载file:///login的问题
            navigate('/login', { replace: true });
        } catch (error) {
            console.error('Logout error:', error);
            // 即使logout过程中出现Error，也要跳转到LoginPage
            navigate('/login', { replace: true });
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
        { key: '/orgs', icon: <ApartmentOutlined />, label: t('menu.organizations') },
        { key: '/vehicles', icon: <CarOutlined />, label: t('menu.vehicles') },
        { key: '/tools', icon: <ToolOutlined />, label: t('menu.tools') },
        { key: '/prompts', icon: <ReadOutlined />, label: t('menu.prompts') },
        { key: '/warehouses', icon: <ShopOutlined />, label: t('menu.warehouses') },
        { key: '/products', icon: <ShoppingOutlined />, label: t('menu.products') },
        { key: '/knowledge-ported', icon: <ReadOutlined />, label: t('menu.knowledge') },
        { key: '/settings', icon: <SettingOutlined />, label: t('menu.settings') },
        { key: '/dashboard', icon: <DashboardOutlined />, label: t('menu.dashboard') },

        { key: '/console', icon: <AlignLeftOutlined />, label: t('menu.console') },
        { key: '/tests', icon: <ExperimentOutlined />, label: t('menu.tests') },
    ], [t]);

    const userMenuItems = React.useMemo<MenuProps['items']>(() => [
        { key: 'profile', icon: <UserOutlined />, label: t('common.profile') },
    ], [t]) as NonNullable<MenuProps['items']>;

    // Prevent navigation if already on the target route
    const onMenuClick = ({ key }: { key: string }) => {
        const currentPath = location.pathname;
        let targetPath = key;
        
        // IfClick Agents Menu，Restore到最后访问的 agents Path
        if (key === '/agents') {
            targetPath = lastAgentsPathRef.current;
        }
        
        // Only navigate if not already on the target path
        if (currentPath !== targetPath && !currentPath.startsWith(targetPath + '/')) {
            navigate(targetPath);
        }
    };

    const isSkillEditor = location.pathname.startsWith('/skill_editor');
    // Check是否在 agents 相关Page，只有这些Page才DisplayRightFastOperationMenu
    const isAgentsPage = location.pathname.startsWith('/agents');

    // Calculate selected menu key based on current pathname
    // Match the longest matching menu key to handle nested routes
    const getSelectedMenuKey = () => {
        const pathname = location.pathname;
        // Find the longest matching menu key
        let selectedKey = '/agents'; // default
        let maxMatchLength = 0;
        
        if (menuItems) {
            menuItems.forEach(item => {
                if (item && item.key) {
                    const key = item.key as string;
                    if (pathname === key || pathname.startsWith(key + '/')) {
                        if (key.length > maxMatchLength) {
                            maxMatchLength = key.length;
                            selectedKey = key;
                        }
                    }
                }
            });
        }
        
        return selectedKey;
    };

    return (
        <StyledLayout>
            <A11yFocusGuard />
            <AppSider
                collapsed={collapsed}
                onLogoClick={handleLogoClick}
                menuItems={menuItems}
                selectedKey={getSelectedMenuKey()}
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