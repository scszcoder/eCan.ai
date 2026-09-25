/**
 * Fleet transfers (fetch logs, move a store's login): live status list.
 * See docs/FLEET_TRANSFER_DESIGN.md.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Space, Tag, Tooltip, Typography } from 'antd';
import { FolderOpenOutlined } from '@ant-design/icons';
import { get_ipc_api } from '@/services/ipc_api';

export interface FleetTransfer {
  transfer_id: string;
  kind: 'logs' | 'profile';
  status: string;
  source_vehicle_id: string;
  receiver_vehicle_id: string;
  params: Record<string, any>;
  route?: string | null;
  error?: string | null;
  created_at?: string;
  /** Set on the machine that received it. */
  path?: string;
  profile_id?: string;
}

const OPEN = ['requested', 'ready', 'sending', 'uploaded'];
const STATUS_COLOR: Record<string, string> = {
  requested: 'default', ready: 'processing', sending: 'processing', uploaded: 'processing',
  done: 'success', failed: 'error', expired: 'default',
};

/** Polls `fleet.transfers` every 3s while one is open, else every 30s. */
export function useFleetTransfers() {
  const [rows, setRows] = useState<FleetTransfer[]>([]);
  const [error, setError] = useState('');
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(async () => {
    if (timer.current) clearTimeout(timer.current);
    let open = false;
    try {
      const res: any = await get_ipc_api().getFleetTransfers();
      if (res?.success) {
        const list: FleetTransfer[] = res.data?.transfers || [];
        setRows(list);
        setError('');
        open = list.some((r) => OPEN.includes(r.status));
      } else {
        setError(res?.error?.message || String(res?.error || ''));
      }
    } catch (e: any) {
      setError(String(e?.message || e));
    }
    timer.current = setTimeout(refresh, open ? 3000 : 30000);
  }, []);

  useEffect(() => {
    refresh();
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [refresh]);

  return { rows, error, refresh };
}

export const TransferList: React.FC<{ rows: FleetTransfer[]; empty?: string }> = ({ rows, empty }) => {
  const { t } = useTranslation();
  const tf = (k: string, d: string) => t(`fleet.${k}`, { defaultValue: d }) as string;
  if (!rows.length) {
    return empty ? <Typography.Text type="secondary">{empty}</Typography.Text> : null;
  }
  return (
    <Space direction="vertical" size={4} style={{ width: '100%' }}>
      {rows.map((r) => (
        <Space key={r.transfer_id} size={6} wrap>
          <Tag color={STATUS_COLOR[r.status] || 'default'}>{tf(`status_${r.status}`, r.status)}</Tag>
          {r.route && <Tag>{r.route === 'lan' ? tf('via_lan', 'over LAN') : tf('via_cloud', 'via cloud')}</Tag>}
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {(r.created_at || '').replace('T', ' ').slice(0, 16)}
          </Typography.Text>
          {r.error && (
            <Tooltip title={r.error}>
              <Typography.Text type="danger" style={{ fontSize: 12, maxWidth: 260 }} ellipsis>{r.error}</Typography.Text>
            </Tooltip>
          )}
          {r.path && (
            <Button size="small" icon={<FolderOpenOutlined />}
              onClick={() => get_ipc_api().openFleetDownloads(r.path)}>
              {tf('open', 'Open')}
            </Button>
          )}
        </Space>
      ))}
    </Space>
  );
};
