/**
 * ChannelSettings — manage messaging channel configuration.
 *
 * Displays one card per channel with:
 *   - Enable/disable toggle
 *   - Channel-specific credential fields
 *   - Live status badge
 *   - WhatsApp Baileys: QR code display for pairing
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  App,
  Badge,
  Button,
  Card,
  Checkbox,
  Divider,
  Form,
  Input,
  InputNumber,
  Space,
  Spin,
  Switch,
  Tooltip,
  Typography,
} from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  InfoCircleOutlined,
  LoadingOutlined,
  QrcodeOutlined,
  ReloadOutlined,
  StopOutlined,
  WifiOutlined,
} from '@ant-design/icons';
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
  const map: Record<string, { color: string; icon: React.ReactNode; label: string }> = {
    running:      { color: 'green',   icon: <CheckCircleOutlined />, label: 'Connected'    },
    connected:    { color: 'green',   icon: <CheckCircleOutlined />, label: 'Connected'    },
    starting:     { color: 'blue',    icon: <LoadingOutlined />,     label: 'Starting…'    },
    reconnecting: { color: 'orange',  icon: <LoadingOutlined />,     label: 'Reconnecting' },
    stopping:     { color: 'orange',  icon: <LoadingOutlined />,     label: 'Stopping…'    },
    stopped:      { color: 'default', icon: <StopOutlined />,        label: 'Stopped'      },
    error:        { color: 'red',     icon: <CloseCircleOutlined />, label: 'Error'        },
    unreachable:  { color: 'red',     icon: <CloseCircleOutlined />, label: 'Unreachable'  },
  };
  const info = map[status] || { color: 'default', icon: null, label: status };
  return (
    <Badge
      color={info.color as any}
      text={
        <Text style={{ fontSize: 12 }}>
          {info.icon} {info.label}
        </Text>
      }
    />
  );
}

// ── WhatsApp Baileys card ─────────────────────────────────────────────────────

function WaBaileysCard({
  entry,
  onSave,
  onStart,
  onStop,
}: {
  entry: ChannelEntry;
  onSave: (config: Record<string, any>) => Promise<void>;
  onStart: () => Promise<void>;
  onStop: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [starting, setStarting] = useState(false);
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

  const handleSave = async () => {
    try {
      const vals = await form.validateFields();
      setSaving(true);
      await onSave(vals);
      message.success('WhatsApp Baileys settings saved');
    } catch (e: any) {
      if (e?.errorFields) return; // validation error, already shown
      message.error(String(e?.message || e));
    } finally {
      setSaving(false);
    }
  };

  const handleStart = async () => {
    setStarting(true);
    try {
      await onStart();
    } finally {
      setStarting(false);
    }
  };

  const isRunning = entry.status === 'running' || entry.status === 'connected';

  return (
    <Form form={form} layout="vertical">
      <Form.Item name="enabled" valuePropName="checked" label="Enable channel">
        <Switch />
      </Form.Item>

      <Divider orientation="left" style={{ fontSize: 13 }}>Bridge connection</Divider>

      {/* Bridge URL row: half-width input + Show QR button + info tooltip */}
      <Form.Item label="Bridge URL" style={{ marginBottom: 8 }}>
        <Space align="center" style={{ width: '100%' }}>
          <Form.Item
            name="bridge_url"
            noStyle
            tooltip="URL of the running Node.js wabaileys-bridge (default: http://127.0.0.1:3210)"
          >
            <Input placeholder="http://127.0.0.1:3210" style={{ width: 200 }} />
          </Form.Item>
          <Button
            icon={<QrcodeOutlined />}
            onClick={() => {
              const url = form.getFieldValue('bridge_url') || 'http://127.0.0.1:3210';
              window.open(url, '_blank');
            }}
          >
            {t('settings.channel.show_qr', 'Show QR Code')}
          </Button>
          <Tooltip
            title={
              <div style={{ whiteSpace: 'pre-line', maxWidth: 320 }}>
                <strong>{t('settings.channel.wa_tip_title', 'How to pair WhatsApp')}</strong>
                {'\n\n'}
                {t('settings.channel.wa_tip_body',
                  '1. Open WhatsApp on your phone.\n2. Tap Menu (⋮) → Linked Devices → Link a Device.\n3. Scan the QR code shown in your browser.\n\n⚠️ Use a dedicated WhatsApp account for eCan.ai agents — do NOT use your personal number.'
                )}
              </div>
            }
            placement="rightTop"
            overlayStyle={{ maxWidth: 360 }}
          >
            <InfoCircleOutlined style={{ color: 'var(--ant-color-primary)', cursor: 'help', fontSize: 16 }} />
          </Tooltip>
        </Space>
      </Form.Item>
      <Form.Item
        name="webhook_port"
        label="Inbound webhook port"
        tooltip="Local port Python listens on for incoming messages forwarded by the bridge"
      >
        <InputNumber min={1024} max={65535} style={{ width: 120 }} />
      </Form.Item>
      <Form.Item name="auto_start_bridge" valuePropName="checked" label="Auto-start bridge process">
        <Checkbox>Launch the Node.js bridge automatically on enable</Checkbox>
      </Form.Item>
      <Form.Item name="default_agent_id" label="Default agent ID (optional)">
        <Input placeholder="Forwards inbound messages to this agent" />
      </Form.Item>

      {/* QR code section */}
      {entry.config.enabled && !isRunning && (
        <div style={{ marginBottom: 16 }}>
          <Text strong>WhatsApp pairing</Text>
          <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 4 }}>
            Start the Node.js bridge, then scan the QR code with WhatsApp on your dedicated
            agent phone number.
          </Paragraph>
          {pollingQr && !qrBase64 && (
            <div style={{ textAlign: 'center', padding: 16 }}>
              <Spin>
                <div>Waiting for QR code from bridge…</div>
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
                  Scan with WhatsApp → Linked Devices → Link a Device
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
          Save
        </Button>
        {!isRunning ? (
          <Button icon={<WifiOutlined />} onClick={handleStart} loading={starting}>
            Connect
          </Button>
        ) : (
          <Button icon={<StopOutlined />} danger onClick={onStop}>
            Disconnect
          </Button>
        )}
      </Space>
    </Form>
  );
}

