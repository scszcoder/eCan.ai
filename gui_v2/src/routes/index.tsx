import React, { Suspense, useEffect } from 'react';
import { Navigate } from 'react-router-dom';
import { Button, Spin } from 'antd';
import MainLayout from '../components/Layout/MainLayout';
import { userStorageManager } from '../services/storage/UserStorageManager';
import { useAppConfig } from '../contexts/AppConfigContext';
import AgentsRouteWrapper from './AgentsRouteWrapper';
import MainRouteWrapper from './MainRouteWrapper';

const VITE_LAZY_RELOAD_KEY = 'vite:lazy-reload-once';

const lazyWithRetry = <T extends React.ComponentType<any>>(
    importer: () => Promise<{ default: T }>
) => React.lazy(async () => {
    try {
        const module = await importer();
        if (typeof window !== 'undefined') {
            sessionStorage.removeItem(VITE_LAZY_RELOAD_KEY);
        }
        return module;
    } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        const isLazyImportFetchError =
            message.includes('Failed to fetch dynamically imported module') ||
            message.includes('Outdated Optimize Dep') ||
            message.includes('Importing a module script failed');

        if (isLazyImportFetchError && typeof window !== 'undefined') {
            const hasRetried = sessionStorage.getItem(VITE_LAZY_RELOAD_KEY) === '1';
            if (!hasRetried) {
                sessionStorage.setItem(VITE_LAZY_RELOAD_KEY, '1');
                window.location.reload();
                await new Promise<never>(() => {});
            }
        }

        throw error;
    }
});

// 懒加载登录组件 - 根据运行时配置选择
const LoginCN = lazyWithRetry(() => import('../pages/Login/LoginCN'));
const LoginIntl = lazyWithRetry(() => import('../pages/Login/Login'));
const AuthCallback = lazyWithRetry(() => import('../pages/AuthCallback'));
const Dashboard = lazyWithRetry(() => import('../pages/Dashboard/Dashboard'));
const Vehicles = lazyWithRetry(() => import('../pages/Vehicles/Vehicles'));
const Schedule = lazyWithRetry(() => import('../pages/Schedule/Schedule'));
const Chat = lazyWithRetry(() => import('../pages/Chat/index'));
const Skills = lazyWithRetry(() => import('../pages/Skills/Skills'));
const SkillEditor = lazyWithRetry(() => import('../pages/SkillEditor/SkillEditor'));
const Analytics = lazyWithRetry(() => import('../pages/Analytics/Analytics'));
const Tasks = lazyWithRetry(() => import('../pages/Tasks/Tasks'));
const Tools = lazyWithRetry(() => import('../pages/Tools/Tools'));
const Settings = lazyWithRetry(() => import('../pages/Settings/Settings'));
const Console = lazyWithRetry(() => import('../pages/Console/Console'));
const KnowledgePorted = lazyWithRetry(() => import('../pages/Knowledge/LightRAGPorted'));
const Tests = lazyWithRetry(() => import('../pages/Tests/Tests'));
const ChatTest = lazyWithRetry(() => import('../pages/ChatTest'));
const OrgNavigator = lazyWithRetry(() => import('../pages/Agents/OrgNavigator'));
const AgentDetails = lazyWithRetry(() => import('../pages/Agents/components/AgentDetails'));
const Orgs = lazyWithRetry(() => import('../pages/Orgs/Orgs'));
const Warehouses = lazyWithRetry(() => import('../pages/Warehouses/Warehouses'));
const Products = lazyWithRetry(() => import('../pages/Products/Products'));
const Prompts = lazyWithRetry(() => import('../pages/Prompts/PromptsEnhanced'));
const Avatars = lazyWithRetry(() => import('../pages/Avatars/Avatars'));
const Account = lazyWithRetry(() => import('../pages/Account/Account'));
const PaymentPlan = lazyWithRetry(() => import('../pages/Account/PaymentPlan'));
const ShippingLabel = lazyWithRetry(() => import('../pages/ShippingLabel/ShippingLabel'));
const RAGDocuments = lazyWithRetry(() => import('../pages/RAG/RAGDocuments'));
const Plugins = lazyWithRetry(() => import('../pages/Plugins/Plugins'));

