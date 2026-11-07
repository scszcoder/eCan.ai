import React, { useState, useCallback, useEffect } from 'react';
import { Spin, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import ActionButtons from '../../components/Common/ActionButtons';
import { useUserStore } from '../../stores/userStore';
import { useToolStore } from '../../stores/toolStore';
import { Tool } from './types';
import ToolsList from './ToolsList';
import ToolDetail from './ToolDetail';
import DetailLayout from '../../components/Layout/DetailLayout';
import RefreshButton from '../../components/Common/RefreshButton';

const Tools: React.FC = () => {
  const { t } = useTranslation();
  const [selectedTool, setSelectedTool] = useState<Tool | null>(null);
  const [isAddingNew, setIsAddingNew] = useState(false);
  const username = useUserStore((state) => state.username);
  const { tools, loading, fetchTools, forceRefresh } = useToolStore();
  const hasFetchedRef = React.useRef(false);

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
    if (username && !hasFetchedRef.current) {
      hasFetchedRef.current = true;
      console.log('[Tools] Auto-loading tools for user:', username);
      fetchTools(username).catch(console.error);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [username]); // Only depend on username, use ref to prevent duplicate fetches

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

  const handleAddTool = useCallback(() => {
    setSelectedTool(null);
    setIsAddingNew(true);
  }, []);

  const handleCancelAdd = useCallback(() => {
    setIsAddingNew(false);
    if (tools.length > 0) {
      setSelectedTool(tools[0]);
    }
  }, [tools]);

  const handleToolSaved = useCallback(() => {
    setIsAddingNew(false);
  }, []);

  const handleSelectTool = useCallback((tool: Tool) => {
    setIsAddingNew(false);
    setSelectedTool(tool);
  }, []);

  const listTitle = (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
      <span style={{ fontSize: '16px', fontWeight: 600, lineHeight: '24px' }}>{t('pages.tools.title')}</span>
      <Tooltip title={t('pages.tools.refresh')}>
        <RefreshButton
          title={t('pages.tools.refresh')}
          onClick={handleRefresh}
          loading={loading}
        />
      </Tooltip>
    </div>
  );

  return (
    <div className="page-shell page-shell--fill">
    <DetailLayout
      listTitle={listTitle}
      detailsTitle={t('pages.tools.details')}
      listContent={
        <Spin spinning={loading}>
          <ToolsList
            tools={tools}
            selectedTool={selectedTool}
            onSelect={handleSelectTool}
            loading={loading}
          />
        </Spin>
      }
      detailsContent={
        <>
          {loading ? <Spin /> : (
            <ToolDetail
              tool={selectedTool}
              isAddingNew={isAddingNew}
              onSaved={handleToolSaved}
              onCancelAdd={handleCancelAdd}
            />
          )}
          {/* ActionButtons hidden while all tools are read-only */}
        </>
      }
      fillDetailsAvailableWidth
    />
    </div>
  );
};

export default Tools;