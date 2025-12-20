import React, { useMemo } from 'react';
import { Dropdown, Button } from 'antd';
import type { MenuProps } from 'antd';
import { MoreOutlined, RobotOutlined } from '@ant-design/icons';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import styled from '@emotion/styled';

/**
 * QuickActionMenu - FastOperationMenuComponent
 * 
 * 提供FastAdd各种资源的下拉Menu，可ExtendedSupport更多Operation
 * 
 * @example
 * <QuickActionMenu />
 */

// Custom下拉Menu样式，与主题一致
const StyledDropdown = styled(Dropdown)`
    .ant-dropdown-menu {
        background: rgba(15, 23, 42, 0.98) !important;
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        padding: 4px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    }
    
    .ant-dropdown-menu-item {
        color: rgba(255, 255, 255, 0.85) !important;
        border-radius: 4px;
        margin: 2px 0;
        padding: 8px 12px;
        
        &:hover {
            background: rgba(96, 165, 250, 0.15) !important;
            color: rgba(147, 197, 253, 1) !important;
        }
        
        .ant-dropdown-menu-item-icon {
            color: rgba(96, 165, 250, 0.9);
        }
    }
    
    .ant-dropdown-menu-item-active {
        background: rgba(96, 165, 250, 0.15) !important;
    }
`;

const MenuButton = styled(Button)`
    background: transparent !important;
    border: 1px solid rgba(255, 255, 255, 0.2) !important;
    color: rgba(255, 255, 255, 0.85) !important;
    padding: 4px 8px !important;
    height: 32px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    border-radius: 6px !important;
    transition: all 0.2s ease !important;
    
    &:hover {
        background: rgba(96, 165, 250, 0.15) !important;
        border-color: rgba(96, 165, 250, 0.5) !important;
        color: rgba(147, 197, 253, 1) !important;
    }
    
    .anticon {
        font-size: 18px;
    }
`;

const QuickActionMenu: React.FC = () => {
    const navigate = useNavigate();
    const location = useLocation();
    const { t } = useTranslation();

    // 从When前Path中提取组织ID
    const currentOrgId = useMemo(() => {
        const orgMatches = location.pathname.match(/organization\/([^/]+)/g);
        if (orgMatches && orgMatches.length > 0) {
            const lastMatch = orgMatches[orgMatches.length - 1];
            const orgId = lastMatch.replace('organization/', '');
            // Exclude特殊的组织ID
            if (orgId !== 'root' && orgId !== 'unassigned') {
                return orgId;
            }
        }
        return null;
    }, [location.pathname]);

    // DefinitionMenu项 - Can轻松Extended
    const menuItems: MenuProps['items'] = [
        {
            key: 'add-agent',
            icon: <RobotOutlined />,
            label: t('agents.addAgent', 'Add代理'),
            onClick: () => {
                // IfWhen前在组织Page，传递组织ID
                const queryParams = new URLSearchParams();
                if (currentOrgId) {
                    queryParams.set('orgId', currentOrgId);
                }
                const queryString = queryParams.toString();
                const targetUrl = `/agents/add${queryString ? `?${queryString}` : ''}`;
                console.log('[QuickActionMenu] Navigating to add agent with orgId:', currentOrgId, 'URL:', targetUrl);
                navigate(targetUrl);
            },
        },
        // Can在这里Add更多Menu项
        // {
        //     key: 'add-skill',
        //     icon: <ToolOutlined />,
        //     label: t('skills.addSkill', 'Add技能'),
        //     onClick: () => navigate('/skills/add'),
        // },
    ];

    return (
        <StyledDropdown
            menu={{ items: menuItems }}
            placement="bottomRight"
            trigger={['click']}
            overlayClassName="quick-action-menu-overlay"
        >
            <MenuButton
                type="text"
                icon={<MoreOutlined />}
            />
        </StyledDropdown>
    );
};

export default QuickActionMenu;
