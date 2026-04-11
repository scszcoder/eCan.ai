/**
 * Skill History Modal
 * Modal component for viewing and restoring skill version history
 */

import React, { useEffect, useState } from 'react';
import {
  Modal,
  Table,
  Button,
  Space,
  Tag,
  Typography,
  Tooltip,
  Spin,
  Empty,
  Popconfirm,
  Toast,
} from '@douyinfe/semi-ui';
import { IconRefresh, IconDelete, IconEdit2 } from '@douyinfe/semi-icons';
import { useTranslation } from 'react-i18next';
import { SkillHistoryRecord } from '../../types/skill-history';
import { useSkillHistoryStore } from '../../stores/skill-history-store';
import { useSkillInfoStore } from '../../stores/skill-info-store';

const { Text, Title } = Typography;

// History icon as inline SVG
const HistoryIcon = ({ size = 20 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <circle cx="12" cy="12" r="9" stroke="#8B5CF6" strokeWidth="2" />
    <path d="M12 7v5l3 2" stroke="#8B5CF6" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

interface HistoryModalProps {
  visible: boolean;
  onClose: () => void;
  onRestore?: (historyData: SkillHistoryRecord) => void;
}

export const HistoryModal: React.FC<HistoryModalProps> = ({ visible, onClose, onRestore }) => {
  const { t } = useTranslation('skillEditor');
  const skillInfo = useSkillInfoStore((state) => state.skillInfo);
  const skillId = (skillInfo as any)?.skillId || (skillInfo as any)?.id;

  const {
    historyList,
    totalCount,
    maxHistory,
    isLoading,
    error,
    selectedHistoryId,
    fetchHistoryList,
    loadMore,
    selectHistory,
    restoreFromHistory,
    deleteHistory,
    deleteAllHistory,
    clearError,
  } = useSkillHistoryStore();

  const [restoring, setRestoring] = useState(false);
  const [selectedRecord, setSelectedRecord] = useState<SkillHistoryRecord | null>(null);

  useEffect(() => {
    if (visible && skillId) {
      fetchHistoryList(skillId);
    }
  }, [visible, skillId, fetchHistoryList]);

  useEffect(() => {
    if (selectedHistoryId) {
      const record = historyList.find((h) => h.id === selectedHistoryId);
      setSelectedRecord(record || null);
    } else {
      setSelectedRecord(null);
    }
  }, [selectedHistoryId, historyList]);

  const handleRestore = (record: SkillHistoryRecord) => {
    if (onRestore) {
      // Parent provides onRestore: delegate completely — API call and editor refresh
      // are handled by the parent so the modal stays passive.
      onRestore(record);
    } else {
      // No parent handler: fall back to a plain close without doing anything.
      setRestoring(true);
      restoreFromHistory(record.id)
        .then((result) => {
          if (result) {
            Toast.success({ content: t('history.restoreSuccess', { version: record.version_number }) });
          }
        })
        .catch((e) => {
          console.error('[HistoryModal] Restore error:', e);
          Toast.error({ content: t('history.restoreFailed') });
        })
        .finally(() => {
          setRestoring(false);
          onClose();
        });
    }
  };

  const handleDelete = async (record: SkillHistoryRecord) => {
    const success = await deleteHistory(record.id);
    if (success) {
      Toast.success({ content: t('history.deleteSuccess') });
    } else {
      Toast.error({ content: t('history.deleteFailed') });
    }
  };

  const handleDeleteAll = async () => {
    if (skillId) {
      const success = await deleteAllHistory(skillId);
      if (success) {
        Toast.success({ content: t('history.deleteAllSuccess') });
      } else {
        Toast.error({ content: t('history.deleteAllFailed') });
      }
    }
  };

  const handleViewDetails = (record: SkillHistoryRecord) => {
    selectHistory(record.id);
  };

  const formatDate = (timestamp: number | string | undefined | null) => {
    if (timestamp === null || timestamp === undefined) return '-';
    let ms: number;
    if (typeof timestamp === 'string') {
      const parsed = Date.parse(timestamp);
      if (Number.isNaN(parsed)) return '-';
      ms = parsed;
    } else {
      const n = Number(timestamp);
      if (!Number.isFinite(n) || n === 0) return '-';
      // Backend sends ms; tolerate seconds if ever mis-serialized (< ~Sep 2001 as ms)
      ms = n < 1e12 ? n * 1000 : n;
    }
    return new Date(ms).toLocaleString(undefined, {
      year: 'numeric',
      month: 'numeric',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  };

  const formatFileSize = (bytes?: number) => {
    if (!bytes) return '-';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const getSaveTypeTag = (saveType: string) => {
    const colorMap: Record<string, 'blue' | 'grey' | 'green' | 'yellow' | 'purple'> = {
      manual: 'blue',
      auto_save: 'grey',
      restore: 'green',
      restore_backup: 'yellow',
      save_as: 'purple',
    };
    const labelKeyMap: Record<string, string> = {
      manual: 'history.saveTypeLabels.manual',
      auto_save: 'history.saveTypeLabels.auto_save',
      restore: 'history.saveTypeLabels.restore',
      restore_backup: 'history.saveTypeLabels.restore_backup',
      save_as: 'history.saveTypeLabels.save_as',
    };
    const color = colorMap[saveType] || 'grey';
    const label = t(labelKeyMap[saveType] || saveType);
    return <Tag color={color}>{label}</Tag>;
  };

  const columns = [
    {
      title: t('history.version'),
      dataIndex: 'version_number',
      key: 'version',
      width: 100,
      render: (versionNumber: number, record: SkillHistoryRecord) => (
        <Space>
          <Text strong>v{versionNumber}</Text>
          <Text type="tertiary" style={{ fontSize: 11 }}>
            {record.version_label ? `#${record.version_label}` : ''}
          </Text>
        </Space>
      ),
    },
    {
      title: t('history.saveType'),
      dataIndex: 'save_type',
      key: 'save_type',
      width: 120,
      render: (saveType: string) => getSaveTypeTag(saveType),
    },
    {
      title: t('history.savedAt'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (createdAt: number) => formatDate(createdAt),
    },
    {
      title: t('history.fileSize'),
      dataIndex: 'file_size',
      key: 'file_size',
      width: 100,
      render: (size?: number) => formatFileSize(size),
    },
    {
      title: t('history.changeSummary'),
      dataIndex: 'change_summary',
      key: 'change_summary',
      ellipsis: true,
      render: (summary?: string) => (
        <Tooltip content={summary}>
          <Text>{summary || '-'}</Text>
        </Tooltip>
      ),
    },
    {
      title: t('history.actions'),
      key: 'actions',
      width: 150,
      render: (_: any, record: SkillHistoryRecord) => (
        <Space>
          <Tooltip content={t('history.viewDetails')}>
            <Button
              size="small"
              icon={<IconEdit2 />}
              onClick={() => handleViewDetails(record)}
              type={selectedHistoryId === record.id ? 'primary' : 'tertiary'}
            />
          </Tooltip>
          <Tooltip content={t('history.restore')}>
            <Button
              size="small"
              icon={<IconRefresh />}
              onClick={() => handleRestore(record)}
              loading={restoring && selectedHistoryId === record.id}
              disabled={restoring}
            />
          </Tooltip>
          <Popconfirm
            title={t('history.deleteRecord')}
            onConfirm={() => handleDelete(record)}
            okText={t('common.remove')}
            cancelText={t('common.cancel')}
          >
            <Tooltip content={t('history.delete')}>
              <Button size="small" icon={<IconDelete />} type="danger" />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const hasMore = historyList.length < totalCount;

  return (
    <Modal
      title={
        <Space>
          <HistoryIcon size={20} />
          <span>{t('history.title')}</span>
          <Tag color="blue">{t('history.records', { count: totalCount })}</Tag>
        </Space>
      }
      visible={visible}
      onCancel={onClose}
      footer={null}
      width={1000}
      maskClosable={false}
      style={{ top: 50 }}
    >
      {error && (
        <div
          style={{
            marginBottom: 16,
            padding: 12,
            background: '#fff2f0',
            border: '1px solid #ffccc7',
            borderRadius: 4,
          }}
        >
          <Space>
            <Text type="danger">{error}</Text>
            <Button size="small" onClick={clearError}>{t('history.dismiss')}</Button>
          </Space>
        </div>
      )}

      <div style={{ marginBottom: 16 }}>
        <Space>
          <Text type="tertiary">
            {t('history.showingRecords', { shown: historyList.length, total: totalCount, max: maxHistory })}
          </Text>
          {totalCount > 0 && (
            <Popconfirm
              title={t('history.deleteAllHistory')}
              description={t('history.deleteAllDesc')}
              onConfirm={handleDeleteAll}
              okText={t('history.deleteAll')}
              cancelText={t('common.cancel')}
              position="topLeft"
            >
              <Button size="small" type="danger" icon={<IconDelete />}>
                {t('history.deleteAll')}
              </Button>
            </Popconfirm>
          )}
        </Space>
      </div>

      <Spin tip={t('history.loading')} spinning={isLoading && historyList.length === 0}>
        {historyList.length === 0 && !isLoading ? (
          <Empty
            title={t('history.noHistory')}
            description={t('history.noHistoryDesc')}
          />
        ) : (
          <>
            <Table
              columns={columns}
              dataSource={historyList}
              rowKey="id"
              pagination={false}
              size="small"
              style={{ marginBottom: 16 }}
            />

            {hasMore && (
              <div style={{ textAlign: 'center', marginTop: 16 }}>
                <Button onClick={() => skillId && loadMore(skillId)} loading={isLoading}>
                  {t('history.loadMore')}
                </Button>
              </div>
            )}
          </>
        )}
      </Spin>

      {selectedRecord && (
        <div
          style={{
            marginTop: 24,
            padding: 16,
            background: '#f7f8fa',
            borderRadius: 8,
            border: '1px solid #e8e8e8',
          }}
        >
          <Title heading={5} style={{ marginTop: 0 }}>
            {t('history.selectedVersion')}
          </Title>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 24px' }}>
            <div>
              <Text type="tertiary">{t('history.skillId')}:</Text>
              <Text style={{ marginLeft: 8 }}>{selectedRecord.skill_id}</Text>
            </div>
            <div>
              <Text type="tertiary">{t('history.historyId')}:</Text>
              <Text style={{ marginLeft: 8 }}>{selectedRecord.id}</Text>
            </div>
            <div>
              <Text type="tertiary">{t('history.version')}:</Text>
              <Text strong style={{ marginLeft: 8 }}>
                v{selectedRecord.version} (#{selectedRecord.version_number})
              </Text>
            </div>
            <div>
              <Text type="tertiary">{t('history.saveType')}:</Text>
              <div style={{ marginLeft: 8 }}>{getSaveTypeTag(selectedRecord.save_type)}</div>
            </div>
            <div>
              <Text type="tertiary">{t('history.created')}:</Text>
              <Text style={{ marginLeft: 8 }}>{formatDate(selectedRecord.created_at)}</Text>
            </div>
            <div>
              <Text type="tertiary">{t('history.fileSize')}:</Text>
              <Text style={{ marginLeft: 8 }}>{formatFileSize(selectedRecord.file_size)}</Text>
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <Text type="tertiary">{t('history.changeSummary')}:</Text>
              <Text style={{ marginLeft: 8, display: 'block' }}>
                {selectedRecord.change_summary || '-'}
              </Text>
            </div>
            {selectedRecord.skill_data && (
              <div style={{ gridColumn: '1 / -1' }}>
                <Text type="tertiary">{t('history.storedFields')}:</Text>
                <div style={{ marginLeft: 8, marginTop: 4 }}>
                  {Object.keys(selectedRecord.skill_data).map((key) => (
                    <Tag key={key} style={{ margin: '2px' }}>
                      {key}
                    </Tag>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
};
