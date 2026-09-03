/**
 * ChannelSettings — manage messaging channel configuration.
 *
 * Layout: one AntD Table row per channel with an expandable row that
 * surfaces the per-channel credential form (WaBaileysCard /
 * GenericChannelCard). Status, enable/disable and start/stop controls
 * are inline so a user can scan all channels without scrolling.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  App,
  Badge,
  Button,
  Checkbox,
  Divider,
  Form,
  Input,
  InputNumber,
  Space,
  Spin,
  Switch,
  Table,
  Tooltip,
  Typography,
} from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  InfoCircleOutlined,
  LoadingOutlined,
  MinusOutlined,
  PlusOutlined,
  QrcodeOutlined,
  ReloadOutlined,
  StopOutlined,
  WifiOutlined,
} from '@ant-design/icons';
import type { ExpandableConfig } from 'antd/es/table/interface';
import { get_ipc_api } from '@/services/ipc_api';

const { Title, Text, Paragraph } = Typography;

// ── Types ────────────────────────────────────────────────────────────────────

interface ChannelEntry {
  config: Record<string, any>;
  status: string;
  restart_count: number;
  last_error: string | null;
}

interface ChannelsMap {
  [channelId: string]: ChannelEntry;
}

// ── Status badge helper ───────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const { t } = useTranslation();
  const statusMap: Record<string, { color: string; icon: React.ReactNode; labelKey: string }> = {
    running:      { color: 'green',   icon: <CheckCircleOutlined />, labelKey: 'pages.settings.channel.status_connected' },
    connected:    { color: 'green',   icon: <CheckCircleOutlined />, labelKey: 'pages.settings.channel.status_connected' },
    starting:     { color: 'blue',    icon: <LoadingOutlined />,     labelKey: 'pages.settings.channel.status_starting' },
    reconnecting: { color: 'orange',  icon: <LoadingOutlined />,     labelKey: 'pages.settings.channel.status_reconnecting' },
    stopping:     { color: 'orange',  icon: <LoadingOutlined />,     labelKey: 'pages.settings.channel.status_stopping' },
    stopped:      { color: 'default', icon: <StopOutlined />,        labelKey: 'pages.settings.channel.status_stopped' },
    error:        { color: 'red',     icon: <CloseCircleOutlined />, labelKey: 'pages.settings.channel.status_error' },
    unreachable:  { color: 'red',     icon: <CloseCircleOutlined />, labelKey: 'pages.settings.channel.status_unreachable' },
  };
  const info = statusMap[status] || { color: 'default', icon: null, labelKey: status };
  return (
    <Badge
      color={info.color as any}
      text={
        <Text style={{ fontSize: 12 }}>
          {info.icon} {t(info.labelKey)}
        </Text>
      }
    />
  );
}

// ── WhatsApp Baileys card ─────────────────────────────────────────────────────

function WaBaileysCard({
  entry,
  onSave,
}: {
  entry: ChannelEntry;
  onSave: (config: Record<string, any>) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [qrBase64, setQrBase64] = useState<string | null>(null);
  const [pollingQr, setPollingQr] = useState(false);
  const qrPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const { message } = App.useApp();

  useEffect(() => {
    form.setFieldsValue(entry.config);
  }, [entry.config]);

  // Poll QR while channel is starting/connecting
  useEffect(() => {
    const isConnected = entry.status === 'running' || entry.status === 'connected';
    if (entry.config.enabled && !isConnected) {
      startQrPoll();
    } else {
      stopQrPoll();
      if (isConnected) setQrBase64(null);
    }
    return () => stopQrPoll();
  }, [entry.status, entry.config.enabled]);

  const startQrPoll = () => {
    if (qrPollRef.current) return;
    setPollingQr(true);
    fetchQr();
    qrPollRef.current = setInterval(fetchQr, 4000);
  };

  const stopQrPoll = () => {
    if (qrPollRef.current) {
      clearInterval(qrPollRef.current);
      qrPollRef.current = null;
    }
    setPollingQr(false);
  };

  const fetchQr = async () => {
    try {
      const resp = await get_ipc_api().getWhatsappQR('whatsapp_baileys') as any;
      if (resp?.success && resp.data?.qr_base64) {
        setQrBase64(resp.data.qr_base64);
      } else if (resp?.data?.bridge_status?.status === 'connected') {
        setQrBase64(null);
        stopQrPoll();
      }
    } catch {
      // silently ignore polling errors
    }
  };

  const isRunning = entry.status === 'running' || entry.status === 'connected';

  const handleSave = async () => {
    try {
      const vals = await form.validateFields();
      setSaving(true);
      await onSave(vals);
      message.success(t('pages.settings.channel.settings_saved'));
    } catch (e: any) {
      if (e?.errorFields) return; // validation error, already shown
      message.error(String(e?.message || e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Form form={form} layout="vertical">
      <Form.Item
        label={t('pages.settings.channel.enable_channel')}
        style={{ marginBottom: 8 }}
      >
        <Space align="center" size={8}>
          <Switch size="small" checked={!!entry.config.enabled} disabled />
          <Text type="secondary" style={{ fontSize: 12 }}>
            {t('pages.settings.channel.enabled_toggle_hint')}
          </Text>
        </Space>
      </Form.Item>

      <Divider orientation="left" style={{ fontSize: 13 }}>{t('pages.settings.channel.bridge_connection')}</Divider>

      {/* Bridge URL row: half-width input + Show QR button + info tooltip */}
      <Form.Item label={t('pages.settings.channel.bridge_url')} style={{ marginBottom: 8 }}>
        <Space align="center" style={{ width: '100%' }}>
          <Form.Item
            name="bridge_url"
            noStyle
            tooltip={t('pages.settings.channel.bridge_url_tooltip')}
          >
            <Input placeholder={t('pages.settings.channel.bridge_url_placeholder')} style={{ width: 240 }} id="whatsapp_baileys-bridge_url" />
          </Form.Item>
          <Button
            icon={<QrcodeOutlined />}
            onClick={() => {
              const url = form.getFieldValue('bridge_url') || 'http://127.0.0.1:3210';
              window.open(url, '_blank');
            }}
          >
            {t('pages.settings.channel.show_qr')}
          </Button>
          <Tooltip
            title={
              <div style={{ whiteSpace: 'pre-line', maxWidth: 320 }}>
                <strong>{t('pages.settings.channel.wa_tip_title')}</strong>
                {'\n\n'}
                {t('pages.settings.channel.wa_tip_body')}
              </div>
            }
            placement="rightTop"
            styles={{ root: { maxWidth: 360 } }}
          >
            <InfoCircleOutlined style={{ color: 'var(--ant-color-primary)', cursor: 'help', fontSize: 16 }} />
          </Tooltip>
        </Space>
      </Form.Item>
      <Form.Item
        name="webhook_port"
        label={t('pages.settings.channel.inbound_webhook_port')}
        tooltip={t('pages.settings.channel.inbound_webhook_port_tooltip')}
      >
        <InputNumber min={1024} max={65535} style={{ width: 140 }} id="whatsapp_baileys-webhook_port" />
      </Form.Item>
      <Form.Item name="auto_start_bridge" valuePropName="checked" label={t('pages.settings.channel.auto_start_bridge')}>
        <Checkbox id="whatsapp_baileys-auto_start_bridge">{t('pages.settings.channel.auto_start_bridge_desc')}</Checkbox>
      </Form.Item>
      <Form.Item name="default_agent_id" label={t('pages.settings.channel.default_agent_id')}>
        <Input placeholder={t('pages.settings.channel.default_agent_id_placeholder')} id="whatsapp_baileys-default_agent_id" style={{ maxWidth: 360 }} />
      </Form.Item>

      {/* QR code section */}
      {entry.config.enabled && !isRunning && (
        <div style={{ marginBottom: 16 }}>
          <Text strong>{t('pages.settings.channel.whatsapp_pairing')}</Text>
          <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 4 }}>
            {t('pages.settings.channel.whatsapp_pairing_desc')}
          </Paragraph>
          {pollingQr && !qrBase64 && (
            <div style={{ textAlign: 'center', padding: 16 }}>
              <Spin>
                <div>{t('pages.settings.channel.waiting_for_qr')}</div>
              </Spin>
            </div>
          )}
          {qrBase64 && (
            <div style={{ textAlign: 'center', padding: 8 }}>
              <img
                src={`data:image/png;base64,${qrBase64}`}
                alt="WhatsApp QR Code"
                style={{ width: 220, height: 220, border: '1px solid #eee', borderRadius: 8 }}
              />
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {t('pages.settings.channel.scan_whatsapp')}
                </Text>
              </div>
            </div>
          )}
        </div>
      )}

      {entry.last_error && (
        <Alert
          type="error"
          message={entry.last_error}
          style={{ marginBottom: 12 }}
          showIcon
        />
      )}

      <Space wrap>
        <Button type="primary" onClick={handleSave} loading={saving}>
          {t('pages.settings.channel.save')}
        </Button>
      </Space>
    </Form>
  );
}

