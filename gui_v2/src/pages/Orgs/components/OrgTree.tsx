/**
 * Org Tree Component
 */

import React from 'react';
import { Tree, Card, Button, Space, Spin, Tooltip } from 'antd';
import { PlusOutlined, ApartmentOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { DataNode } from 'antd/es/tree';
import type { Org } from '../types';
import { TREE_CONFIG } from '../constants';

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

  const convertToTreeData = React.useCallback((orgs: Org[]): DataNode[] => {
    return orgs.map(org => {
      // 使用 agent_count 显示总代理数量（包括子组织的代理）
      const agentCount = (org as any).agent_count || 0;
      
      return {
        key: org.id,
        value: org.id,  // Add value to fix TreeNode warning
        title: (
          <Space>
            <ApartmentOutlined />
            <span>{org.name}</span>
            {agentCount > 0 && (
              <span style={{ color: '#1890ff', fontSize: '12px', fontWeight: 500 }}>
                ({agentCount})
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
            <Button
              type="primary"
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
        <Tree
          {...TREE_CONFIG}
          treeData={treeData}
          onSelect={onSelect}
          onDrop={onDrop}
        />
      </Spin>
    </Card>
  );
};

export default OrgTree;