// 根据 auth_type 动态选择登录组件（配置加载期间必须等待，不允许默认
// 渲染 LoginIntl — 否则用户刷新页面时，由于 config 仍是 null，路由会
// 短暂渲染 LoginIntl，然后即使 config 加载成功也不会自动切换到
// LoginCN，造成"后端明明是 CN 配置却显示 LoginIntl"的用户体验事故）。
//
// 复现路径：
//   1. 用户按 F5 / Vite HMR reload LoginCN
//   2. AppConfigProvider mount，useState(null) ⇒ config=null，loading=true
//   3. LoginPageWrapper 立即渲染，useLoginComponent() 走到 fallback
//      `config?.auth_type || 'cognito'` ⇒ 渲染 LoginIntl
//   4. AppConfigProvider.loadConfig() 在 catch 里把 fallback 写成
//      intl/cognito ⇒ 即使 backend 后来给出真实配置，React 也不会
//      把 LoginIntl 切换回 LoginCN（useLoginComponent 在 fallback
//      值下永远命中 LoginIntl 分支）
//
// 解决：useLoginComponent 在 config 尚未就绪时返回 null，强制
// LoginPageWrapper 显示 loading spinner 而非错误的 LoginIntl。
// 此外，如果后端 fetchConfig() 失败并已经写入了 intl/cognito fallback，
// 我们用一个 watchdog 周期性地 refetch — 当 backend 复活后会自动切
// 到正确的 LoginCN。
function useLoginComponent() {
  const { config, loading, error, refetch } = useAppConfig();

  // 看门狗：一旦用户停留在登录页（可能是 fallback 状态），就周期性
  // refetch AppConfig。backend 一旦 ready，下次 refetch 就会把 fallback
  // 覆盖掉，useLoginComponent 切到 LoginCN。
  useEffect(() => {
    if (!config) return;
    // Fallback 特征：auth_type=cognito + empty cloudbase_env_id + is_cn=false。
    // 如果这三个条件都成立，说明我们处于 backend 不可达状态而不是真正的
    // intl 配置。  True intl 配置会有 cognito_domain / cognito_client_id
    // 非空。
    const looksLikeFallback =
      config.auth_type === 'cognito' &&
      !config.is_cn &&
      !config.auth.cloudbase_env_id &&
      !config.auth.cognito_domain &&
      !config.auth.cognito_client_id;
    if (!looksLikeFallback) return;

    const interval = setInterval(() => {
      console.debug('[useLoginComponent] Watchdog refetching AppConfig');
      refetch();
    }, 5000);
    return () => clearInterval(interval);
  }, [config, refetch]);

  // 配置加载中或 backend 不可达：保持 spinner，让 watchdog 在后台尝试恢复。
  if (loading || !config) {
    return null;
  }
  // 一旦 config 真正 ready（AppConfigProvider 已成功 fetchConfig 或
  // 全部 retry 失败后写入了 fallback），auth_type 由 backend 决定。
  // 这里绝对不要 `|| 'cognito'` fallback — 那会让 'cloudbase' 之外的
  // 任何值（undefined / null / 拼写错误）都走 LoginIntl，造成刷新
  // 页面后短暂渲染错组件的回归（见本文件注释）。
  return config.auth_type === 'cloudbase' ? LoginCN : LoginIntl;
}

// 登录页面包装器
function LoginPageWrapper() {
  const LoginComponent = useLoginComponent();
  // 配置加载中或 backend 不可达：显示通用 spinner 而非错误的 LoginIntl。
  // 这避免了刷新页面后短暂（甚至永远）显示 LoginIntl 的回归。
  if (!LoginComponent) {
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100vh',
          width: '100vw',
          background: '#0f172a',
        }}
      >
        <Spin size="large" />
      </div>
    );
  }
  return (
    <LazyWrapper>
      <LoginComponent />
    </LazyWrapper>
  );
}

interface LazyErrorBoundaryState {
    hasError: boolean;
    errorMessage: string;
}

class LazyErrorBoundary extends React.Component<{ children: React.ReactNode }, LazyErrorBoundaryState> {
    state: LazyErrorBoundaryState = {
        hasError: false,
        errorMessage: ''
    };

    static getDerivedStateFromError(error: unknown): LazyErrorBoundaryState {
        const message = error instanceof Error ? error.message : String(error);
        return {
            hasError: true,
            errorMessage: message
        };
    }

    private lastAutoRetryAt = 0;