// ── Generic channel card ──────────────────────────────────────────────────────

const CHANNEL_FIELD_DEFS: Record<string, Array<{ key: string; i18nKey: string; secret?: boolean; type?: string }>> = {
  telegram: [
    { key: 'bot_token', i18nKey: 'pages.settings.channel.field_bot_token', secret: true },
    { key: 'default_agent_id', i18nKey: 'pages.settings.channel.default_agent_id' },
  ],
  slack: [
    { key: 'bot_token', i18nKey: 'pages.settings.channel.field_bot_token', secret: true },
    { key: 'app_token', i18nKey: 'pages.settings.channel.field_app_token', secret: true },
    { key: 'default_agent_id', i18nKey: 'pages.settings.channel.default_agent_id' },
  ],
  whatsapp: [
    { key: 'phone_number_id', i18nKey: 'pages.settings.channel.field_phone_number_id' },
    { key: 'access_token', i18nKey: 'pages.settings.channel.field_access_token', secret: true },
    { key: 'verify_token', i18nKey: 'pages.settings.channel.field_verify_token' },
    { key: 'webhook_port', i18nKey: 'pages.settings.channel.field_webhook_port', type: 'number' },
    { key: 'default_agent_id', i18nKey: 'pages.settings.channel.default_agent_id' },
  ],
  discord: [
    { key: 'bot_token', i18nKey: 'pages.settings.channel.field_bot_token', secret: true },
    { key: 'default_agent_id', i18nKey: 'pages.settings.channel.default_agent_id' },
  ],
  dingtalk: [
    { key: 'client_id', i18nKey: 'pages.settings.channel.field_client_id' },
    { key: 'client_secret', i18nKey: 'pages.settings.channel.field_client_secret', secret: true },
    { key: 'default_agent_id', i18nKey: 'pages.settings.channel.default_agent_id' },
  ],
};

