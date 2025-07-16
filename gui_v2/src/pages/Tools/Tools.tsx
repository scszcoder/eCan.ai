import React, { useState, useCallback, useEffect } from 'react';
import { Spin, Button, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import ActionButtons from '../../components/Common/ActionButtons';
import { IPCAPI } from '../../services/ipc/api';
import { APIResponse } from '@/services/ipc';
import { useUserStore } from '../../stores/userStore';
import ToolsList from './ToolsList';
import ToolDetail from './ToolDetail';
import { Tool } from './types';
import DetailLayout from '../../components/Layout/DetailLayout';

const { Text } = Typography;

const Tools: React.FC = () => {
  const { t } = useTranslation();
  const [tools, setTools] = useState<Tool[]>([]);
  const [selectedTool, setSelectedTool] = useState<Tool | null>(null);
  const [loading, setLoading] = useState(false);

  const username = useUserStore((state) => state.username);

  const fetchTools = useCallback(async () => {
    try {
      setLoading(true);
      const response: APIResponse<{ tools: Tool[] }> = await IPCAPI.getInstance().getTools(username || '', []);
      if (response && response.success && response.data && response.data.tools) {
        setTools(response.data.tools);
        setSelectedTool(response.data.tools[0] || null);
      }
    } catch (error) {
      console.error('Error fetching tools:', error);
    } finally {
      setLoading(false);
    }
  }, [username]);

  useEffect(() => {
    fetchTools();
  }, [fetchTools]);

  const handleRefresh = useCallback(async () => {
    await fetchTools();
  }, [fetchTools]);

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