// ── Generic channel card ──────────────────────────────────────────────────────

const CHANNEL_FIELD_DEFS: Record<string, Array<{ key: string; label: string; secret?: boolean; type?: string }>> = {
  telegram: [
    { key: 'bot_token', label: 'Bot Token', secret: true },
    { key: 'default_agent_id', label: 'Default Agent ID' },
  ],
  slack: [
    { key: 'bot_token', label: 'Bot Token', secret: true },
    { key: 'app_token', label: 'App Token', secret: true },
    { key: 'default_agent_id', label: 'Default Agent ID' },
  ],
  whatsapp: [
    { key: 'phone_number_id', label: 'Phone Number ID' },
    { key: 'access_token', label: 'Access Token', secret: true },
    { key: 'verify_token', label: 'Verify Token' },
    { key: 'webhook_port', label: 'Webhook Port', type: 'number' },
    { key: 'default_agent_id', label: 'Default Agent ID' },
  ],
  discord: [
    { key: 'bot_token', label: 'Bot Token', secret: true },
    { key: 'default_agent_id', label: 'Default Agent ID' },
  ],
  dingtalk: [
    { key: 'client_id', label: 'Client ID' },
    { key: 'client_secret', label: 'Client Secret', secret: true },
    { key: 'default_agent_id', label: 'Default Agent ID' },
  ],
};

function GenericChannelCard({
  channelId,
  entry,
  onSave,
  onStart,
  onStop,
}: {
  channelId: string;
  entry: ChannelEntry;
  onSave: (config: Record<string, any>) => Promise<void>;
  onStart: () => Promise<void>;
  onStop: () => Promise<void>;
}) {
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
      message.success('Settings saved');
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(String(e?.message || e));
    } finally {
      setSaving(false);
    }
  };

  const isRunning = entry.status === 'running' || entry.status === 'connected';

  return (
    <Form form={form} layout="vertical">
      <Form.Item name="enabled" valuePropName="checked" label="Enable channel">
        <Switch />
      </Form.Item>
      {fields.map((f) => (
        <Form.Item key={f.key} name={f.key} label={f.label}>
          {f.type === 'number' ? (
            <InputNumber min={1024} max={65535} style={{ width: 120 }} />
          ) : f.secret ? (
            <Input.Password placeholder={f.label} />
          ) : (
            <Input placeholder={f.label} />
          )}
        </Form.Item>
      ))}
      {entry.last_error && (
        <Alert type="error" message={entry.last_error} style={{ marginBottom: 12 }} showIcon />
      )}
      <Space wrap>
        <Button type="primary" onClick={handleSave} loading={saving}>
          Save
        </Button>
        {!isRunning ? (
          <Button icon={<WifiOutlined />} onClick={onStart}>
            Start
          </Button>
        ) : (
          <Button icon={<StopOutlined />} danger onClick={onStop}>
            Stop
          </Button>
        )}
      </Space>
    </Form>
  );
}