function GenericChannelCard({
  channelId,
  entry,
  onSave,
}: {
  channelId: string;
  entry: ChannelEntry;
  onSave: (config: Record<string, any>) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const { message } = App.useApp();
  const fields = CHANNEL_FIELD_DEFS[channelId] || [];

  useEffect(() => {
    form.setFieldsValue(entry.config);
  }, [entry.config]);

  const handleSave = async () => {
    try {
      const vals = await form.validateFields();
      setSaving(true);
      await onSave(vals);
      message.success(t('pages.settings.channel.settings_saved'));
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(String(e?.message || e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Form form={form} layout="vertical">
      <Form.Item
        label={t('pages.settings.channel.enable_channel')}
        style={{ marginBottom: 8 }}
      >
        <Space align="center" size={8}>
          <Switch size="small" checked={!!entry.config.enabled} disabled />
          <Text type="secondary" style={{ fontSize: 12 }}>
            {t('pages.settings.channel.enabled_toggle_hint')}
          </Text>
        </Space>
      </Form.Item>
      {fields.map((f) => (
        <Form.Item key={f.key} name={f.key} label={t(f.i18nKey)}>
          {f.type === 'number' ? (
            <InputNumber min={1024} max={65535} style={{ width: 140 }} id={`${channelId}-${f.key}`} />
          ) : f.secret ? (
            <Input.Password placeholder={t(f.i18nKey)} id={`${channelId}-${f.key}`} style={{ maxWidth: 360 }} />
          ) : (
            <Input placeholder={t(f.i18nKey)} id={`${channelId}-${f.key}`} style={{ maxWidth: 360 }} />
          )}
        </Form.Item>
      ))}
      {entry.last_error && (
        <Alert type="error" message={entry.last_error} style={{ marginBottom: 12 }} showIcon />
      )}
      <Space wrap>
        <Button type="primary" onClick={handleSave} loading={saving}>
          {t('pages.settings.channel.save')}
        </Button>
      </Space>
    </Form>
  );
}

// ── Channel label helpers ─────────────────────────────────────────────────────

const CHANNEL_LABELS_KEYS: Record<string, string> = {
  whatsapp_baileys: 'pages.settings.channel.channel_whatsapp_baileys',
  whatsapp:         'pages.settings.channel.channel_whatsapp',
  telegram:         'pages.settings.channel.channel_telegram',
  slack:            'pages.settings.channel.channel_slack',
  discord:          'pages.settings.channel.channel_discord',
  dingtalk:         'pages.settings.channel.channel_dingtalk',
  messenger:        'pages.settings.channel.channel_messenger',
  twitter:          'pages.settings.channel.channel_twitter',
  webchat:          'pages.settings.channel.channel_webchat',
};

// Preferred display order
const CHANNEL_ORDER = [
  'whatsapp_baileys', 'telegram', 'slack', 'discord',
  'dingtalk', 'messenger', 'twitter', 'whatsapp', 'webchat',
];

// ── Main ChannelSettings component ───────────────────────────────────────────

export function ChannelSettings() {
  const [channels, setChannels] = useState<ChannelsMap>({});
  const [loading, setLoading] = useState(false);
  const [expandedKeys, setExpandedKeys] = useState<React.Key[]>([]);
  const [busyChannel, setBusyChannel] = useState<string | null>(null);
  const { t } = useTranslation();
  const { message } = App.useApp();

  const loadChannels = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await get_ipc_api().getChannels() as any;
      if (resp?.success && resp.data?.channels) {
        setChannels(resp.data.channels);
      } else {
        message.error(resp?.error?.message || t('pages.settings.channel.no_channels'));
      }
    } catch (e: any) {
      message.error(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }, [message, t]);

  useEffect(() => {
    loadChannels();
    // Refresh status every 10 s
    const t = setInterval(loadChannels, 10_000);
    return () => clearInterval(t);
  }, [loadChannels]);

  const handleSave = useCallback(async (channelId: string, cfg: Record<string, any>) => {
    const resp = await get_ipc_api().saveChannelConfig(channelId, cfg) as any;
    if (!resp?.success) throw new Error(resp?.error?.message || 'Save failed');
    await loadChannels();
  }, [loadChannels]);

  const handleStart = useCallback(async (channelId: string) => {
    setBusyChannel(channelId);
    try {
      const resp = await get_ipc_api().startChannel(channelId) as any;
      if (!resp?.success) {
        message.error(resp?.error?.message || 'Start failed');
      } else {
        message.success(`${t(CHANNEL_LABELS_KEYS[channelId] || channelId)} ${t('pages.settings.channel.status_starting')}`);
      }
      setTimeout(loadChannels, 1500);
    } finally {
      setBusyChannel(null);
    }
  }, [loadChannels, message, t]);

  const handleStop = useCallback(async (channelId: string) => {
    setBusyChannel(channelId);
    try {
      const resp = await get_ipc_api().stopChannel(channelId) as any;
      if (!resp?.success) {
        message.error(resp?.error?.message || 'Stop failed');
      } else {
        message.success(`${t(CHANNEL_LABELS_KEYS[channelId] || channelId)} ${t('pages.settings.channel.status_stopped')}`);
      }
      setTimeout(loadChannels, 1500);
    } finally {
      setBusyChannel(null);
    }
  }, [loadChannels, message, t]);

  const handleEnabledChange = useCallback(async (channelId: string, enabled: boolean) => {
    setBusyChannel(channelId);
    try {
      const resp = await get_ipc_api().saveChannelConfig(channelId, { enabled }) as any;
      if (!resp?.success) {
        message.error(resp?.error?.message || 'Save failed');
        return;
      }
      // Optimistic update so the switch reflects instantly
      setChannels((prev) => ({
        ...prev,
        [channelId]: {
          ...prev[channelId],
          config: { ...prev[channelId]?.config, enabled },
        },
      }));
      setTimeout(loadChannels, 800);
    } finally {
      setBusyChannel(null);
    }
  }, [loadChannels, message]);

  // Determine display order: preferred order first, then any remaining keys
  const channelIds = [
    ...CHANNEL_ORDER.filter((id) => id in channels),
    ...Object.keys(channels).filter((id) => !CHANNEL_ORDER.includes(id)),
  ];

  const isRunning = (status: string) => status === 'running' || status === 'connected';

  const columns = [
    {
      title: t('pages.settings.channel.column_channel'),
      dataIndex: 'channelId',
      key: 'channel',
      width: 220,
      render: (cid: string) => (
        <Text strong>{t(CHANNEL_LABELS_KEYS[cid] || cid)}</Text>
      ),
    },
    {
      title: t('pages.settings.channel.column_status'),
      dataIndex: 'status',
      key: 'status',
      width: 160,
      render: (status: string) => <StatusBadge status={status} />,
    },
    {
      title: t('pages.settings.channel.column_agent'),
      dataIndex: ['config', 'default_agent_id'],
      key: 'agent',
      ellipsis: true,
      render: (agentId?: string) =>
        agentId ? (
          <Text style={{ fontFamily: 'monospace', fontSize: 12 }}>{agentId}</Text>
        ) : (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {t('pages.settings.channel.no_default_agent')}
          </Text>
        ),
    },
    {
      title: t('pages.settings.channel.column_enabled'),
      key: 'enabled',
      width: 90,
      render: (_: any, row: { channelId: string; config: Record<string, any> }) => (
        <Switch
          size="small"
          checked={!!row.config.enabled}
          disabled={busyChannel === row.channelId}
          onChange={(checked) => handleEnabledChange(row.channelId, checked)}
          id={`${row.channelId}-enabled`}
        />
      ),
    },
    {
      title: t('pages.settings.channel.column_actions'),
      key: 'actions',
      width: 160,
      render: (_: any, row: { channelId: string; status: string }) => {
        const running = isRunning(row.status);
        return (
          <Space size={4}>
            {!running ? (
              <Button
                size="small"
                type="primary"
                icon={<WifiOutlined />}
                loading={busyChannel === row.channelId}
                onClick={() => handleStart(row.channelId)}
                id={`${row.channelId}-connect`}
              >
                {t('pages.settings.channel.connect')}
              </Button>
            ) : (
              <Button
                size="small"
                danger
                icon={<StopOutlined />}
                loading={busyChannel === row.channelId}
                onClick={() => handleStop(row.channelId)}
                id={`${row.channelId}-disconnect`}
              >
                {t('pages.settings.channel.disconnect')}
              </Button>
            )}
          </Space>
        );
      },
    },
  ];

  const dataSource = channelIds.map((cid) => ({
    key: cid,
    channelId: cid,
    status: channels[cid].status,
    config: channels[cid].config,
  }));

  const expandable: ExpandableConfig<typeof dataSource[number]> = {
    expandedRowKeys: expandedKeys,
    onExpand: (expanded, row) => {
      setExpandedKeys((prev) =>
        expanded ? [...prev, row.key] : prev.filter((k) => k !== row.key),
      );
    },
    expandRowByClick: true,
    expandIcon: ({ expanded, onExpand, record }) => (
      <Tooltip
        title={expanded ? t('pages.settings.channel.collapse') : t('pages.settings.channel.expand')}
        mouseEnterDelay={0.4}
      >
        <Button
          type="text"
          size="small"
          shape="circle"
          aria-label={expanded ? t('pages.settings.channel.collapse') : t('pages.settings.channel.expand')}
          aria-expanded={expanded}
          icon={expanded ? <MinusOutlined /> : <PlusOutlined />}
          onClick={(event) => {
            event.stopPropagation();
            onExpand(record, event);
          }}
          style={{
            width: 24,
            minWidth: 24,
            height: 24,
            color: 'var(--ant-color-text-secondary)',
            background: 'transparent',
            borderColor: 'transparent',
            boxShadow: 'none',
          }}
        />
      </Tooltip>
    ),
    expandedRowRender: (row) => {
      const entry = channels[row.channelId];
      return (
        <div style={{ padding: '4px 0 4px 32px', maxWidth: 720 }}>
          {row.channelId === 'whatsapp_baileys' ? (
            <WaBaileysCard
              entry={entry}
              onSave={(cfg) => handleSave(row.channelId, cfg)}
            />
          ) : (
            <GenericChannelCard
              channelId={row.channelId}
              entry={entry}
              onSave={(cfg) => handleSave(row.channelId, cfg)}
            />
          )}
        </div>
      );
    },
  };

  return (
    <div style={{ padding: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>{t('pages.settings.channel.title')}</Title>
        <Button icon={<ReloadOutlined />} onClick={loadChannels} loading={loading} size="small">
          {t('pages.settings.channel.refresh')}
        </Button>
      </div>

      <Paragraph type="secondary" style={{ marginBottom: 16 }}>
        {t('pages.settings.channel.description')}
      </Paragraph>

      {loading && channelIds.length === 0 ? (
        <Spin />
      ) : channelIds.length === 0 ? (
        <Alert
          type="info"
          message={t('pages.settings.channel.no_channels')}
          description={t('pages.settings.channel.no_channels_desc')}
        />
      ) : (
        <Table
          size="small"
          rowKey="key"
          columns={columns as any}
          dataSource={dataSource}
          expandable={expandable}
          pagination={false}
          loading={loading && channelIds.length > 0}
          locale={{
            emptyText: t('pages.settings.channel.no_channels'),
          }}
        />
      )}
    </div>
  );
}

export default ChannelSettings;
