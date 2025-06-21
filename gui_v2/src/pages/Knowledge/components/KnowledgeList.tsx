import React from 'react';
import { List, Space, Tag, Progress, Typography } from 'antd';
import { ClusterOutlined, EnvironmentOutlined } from '@ant-design/icons';
import StatusTag from '../../../components/Common/StatusTag';
import SearchFilter from '../../../components/Common/SearchFilter';
import ActionButtons from '../../../components/Common/ActionButtons';
import styled from '@emotion/styled';

const { Text } = Typography;

const KnowledgeItem = styled.div`
  padding: 12px;
  border-bottom: 1px solid var(--border-color);
  &:last-child { border-bottom: none; }
  cursor: pointer;
  transition: all 0.3s ease;
  background-color: var(--bg-secondary);
  border-radius: 8px;
  margin: 4px 0;
  &:hover {
    background-color: var(--bg-tertiary);
    transform: translateX(4px);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  }
  .ant-typography { color: var(--text-primary); }
  .ant-tag { background-color: var(--bg-primary); border-color: var(--border-color); }
  .ant-progress-text { color: var(--text-primary); }
`;

export function KnowledgeList({
  knowledges, loading, selectItem, t,
  handleSearch, handleFilterChange, handleReset, handleRefresh
}: any) {
  return (
    <>
      <SearchFilter
        onSearch={handleSearch}
        onFilter={handleFilterChange}
        onFilterReset={handleReset}
        filterOptions={[
          {
            key: 'status',
            label: t('pages.knowledge.status'),
            options: [
              { label: t('pages.knowledge.status.active'), value: 'active' },
              { label: t('pages.knowledge.status.maintenance'), value: 'maintenance' },
              { label: t('pages.knowledge.status.offline'), value: 'offline' },
            ],
          },
          {
            key: 'type',
            label: t('pages.knowledge.type'),
            options: [
              { label: t('pages.knowledge.groundVehicle'), value: t('pages.knowledge.groundVehicle') },
              { label: t('pages.knowledge.aerialVehicle'), value: t('pages.knowledge.aerialVehicle') },
            ],
          },
        ]}
        placeholder={t('pages.knowledge.searchPlaceholder')}
      />
      <ActionButtons
        onAdd={() => {}}
        onEdit={() => {}}
        onDelete={() => {}}
        onRefresh={handleRefresh}
      />
      <List
        dataSource={Array.isArray(knowledges) ? knowledges : []}
        loading={loading}
        renderItem={knowledgePoint => (
          <KnowledgeItem onClick={() => selectItem(knowledgePoint)}>
            <Space direction="vertical" style={{ width: '100%' }}>
              <Space>
                <StatusTag status={knowledgePoint.status} />
                <ClusterOutlined />
                <Text strong>{knowledgePoint.name}</Text>
              </Space>
              <Space>
                <Tag color="blue">{knowledgePoint.type}</Tag>
                {knowledgePoint.currentTask && (
                  <Tag color="processing">{t('pages.knowledge.currentTask')}: {knowledgePoint.currentTask}</Tag>
                )}
              </Space>
              <Space>
                <EnvironmentOutlined />
                <Text type="secondary">{knowledgePoint.location}</Text>
              </Space>
              <Progress
                percent={knowledgePoint.battery}
                size="small"
                status={knowledgePoint.battery < 20 ? 'exception' : 'normal'}
              />
            </Space>
          </KnowledgeItem>
        )}
      />
    </>
  );
} 