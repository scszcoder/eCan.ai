import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
 import {
   App, Badge, Button, Card, Descriptions, Empty, Popconfirm, Select, Space, Statistic, Table, Tag, Tooltip, Typography,
 } from 'antd';
 import { AppstoreOutlined, EditOutlined, DeleteOutlined, SyncOutlined, SwapOutlined, ShopOutlined, FundOutlined, ClusterOutlined, EnvironmentOutlined } from '@ant-design/icons';
import { get_ipc_api } from '@/services/ipc_api';
import { useFastDeployStore } from '@/stores/fastDeployStore';
import { useUserStore } from '@/stores/userStore';
import type { StoreDefinition } from './StoreFormModal';
import { platformLabel } from '@/components/FastDeploy/scenarios';
import type { StoreDeletePlan, StoreMachine, StoreMeter, StoreRow } from './types';
import MoveStoreModal from './MoveStoreModal';
import { TransferList, useFleetTransfers } from '@/components/Fleet/FleetTransfers';
import styled from '@emotion/styled';

const LOGIN_COLORS: Record<string, string> = { ok: 'green', needs_login: 'orange', unknown: 'default' };

/** The outer DetailsCard zeros `.ant-card-body` padding and the app's global.css
 *  forces 8px on every card body; reclaim sensible padding for THIS panel's
 *  nested cards so text and controls don't hug the card borders. */
 /**
  * Scoped visual de-noising for the store detail panel.
  *
  * global.css decorates every `.ant-card-bordered` card with a heavy 4-layer
  * shadow, top-glow ::before, and hover-lift. Inside the borderless DetailsCard
  * this produces multiple stacked borders + shadows (the "too many thick edges"
  * look). We strip it for every card nested inside this panel, restoring flat
  * hairline-styled sections.
  */
 const StoreDetailPanel = styled.div`
    /* Section cards lose the heavy global decoration */
    .ant-card-bordered {
        border: 1px solid rgba(255, 255, 255, 0.07) !important;
        border-radius: 10px !important;
        box-shadow: none !important;
        background: rgba(255, 255, 255, 0.02) !important;
        transform: none !important;
        transition: border-color 0.15s ease !important;
    }
    .ant-card-bordered:hover {
        border-color: rgba(255, 255, 255, 0.12) !important;
        box-shadow: none !important;
        transform: none !important;
    }
    .ant-card-bordered::before {
        display: none !important;
    }

    /* Headers: compact, no gradient band */
    .ant-card-bordered .ant-card-head {
        height: auto !important;
        min-height: auto !important;
        padding: 0 20px !important;
        background: transparent !important;
        border-bottom: 1px solid rgba(255, 255, 255, 0.06) !important;
    }
    .ant-card-bordered .ant-card-head-wrapper {
        padding: 10px 0;
    }
    .ant-card-bordered .ant-card-head-title {
        font-size: 14px !important;
        font-weight: 600 !important;
    }

    /* Bodies: comfortable breathing room */
    .ant-card-bordered .ant-card-body {
        padding: 16px 20px !important;
    }

    /* Descriptions rendered borderless: airy label/value rows */
    .ant-descriptions-item-label {
        color: rgba(255, 255, 255, 0.45) !important;
        font-size: 13px !important;
    }
    .ant-descriptions-item-content {
        font-size: 14px !important;
    }
    /* Strip dividers between description rows */
    .ant-descriptions-view,
    .ant-descriptions-row,
    .ant-descriptions-item {
        border: none !important;
    }
    .ant-descriptions-row > td {
        border-bottom: none !important;
    }
`;

interface Props {
  store: StoreRow | null;
  thisVehicleId: string;
  onChanged: () => void;
  onEdit: (def: StoreDefinition) => void;
  /** Machines it can be assigned to (this one first), from the cloud registry. */
  machines: StoreMachine[];
}

