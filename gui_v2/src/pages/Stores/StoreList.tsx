import React from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Badge, Button, Checkbox, List, Space, Tag, Tooltip, Typography } from 'antd';
import { ReloadOutlined, WarningOutlined } from '@ant-design/icons';
import type { StoreRow } from './types';

interface StoreListProps {
  stores: StoreRow[];
  thisVehicleId: string;
  selectedId: string | null;
  onSelect: (id: string) => void;
  loading: boolean;
  onRefresh: () => void;
  showArchived: boolean;
  onShowArchived: (v: boolean) => void;
  cloudError: string;
}

/** Where a store runs, in one word: here / elsewhere / nowhere. */
export const placementBadge = (s: StoreRow, thisVehicleId: string) => {
  const running = s.reportedVehicleId;
  if (!running) return 'default' as const;
  if (s.reportedVehicleOnline === false) return 'error' as const;
  return running === thisVehicleId ? ('success' as const) : ('processing' as const);
};

const StoreList: React.FC<StoreListProps> = ({
  stores, thisVehicleId, selectedId, onSelect, loading, onRefresh, showArchived, onShowArchived, cloudError,
}) => {
  const { t } = useTranslation();
  const ts = (k: string, d: string) => t(`pages.stores.${k}`, d) as string;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ padding: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography.Text strong style={{ color: '#fff' }}>{ts('title', 'Stores')}</Typography.Text>
        <Space size={4}>
          <Checkbox checked={showArchived} onChange={(e) => onShowArchived(e.target.checked)}>
            {ts('show_archived', 'Show archived')}
          </Checkbox>
          <Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={onRefresh} />
        </Space>
      </div>
      {cloudError && (
        <Alert type="warning" showIcon style={{ margin: '0 12px 8px' }}
          message={ts('cloud_unavailable', 'Placement unavailable; showing local data only')}
          description={cloudError} />
      )}
      <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
        <List
          dataSource={stores}
          locale={{ emptyText: ts('empty', 'No stores yet') }}
          renderItem={(s) => {
            const attention = s.loginState === 'needs_login' || s.misplaced;
            return (
              <List.Item
                onClick={() => onSelect(s.storeId)}
                style={{ cursor: 'pointer', paddingLeft: 16, paddingRight: 12,
                  background: selectedId === s.storeId ? 'rgba(255,255,255,0.06)' : 'transparent' }}
              >
                <Space direction="vertical" size={2} style={{ width: '100%' }}>
                  <Space size={6}>
                    <Badge status={placementBadge(s, thisVehicleId)} />
                    <Typography.Text strong>{s.label || s.storeId}</Typography.Text>
                    {s.platform && <Tag>{s.platform}</Tag>}
                    {s.status === 'archived' && <Tag>{ts('archived', 'archived')}</Tag>}
                    {attention && (
                      <Tooltip title={s.misplaced ? ts('misplaced', 'Running somewhere other than assigned')
                        : ts('needs_login', 'Needs login')}>
                        <WarningOutlined style={{ color: '#faad14' }} />
                      </Tooltip>
                    )}
                  </Space>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {t('pages.stores.counts', {
                      defaultValue: '{{agents}} agents · {{tasks}} tasks',
                      agents: s.local.agents.length, tasks: s.local.tasks.length,
                    })}
                  </Typography.Text>
                </Space>
              </List.Item>
            );
          }}
        />
      </div>
    </div>
  );
};

export default StoreList;
