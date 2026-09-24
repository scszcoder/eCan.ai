import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import {
  App, Badge, Button, Card, Descriptions, Empty, Popconfirm, Space, Statistic, Table, Tag, Tooltip, Typography,
} from 'antd';
import { get_ipc_api } from '@/services/ipc_api';
import { useFastDeployStore } from '@/stores/fastDeployStore';
import type { StoreDefinition } from './StoreFormModal';
import { platformLabel } from '@/components/FastDeploy/scenarios';
import type { StoreMeter, StoreRow } from './types';

const LOGIN_COLORS: Record<string, string> = { ok: 'green', needs_login: 'orange', unknown: 'default' };

interface Props {
  store: StoreRow | null;
  thisVehicleId: string;
  onChanged: () => void;
  onEdit: (def: StoreDefinition) => void;
}

const StoreDetail: React.FC<Props> = ({ store, thisVehicleId, onChanged, onEdit }) => {
  const { t, i18n } = useTranslation();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const openFastDeploy = useFastDeployStore((s) => s.openFor);
  const [busy, setBusy] = useState(false);
  const ts = (k: string, d: string, o?: Record<string, unknown>) =>
    t(`pages.stores.${k}`, { defaultValue: d, ...(o || {}) }) as string;
  const zh = (i18n.language || '').toLowerCase().startsWith('zh');

  if (!store) return <Empty description={ts('select', 'Select a store')} style={{ marginTop: 48 }} />;

  const act = async (run: () => Promise<any>, ok?: string) => {
    setBusy(true);
    try {
      const res = await run();
      if (res.success) {
        for (const w of res.data?.warnings || []) message.warning(w);
        if (ok) message.success(ok);
        onChanged();
      } else {
        message.error((res.error && (res.error.message || res.error)) || ts('action_failed', 'Action failed'));
      }
    } finally {
      setBusy(false);
    }
  };
  const api = get_ipc_api();

  const machine = (id?: string | null, online?: boolean | null) => {
    if (!id) return <Typography.Text type="secondary">{ts('none', '—')}</Typography.Text>;
    return (
      <Tooltip title={id}>
        <Space size={4}>
          <Typography.Text strong={id === thisVehicleId}>
            {id === thisVehicleId ? ts('this_machine', 'This machine') : ts('other_machine', 'Other machine')}
          </Typography.Text>
          {online === false && <Tag>{ts('offline', 'offline')}</Tag>}
        </Space>
      </Tooltip>
    );
  };

  const meterName = (m: StoreMeter) =>
    (zh ? m.display_name_zh : m.display_name_en) || m.display_name_zh || m.display_name_en
    || `${m.scenario_code}.${m.meter_code}`;

  const cloud = store.cloudKnown !== false;
  const archived = store.status === 'archived';

  const def = store.definition;
  const deploy = () => {
    // Fast Deploy lives on the Agents page; it opens preset to this store.
    openFastDeploy(store.storeId);
    navigate('/agents');
  };

  return (
    <Space direction="vertical" size={16} style={{ width: '100%', padding: 16 }}>
      <Card size="small" title={ts('definition', 'Store')}
        extra={
          <Space size={4}>
            {def && (
              <Button size="small" onClick={() => onEdit({ store_id: store.storeId, name: def.name,
                platform: def.platform, store_urls: def.store_urls || [], browser_profile_id: def.browser_profile_id })}>
                {ts('edit', 'Edit')}
              </Button>
            )}
            <Button size="small" type="primary" onClick={deploy}>{ts('deploy_agents', 'Deploy agents')}</Button>
          </Space>
        }
      >
        <Descriptions size="small" column={1}>
          <Descriptions.Item label={ts('name', 'Name')}>{def?.name || store.label || store.storeId}</Descriptions.Item>
          <Descriptions.Item label={ts('platform', 'Platform')}>{platformLabel(def?.platform || store.platform, i18n.language) || ts('none', '—')}</Descriptions.Item>
          <Descriptions.Item label={ts('urls_short', 'URLs')}>
            {def?.store_urls?.length
              ? <Space direction="vertical" size={0}>{def.store_urls.map((u) => <Typography.Text key={u} copyable>{u}</Typography.Text>)}</Space>
              : ts('none', '—')}
          </Descriptions.Item>
          <Descriptions.Item label={ts('profile', 'Login profile')}>{def?.browser_profile_id || ts('none', '—')}</Descriptions.Item>
        </Descriptions>
      </Card>
      <Card size="small" title={ts('placement', 'Where it runs')}
        extra={cloud && (archived ? (
          <Button size="small" loading={busy}
            onClick={() => act(() => api.archiveStore(store.storeId, true))}>{ts('restore', 'Restore')}</Button>
        ) : (
          <Space size={4}>
            <Button size="small" type="primary" loading={busy}
              disabled={!thisVehicleId || store.assignedVehicleId === thisVehicleId}
              onClick={() => act(() => api.assignStore(store.storeId, { this_machine: true }), ts('assigned_ok', 'Assigned'))}>
              {ts('assign_here', 'Assign here')}
            </Button>
            <Button size="small" loading={busy} disabled={!store.assignedVehicleId}
              onClick={() => act(() => api.assignStore(store.storeId, { vehicle_id: null }))}>
              {ts('unassign', 'Unassign')}
            </Button>
            <Popconfirm title={ts('archive_confirm', 'Archive this store?')}
              onConfirm={() => act(() => api.archiveStore(store.storeId))}>
              <Button size="small" danger loading={busy}>{ts('archive', 'Archive')}</Button>
            </Popconfirm>
          </Space>
        ))}
      >
        {cloud ? (
          <Descriptions size="small" column={1}>
            <Descriptions.Item label={ts('store_id', 'Store ID')}>
              <Typography.Text copyable>{store.storeId}</Typography.Text>
              {store.platform && <Tag style={{ marginLeft: 8 }}>{platformLabel(store.platform, i18n.language)}</Tag>}
            </Descriptions.Item>
            <Descriptions.Item label={ts('assigned', 'Assigned to')}>
              {machine(store.assignedVehicleId, store.assignedVehicleOnline)}
            </Descriptions.Item>
            <Descriptions.Item label={ts('reported', 'Running on')}>
              <Space size={4}>
                {machine(store.reportedVehicleId, store.reportedVehicleOnline)}
                {store.misplaced && <Tag color="red">{ts('misplaced', 'Running somewhere other than assigned')}</Tag>}
              </Space>
            </Descriptions.Item>
            <Descriptions.Item label={ts('login', 'Login')}>
              <Tag color={LOGIN_COLORS[store.loginState || 'unknown'] || 'default'}>{store.loginState || 'unknown'}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label={ts('last_report', 'Last report')}>
              {store.lastReportedAt ? new Date(store.lastReportedAt).toLocaleString() : ts('none', '—')}
            </Descriptions.Item>
          </Descriptions>
        ) : (
          <Typography.Text type="secondary">
            {ts('local_only', 'Known on this machine only; it appears in the cloud once a machine running it reports.')}
          </Typography.Text>
        )}
      </Card>

      <Card size="small" title={ts('outcomes', 'Outcomes')}>
        <Space size={32} wrap style={{ marginBottom: store.local.meters.length ? 12 : 0 }}>
          {cloud && (
            <Tooltip title={ts('billed_hint', 'What this account was charged for AI usage by this store, not the vendor cost.')}>
              <Statistic title={ts('billed_30d', 'Billed, last 30 days')} prefix="¥"
                value={((store.llm30d?.costFen || 0) / 100).toFixed(2)} />
            </Tooltip>
          )}
        </Space>
        {store.local.meters.length ? (
          <Table<StoreMeter>
            size="small" pagination={false} rowKey={(m) => `${m.scenario_code}.${m.meter_code}`}
            dataSource={store.local.meters}
            columns={[
              { title: ts('meter', 'Outcome'), key: 'n', render: (_, m) =>
                  <Tooltip title={m.definition || undefined}><span>{meterName(m)}</span></Tooltip> },
              { title: ts('last_7d', 'Last 7 days'), key: 'd7', render: (_, m) => `${m.d7} ${m.unit}` },
              { title: ts('last_30d', 'Last 30 days'), key: 'd30', render: (_, m) => `${m.d30} ${m.unit}` },
            ]}
          />
        ) : (
          <Typography.Text type="secondary">{ts('no_outcomes', 'No outcomes recorded for this store yet.')}</Typography.Text>
        )}
      </Card>

      <Card size="small" title={ts('agents_tasks', 'Agents & tasks')}>
        {store.local.agents.length ? (
          <Table
            size="small" pagination={false} rowKey="id" dataSource={store.local.agents}
            columns={[
              { title: ts('agent', 'Agent'), key: 'n', render: (_, a: any) =>
                  <Typography.Link onClick={() => navigate(`/agents/details/${a.id}`)}>{a.name || a.id}</Typography.Link> },
              { title: ts('state', 'State'), key: 's', render: (_, a: any) =>
                  <Badge status={a.running ? 'success' : 'default'}
                    text={a.running ? ts('running_here', 'Running here') : ts('not_running_here', 'Not running here')} /> },
              { title: ts('tasks', 'Tasks'), key: 't', render: (_, a: any) =>
                  store.local.tasks.filter((x) => x.agent_id === a.id).map((x) =>
                    <Tag key={x.id} style={{ cursor: 'pointer' }} onClick={() => navigate('/tasks')}>{x.name || x.id}</Tag>) },
            ]}
          />
        ) : (
          <Typography.Text type="secondary">{ts('no_agents', 'No agents on this machine serve this store.')}</Typography.Text>
        )}
      </Card>
    </Space>
  );
};

export default StoreDetail;
