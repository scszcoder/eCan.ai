import React from 'react';
import { useKnowledgeData } from './hooks/useKnowledgeData';
import { KnowledgeList } from './components/KnowledgeList';
import DetailLayout from '../../components/Layout/DetailLayout';
import { useTranslation } from 'react-i18next';
import { Statistic, Space, Button } from 'antd';
import { ClusterOutlined, CheckCircleOutlined, EnvironmentOutlined, ThunderboltOutlined, ToolOutlined, ClockCircleOutlined, PlusOutlined, HistoryOutlined } from '@ant-design/icons';
import type { DetailItem } from '../../components/Common/DetailCard';
import DetailCard from '../../components/Common/DetailCard';

const Knowledge: React.FC = () => {
  const { t } = useTranslation();
  const knowledge = useKnowledgeData();

  const listTitle = (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <span>{t('pages.knowledge.title')}</span>
    </div>
  );

  const renderDetailsContent = (): React.ReactNode => {
    const selectedKnowledge = knowledge.selectedKnowledge;
    if (!selectedKnowledge) {
      return <span style={{ color: '#888' }}>{t('pages.knowledge.selectKnowledge')}</span>;
    }
    return (
      <Space direction="vertical" style={{ width: '100%' }}>
        <DetailCard
          title={t('pages.knowledge.vehicleInformation')}
          items={[
            {
              label: t('pages.knowledge.name'),
              value: selectedKnowledge.name,
              icon: <ClusterOutlined />, },
            {
              label: t('pages.knowledge.type'),
              value: selectedKnowledge.type,
              icon: <ClusterOutlined />, },
            {
              label: t('pages.knowledge.status'),
              value: (<span><CheckCircleOutlined /> {selectedKnowledge.status}</span>) as React.ReactNode,
              icon: <CheckCircleOutlined />, },
            {
              label: t('pages.knowledge.location'),
              value: selectedKnowledge.location,
              icon: <EnvironmentOutlined />, },
          ] as DetailItem[]}
        />
        <DetailCard
          title={t('pages.knowledge.performanceMetrics')}
          items={[
            {
              label: t('pages.knowledge.batteryLevel'),
              value: (
                <Statistic
                  value={selectedKnowledge.battery}
                  suffix="%"
                  prefix={<ThunderboltOutlined />}
                />
              ) as React.ReactNode,
              icon: <ThunderboltOutlined />, },
            {
              label: t('pages.knowledge.totalDistance'),
              value: (
                <Statistic
                  value={selectedKnowledge.totalDistance}
                  suffix="km"
                />
              ) as React.ReactNode,
              icon: <ClusterOutlined />, },
            {
              label: t('pages.knowledge.lastMaintenance'),
              value: selectedKnowledge.lastMaintenance || '',
              icon: <ToolOutlined />, },
            {
              label: t('pages.knowledge.nextMaintenance'),
              value: selectedKnowledge.nextMaintenance || '',
              icon: <ClockCircleOutlined />, },
          ] as DetailItem[]}
        />
        <Space>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => knowledge.handleStatusChange(selectedKnowledge.id, 'active')}
            disabled={selectedKnowledge.status === 'active'}
          >
            {t('pages.knowledge.activate')}
          </Button>
          <Button
            icon={<ToolOutlined />}
            onClick={() => knowledge.handleMaintenance(selectedKnowledge.id)}
            disabled={selectedKnowledge.status === 'maintenance'}
          >
            {t('pages.knowledge.scheduleMaintenance')}
          </Button>
          <Button
            icon={<HistoryOutlined />}
            onClick={() => knowledge.handleStatusChange(selectedKnowledge.id, 'offline')}
            disabled={selectedKnowledge.status === 'offline'}
          >
            {t('pages.knowledge.setOffline')}
          </Button>
        </Space>
      </Space>
    );
  };

  return (
    <DetailLayout
      listTitle={listTitle}
      detailsTitle={t('pages.knowledge.details')}
      listContent={
        <KnowledgeList
          knowledges={knowledge.knowledges}
          loading={knowledge.loading}
          selectItem={knowledge.selectItem}
          t={t}
          handleSearch={knowledge.handleSearch}
          handleFilterChange={knowledge.handleFilterChange}
          handleReset={knowledge.handleReset}
          handleRefresh={knowledge.handleRefresh}
        />
      }
      detailsContent={renderDetailsContent()}
    />
  );
};

export default Knowledge;