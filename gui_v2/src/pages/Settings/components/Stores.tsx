/**
 * Stores — where each store should run, and where it actually runs.
 *
 * "Assigned to" is the owner's desired state (store_assign); "Running on" is
 * what a machine last reported (store_report, sent on every heartbeat). They
 * are shown side by side and never merged: a store assigned to A that still
 * reports from B must be visible as exactly that.
 *
 * Machines are shown by role relative to this one, because the cloud row
 * carries only a stable id -- "This machine" is the heartbeat id the backend
 * hands back as `this_vehicle_id`.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { App, Alert, Button, Checkbox, Empty, Popconfirm, Space, Table, Tag, Tooltip, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { get_ipc_api } from '@/services/ipc_api';

const { Text, Paragraph } = Typography;

interface StoreRow {
  storeId: string;
  platform?: string;
  label?: string;
  status?: string;
  assignedVehicleId: string | null;
  assignedVehicleOnline: boolean | null;
  reportedVehicleId: string | null;
  reportedVehicleOnline: boolean | null;
  misplaced: boolean;
  loginState?: string;
  lastReportedAt?: string | null;
}

interface StoreListResult {
  stores: StoreRow[];
  needs_login: number;
  misplaced: number;
  this_vehicle_id: string;
}

const LOGIN_COLORS: Record<string, string> = { ok: 'green', needs_login: 'orange', unknown: 'default' };

const Stores: React.FC = () => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const ts = useCallback(
    (key: string, fallback?: string, opts?: Record<string, unknown>) =>
      t(`pages.settings.stores.${key}`, { defaultValue: fallback ?? key, ...(opts || {}) }) as string,
    [t],
  );
  const errText = (err: unknown, fallback: string): string =>
    (typeof err === 'string' ? err : (err as { message?: string })?.message) || fallback;

  const [data, setData] = useState<StoreListResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [showArchived, setShowArchived] = useState(false);
  const [busyId, setBusyId] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await get_ipc_api().listStores<StoreListResult>(showArchived);
      if (res.success && res.data) {
        setData(res.data);
        setLoadError('');
      } else {
        setLoadError(errText(res.error, ts('load_failed', 'Failed to load stores')));
      }
    } catch (err) {
      setLoadError(errText(err, ts('load_failed', 'Failed to load stores')));
    } finally {
      setLoading(false);
    }
  }, [showArchived, ts]);

  useEffect(() => { load(); }, [load]);

  const act = async (storeId: string, run: () => Promise<any>, okText?: string) => {
    setBusyId(storeId);
    try {
      const res = await run();
      if (res.success) {
        for (const w of res.data?.warnings || []) message.warning(w);
        if (okText) message.success(okText);
        await load();
      } else {
        message.error(errText(res.error, ts('action_failed', 'Action failed')));
      }
    } catch (err) {
      message.error(errText(err, ts('action_failed', 'Action failed')));
    } finally {
      setBusyId('');
    }
  };

  const thisId = data?.this_vehicle_id || '';

  const machine = (id: string | null, online: boolean | null) => {
    if (!id) return <Text type="secondary">{ts('none', '—')}</Text>;
    const name = id === thisId ? ts('this_machine', 'This machine') : ts('other_machine', 'Other machine');
    return (
      <Tooltip title={id}>
        <Space size={4}>
          <Text strong={id === thisId}>{name}</Text>
          {online === false && <Tag color="default">{ts('offline', 'offline')}</Tag>}
        </Space>
      </Tooltip>
    );
  };

  const columns = [
    {
      title: ts('store', 'Store'),
      key: 'store',
      render: (_: unknown, r: StoreRow) => (
        <Space size={4} wrap>
          <Text>{r.label || r.storeId}</Text>
          {r.label && r.label !== r.storeId && <Text type="secondary">({r.storeId})</Text>}
          {r.platform && <Tag>{r.platform}</Tag>}
          {r.status === 'archived' && <Tag color="default">{ts('archive', 'Archive')}</Tag>}
        </Space>
      ),
    },
    {
      title: ts('assigned', 'Assigned to'),
      key: 'assigned',
      render: (_: unknown, r: StoreRow) => machine(r.assignedVehicleId, r.assignedVehicleOnline),
    },
    {
      title: ts('reported', 'Running on'),
      key: 'reported',
      render: (_: unknown, r: StoreRow) => (
        <Space size={4}>
          {machine(r.reportedVehicleId, r.reportedVehicleOnline)}
          {r.misplaced && <Tag color="red">{ts('misplaced', 'Assigned elsewhere')}</Tag>}
        </Space>
      ),
    },
    {
      title: ts('login', 'Login'),
      key: 'login',
      render: (_: unknown, r: StoreRow) => {
        const state = r.loginState || 'unknown';
        return <Tag color={LOGIN_COLORS[state] || 'default'}>{state}</Tag>;
      },
    },
    {
      title: ts('last_report', 'Last report'),
      key: 'last',
      render: (_: unknown, r: StoreRow) =>
        r.lastReportedAt ? new Date(r.lastReportedAt).toLocaleString() : ts('none', '—'),
    },
    {
      title: '',
      key: 'actions',
      render: (_: unknown, r: StoreRow) => {
        const busy = busyId === r.storeId;
        const api = get_ipc_api();
        if (r.status === 'archived') {
          return (
            <Button size="small" loading={busy}
              onClick={() => act(r.storeId, () => api.archiveStore(r.storeId, true))}>
              {ts('restore', 'Restore')}
            </Button>
          );
        }
        return (
          <Space size={4}>
            <Button size="small" type="primary" loading={busy}
              disabled={!thisId || r.assignedVehicleId === thisId}
              onClick={() => act(r.storeId, () => api.assignStore(r.storeId, { this_machine: true }),
                ts('assigned_ok', 'Assigned'))}>
              {ts('assign_here', 'Assign here')}
            </Button>
            <Button size="small" loading={busy} disabled={!r.assignedVehicleId}
              onClick={() => act(r.storeId, () => api.assignStore(r.storeId, { vehicle_id: null }))}>
              {ts('unassign', 'Unassign')}
            </Button>
            <Popconfirm title={ts('archive', 'Archive') + '?'}
              onConfirm={() => act(r.storeId, () => api.archiveStore(r.storeId))}>
              <Button size="small" danger loading={busy}>{ts('archive', 'Archive')}</Button>
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  return (
    <div>
      <Paragraph type="secondary">{ts('intro')}</Paragraph>
      <Space style={{ marginBottom: 12 }} wrap>
        <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>{ts('refresh', 'Refresh')}</Button>
        <Checkbox checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)}>
          {ts('show_archived', 'Show archived')}
        </Checkbox>
        {!!data?.needs_login && (
          <Tag color="orange">{ts('needs_login_count', undefined, { count: data.needs_login })}</Tag>
        )}
        {!!data?.misplaced && (
          <Tag color="red">{ts('misplaced_count', undefined, { count: data.misplaced })}</Tag>
        )}
      </Space>
      {loadError && <Alert type="warning" showIcon message={loadError} style={{ marginBottom: 12 }} />}
      <Table<StoreRow>
        rowKey="storeId"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={data?.stores || []}
        pagination={false}
        locale={{ emptyText: <Empty description={ts('empty')} /> }}
        scroll={{ x: true }}
      />
    </div>
  );
};

export default Stores;
