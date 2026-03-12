/**
 * RevisionPanel - Browseable version history for skill files.
 * Shows timestamped snapshots and allows one-click revert.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Tooltip, Modal, message } from 'antd';
import {
  HistoryOutlined,
  ReloadOutlined,
  RollbackOutlined,
  FileTextOutlined,
  CloseOutlined,
} from '@ant-design/icons';
import styled from 'styled-components';
import { IPCAPI } from '../../../../services/ipc/file-api';
import { useSkillInfoStore } from '../../stores/skill-info-store';
import type { SkillRevisionItem } from '../../../../services/ipc/file-api';

/* ------------------------------------------------------------------ */
/*  Styled components                                                  */
/* ------------------------------------------------------------------ */

const PanelContainer = styled.div<{ $collapsed: boolean; $width: number }>`
  display: flex;
  flex-direction: column;
  width: ${p => (p.$collapsed ? '0px' : `${p.$width}px`)};
  min-width: ${p => (p.$collapsed ? '0px' : `${p.$width}px`)};
  background: rgba(15, 23, 42, 0.95);
  border-right: ${p => (p.$collapsed ? 'none' : '1px solid rgba(148, 163, 184, 0.15)')};
  height: 100%;
  overflow: hidden;
  transition: width 0.25s ease, min-width 0.25s ease;
`;

const Header = styled.div`
  display: flex;
  align-items: center;
  padding: 10px 14px;
  gap: 8px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
  flex-shrink: 0;
`;

const HeaderTitle = styled.span`
  font-size: 13px;
  font-weight: 600;
  color: rgba(226, 232, 240, 0.9);
  flex: 1;
  white-space: nowrap;
`;

const IconBtn = styled.button`
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 4px;
  color: rgba(148, 163, 184, 0.8);
  cursor: pointer;
  font-size: 14px;
  &:hover {
    color: #3b82f6;
    background: rgba(59, 130, 246, 0.1);
  }
`;

const ListContainer = styled.div`
  flex: 1;
  overflow-y: auto;
  padding: 6px 8px;

  &::-webkit-scrollbar { width: 4px; }
  &::-webkit-scrollbar-thumb {
    background: rgba(148, 163, 184, 0.25);
    border-radius: 2px;
  }
`;

const EmptyState = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 16px;
  gap: 10px;
  color: rgba(148, 163, 184, 0.5);
  font-size: 13px;
  text-align: center;
`;

const RevisionItem = styled.div<{ $active?: boolean }>`
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  margin: 2px 0;
  border-radius: 6px;
  cursor: pointer;
  background: ${p => (p.$active ? 'rgba(59, 130, 246, 0.15)' : 'transparent')};
  transition: background 0.15s;
  &:hover {
    background: rgba(51, 65, 85, 0.45);
  }
`;

const RevisionMeta = styled.div`
  flex: 1;
  min-width: 0;
`;

const RevisionFileName = styled.div`
  font-size: 12px;
  font-weight: 500;
  color: rgba(226, 232, 240, 0.85);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

const RevisionTimestamp = styled.div`
  font-size: 11px;
  color: rgba(148, 163, 184, 0.6);
  margin-top: 2px;
`;

const RevisionSize = styled.span`
  font-size: 11px;
  color: rgba(148, 163, 184, 0.45);
  white-space: nowrap;
`;

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

