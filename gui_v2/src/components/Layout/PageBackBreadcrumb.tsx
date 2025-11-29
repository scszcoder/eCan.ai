import React, { useMemo, useState, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Button, Breadcrumb, Tooltip, App, Input } from 'antd';
import { ArrowLeftOutlined, HomeOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import styled from '@emotion/styled';
import { useOrgStore } from '../../stores/orgStore';
import { useTaskStore } from '../../stores/domain/taskStore';
import { useSkillStore } from '../../stores/domain/skillStore';
import { useUserStore } from '../../stores/userStore';
import { get_ipc_api } from '@/services/ipc_api';

// ==================== 样式Component ====================
const BreadcrumbContainer = styled.div`
    display: flex;
    align-items: center;
    gap: 16px;
    justify-content: space-between;
    width: 100%;
`;

const LeftSection = styled.div`
    display: flex;
    align-items: center;
    gap: 16px;
    flex: 1;
    min-width: 0;
`;

const RightSection = styled.div`
    display: flex;
    align-items: center;
    gap: 12px;
    flex-shrink: 0;
`;

const StyledBackButton = styled(Button)`
    color: rgba(203, 213, 225, 0.9) !important;
    padding-left: 0 !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    height: 32px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    
    &:hover {
        color: rgba(248, 250, 252, 1) !important;
        background: rgba(255, 255, 255, 0.08) !important;
    }
    
    .anticon {
        transition: color 0.3s ease;
    }
`;

const StyledBreadcrumb = styled(Breadcrumb)`
    .ant-breadcrumb-separator {
        color: rgba(148, 163, 184, 0.5) !important;
        margin: 0 8px !important;
    }
    
    .ant-breadcrumb-link {
        color: rgba(203, 213, 225, 0.85) !important;
        transition: all 0.3s ease !important;
        font-size: 14px !important;
        font-weight: 500 !important;
    }
`;

const BreadcrumbLink = styled.span<{ $isClickable?: boolean }>`
    cursor: ${props => props.$isClickable ? 'pointer' : 'default'};
    color: ${props => props.$isClickable 
        ? 'rgba(96, 165, 250, 0.95)' 
        : 'rgba(248, 250, 252, 0.95)'} !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    font-weight: ${props => props.$isClickable ? '500' : '600'};
    display: flex;
    align-items: center;
    gap: 6px;
    
    ${props => props.$isClickable && `
        &:hover {
            color: rgba(147, 197, 253, 1) !important;
        }
    `}
    
    .anticon {
        font-size: 16px;
    }
`;

const StyledSearchInput = styled(Input)`
    width: 280px;
    height: 36px !important;
    background: rgba(51, 65, 85, 0.3) !important;
    border: none !important;
    border-radius: 8px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.2);
    padding: 0 12px !important;
    line-height: 36px !important;
    
    &:hover {
        background: rgba(51, 65, 85, 0.5) !important;
        box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.3);
    }
    
    &:focus, &.ant-input-focused, &.ant-input-affix-wrapper-focused {
        background: rgba(51, 65, 85, 0.6) !important;
        box-shadow: 
            0 0 0 2px rgba(59, 130, 246, 0.15),
            inset 0 1px 3px rgba(0, 0, 0, 0.3) !important;
    }
    
    /* InternalInput框 */
    input {
        background: transparent !important;
        color: rgba(248, 250, 252, 0.95) !important;
        height: 34px !important;
        line-height: 34px !important;
        padding: 0 !important;
        border: none !important;
        
        &::placeholder {
            color: rgba(148, 163, 184, 0.6) !important;
        }
    }
    
    /* 前缀图标 */
    .ant-input-prefix {
        color: rgba(148, 163, 184, 0.8) !important;
        margin-right: 8px !important;
        display: flex;
        align-items: center;
        
        .anticon {
            font-size: 14px;
        }
    }
    
    /* 清除Button */
    .ant-input-clear-icon {
        color: rgba(148, 163, 184, 0.6) !important;
        font-size: 12px;
        
        &:hover {
            color: rgba(203, 213, 225, 0.9) !important;
        }
    }
    
    /* 后缀区域 */
    .ant-input-suffix {
        display: flex;
        align-items: center;
        margin-left: 4px;
    }
`;

const StyledRefreshButton = styled(Button)`
    color: rgba(203, 213, 225, 0.9) !important;
    font-size: 16px !important;
    width: 36px !important;
    height: 36px !important;
    padding: 0 !important;
    border-radius: 8px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    display: flex;
    align-items: center;
    justify-content: center;
    
    &:hover:not(:disabled) {
        color: rgba(248, 250, 252, 1) !important;
        background: rgba(59, 130, 246, 0.15) !important;
    }
    
    &:active:not(:disabled) {
        opacity: 0.8;
    }
    
    &:disabled {
        opacity: 0.5;
    }
`;

// ==================== TypeDefinition ====================
interface BreadcrumbItem {
    key: string;
    title: React.ReactNode;
    path?: string;
}

interface PathHandler {
    // Check是否匹配该Path
    match: (segments: string[], path: string) => boolean;
    // 生成面包屑项（Add context ParameterUsed for传递ComponentData）
    generate: (segments: string[], path: string, t: any, navigate: any, context?: any) => BreadcrumbItem[];
}

// ==================== ToolFunction ====================
// 查找树节点
function findTreeNodeById(node: any, targetId: string): any | null {
    if (node.id === targetId) {
        return node;
    }
    if (!node.children || node.children.length === 0) {
        return null;
    }
    for (const child of node.children) {
        const found = findTreeNodeById(child, targetId);
        if (found) return found;
    }
    return null;
}

// Create可Click的Link
function createClickableLink(text: string, path: string, navigate: any): React.ReactNode {
    return (
        <BreadcrumbLink 
            $isClickable={true}
            onClick={() => navigate(path)}
        >
            {text}
        </BreadcrumbLink>
    );
}

// CreateWhen前节点（不可Click）
function createCurrentNode(text: string): React.ReactNode {
    return <BreadcrumbLink $isClickable={false}>{text}</BreadcrumbLink>;
}

// ==================== Agents PathProcess器 ====================
const agentsPathHandler: PathHandler = {
    match: (segments) => segments[0] === 'agents',
    
    generate: (_segments, path, t, navigate, context) => {
        const items: BreadcrumbItem[] = [];
        const treeOrgs = context?.treeOrgs || [];
        const searchParams = context?.searchParams;
        const rootNode = treeOrgs[0];
        
        // Add Agents 根节点
        items.push({
            key: '/agents',
            title: (
                <BreadcrumbLink 
                    $isClickable={true}
                    onClick={() => navigate('/agents')}
                >
                    <HomeOutlined />
                    {rootNode?.name || t('menu.agents')}
                </BreadcrumbLink>
            ),
            path: '/agents'
        });
        
        // Parse organization Path
        const orgMatches = path.match(/organization\/([^/]+)/g);
        if (orgMatches && rootNode) {
            let currentPath = '/agents';
            orgMatches.forEach((match, index) => {
                const orgId = match.replace('organization/', '');
                const node = findTreeNodeById(rootNode, orgId);
                
                if (node) {
                    currentPath += `/organization/${orgId}`;
                    const isLast = index === orgMatches.length - 1 && !path.includes('/details/');
                    
                    items.push({
                        key: currentPath,
                        title: isLast 
                            ? createCurrentNode(node.name)
                            : createClickableLink(node.name, currentPath, navigate),
                        path: isLast ? undefined : currentPath
                    });
                }
            });
        }
        
        // If是 details Page或 add Page，尝试从URLParameterGetorgId
        if (path.includes('/details/') || path.includes('/add')) {
            // 从URL中GetorgIdParameter
            const orgIdParam = searchParams?.get('orgId');

            if (orgIdParam && rootNode) {
                // IfURL中有orgId，构建组织Path
                const node = findTreeNodeById(rootNode, orgIdParam);
                if (node) {
                    // 构建从根到When前组织的完整Path
                    const buildOrgPath = (targetNode: any, currentNode: any, pathSoFar: any[] = []): any[] | null => {
                        if (currentNode.id === targetNode.id) {
                            return [...pathSoFar, currentNode];
                        }
                        if (currentNode.children) {
                            for (const child of currentNode.children) {
                                const result = buildOrgPath(targetNode, child, [...pathSoFar, currentNode]);
                                if (result) return result;
                            }
                        }
                        return null;
                    };

                    const orgPath = buildOrgPath(node, rootNode);
                    if (orgPath) {
                        // IfPath中已经有organization段，则不重复Add
                        if (!orgMatches) {
                            // Add组织Path的面包屑（跳过根节点，因为已经Add了）
                            let currentOrgPath = '/agents';
                            orgPath.slice(1).forEach((orgNode) => {
                                currentOrgPath += `/organization/${orgNode.id}`;
                                items.push({
                                    key: currentOrgPath,
                                    title: createClickableLink(orgNode.name, currentOrgPath, navigate),
                                    path: currentOrgPath
                                });
                            });
                        }
                    }
                }
            }

            // AddDetails/新增Page标题
            items.push({
                key: path,
                title: createCurrentNode(
                    path.includes('/add')
                        ? t('pages.agents.create_agent', 'Create Agent')
                        : t('pages.agents.agent_details', 'Agent Details')
                )
            });
        }
        
        return items;
    }
};

// ==================== DefaultPathProcess器 ====================
const defaultPathHandler: PathHandler = {
    match: () => true, // 匹配AllPath
    
    generate: (segments, _path, t, navigate) => {
        const items: BreadcrumbItem[] = [];
        
        segments.forEach((seg, idx) => {
            const segPath = '/' + segments.slice(0, idx + 1).join('/');
            const isLast = idx === segments.length - 1;
            
            // 尝试翻译
            let label = t(`breadcrumb.${seg}`);
            if (label === `breadcrumb.${seg}`) {
                // If没有翻译，尝试Menu翻译
                label = t(`menu.${seg}`);
                if (label === `menu.${seg}`) {
                    // If还是没有，使用原始Value并解码
                    label = decodeURIComponent(seg);
                }
            }
            
            items.push({
                key: segPath,
                title: isLast 
                    ? createCurrentNode(label)
                    : createClickableLink(label, segPath, navigate),
                path: isLast ? undefined : segPath
            });
        });
        
        return items;
    }
};

// ==================== PathProcess器Register表 ====================
const pathHandlers: PathHandler[] = [
    agentsPathHandler,
    // Can在这里Add其他Module的Process器
    // tasksPathHandler,
    // skillsPathHandler,
    // ...
    defaultPathHandler, // DefaultProcess器放在最后
];

// ==================== 主Component ====================
interface PageBackBreadcrumbProps {
    searchQuery?: string;
    onSearchChange?: (query: string) => void;
}

const PageBackBreadcrumb: React.FC<PageBackBreadcrumbProps> = ({ searchQuery = '', onSearchChange }) => {
    const navigate = useNavigate();
    const location = useLocation();
    const { t } = useTranslation();
    const { message } = App.useApp();
    const { treeOrgs } = useOrgStore(); // 在Component中GetData
    const username = useUserStore((state) => state.username);
    const path = location.pathname;
    const [refreshing, setRefreshing] = useState(false);
    
    // ParsePath段 - Need在 handleRefresh 之前Definition
    const segments = path.split('/').filter(Boolean);

    // ProcessRefreshData - 根据When前Page智能Refresh
    const handleRefresh = useCallback(async () => {
        if (refreshing || !username) return;
        
        setRefreshing(true);
        try {
            const api = get_ipc_api();
            const currentPath = segments[0];
            
            // 根据When前PageRefresh对应的Data
            if (currentPath === 'agents') {
                // Agents Page：调用 get_all_org_agents InterfaceRefresh组织和代理Data
                const res = await api.getAllOrgAgents(username).catch((e: any) => ({ success: false, error: e, data: null }));
                
                if (res.success && res.data) {
                    useOrgStore.getState().refreshOrgData();
                }
            } else if (currentPath === 'tasks') {
                // Tasks Page：只Refresh tasks Data
                const tasksRes = await api.getAgentTasks(username, []).catch((e: any) => ({ success: false, error: e, data: null }));
                
                if (tasksRes.success && tasksRes.data && (tasksRes.data as any).tasks) {
                    useTaskStore.getState().setItems((tasksRes.data as any).tasks);
                }
            } else if (currentPath === 'skills') {
                // Skills Page：只Refresh skills Data
                const skillsRes = await api.getAgentSkills(username, []).catch((e: any) => ({ success: false, error: e, data: null }));
                
                if (skillsRes.success && skillsRes.data && (skillsRes.data as any).skills) {
                    useSkillStore.getState().setItems((skillsRes.data as any).skills);
                }
            }
            
            message.success(t('common.refresh_success') || 'DataRefreshSuccess');
        } catch (error) {
            console.error('[PageBackBreadcrumb] Refresh error:', error);
            message.error(t('common.refresh_failed') || 'DataRefreshFailed');
        } finally {
            setRefreshing(false);
        }
    }, [refreshing, username, message, t, segments]);

    // 从 location.search GetQueryParameter
    const searchParams = useMemo(() => new URLSearchParams(location.search), [location.search]);
    
    // 构建面包屑项 - 使用Process器模式
    const items = useMemo(() => {
        // 找到第一个匹配的Process器
        const handler = pathHandlers.find(h => h.match(segments, path));

        // 准备上下文Data
        const context = {
            treeOrgs,
            searchParams
        };

        // 使用Process器生成面包屑项
        return handler ? handler.generate(segments, path, t, navigate, context) : [];
    }, [path, segments, t, navigate, treeOrgs, searchParams]);
    
    // 计算返回Path
    const parentPath = useMemo(() => {
        // If是 details 或 add Page，Check是否有 orgId Parameter
        if (path.includes('/details/') || path.includes('/add')) {
            const orgIdParam = searchParams.get('orgId');
            if (orgIdParam) {
                // 返回到对应的组织Page
                // Need构建完整的组织Path
                const rootNode = treeOrgs[0];
                if (rootNode) {
                    const node = findTreeNodeById(rootNode, orgIdParam);
                    if (node) {
                        // 构建从根到When前组织的完整Path
                        const buildOrgPath = (targetNode: any, currentNode: any, pathSoFar: any[] = []): any[] | null => {
                            if (currentNode.id === targetNode.id) {
                                return [...pathSoFar, currentNode];
                            }
                            if (currentNode.children) {
                                for (const child of currentNode.children) {
                                    const result = buildOrgPath(targetNode, child, [...pathSoFar, currentNode]);
                                    if (result) return result;
                                }
                            }
                            return null;
                        };

                        const orgPath = buildOrgPath(node, rootNode);
                        if (orgPath && orgPath.length > 1) {
                            // 构建完整的组织Path
                            let fullOrgPath = '/agents';
                            orgPath.slice(1).forEach((orgNode) => {
                                fullOrgPath += `/organization/${orgNode.id}`;
                            });
                            return fullOrgPath;
                        }
                    }
                }
                // If找不到节点，返回到 agents 根Page
                return '/agents';
            }
        }

        // If是组织Details页，返回到组织List
        if (path.includes('/organization/')) {
            const lastOrgIndex = path.lastIndexOf('/organization/');
            return path.substring(0, lastOrgIndex) || '/agents';
        }
        // Default返回上一级
        return '/' + segments.slice(0, -1).join('/');
    }, [path, segments, treeOrgs, searchParams]);
    
    // 总是Display面包屑（包括根目录）
    // 只有在非根目录时Display返回Button
    const showBackButton = segments.length >= 2;
    
    // 判断是否在 agents Page（DisplaySearch框）
    const isAgentsPage = segments[0] === 'agents';
    
    return (
        <BreadcrumbContainer>
            <LeftSection>
                {showBackButton && (
                    <StyledBackButton
                        type="text"
                        icon={<ArrowLeftOutlined />}
                        onClick={() => navigate(parentPath)}
                    >
                        {t('common.back', '返回')}
                    </StyledBackButton>
                )}
                {items.length > 0 && (
                    <StyledBreadcrumb 
                        items={items as any}
                        itemRender={(item, params, items) => {
                            const isLast = params.index === items.length - 1;
                            if (isLast || !item.path) {
                                return item.title;
                            }
                            return (
                                <BreadcrumbLink 
                                    $isClickable={true}
                                    onClick={(e) => {
                                        e.preventDefault();
                                        navigate(item.path as string);
                                    }}
                                >
                                    {item.title}
                                </BreadcrumbLink>
                            );
                        }}
                    />
                )}
            </LeftSection>
            
            <RightSection>
                {/* Search框 - 仅在 agents PageDisplay */}
                {isAgentsPage && onSearchChange && (
                    <StyledSearchInput
                        placeholder={t('pages.agents.search_placeholder') || '请InputName或其他关键字'}
                        prefix={<SearchOutlined />}
                        value={searchQuery}
                        onChange={(e) => onSearchChange(e.target.value)}
                        allowClear
                    />
                )}
                
                {/* RefreshButton */}
                <Tooltip title={t('common.refresh') || 'RefreshData'}>
                    <StyledRefreshButton
                        type="text"
                        icon={<ReloadOutlined spin={refreshing} />}
                        onClick={handleRefresh}
                        disabled={refreshing}
                    />
                </Tooltip>
            </RightSection>
        </BreadcrumbContainer>
    );
};

export default PageBackBreadcrumb; 