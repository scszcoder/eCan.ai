/**
 * Organization Tree Component
 */

import React from 'react';
import { Tree, Card, Button, Space, Spin } from 'antd';
import { PlusOutlined, ApartmentOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { DataNode } from 'antd/es/tree';
import type { Organization } from '../types';
import { TREE_CONFIG } from '../constants';

interface OrganizationTreeProps {
  organizations: Organization[];
  loading: boolean;
  onSelect: (selectedKeys: React.Key[]) => void;
  onDrop: (info: any) => void;
  onAdd: () => void;
}

const OrganizationTree: React.FC<OrganizationTreeProps> = ({
  organizations,
  loading,
  onSelect,
  onDrop,
  onAdd,
}) => {
  const { t } = useTranslation();

  const findOrganizationById = (orgs: Organization[], id: string): Organization | null => {
    for (const org of orgs) {
      if (org.id === id) return org;
      if (org.children) {
        const found = findOrganizationById(org.children, id);
        if (found) return found;
      }
    }
    return null;
  };

  const convertToTreeData = (orgs: Organization[]): DataNode[] => {
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
        <Space>
          <ApartmentOutlined />
          {t('org.tree.title')}
          <Button
            type="primary"
            size="small"
            icon={<PlusOutlined />}
            onClick={onAdd}
          >
            {t('org.actions.add')}
          </Button>
        </Space>
      }
      style={{ height: '100%' }}
    >
      <Spin spinning={loading}>
        <Tree
          {...TREE_CONFIG}
          treeData={convertToTreeData(organizations)}
          onSelect={onSelect}
          onDrop={onDrop}
        />
      </Spin>
    </Card>
  );
};

export default OrganizationTree;
