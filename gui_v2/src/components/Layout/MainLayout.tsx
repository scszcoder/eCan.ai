import React, { useState, useEffect } from 'react';
import { Layout, Button } from 'antd';
import type { MenuProps } from 'antd';
import {
    DashboardOutlined,
    LaptopOutlined,
    CalendarOutlined,
    MessageOutlined,
    ThunderboltOutlined,
    EditOutlined,
    TeamOutlined,
    ToolOutlined,
    SettingOutlined,
    OrderedListOutlined,
    AlignLeftOutlined,
    ReadOutlined,
    ExperimentOutlined,
    CustomerServiceOutlined,
    UserOutlined,
    IdcardOutlined,
    ApartmentOutlined,
    ShopOutlined,
    ShoppingOutlined,
    PrinterOutlined,
    DatabaseOutlined,
    AppstoreOutlined
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
import FastDeployPanel from '../FastDeploy/FastDeployPanel';
import A11yFocusGuard from '../Common/A11yFocusGuard';
import { useAccountStore } from '../../stores/accountStore';
import { logoutManager } from '../../services/LogoutManager';
import { isDesktopPlatform, isWebPlatform } from '../../config/platform';


const StyledLayout = styled(Layout)`
    min-height: 100vh;
`;

const StyledInnerLayout = styled(Layout)`
    height: 100vh;
    display: flex;
    flex-direction: column;
`;

const DEV_MENU_KEYS = new Set(['/tests', '/chat-test']);

const MainLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [collapsed, setCollapsed] = useState(false);
    const [searchQuery, setSearchQuery] = useState('');
    const [fastDeployOpen, setFastDeployOpen] = useState(false);
    const [showDevMenu, setShowDevMenu] = useState(false);
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
    
    // Listen for search query changes via CustomEvent (event-driven, no polling)
    useEffect(() => {
        const handler = (e: Event) => {
            const query = (e as CustomEvent).detail ?? '';
            setSearchQuery(query);
        };
        window.addEventListener('agentsSearchQueryChanged', handler);

        // Seed initial value in case it was set before this component mounted
        const initial = (window as any).__agentsSearchQuery;
        if (initial !== undefined) {
            setSearchQuery(initial);
        }

        return () => window.removeEventListener('agentsSearchQueryChanged', handler);
    }, []);
    
    // ProcessSearch变化
    const handleSearchChange = (query: string) => {
        setSearchQuery(query);
        // Keep window global for backward compat + dispatch event for listeners
        (window as any).__agentsSearchQuery = query;
        window.dispatchEvent(new CustomEvent('agentsSearchQueryChanged', { detail: query }));
    };

    useEffect(() => {
        const savedLanguage = localStorage.getItem('i18nextLng');
        if (savedLanguage && savedLanguage !== i18n.language) {
            i18n.changeLanguage(savedLanguage);
        }
    }, [i18n]);

    // Ctrl+Shift+T toggles visibility of Test / Chat Test sidebar items
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.ctrlKey && e.shiftKey && e.key === 'T') {
                e.preventDefault();
                setShowDevMenu(prev => !prev);
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, []);

    // Periodic account-info refresh (2026-08-31): fetch once shortly after
    // load, then every 20 minutes, so the fund balance and verification flags
    // stay current without a manual Account-page refresh (customer report:
    // top-ups weren't reflected). Feeds the low-fund banner + red-flag badge.
    useEffect(() => {
        const { fetchAccountInfo } = useAccountStore.getState();
        const initial = setTimeout(() => { void fetchAccountInfo(); }, 15_000);
        const interval = setInterval(() => { void fetchAccountInfo(); }, 20 * 60_000);
        return () => { clearTimeout(initial); clearInterval(interval); };
    }, []);

    // Trigger test ads after login initialization completes
    // useEffect(() => {
    //     const timer = setTimeout(() => {
    //         console.log('[MainLayout] Triggering test ads for 1 minute');
    //         pushTestAds(60000);
    //     }, 1000);
    //     return () => clearTimeout(timer);
    // }, []);

    const handleLogout = async () => {
        try {
            // Navigate to /login FIRST so the UI flip is instant.
            // ``logoutManager.logout()`` is now fast (~50-150ms): it runs
            // frontend cleanup in parallel and fires the backend IPC
            // fire-and-forget.  This means the user sees the login page
            // appear within one animation frame of clicking 确认 — no
            // "卡顿" (freeze) while we wait for the backend.
            navigate('/login', { replace: true });

            // Run the full cleanup after navigation so the current page's
            // React tree unmounts cleanly and any async effects have a
            // chance to settle.  Errors are swallowed — logout is
            // best-effort; the user is already at /login.
            await logoutManager.logout();
        } catch (error) {
            console.error('Logout error:', error);
            // navigate('/login') is already called above, but in case
            // an exception escapes the try block somehow, do it again.
            navigate('/login', { replace: true });
        }
    };


    const menuItems = React.useMemo<MenuProps['items']>(() => {
        const isDesktop = isDesktopPlatform();
        const isWeb = isWebPlatform();

        return [
            { key: '/agents', icon: <TeamOutlined />, label: t('menu.agents') },
            { key: '/chat', icon: <MessageOutlined />, label: t('menu.chat') },
            { key: '/tasks', icon: <OrderedListOutlined />, label: t('menu.tasks') },
            { key: '/skills', icon: <ThunderboltOutlined />, label: t('menu.skills') },
            { key: '/skill_editor', icon: <EditOutlined />, label: t('menu.skill_editor') },
            { key: '/schedule', icon: <CalendarOutlined />, label: t('menu.schedule') },
            { key: '/orgs', icon: <ApartmentOutlined />, label: t('menu.organizations') },
            { key: '/vehicles', icon: <LaptopOutlined />, label: t('menu.vehicles') },
            { key: '/tools', icon: <ToolOutlined />, label: t('menu.tools') },
            { key: '/prompts', icon: <ReadOutlined />, label: t('menu.prompts') },
            { key: '/avatars', icon: <UserOutlined />, label: t('menu.avatars') },
            { key: '/warehouses', icon: <ShopOutlined />, label: t('menu.warehouses') },
            { key: '/products', icon: <ShoppingOutlined />, label: t('menu.products') },
            ...(!isWeb ? [{ key: '/knowledge-ported', icon: <ReadOutlined />, label: t('menu.knowledge') }] : []),
            { key: '/shipping-label', icon: <PrinterOutlined />, label: t('menu.shipping_label') },
            ...(!isDesktop ? [{ key: '/rag', icon: <DatabaseOutlined />, label: 'RAG Documents' }] : []),
            { key: '/plugins', icon: <AppstoreOutlined />, label: t('menu.plugins') },
            { key: '/settings', icon: <SettingOutlined />, label: t('menu.settings') },
            { key: '/dashboard', icon: <DashboardOutlined />, label: t('menu.dashboard') },
            { key: '/console', icon: <AlignLeftOutlined />, label: t('menu.console') },
            { key: '/tests', icon: <ExperimentOutlined />, label: t('menu.tests') },
            { key: '/chat-test', icon: <CustomerServiceOutlined />, label: t('menu.chat_test') },
        ];
    }, [t]);

    // Filter out dev/test menu items unless toggled visible via Ctrl+Shift+T
    const filteredMenuItems = React.useMemo(() => {
        if (showDevMenu) return menuItems;
        return menuItems?.filter(item => item && !DEV_MENU_KEYS.has(item.key as string)) ?? [];
    }, [menuItems, showDevMenu]);

    const userMenuItems = React.useMemo<MenuProps['items']>(() => [
        { key: 'profile', icon: <UserOutlined />, label: t('common.profile') },
        {
            key: 'account',
            icon: <IdcardOutlined />,
            label: t('common.account'),
            onClick: () => navigate('/account'),
        },
    ], [navigate, t]) as NonNullable<MenuProps['items']>;

    // Prevent navigation if already on the target route
    const onMenuClick = ({ key }: { key: string }) => {
        const currentPath = location.pathname;
        let targetPath = key;
        
        // IfClick Agents Menu，Restore到最后访问的 agents Path
        if (key === '/agents') {
            targetPath = lastAgentsPathRef.current;
        }
        
        // Only skip navigation if exactly on the same path
        // Don't skip for different menu items even if current path starts with target
        const shouldSkip = currentPath === targetPath || 
            (key === '/agents' && currentPath.startsWith('/agents'));
        
        if (!shouldSkip) {
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
                menuItems={filteredMenuItems}
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
                            <Button
                                type={fastDeployOpen ? 'primary' : 'default'}
                                icon={<ThunderboltOutlined />}
                                onClick={() => setFastDeployOpen((v) => !v)}
                                style={{ margin: '0 12px' }}
                            >
                                {t('pages.agents.fast_deploy', 'Fast Deploy')}
                            </Button>
                            <QuickActionMenu />
                        </div>
                    )}
                    {!isSkillEditor && isAgentsPage && (
                        <FastDeployPanel open={fastDeployOpen} onClose={() => setFastDeployOpen(false)} />
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