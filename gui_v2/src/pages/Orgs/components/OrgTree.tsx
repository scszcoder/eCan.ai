/**
 * Org Tree Component
 */

import React from 'react';
import { Tree, Card, Button, Space, Spin, Tooltip } from 'antd';
import { PlusOutlined, ApartmentOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import type { DataNode } from 'antd/es/tree';
import type { Org } from '../types';
import { TREE_CONFIG } from '../constants';

const StyledAddButton = styled(Button)`
  &.ant-btn {
    background: transparent !important;
    border: none !important;
    color: rgba(203, 213, 225, 0.9) !important;
    box-shadow: none !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;

    &:hover {
      background: rgba(255, 255, 255, 0.1) !important;
      color: rgba(248, 250, 252, 0.95) !important;
    }

    &:active {
      opacity: 0.8 !important;
    }

    .anticon {
      transition: all 0.3s ease !important;
    }
  }
`;

const StyledTree = styled(Tree)`
  background: transparent;
  
  /* 树节点样式 */
  .ant-tree-treenode {
    padding: 0;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    display: flex;
    align-items: center;
  }

  /* 节点Content包装器 - Default无背景 */
  .ant-tree-node-content-wrapper {
    padding: 6px 10px;
    border-radius: 6px;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    background: transparent;
    border: 1px solid transparent;
    margin: 1px 0;
    min-height: 30px;
    display: flex !important;
    align-items: center !important;
    line-height: 30px;

    &:hover {
      background: rgba(59, 130, 246, 0.1) !important;
      border-color: rgba(59, 130, 246, 0.2);
      box-shadow: 0 2px 8px rgba(59, 130, 246, 0.15);
    }
  }

  /* 选中的节点 */
  .ant-tree-node-selected {
    .ant-tree-node-content-wrapper {
      background: linear-gradient(90deg, rgba(59, 130, 246, 0.2) 0%, rgba(59, 130, 246, 0.1) 100%) !important;
      border-left: 3px solid rgba(59, 130, 246, 0.8);
      border-right: 1px solid rgba(59, 130, 246, 0.3);
      border-top: 1px solid rgba(59, 130, 246, 0.3);
      border-bottom: 1px solid rgba(59, 130, 246, 0.3);
      box-shadow: 0 2px 12px rgba(59, 130, 246, 0.2);
      padding-left: 9px;

      &:hover {
        background: linear-gradient(90deg, rgba(59, 130, 246, 0.25) 0%, rgba(59, 130, 246, 0.15) 100%) !important;
        box-shadow: 0 4px 16px rgba(59, 130, 246, 0.25);
      }
    }
  }

  /* 标题样式 */
  .ant-tree-title {
    font-size: 14px;
    font-weight: 500;
    color: rgba(248, 250, 252, 0.95);
    display: flex;
    align-items: center;
    line-height: normal;
  }

  /* Expand/折叠开关 */
  .ant-tree-switcher {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    width: 20px;
    min-height: 30px;
    color: rgba(148, 163, 184, 0.7);
    transition: all 0.3s ease;
    flex-shrink: 0;

    &:hover {
      color: rgba(96, 165, 250, 1);
      background: rgba(59, 130, 246, 0.15);
      border-radius: 4px;
    }

    .ant-tree-switcher-icon {
      font-size: 10px;
      display: flex;
      align-items: center;
    }
  }

  /* Connection线样式 */
  .ant-tree-indent-unit {
    width: 16px;
  }

  .ant-tree-indent-unit::before {
    border-right: 1px solid rgba(148, 163, 184, 0.15);
  }

  /* Drag时的样式 */
  .ant-tree-treenode-draggable {
    .ant-tree-node-content-wrapper {
      cursor: move;
      
      &:hover {
        cursor: move !important;
      }
    }
  }

  .ant-tree-node-content-wrapper[draggable="true"] {
    cursor: move;
    user-select: none;
  }

  /* Drag目标样式 */
  .ant-tree-drop-indicator {
    position: absolute;
    height: 2px;
    background: rgba(59, 130, 246, 0.8);
    border-radius: 1px;
    pointer-events: none;
    box-shadow: 0 0 8px rgba(59, 130, 246, 0.6);
  }
`;

interface OrgTreeProps {
  orgs: Org[];
  loading: boolean;
  onSelect: (selectedKeys: React.Key[]) => void;
  onDrop: (info: any) => void;
  onAdd: () => void;
}

const OrgTree: React.FC<OrgTreeProps> = ({
  orgs,
  loading,
  onSelect,
  onDrop,
  onAdd,
}) => {
  const { t } = useTranslation();
  
  // 管理Expand的节点
  const [expandedKeys, setExpandedKeys] = React.useState<React.Key[]>([]);
  const [autoExpandedExecuted, setAutoExpandedExecuted] = React.useState(false);

  const findOrgById = React.useCallback((orgs: Org[], id: string): Org | null => {
    for (const org of orgs) {
      if (org.id === id) return org;
      if (org.children) {
        const found = findOrgById(org.children, id);
        if (found) return found;
      }
    }
    return null;
  }, []);

  const getOrgTypeColor = (orgType: string) => {
    const colorMap: Record<string, string> = {
      company: 'rgba(139, 92, 246, 0.9)',      // 紫色
      department: 'rgba(59, 130, 246, 0.9)',   // 蓝色
      team: 'rgba(16, 185, 129, 0.9)',         // 绿色
      group: 'rgba(245, 158, 11, 0.9)',        // 橙色
    };
    return colorMap[orgType] || 'rgba(148, 163, 184, 0.9)';
  };

  const getOrgTypeIcon = (orgType: string) => {
    // Can根据Type返回不同图标，这里统一使用 ApartmentOutlined
    return <ApartmentOutlined />;
  };

  const convertToTreeData = React.useCallback((orgs: Org[]): DataNode[] => {
    return orgs.map(org => {
      // 使用 agent_count Display总代理Count（包括子组织的代理）
      const agentCount = (org as any).agent_count || 0;
      const orgColor = getOrgTypeColor(org.org_type);
      const hasChildren = org.children && org.children.length > 0;
      
      return {
        key: org.id,
        value: org.id,  // Add value to fix TreeNode warning
        title: (
          <Space size={6} style={{ width: '100%', justifyContent: 'space-between' }}>
            <Space size={6}>
              <span style={{ 
                color: orgColor,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '18px',
                height: '18px',
                background: `${orgColor}15`,
                borderRadius: '3px',
                border: `1px solid ${orgColor}40`,
                fontSize: '12px'
              }}>
                {getOrgTypeIcon(org.org_type)}
              </span>
              <span style={{ 
                color: 'rgba(248, 250, 252, 0.95)',
                fontWeight: hasChildren ? 600 : 500,
                fontSize: '13px'
              }}>
                {org.name}
              </span>
            </Space>
            {agentCount > 0 && (
              <span style={{ 
                color: 'rgba(255, 255, 255, 0.95)', 
                fontSize: '11px', 
                fontWeight: 600,
                background: 'linear-gradient(135deg, rgba(59, 130, 246, 0.8) 0%, rgba(99, 102, 241, 0.7) 100%)',
                padding: '1px 6px',
                borderRadius: '8px',
                border: '1px solid rgba(59, 130, 246, 0.5)',
                boxShadow: '0 2px 4px rgba(59, 130, 246, 0.3)',
                minWidth: '20px',
                textAlign: 'center',
                lineHeight: '14px'
              }}>
                {agentCount}
              </span>
            )}
          </Space>
        ),
        children: org.children ? convertToTreeData(org.children) : undefined,
        isLeaf: !org.children || org.children.length === 0
      };
    });
  }, []);

  const treeData = React.useMemo(() => convertToTreeData(orgs), [orgs, convertToTreeData]);

  // When组织DataLoadCompleted后，自动Expand第一层节点（只Execute一次）
  React.useEffect(() => {
    if (!autoExpandedExecuted && orgs.length > 0 && !loading) {
      const firstLevelKeys = orgs.map(org => org.id);
      setExpandedKeys(firstLevelKeys);
      setAutoExpandedExecuted(true);
    }
  }, [orgs, loading, autoExpandedExecuted]);

  // ProcessExpand/折叠Event
  const handleExpand = (expandedKeysValue: React.Key[]) => {
    setExpandedKeys(expandedKeysValue);
  };

  return (
    <Card
      title={
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
          <Space>
            <ApartmentOutlined />
            {t('pages.org.tree.title')}
          </Space>
          <Tooltip
            title={t('pages.org.actions.add')}
            mouseEnterDelay={0.5}
            mouseLeaveDelay={0.1}
            placement="bottom"
          >
            <StyledAddButton
              size="small"
              icon={<PlusOutlined />}
              onClick={onAdd}
              shape="circle"
            />
          </Tooltip>
        </div>
      }
      style={{ height: '100%', display: 'flex', flexDirection: 'column' }}
      styles={{ body: { flex: 1, overflowX: 'hidden', overflowY: 'auto', padding: '16px' } }}
    >
      <Spin spinning={loading}>
        <StyledTree
          {...TREE_CONFIG}
          treeData={treeData}
          expandedKeys={expandedKeys}
          onExpand={handleExpand}
          onSelect={onSelect}
          onDrop={onDrop}
        />
      </Spin>
    </Card>
  );
};

export default OrgTree;