/** Format a revision timestamp like 20260312T153045Z to a readable string. */
function formatTimestamp(ts: string): string {
  if (!ts || ts.length < 15) return ts;
  // 20260312T153045Z → 2026-03-12 15:30:45 UTC
  const y = ts.slice(0, 4);
  const m = ts.slice(4, 6);
  const d = ts.slice(6, 8);
  const hh = ts.slice(9, 11);
  const mm = ts.slice(11, 13);
  const ss = ts.slice(13, 15);
  return `${y}-${m}-${d}  ${hh}:${mm}:${ss} UTC`;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Strip the timestamp prefix to get the original file name. */
function originalName(fileName: string): string {
  // 20260312T153045Z_my_skill_skill.json → my_skill_skill.json
  const idx = fileName.indexOf('_');
  return idx > 0 ? fileName.slice(idx + 1) : fileName;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

interface RevisionPanelProps {
  isCollapsed: boolean;
  onToggle: () => void;
  width?: number;
}

export const RevisionPanel: React.FC<RevisionPanelProps> = ({
  isCollapsed,
  onToggle,
  width = 320,
}) => {
  const { skillInfo } = useSkillInfoStore();
  const skillName = skillInfo?.skillName || '';

  const [revisions, setRevisions] = useState<SkillRevisionItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [reverting, setReverting] = useState<string | null>(null);

  const fetchRevisions = useCallback(async () => {
    if (!skillName) return;
    setLoading(true);
    try {
      const resp = await IPCAPI.getInstance().listSkillRevisions(skillName);
      if (resp.success && resp.data) {
        setRevisions(resp.data as SkillRevisionItem[]);
      } else {
        console.warn('[RevisionPanel] Failed to list revisions:', resp.error);
        setRevisions([]);
      }
    } catch (e) {
      console.error('[RevisionPanel] Error listing revisions:', e);
      setRevisions([]);
    } finally {
      setLoading(false);
    }
  }, [skillName]);

  // Auto-fetch when panel opens or skill changes
  useEffect(() => {
    if (!isCollapsed && skillName) {
      fetchRevisions();
    }
  }, [isCollapsed, skillName, fetchRevisions]);

  const handleRevert = useCallback(
    (rev: SkillRevisionItem) => {
      Modal.confirm({
        title: 'Revert to this revision?',
        content: (
          <div>
            <p>
              File: <strong>{originalName(rev.fileName)}</strong>
            </p>
            <p>
              Snapshot: <strong>{formatTimestamp(rev.timestamp)}</strong>
            </p>
            <p style={{ color: '#faad14', marginTop: 8 }}>
              The current version will be snapshotted first, so you can undo this
              revert later.
            </p>
          </div>
        ),
        okText: 'Revert',
        cancelText: 'Cancel',
        onOk: async () => {
          setReverting(rev.key);
          try {
            const resp = await IPCAPI.getInstance().revertSkillRevision(
              skillName,
              rev.key
            );
            if (resp.success && (resp.data as any)?.success) {
              message.success('Revision restored successfully');
              fetchRevisions();
            } else {
              message.error('Revert failed: ' + ((resp as any).error || 'unknown'));
            }
          } catch (e: any) {
            message.error('Revert error: ' + e.message);
          } finally {
            setReverting(null);
          }
        },
      });
    },
    [skillName, fetchRevisions]
  );

  if (isCollapsed) {
    return <PanelContainer $collapsed $width={width} />;
  }

  return (
    <PanelContainer $collapsed={false} $width={width}>
      <Header>
        <HistoryOutlined style={{ fontSize: 15, color: '#3b82f6' }} />
        <HeaderTitle>Revision History</HeaderTitle>
        <Tooltip title="Refresh">
          <IconBtn onClick={fetchRevisions} disabled={loading}>
            <ReloadOutlined spin={loading} />
          </IconBtn>
        </Tooltip>
        <Tooltip title="Close">
          <IconBtn onClick={onToggle}>
            <CloseOutlined />
          </IconBtn>
        </Tooltip>
      </Header>

      <ListContainer>
        {!skillName && (
          <EmptyState>
            <HistoryOutlined style={{ fontSize: 28 }} />
            Open a skill to see its revision history
          </EmptyState>
        )}
        {skillName && revisions.length === 0 && !loading && (
          <EmptyState>
            <HistoryOutlined style={{ fontSize: 28 }} />
            No revisions yet.
            <span style={{ fontSize: 11 }}>
              Revisions are created automatically when you save changes.
            </span>
          </EmptyState>
        )}
        {revisions.map(rev => (
          <RevisionItem key={rev.key} $active={reverting === rev.key}>
            <FileTextOutlined
              style={{ marginTop: 3, fontSize: 14, color: 'rgba(148,163,184,0.6)' }}
            />
            <RevisionMeta>
              <RevisionFileName title={originalName(rev.fileName)}>
                {originalName(rev.fileName)}
              </RevisionFileName>
              <RevisionTimestamp>{formatTimestamp(rev.timestamp)}</RevisionTimestamp>
            </RevisionMeta>
            <RevisionSize>{formatBytes(rev.size)}</RevisionSize>
            <Tooltip title="Revert to this version">
              <IconBtn
                onClick={e => {
                  e.stopPropagation();
                  handleRevert(rev);
                }}
              >
                <RollbackOutlined />
              </IconBtn>
            </Tooltip>
          </RevisionItem>
        ))}
      </ListContainer>
    </PanelContainer>
  );
};