const StoreDetail: React.FC<Props> = ({ store, thisVehicleId, onChanged, onEdit, machines }) => {
  const { t, i18n } = useTranslation();
  const { message, modal } = App.useApp();
  const navigate = useNavigate();
  const openFastDeploy = useFastDeployStore((s) => s.openFor);
  const [busy, setBusy] = useState(false);
  const [moveOpen, setMoveOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const username = useUserStore((state) => state.username);
  const { rows: transfers, refresh: refreshTransfers } = useFleetTransfers();
  const ts = (k: string, d: string, o?: Record<string, unknown>) =>
    t(`pages.stores.${k}`, { defaultValue: d, ...(o || {}) }) as string;
  const zh = (i18n.language || '').toLowerCase().startsWith('zh');
 
  const cardTitle = (icon: React.ReactNode, text: string) => (
    <Space size={6}>{icon}<span>{text}</span></Space>
  );
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
            {id === thisVehicleId ? ts('this_machine', 'This machine')
              : (machines.find((m) => m.id === id)?.name || ts('other_machine', 'Other machine'))}
          </Typography.Text>
          {online === false && <Tag>{ts('offline', 'offline')}</Tag>}
        </Space>
      </Tooltip>
    );
  };

  const meterName = (m: StoreMeter) =>
    (zh ? m.display_name_zh : m.display_name_en) || m.display_name_zh || m.display_name_en
    || `${m.scenario_code}.${m.meter_code}`;


  // Ask the backend what goes with the store first, so the confirm names it.
  const confirmDelete = async () => {
    setDeleting(true);
    let plan: StoreDeletePlan | null = null;
    try {
      const res = await api.deleteStore<{ plan: StoreDeletePlan }>(store.storeId, username || '', true);
      plan = res.success ? res.data?.plan || null : null;
      if (!res.success) {
        const err: any = res.error;
        message.error(String((err && (err.message || err)) || ts('action_failed', 'Action failed')));
        return;
      }
    } finally {
      setDeleting(false);
    }
    const names = (rows: { name: string; id: string }[]) => rows.map((r) => r.name || r.id).join('、');
    modal.confirm({
      title: ts('delete_confirm_title', 'Delete this store?'),
      okText: ts('delete', 'Delete'),
      okButtonProps: { danger: true },
      cancelText: ts('cancel', 'Cancel'),
      content: (
        <Space direction="vertical" size={4}>
          <Typography.Text>{ts('delete_confirm_store', 'Store')}: {store.label || store.storeId}</Typography.Text>
          {plan && plan.agents.length > 0 && (
            <Typography.Text>{ts('delete_confirm_agents', 'Agents removed')} ({plan.agents.length}): {names(plan.agents)}</Typography.Text>
          )}
          {plan && plan.tasks.length > 0 && (
            <Typography.Text>{ts('delete_confirm_tasks', 'Tasks removed')} ({plan.tasks.length}): {names(plan.tasks)}</Typography.Text>
          )}
          {plan && plan.kept_agents.length > 0 && (
            <Typography.Text type="secondary">
              {ts('delete_confirm_kept', 'Kept (they also serve other stores)')}: {names(plan.kept_agents)}
            </Typography.Text>
          )}
          <Typography.Text type="secondary">
            {ts('delete_confirm_profile', 'The browser login profile stays; remove it in Settings → Browser Profiles if no longer needed. This cannot be undone.')}
          </Typography.Text>
        </Space>
      ),
      onOk: () => act(() => api.deleteStore(store.storeId, username || ''), ts('deleted_ok', 'Store deleted')),
    });
  };

  const cloud = store.cloudKnown !== false;
  const archived = store.status === 'archived';

  const def = store.definition;
  const deploy = () => {
    // Fast Deploy lives on the Agents page; it opens preset to this store.
    openFastDeploy(store.storeId);
    navigate('/agents');
  };

  return (
    <StoreDetailPanel style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', overflowX: 'hidden', paddingRight: 4, paddingBottom: 8 }}>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card 
        title={cardTitle(<ShopOutlined />, ts('definition', 'Store'))}
        extra={
          <Space size={8}>
            {def && (
              <Button size="small" icon={<EditOutlined />} onClick={() => onEdit({ store_id: store.storeId, name: def.name,
                platform: def.platform, store_urls: def.store_urls || [], browser_profile_id: def.browser_profile_id })}>
                {ts('edit', 'Edit')}
              </Button>
            )}
            <Button size="small" type="primary" icon={<AppstoreOutlined />} onClick={deploy}>{ts('deploy_agents', 'Deploy agents')}</Button>
          </Space>
        }
        styles={{ header: { padding: '12px 16px' }, body: { padding: 16 } }}
      >
         <Descriptions column={1} size="middle" styles={{ label: { color: 'rgba(255,255,255,0.45)', fontSize: 13, padding: '6px 0' } }}>
          <Descriptions.Item label="Name">{def?.name || store.label || store.storeId}</Descriptions.Item>
          <Descriptions.Item label="Platform"><Typography.Text type="secondary">{platformLabel(def?.platform || store.platform, i18n.language) || ts('none', '—')}</Typography.Text></Descriptions.Item>
          <Descriptions.Item label="URLs">
            {def?.store_urls?.length
              ? def.store_urls.map((u) => <Typography.Text key={u} copyable ellipsis style={{ fontSize: 14 }}>{u}</Typography.Text>)
              : <Typography.Text type="secondary">—</Typography.Text>}
          </Descriptions.Item>
          <Descriptions.Item label="Login Profile"><Typography.Text type="secondary" copyable>{def?.browser_profile_id || ts('none', '—')}</Typography.Text></Descriptions.Item>
        </Descriptions>
      </Card>
      <Card
        title={cardTitle(<EnvironmentOutlined />, ts('placement', 'Where it runs'))}
        extra={archived ? (
          <Space size={8}>
            <Button size="small" icon={<SyncOutlined />} loading={busy}
              onClick={() => act(() => api.archiveStore(store.storeId, true))}>{ts('restore', 'Restore')}</Button>
            <Button size="small" danger icon={<DeleteOutlined />} loading={busy || deleting} onClick={confirmDelete}>{ts('delete', 'Delete')}</Button>
          </Space>
        ) : (
          <Space size={8}>
            <Popconfirm title={ts('archive_confirm', 'Archive this store?')}
              onConfirm={() => act(() => api.archiveStore(store.storeId))}>
              <Button size="small" loading={busy}>{ts('archive', 'Archive')}</Button>
            </Popconfirm>
            <Button size="small" danger type="primary" icon={<DeleteOutlined />} loading={busy || deleting} onClick={confirmDelete}>
              {ts('delete', 'Delete')}
            </Button>
          </Space>
        )}
        styles={{ header: { padding: '12px 16px' }, body: { padding: 16 } }}
      >
        {!archived && (
          <Space size={8} wrap style={{ marginBottom: 16 }}>
            {/* Assign to any machine on the account -- this one or another. */}
            <Select size="small" style={{ minWidth: 200 }} loading={busy}
              placeholder={ts('assign_to', 'Assign to…')}
              value={store.assignedVehicleId || undefined}
              onChange={(id: string) => act(() => api.assignStore(store.storeId,
                id === thisVehicleId ? { this_machine: true } : { vehicle_id: id }), ts('assigned_ok', 'Assigned'))}
              options={machines.map((m) => ({
                value: m.id,
                label: `${m.id === thisVehicleId ? ts('this_machine', 'This machine') + ' · ' : ''}${m.name}`
                  + `${m.type === 'cloud' ? ' (cloud)' : ''}${m.status !== 'active' ? ' · ' + ts('offline', 'offline') : ''}`,
              }))}
            />
            <Button size="small" loading={busy} disabled={!store.assignedVehicleId}
              onClick={() => act(() => api.assignStore(store.storeId, { vehicle_id: null }))}>
              {ts('unassign', 'Unassign')}
            </Button>
            {/* Reassigning alone leaves the login behind; this brings it along. */}
            <Button size="small" icon={<SwapOutlined />} disabled={!(store.assignedVehicleId || store.reportedVehicleId)}
              onClick={() => setMoveOpen(true)}>
              {t('fleet.move_button', { defaultValue: 'Move with login…' })}
            </Button>
          </Space>
        )}
        {cloud ? (
          <Descriptions column={1} size="middle" styles={{ label: { color: 'rgba(255,255,255,0.45)', fontSize: 13, padding: '6px 0' } }}>
            <Descriptions.Item label={ts('store_id', 'Store ID')}>
              <Space size={8}>
                <Typography.Text copyable>{store.storeId}</Typography.Text>
                {store.platform && <Tag style={{ marginInlineEnd: 0 }}>{platformLabel(store.platform, i18n.language)}</Tag>}
              </Space>
            </Descriptions.Item>
            <Descriptions.Item label={ts('assigned', 'Assigned to')}>
              {machine(store.assignedVehicleId, store.assignedVehicleOnline)}
            </Descriptions.Item>
            <Descriptions.Item label={ts('reported', 'Running on')}>
              <Space size={8} wrap>
                {machine(store.reportedVehicleId, store.reportedVehicleOnline)}
                {store.misplaced && <Tag color="red" style={{ marginInlineEnd: 0 }}>{ts('misplaced', 'Running somewhere other than assigned')}</Tag>}
              </Space>
            </Descriptions.Item>
            <Descriptions.Item label={ts('login', 'Login')}>
              <Tag color={LOGIN_COLORS[store.loginState || 'unknown'] || 'default'} style={{ marginInlineEnd: 0 }}>{store.loginState || 'unknown'}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label={ts('last_report', 'Last report')}>
              <Typography.Text type="secondary">
                {store.lastReportedAt ? new Date(store.lastReportedAt).toLocaleString() : ts('none', '—')}
              </Typography.Text>
            </Descriptions.Item>
          </Descriptions>
        ) : (
          <Typography.Text type="secondary">
            {ts('local_only', 'Known on this machine only; it appears in the cloud once a machine running it reports.')}
          </Typography.Text>
        )}
        <TransferList rows={transfers.filter((r) => r.kind === 'profile'
          && r.params?.store_id === store.storeId).slice(0, 3)} />
      </Card>
      {moveOpen && (
        <MoveStoreModal open={moveOpen} store={store} machines={machines} thisVehicleId={thisVehicleId}
          onClose={() => setMoveOpen(false)} onMoved={() => { refreshTransfers(); onChanged(); }} />
      )}

      <Card
        title={cardTitle(<FundOutlined />, ts('outcomes', 'Outcomes'))}
        styles={{ header: { padding: '12px 16px' }, body: { padding: 16 } }}
      >
        <Space size={32} wrap style={{ marginBottom: store.local.meters.length ? 16 : 0 }}>
          {cloud && (
            <Tooltip title={ts('billed_hint', 'What this account was charged for AI usage by this store, not the vendor cost.')}>
              <Statistic
                title={ts('billed_30d', 'Billed, last 30 days')}
                prefix="¥"
                value={((store.llm30d?.costFen || 0) / 100)}
                precision={2}
                valueStyle={{ fontSize: 24, fontWeight: 500 }}
              />
            </Tooltip>
          )}
        </Space>
        {store.local.meters.length ? (
          <Table<StoreMeter>
            pagination={false} rowKey={(m) => `${m.scenario_code}.${m.meter_code}`}
            dataSource={store.local.meters}
            columns={[
              { title: ts('meter', 'Outcome'), key: 'n', render: (_, m) =>
                  <Tooltip title={m.definition || undefined}><span>{meterName(m)}</span></Tooltip> },
              { title: ts('last_7d', 'Last 7 days'), key: 'd7', align: 'right', render: (_, m) => `${m.d7} ${m.unit}` },
              { title: ts('last_30d', 'Last 30 days'), key: 'd30', align: 'right', render: (_, m) => `${m.d30} ${m.unit}` },
            ]}
          />
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={<Typography.Text type="secondary">{ts('no_outcomes', 'No outcomes recorded for this store yet.')}</Typography.Text>}
            style={{ padding: 16 }}
          />
        )}
      </Card>

      <Card
        title={cardTitle(<ClusterOutlined />, ts('agents_tasks', 'Agents & tasks'))}
        styles={{ header: { padding: '12px 16px' }, body: { padding: 16 } }}
      >
        {store.local.agents.length ? (
          <Table
            pagination={false} rowKey="id" dataSource={store.local.agents}
            columns={[
              { title: ts('agent', 'Agent'), key: 'n', render: (_, a: any) =>
                  <Typography.Link style={{ fontSize: 14 }} onClick={() => navigate(`/agents/details/${a.id}`)}>{a.name || a.id}</Typography.Link> },
              { title: ts('state', 'State'), key: 's', render: (_, a: any) =>
                  <Badge
                    status={a.running ? 'success' : 'default'}
                    text={<Typography.Text style={{ fontSize: 13 }} type={a.running ? 'secondary' : undefined}>
                      {a.running ? ts('running_here', 'Running here') : ts('not_running_here', 'Not running here')}
                    </Typography.Text>}
                  /> },
              { title: ts('tasks', 'Tasks'), key: 't', render: (_, a: any) =>
                  <Space size={4} wrap>
                    {store.local.tasks.filter((x) => x.agent_id === a.id).map((x) =>
                      <Tag key={x.id} style={{ cursor: 'pointer', marginInlineEnd: 0 }} onClick={() => navigate('/tasks')}>
                        {x.name || x.id}
                      </Tag>)
                    }
                  </Space> },
            ]}
          />
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={<Typography.Text type="secondary">{ts('no_agents', 'No agents on this machine serve this store.')}</Typography.Text>}
            style={{ padding: 16 }}
          />
        )}
      </Card>
    </Space>
      </div>
    </StoreDetailPanel>
  );
};

export default StoreDetail;
