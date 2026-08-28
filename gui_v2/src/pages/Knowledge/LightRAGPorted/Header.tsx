import React, { useEffect, useState, useRef } from 'react';
import { theme, Tooltip } from 'antd';
import { SyncOutlined, CheckCircleOutlined, ClockCircleOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import WorkspacePicker from './WorkspacePicker';
import { useWorkspace } from './useWorkspace';
import { get_ipc_api } from '@/services/ipc_api';
import type { ProcessingProgress } from '@/services/ipc/lightragApi';
import type { TabKey } from './Tabs';

// Minimal header without branding, login/version/lang, github, etc.
// Scoped styles via inline classes to avoid leaking globals.
//
// The right-hand side hosts the GLOBAL workspace (tenant) selector. It is
// backed by useWorkspace(), which is a sessionStorage-backed singleton
// shared with the per-tab pickers in DocumentsTab / RetrievalTab — so all
// three stay in sync regardless of which one the user touched last.

interface HeaderProps {
  activeTab?: TabKey;
}

const Header: React.FC<HeaderProps> = ({ activeTab }) => {
  const { token } = theme.useToken();
  const { t } = useTranslation();
  const [workspace, setWorkspace] = useWorkspace();
  const [processingProgress, setProcessingProgress] = useState<ProcessingProgress | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(false);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // 获取处理状态
  const fetchProcessingStatus = async () => {
    try {
      setLoadingStatus(true);
      const response = await get_ipc_api().lightragApi.getProcessingProgress(undefined, workspace || undefined);
      if (response.success && response.data) {
        setProcessingProgress(response.data);
      }
    } catch (e) {
      // 静默失败，不影响 UI
    } finally {
      setLoadingStatus(false);
    }
  };

  // 启动/停止轮询
  useEffect(() => {
    // 立即获取一次
    fetchProcessingStatus();

    // 每 5 秒轮询一次
    pollIntervalRef.current = setInterval(fetchProcessingStatus, 5000);

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    };
  }, [workspace]);

  // 计算是否有活动状态
  const hasActivity = processingProgress && (
    (processingProgress.processing_count || 0) > 0 ||
    (processingProgress.pending_count || 0) > 0
  );

  // 获取状态颜色
  const getStatusColor = () => {
    if (!processingProgress) return token.colorTextTertiary;
    const failed = processingProgress.failed_count || 0;
    if (failed > 0) return token.colorError;
    if (hasActivity) return token.colorWarning;
    return token.colorSuccess;
  };

  // 获取状态图标
  const StatusIcon = () => {
    if (!processingProgress) return <ClockCircleOutlined style={{ color: token.colorTextTertiary }} />;
    const failed = processingProgress.failed_count || 0;
    if (failed > 0) return <ExclamationCircleOutlined style={{ color: token.colorError }} />;
    if (hasActivity) return <SyncOutlined spin style={{ color: token.colorWarning }} />;
    return <CheckCircleOutlined style={{ color: token.colorSuccess }} />;
  };

  // 获取状态文字
  const getStatusText = () => {
    if (!processingProgress) return t('pages.knowledge.lightrag.headerStatus.loading');
    const processing = processingProgress.processing_count || 0;
    const pending = processingProgress.pending_count || 0;
    const failed = processingProgress.failed_count || 0;
    const processed = processingProgress.processed_count || 0;
    const total = processingProgress.total_count || 0;

    if (failed > 0) {
      return t('pages.knowledge.lightrag.headerStatus.failed', { failed });
    }
    if (processing > 0 && pending > 0) {
      return t('pages.knowledge.lightrag.headerStatus.processingAndPending', { processing, pending });
    }
    if (processing > 0) {
      return t('pages.knowledge.lightrag.headerStatus.processing', { processing });
    }
    if (pending > 0) {
      return t('pages.knowledge.lightrag.headerStatus.pending', { pending });
    }
    if (total > 0) {
      return t('pages.knowledge.lightrag.headerStatus.processed', { processed, total });
    }
    return t('pages.knowledge.lightrag.headerStatus.idle');
  };

  // 从 LightRAG 1.5.6 latest_message 解析 "Chunk N of M ..." 的实时摘要。
  // 文档级加工完成阶段消息也可能命中（无 chunk 前缀），需要保守返回 null。
  const latestMessage = processingProgress?.pipeline?.latest_message;
  const CHUNK_SUMMARY_REGEX =
    /Chunk\s+(\d+)\s+of\s+(\d+)\s+extracted\s+(\d+)\s+Ent\s*\+\s*(\d+)\s+Rel/i;
  const chunkSummaryMatch = latestMessage ? CHUNK_SUMMARY_REGEX.exec(latestMessage) : null;
  const chunkSummary = chunkSummaryMatch
    ? `Chunk ${chunkSummaryMatch[1]}/${chunkSummaryMatch[2]} · ${chunkSummaryMatch[3]} Ent + ${chunkSummaryMatch[4]} Rel`
    : null;

  // 使用主题 token 的背景色
  const headerBg = token.colorBgContainer;

  // 在 settings tab 隐藏状态
  const showStatus = activeTab !== 'settings';

  return (
    <header
      style={{
        background: headerBg,
        padding: '8px 48px 20px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}
      data-ec-scope="lightrag-ported"
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        {showStatus && (
          <Tooltip
            title={loadingStatus ? t('pages.knowledge.lightrag.headerStatus.tooltipRefreshing') : getStatusText()}
            placement="bottom"
          >
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontSize: 12,
              color: getStatusColor(),
              cursor: 'default',
              whiteSpace: 'nowrap'
            }}>
              {loadingStatus ? (
                <SyncOutlined spin style={{ fontSize: 14 }} />
              ) : (
                <StatusIcon />
              )}
              <span style={{ fontWeight: 500 }}>
                {getStatusText()}
              </span>
              {chunkSummary && (
                <Tooltip title={latestMessage} placement="bottom">
                  <span
                    style={{
                      fontSize: 11,
                      color: token.colorTextSecondary,
                      fontWeight: 400,
                      whiteSpace: 'nowrap',
                      maxWidth: 320,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis'
                    }}
                  >
                    · {chunkSummary}
                  </span>
                </Tooltip>
              )}
            </div>
          </Tooltip>
        )}
      </div>
      <div style={{ display: 'flex', alignItems: 'center' }}>
        {/* Tabs are rendered by parent; keep center clean */}
      </div>
      <nav style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <WorkspacePicker
          value={workspace}
          onChange={setWorkspace}
          label="Workspace"
          placeholder="(server default)"
        />
      </nav>
    </header>
  );
};

export default Header;