// ── Channel label helpers ─────────────────────────────────────────────────────

const CHANNEL_LABELS: Record<string, string> = {
  whatsapp_baileys: 'WhatsApp (Baileys)',
  whatsapp:         'WhatsApp (Cloud API)',
  telegram:         'Telegram',
  slack:            'Slack',
  discord:          'Discord',
  dingtalk:         'DingTalk',
  messenger:        'Facebook Messenger',
  twitter:          'Twitter / X',
  webchat:          'Web Chat',
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
  const { message } = App.useApp();

  const loadChannels = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await get_ipc_api().getChannels() as any;
      if (resp?.success && resp.data?.channels) {
        setChannels(resp.data.channels);
      } else {
        message.error(resp?.error?.message || 'Failed to load channel config');
      }
    } catch (e: any) {
      message.error(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }, []);

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
    const resp = await get_ipc_api().startChannel(channelId) as any;
    if (!resp?.success) {
      message.error(resp?.error?.message || 'Start failed');
    } else {
      message.success(`${CHANNEL_LABELS[channelId] || channelId} starting…`);
    }
    setTimeout(loadChannels, 1500);
  }, [loadChannels]);

  const handleStop = useCallback(async (channelId: string) => {
    const resp = await get_ipc_api().stopChannel(channelId) as any;
    if (!resp?.success) {
      message.error(resp?.error?.message || 'Stop failed');
    } else {
      message.success(`${CHANNEL_LABELS[channelId] || channelId} stopped`);
    }
    setTimeout(loadChannels, 1500);
  }, [loadChannels]);

  // Determine display order: preferred order first, then any remaining keys
  const channelIds = [
    ...CHANNEL_ORDER.filter((id) => id in channels),
    ...Object.keys(channels).filter((id) => !CHANNEL_ORDER.includes(id)),
  ];

  return (
    <div style={{ padding: '24px', maxWidth: 800 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>Messaging Channels</Title>
        <Button icon={<ReloadOutlined />} onClick={loadChannels} loading={loading} size="small">
          Refresh
        </Button>
      </div>

      <Paragraph type="secondary" style={{ marginBottom: 24 }}>
        Configure external messaging channels. Each channel requires a dedicated account —
        do not reuse personal accounts, as inbound/outbound traffic will be routed to agents.
      </Paragraph>

      {loading && channelIds.length === 0 ? (
        <Spin />
      ) : channelIds.length === 0 ? (
        <Alert
          type="info"
          message="No channels configured"
          description="channels.json not found or empty. Default entries will appear after the first save."
        />
      ) : (
        <Space direction="vertical" style={{ width: '100%' }} size={16}>
          {channelIds.map((cid) => {
            const entry = channels[cid];
            const label = CHANNEL_LABELS[cid] || cid;
            return (
              <Card
                key={cid}
                title={
                  <Space>
                    <Text strong>{label}</Text>
                    <StatusBadge status={entry.status} />
                  </Space>
                }
                size="small"
                style={{ width: '100%' }}
              >
                {cid === 'whatsapp_baileys' ? (
                  <WaBaileysCard
                    entry={entry}
                    onSave={(cfg) => handleSave(cid, cfg)}
                    onStart={() => handleStart(cid)}
                    onStop={() => handleStop(cid)}
                  />
                ) : (
                  <GenericChannelCard
                    channelId={cid}
                    entry={entry}
                    onSave={(cfg) => handleSave(cid, cfg)}
                    onStart={() => handleStart(cid)}
                    onStop={() => handleStop(cid)}
                  />
                )}
              </Card>
            );
          })}
        </Space>
      )}
    </div>
  );
}

export default ChannelSettings;
