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

  const findOrgById = (orgs: Org[], id: string): Org | null => {
    for (const org of orgs) {
      if (org.id === id) return org;
      if (org.children) {
        const found = findOrgById(org.children, id);
        if (found) return found;
      }
    }
    return null;
  };

  const convertToTreeData = (orgs: Org[]): DataNode[] => {

    return orgs.map(org => ({
      key: org.id,
      title: (
        <Space>
          <ApartmentOutlined />
          <span>{org.name}</span>
          {org.children && org.children.length > 0 && (
            <span style={{ color: '#666', fontSize: '12px' }}>
              ({org.children.length})
            </span>
          )}
        </Space>
      ),
      children: org.children ? convertToTreeData(org.children) : undefined,
      isLeaf: !org.children || org.children.length === 0
    }));
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
      style={{ height: '100%' }}
    >
      <Spin spinning={loading}>
        <Tree
          {...TREE_CONFIG}
          treeData={convertToTreeData(orgs)}
          onSelect={onSelect}
          onDrop={onDrop}
        />
      </Spin>
    </Card>
  );
};

export default OrgTree;
