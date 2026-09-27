import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Badge, Button, Drawer, Space, Tag, Tooltip, Typography } from 'antd';
import { EyeOutlined, ReloadOutlined } from '@ant-design/icons';
import MachineActivity, { FLEET_STALE_MS } from './MachineActivity';
import { useFleetFeedStore } from '@/stores/fleetFeedStore';
import { sendFleetCommand, startFleetFeed, stopFleetFeed } from '@/services/web/fleetFeed';

interface Props {
  machineId: string;
  name: string;
  role?: string;
  online: boolean;
}

/** "Watch this machine": opens a drawer with its live activity (Vehicles panel). */
const WatchMachineButton: React.FC<Props> = ({ machineId, name, role, online }) => {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const m = useFleetFeedStore((s) => s.machines[machineId]);
  const connection = useFleetFeedStore((s) => s.connection);

  const show = (e: React.MouseEvent) => {
    e.stopPropagation();                      // the card's own click selects it
    setOpen(true);
    startFleetFeed();
    void sendFleetCommand('snapshot', machineId);
  };

  const close = () => {
    setOpen(false);
    if (useFleetFeedStore.getState().machines[machineId]?.logTail) {
      void sendFleetCommand('log_stop', machineId);   // nothing keeps streaming once closed
    }
    stopFleetFeed();
  };

  const live = Boolean(m && Date.now() - m.lastSeen < FLEET_STALE_MS);

  return (
    <>
      <Tooltip title={online ? t('pages.fleet.watch', 'Live activity') : t('pages.fleet.offline', 'This machine is offline')}>
        <Button type="text" size="small" icon={<EyeOutlined />} disabled={!online} onClick={show} />
      </Tooltip>
      <Drawer
        open={open}
        onClose={close}
        width={560}
        destroyOnHidden
        title={
          <Space wrap>
            <Badge status={live ? 'success' : 'default'} />
            <span>{t('pages.fleet.liveActivity', 'Live activity')}: {name}</span>
            {role && <Tag>{role}</Tag>}
          </Space>
        }
        extra={
          <Button size="small" icon={<ReloadOutlined />} onClick={() => sendFleetCommand('snapshot', machineId)}>
            {t('pages.fleet.refresh', 'Refresh')}
          </Button>
        }
      >
        <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>
          {t('pages.fleet.lastSeen', 'last seen')} {m?.lastSeen ? new Date(m.lastSeen).toLocaleTimeString() : '—'}
          {connection !== 'live' && connection !== 'idle' ? ` · ${connection}` : ''}
        </Typography.Text>
        <MachineActivity machineId={machineId} />
      </Drawer>
    </>
  );
};

export default WatchMachineButton;
