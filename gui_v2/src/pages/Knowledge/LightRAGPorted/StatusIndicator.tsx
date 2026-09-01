import React, { useEffect, useState, useRef } from 'react';
import { theme, Tooltip } from 'antd';
import { SyncOutlined, CheckCircleOutlined, ClockCircleOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useWorkspace } from './useWorkspace';
import { get_ipc_api } from '@/services/ipc_api';
import type { ProcessingProgress } from '@/services/ipc/lightragApi';

/**
 * Live processing-status indicator for the LightRAG Knowledge page.
 *
 * Polls ``lightragApi.getProcessingProgress`` every 5s (workspace-scoped
 * via the shared ``useWorkspace`` singleton) and renders the current
 * state as an icon + short label, with a tooltip showing the latest
 * chunk-level summary if one is available.
 *
 * Extracted from the legacy Header so it can live in the tab bar (see
 * Tabs.tsx) without dragging the rest of the header chrome along.
 */
const StatusIndicator: React.FC = () => {
  const { token } = theme.useToken();
  const { t } = useTranslation();
  const [workspace] = useWorkspace();
  const [processingProgress, setProcessingProgress] = useState<ProcessingProgress | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(false);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const fetchProcessingStatus = async () => {
    try {
      setLoadingStatus(true);
      const response = await get_ipc_api().lightragApi.getProcessingProgress(undefined, workspace || undefined);
      if (response.success && response.data) {
        setProcessingProgress(response.data);
      }
    } catch {
      // 静默失败，不影响 UI
    } finally {
      setLoadingStatus(false);
    }
  };

  useEffect(() => {
    fetchProcessingStatus();
    pollIntervalRef.current = setInterval(fetchProcessingStatus, 5000);
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    };
  }, [workspace]);

  const hasActivity = processingProgress && (
    (processingProgress.processing_count || 0) > 0 ||
    (processingProgress.pending_count || 0) > 0
  );

  const getStatusColor = () => {
    if (!processingProgress) return token.colorTextTertiary;
    const failed = processingProgress.failed_count || 0;
    if (failed > 0) return token.colorError;
    if (hasActivity) return token.colorWarning;
    return token.colorSuccess;
  };

  const StatusIcon = () => {
    if (!processingProgress) return <ClockCircleOutlined style={{ color: token.colorTextTertiary }} />;
    const failed = processingProgress.failed_count || 0;
    if (failed > 0) return <ExclamationCircleOutlined style={{ color: token.colorError }} />;
    if (hasActivity) return <SyncOutlined spin style={{ color: token.colorWarning }} />;
    return <CheckCircleOutlined style={{ color: token.colorSuccess }} />;
  };

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

  const latestMessage = processingProgress?.pipeline?.latest_message;
  const CHUNK_SUMMARY_REGEX =
    /Chunk\s+(\d+)\s+of\s+(\d+)\s+extracted\s+(\d+)\s+Ent\s*\+\s*(\d+)\s+Rel/i;
  const chunkSummaryMatch = latestMessage ? CHUNK_SUMMARY_REGEX.exec(latestMessage) : null;
  const chunkSummary = chunkSummaryMatch
    ? `Chunk ${chunkSummaryMatch[1]}/${chunkSummaryMatch[2]} · ${chunkSummaryMatch[3]} Ent + ${chunkSummaryMatch[4]} Rel`
    : null;

  return (
    <Tooltip
      title={loadingStatus ? t('pages.knowledge.lightrag.headerStatus.tooltipRefreshing') : getStatusText()}
      placement="bottom"
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          fontSize: 12,
          color: getStatusColor(),
          cursor: 'default',
          whiteSpace: 'nowrap'
        }}
      >
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
  );
};

export default StatusIndicator;