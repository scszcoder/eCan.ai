import React, { useState, useCallback, useEffect } from 'react';
import { Spin, Button, Tooltip } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import ActionButtons from '../../components/Common/ActionButtons';
import { useUserStore } from '../../stores/userStore';
import { useToolStore } from '../../stores/toolStore';
import { Tool } from './types';
import ToolsList from './ToolsList';
import ToolDetail from './ToolDetail';
import DetailLayout from '../../components/Layout/DetailLayout';

const StyledRefreshButton = styled(Button)`
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

const Tools: React.FC = () => {
  const { t } = useTranslation();
  const [selectedTool, setSelectedTool] = useState<Tool | null>(null);
  const username = useUserStore((state) => state.username);
  const { tools, loading, fetchTools, forceRefresh } = useToolStore();

  // Debug: log raw tools payload including schemas
  useEffect(() => {
    try {
      if (tools && tools.length) {
        // Avoid spamming huge logs repeatedly by stringifying succinctly
        console.log('[Tools] tools count =', tools.length);
        // console.log('[Tools] tools raw array JSON:', JSON.stringify(tools, null, 2));
      } else {
        console.log('[Tools] tools empty');
      }
    } catch {}
  }, [tools]);

  // Debug: log selected tool and its schemas whenever it changes
  useEffect(() => {
    if (!selectedTool) return;
    try {
      console.log('[Tools] selected tool:', selectedTool);
      // Some backends may nest schemas under different keys; dump common candidates
      console.log('[Tools] selected tool inputSchema:', (selectedTool as any).inputSchema);
      console.log('[Tools] selected tool outputSchema:', (selectedTool as any).outputSchema);
    } catch {}
  }, [selectedTool]);

  // Auto-load tools when component mounts or username changes
  useEffect(() => {
    if (username && tools.length === 0 && !loading) {
      console.log('[Tools] Auto-loading tools for user:', username);
      fetchTools(username).catch(console.error);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [username, tools.length, loading]); // Remove fetchTools 避免无限Loop

  useEffect(() => {
    if (tools.length > 0 && !selectedTool) {
      setSelectedTool(tools[0]);
    }
  }, [tools, selectedTool]);

  const handleRefresh = useCallback(async () => {
    if (username) {
      await forceRefresh(username);
    }
  }, [username, forceRefresh]);

  const listTitle = (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
      <span style={{ fontSize: '16px', fontWeight: 600, lineHeight: '24px' }}>{t('pages.tools.title')}</span>
      <Tooltip title={t('pages.tools.refresh')}>
        <StyledRefreshButton
          shape="circle"
          icon={<ReloadOutlined />}
          onClick={handleRefresh}
          loading={loading}
        />
      </Tooltip>
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