    componentDidCatch(error: Error, info: React.ErrorInfo) {
        console.error('[LazyErrorBoundary] Render failed:', error, info?.componentStack || '');
        // Self-heal: transient post-mutation crashes (e.g. a modal briefly
        // rendering with cleared state) recover on a plain re-render — the
        // manual 重试加载 button already proved that. Auto-retry ONCE; if the
        // same crash recurs within 5s, keep the error UI so a real bug is
        // still visible instead of looping.
        const now = Date.now();
        if (now - this.lastAutoRetryAt > 5000) {
            this.lastAutoRetryAt = now;
            setTimeout(() => this.setState({ hasError: false, errorMessage: '' }), 50);
        }
    }

    handleRetry = () => {
        this.setState({ hasError: false, errorMessage: '' });
    };

    handleReload = () => {
        if (typeof window !== 'undefined') {
            window.location.reload();
        }
    };

    render() {
        if (this.state.hasError) {
            const isImportError =
                this.state.errorMessage.includes('Failed to fetch dynamically imported module') ||
                this.state.errorMessage.includes('Outdated Optimize Dep') ||
                this.state.errorMessage.includes('Importing a module script failed');

            return (
                <div style={{
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'center',
                    alignItems: 'center',
                    gap: '12px',
                    height: '260px',
                    color: 'var(--text-primary, #e2e8f0)',
                    background: 'var(--bg-primary, #0f172a)',
                    borderRadius: '8px',
                    padding: '16px'
                }}>
                    <div style={{ fontSize: '16px', fontWeight: 600 }}>
                        {isImportError ? '页面资源加载失败' : '页面渲染失败'}
                    </div>
                    <div style={{ fontSize: '13px', opacity: 0.85, textAlign: 'center', maxWidth: '560px' }}>
                        {isImportError
                            ? '检测到前端依赖缓存失效，请点击“刷新页面”恢复。'
                            : '检测到组件渲染异常，请点击“重试加载”或“刷新页面”。'}
                    </div>
                    <div style={{ display: 'flex', gap: '8px' }}>
                        <Button onClick={this.handleRetry}>重试加载</Button>
                        <Button type="primary" onClick={this.handleReload}>刷新页面</Button>
                    </div>
                </div>
            );
        }

        return this.props.children;
    }
}

// LoadComponent包装器
const LazyWrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => (
    <LazyErrorBoundary>
        <Suspense fallback={
            <div style={{
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                height: '100vh',
                width: '100vw',
                background: '#0f172a'
            }}>
                <Spin size="large" />
            </div>
        }>
            {children}
        </Suspense>
    </LazyErrorBoundary>
);

// 路由ConfigurationType
export interface RouteConfig {
    path: string;
    element: React.ReactNode;
    children?: RouteConfig[];
    auth?: boolean;
    keepAlive?: boolean; // 是否EnabledPage持久化
}

// Check认证Status
export const isAuthenticated = () => {
    return userStorageManager.isAuthenticated();
};

// 受保护的路由Component
export const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    if (!isAuthenticated()) {
        // During the post-login grace period, the token may have been transiently
        // cleared by an early INVALID_TOKEN response while the backend was still
        // initializing.  Don't redirect to login in that case — the token-clear
        // suppression in api-router / api.ts should prevent this, but this serves
        // as a safety net to avoid the "double login" bounce.
        if (userStorageManager.isInPostLoginGracePeriod()) {
            console.warn('[ProtectedRoute] Not authenticated but within post-login grace period, allowing through');
            return <MainLayout>{children}</MainLayout>;
        }
        return <Navigate to="/login" replace />;
    }
    return <MainLayout>{children}</MainLayout>;
};

// 登录路由组件 - 如果已登录则重定向，根据运行时配置选择登录页面
const LoginRoute: React.FC = () => {
    if (isAuthenticated()) {
        return <Navigate to="/" replace />;
    }
    return <LoginPageWrapper />;
};

// Public路由
export const publicRoutes: RouteConfig[] = [
    {
        path: '/login',
        element: <LoginRoute />,
    },
    {
        path: '/auth/callback',
        element: <LazyWrapper><AuthCallback /></LazyWrapper>,
    },
];

