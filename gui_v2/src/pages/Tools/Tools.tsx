import React, { useState, useCallback, useEffect } from 'react';
import { Spin, Button, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import ActionButtons from '../../components/Common/ActionButtons';
import { useUserStore } from '../../stores/userStore';
import { useToolStore, Tool } from '../../stores/toolStore';
import ToolsList from './ToolsList';
import ToolDetail from './ToolDetail';
import DetailLayout from '../../components/Layout/DetailLayout';

const { Text } = Typography;

const Tools: React.FC = () => {
  const { t } = useTranslation();
  const [selectedTool, setSelectedTool] = useState<Tool | null>(null);
  const username = useUserStore((state) => state.username);
  const { tools, loading, fetchTools } = useToolStore();

  useEffect(() => {
    if (username) {
      fetchTools(username);
    }
  }, [username, fetchTools]);

  useEffect(() => {
    if (tools.length > 0 && !selectedTool) {
      setSelectedTool(tools[0]);
    }
  }, [tools, selectedTool]);

  const handleRefresh = useCallback(async () => {
    if (username) {
      await fetchTools(username);
    }
  }, [username, fetchTools]);

  const listTitle = (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <Text strong>{t('pages.tools.title')}</Text>
      <Button
        shape="circle"
        icon={<ReloadOutlined />}
        onClick={handleRefresh}
        loading={loading}
        title={t('pages.tools.refresh')}
      />
    </div>
  );

  return (
    <DetailLayout
      listTitle={listTitle}
      detailsTitle={t('pages.tools.details')}
      listContent={
        <Spin spinning={loading}>
          <ToolsList
            tools={tools}
            selectedTool={selectedTool}
            onSelect={setSelectedTool}
            loading={loading}
          />
        </Spin>
      }
      detailsContent={
        <>
          {loading ? <Spin /> : <ToolDetail tool={selectedTool} />}
          <ActionButtons
            onAdd={() => {}}
            onEdit={() => {}}
            onDelete={() => {}}
            onRefresh={handleRefresh}
            onExport={() => {}}
            onImport={() => {}}
            onSettings={() => {}}
            addText={t('pages.tools.addTool')}
            editText={t('pages.tools.editTool')}
            deleteText={t('pages.tools.deleteTool')}
            refreshText={t('pages.tools.refreshTools')}
            exportText={t('pages.tools.exportTools')}
            importText={t('pages.tools.importTools')}
            settingsText={t('pages.tools.toolSettings')}
          />
        </>
      }
    />
  );
};

export default Tools;