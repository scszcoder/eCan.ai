/**
 * Fetch another machine's run logs to this one. Same LAN: straight across;
 * otherwise through the cloud, sealed so only this machine can open them.
 */
import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { App, Button, Card, Select, Space, Typography } from 'antd';
import { CloudDownloadOutlined, FolderOpenOutlined } from '@ant-design/icons';
import type { Vehicle } from '@/types/domain/vehicle';
import { get_ipc_api } from '@/services/ipc_api';
import { TransferList, useFleetTransfers } from '@/components/Fleet/FleetTransfers';

const FetchLogsCard: React.FC<{ vehicle: Vehicle }> = ({ vehicle }) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const tf = (k: string, d: string) => t(`fleet.${k}`, { defaultValue: d }) as string;
  const [hours, setHours] = useState(24);
  const [busy, setBusy] = useState(false);
  const { rows, refresh } = useFleetTransfers();

  const mine = rows.filter((r) => r.kind === 'logs' && r.source_vehicle_id === vehicle.id).slice(0, 5);

  const fetchLogs = async () => {
    setBusy(true);
    try {
      const res: any = await get_ipc_api().fetchMachineLogs(vehicle.id, hours);
      if (res?.success) {
        message.success(tf('logs_requested', 'Requested — it picks this up within a minute'));
        refresh();
      } else {
        message.error(res?.error?.message || tf('failed', 'Request failed'));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card size="small" title={tf('logs_title', 'Run logs')}
      extra={
        <Button size="small" type="text" icon={<FolderOpenOutlined />}
          onClick={() => get_ipc_api().openFleetDownloads()}>
          {tf('downloads', 'Downloads')}
        </Button>
      }>
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {tf('logs_hint', 'Copies its logs to this machine: over the LAN when you share one, through the cloud (encrypted) when you do not.')}
        </Typography.Text>
        <Space>
          <Select size="small" value={hours} onChange={setHours} style={{ width: 130 }}
            options={[2, 6, 24, 72, 168].map((h) => ({
              value: h, label: h < 24 ? `${h} ${tf('hours', 'hours')}` : `${h / 24} ${tf('days', 'day(s)')}`,
            }))} />
          <Button size="small" type="primary" icon={<CloudDownloadOutlined />} loading={busy}
            disabled={vehicle.status === 'offline'} onClick={fetchLogs}>
            {tf('fetch_logs', 'Fetch logs')}
          </Button>
        </Space>
        <TransferList rows={mine} />
      </Space>
    </Card>
  );
};

export default FetchLogsCard;