// 受保护的路由
export const protectedRoutes: RouteConfig[] = [
    {
        path: '/',
        element: <ProtectedRoute><MainRouteWrapper /></ProtectedRoute>,
        children: [
            {
                path: '',
                element: <Navigate to="/agents" replace />,
            },
            {
                path: 'dashboard',
                element: <LazyWrapper><Dashboard /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'vehicles',
                element: <LazyWrapper><Vehicles /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'schedule',
                element: <LazyWrapper><Schedule /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'chat',
                element: <LazyWrapper><Chat /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'skills',
                element: <LazyWrapper><Skills /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'skill_editor',
                element: <LazyWrapper><SkillEditor /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'agents',
                element: <AgentsRouteWrapper />,
                children: [
                    {
                        path: '',
                        element: <LazyWrapper><OrgNavigator /></LazyWrapper>,
                        keepAlive: true,
                    },
                    {
                        path: 'details/:id',
                        element: <LazyWrapper><AgentDetails /></LazyWrapper>,
                        keepAlive: false, // Details页不Need保活，每次都重新Load
                    },
                    {
                        path: 'add',
                        element: <LazyWrapper><AgentDetails /></LazyWrapper>,
                        keepAlive: false, // Add页不Need保活
                    },
                    {
                        path: 'organization/:orgId/*',
                        element: <LazyWrapper><OrgNavigator /></LazyWrapper>,
                        keepAlive: true,
                        // Note：All organization Path共享同一个Cache实例（通过 AgentsRouteWrapper Implementation）
                        // 这样在不同组织间Toggle时，OrgNavigator 会保持Status
                    },
                ],
            },
            {
                path: 'analytics',
                element: <LazyWrapper><Analytics /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'tasks',
                element: <LazyWrapper><Tasks /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'tools',
                element: <LazyWrapper><Tools /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'warehouses',
                element: <LazyWrapper><Warehouses /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'products',
                element: <LazyWrapper><Products /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'prompts',
                element: <LazyWrapper><Prompts /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'avatars',
                element: <LazyWrapper><Avatars /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'account',
                element: <LazyWrapper><Account /></LazyWrapper>,
                keepAlive: false,
            },
            {
                path: 'account/payment-plan',
                element: <LazyWrapper><PaymentPlan /></LazyWrapper>,
                keepAlive: false,
            },
            {
                path: 'settings',
                element: <LazyWrapper><Settings /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'plugins',
                element: <LazyWrapper><Plugins /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'console',
                element: <LazyWrapper><Console /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'knowledge-ported',
                element: <LazyWrapper><KnowledgePorted /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'tests',
                element: <LazyWrapper><Tests /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'chat-test',
                element: <LazyWrapper><ChatTest /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'orgs',
                element: <LazyWrapper><Orgs /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'shipping-label',
                element: <LazyWrapper><ShippingLabel /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'rag',
                element: <LazyWrapper><RAGDocuments /></LazyWrapper>,
                keepAlive: true,
            },
        ],
    },
];

// 404路由
export const notFoundRoute: RouteConfig = {
    path: '*',
    element: <Navigate to="/" replace />,
};

// All路由
export const routes: RouteConfig[] = [
    ...publicRoutes,
    ...protectedRoutes,
    notFoundRoute,
];

// MenuConfiguration
export const menuItems = [
    {
        key: '/dashboard',
        icon: 'DashboardOutlined',
        label: 'menu.dashboard',
    },
    {
        key: '/vehicles',
        icon: 'ClusterOutlined',
        label: 'menu.vehicles',
    },
    {
        key: '/schedule',
        icon: 'CalendarOutlined',
        label: 'menu.schedule',
    },
    {
        key: '/chat',
        icon: 'MessageOutlined',
        label: 'menu.chat',
    },
    {
        key: '/skills',
        icon: 'RobotOutlined',
        label: 'menu.skills',
    },
    {
        key: '/skill_editor',
        icon: 'EditOutlined',
        label: 'menu.skill_editor',
    },
    {
        key: '/agents',
        icon: 'TeamOutlined',
        label: 'menu.agents',
    },
    {
        key: '/analytics',
        icon: 'BarChartOutlined',
        label: 'menu.analytics',
    },
    {
        key: '/tasks',
        icon: 'OrderedListOutlined',
        label: 'menu.tasks',
    },
    {
        key: '/tools',
        icon: 'ToolOutlined',
        label: 'menu.tools',
    },
    {
        key: '/settings',
        icon: 'SettingOutlined',
        label: 'menu.settings',
    },
    {
        key: '/console',
        icon: 'SettingOutlined',
        label: 'menu.console',
    },
    {
        key: '/tests',
        icon: 'ExperimentOutlined',
        label: 'menu.tests',
    },
    {
        key: '/shipping-label',
        icon: 'PrinterOutlined',
        label: 'menu.shipping_label',
    },
]; 
