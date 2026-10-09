import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert, App, Button, Card, Col, Empty, Input, List, Modal, Popconfirm, Radio, Row, Space, Switch, Tag, Typography,
} from 'antd';
import { ClusterOutlined, CopyOutlined, DesktopOutlined, LinkOutlined, ReloadOutlined, WifiOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { ksApi, KSLanStatus } from '@/services/ipc/ksApi';

const { Text, Paragraph, Title } = Typography;

const ago = (ts: number) => {
  const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
  if (s < 90) return `${s}s`;
  if (s < 5400) return `${Math.round(s / 60)}m`;
  if (s < 172800) return `${Math.round(s / 3600)}h`;
  return `${Math.round(s / 86400)}d`;
};

/**
 * LAN sharing between the commander machine and its platoon machines.
 * Commander: share on/off, pairing code, paired machines.
 * Platoon:   find the commander, pair once, choose whose knowledge to use.
 */
const LanPanel: React.FC<{ onChanged?: () => void }> = ({ onChanged }) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const k = (key: string, o?: Record<string, unknown>): string => String(t(`pages.knowledge.ks.lan.${key}`, o as any));
  const [status, setStatus] = useState<KSLanStatus | null>(null);
  const [code, setCode] = useState<{ code: string; expires: number } | null>(null);
  const [now, setNow] = useState(Date.now());
  const [found, setFound] = useState<{ machine_name: string; host: string; url: string; sharing: boolean }[] | null>(null);
  const [scanning, setScanning] = useState(false);
  const [pairTarget, setPairTarget] = useState<{ url: string; name: string } | null>(null);
  const [pairCode, setPairCode] = useState('');
  const [manualUrl, setManualUrl] = useState('');
  const [test, setTest] = useState<{ ok: boolean; ms: number; detail: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setStatus(await ksApi.lanStatus()); } catch (e: any) { message.error(e.message); }
  }, [message]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!code) return;
    const timer = setInterval(() => { setNow(Date.now()); load(); }, 1000);
    return () => clearInterval(timer);
  }, [code, load]);

  if (!status) return null;
  const isCommander = status.role.toLowerCase().includes('commander');
  const remaining = code ? Math.max(0, Math.round((code.expires - now) / 1000)) : 0;

  const toggleSharing = async (enabled: boolean) => {
    setBusy(true);
    try {
      const s = await ksApi.lanSetSharing(enabled);
      setStatus(s);
      if (enabled && !s.running) message.error(s.error || k('startFailed'));
    } catch (e: any) { message.error(e.message); } finally { setBusy(false); }
  };

  const newCode = async () => {
    const c = await ksApi.lanNewCode();
    setCode({ code: c.code, expires: Date.now() + c.expires_in * 1000 });
  };

  const scan = async () => {
    setScanning(true);
    try { setFound(await ksApi.lanDiscover()); } catch (e: any) { message.error(e.message); } finally { setScanning(false); }
  };

  const pair = async () => {
    if (!pairTarget) return;
    setBusy(true);
    try {
      await ksApi.lanPair(pairTarget.url, pairCode.replace(/\s/g, ''), pairTarget.name);
      message.success(k('paired', { name: pairTarget.name || pairTarget.url }));
      setPairTarget(null);
      setPairCode('');
      await load();
      setTest(await ksApi.lanTestSource());
      onChanged?.();
    } catch (e: any) { message.error(e.message); } finally { setBusy(false); }
  };

  const commanderCard = (
    <Card size="small" title={<Space><ClusterOutlined />{k('commanderTitle')}</Space>}
          extra={<Switch checked={status.enabled} loading={busy} onChange={toggleSharing} />}>
      <Paragraph type="secondary" style={{ fontSize: 12 }}>{k('commanderIntro')}</Paragraph>
      {status.enabled && !status.running && <Alert type="error" showIcon style={{ marginBottom: 8 }} message={status.error || k('startFailed')} description={k('firewallHint')} />}
      {status.enabled && status.running && (
        <>
          <Text type="secondary" style={{ fontSize: 12 }}>{k('addresses')}</Text>
          <div style={{ marginBottom: 8 }}>
            <Space wrap>{status.addresses.map(a => <Tag key={a} color="blue">{a}</Tag>)}</Space>
          </div>
          <Button type="primary" icon={<LinkOutlined />} onClick={newCode}>{k('addPlatoon')}</Button>
          <List
            style={{ marginTop: 12 }} size="small"
            header={<Text strong>{k('pairedMachines', { count: status.devices.length })}</Text>}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={k('noDevices')} /> }}
            dataSource={status.devices}
            renderItem={d => (
              <List.Item actions={[
                <Popconfirm key="r" title={k('revokeConfirm', { name: d.name })} okButtonProps={{ danger: true }}
                            onConfirm={async () => { await ksApi.lanRevoke(d.id); load(); }}>
                  <Button size="small" danger type="link">{k('revoke')}</Button>
                </Popconfirm>,
              ]}>
                <List.Item.Meta avatar={<DesktopOutlined />} title={d.name}
                                description={<Text type="secondary" style={{ fontSize: 12 }}>{d.ip} · {k('lastSeen', { ago: ago(d.last_seen) })}</Text>} />
              </List.Item>
            )}
          />
        </>
      )}
    </Card>
  );

  const platoonCard = (
    <Card size="small" title={<Space><WifiOutlined />{k('platoonTitle')}</Space>}>
      <Paragraph type="secondary" style={{ fontSize: 12 }}>{k('platoonIntro')}</Paragraph>
      <Radio.Group
        value={status.source.mode} disabled={!status.source.paired}
        onChange={async e => { setStatus({ ...status, source: await ksApi.lanSetSource(e.target.value) }); onChanged?.(); }}
        options={[{ value: 'local', label: k('useLocal') }, { value: 'commander', label: k('useCommander') }]}
        optionType="button" style={{ marginBottom: 8 }}
      />
      {status.source.paired && (
        <div style={{ marginBottom: 8 }}>
          <Text style={{ fontSize: 12 }}>{k('pairedWith', { name: status.source.commander || status.source.url })}</Text>{' '}
          <Button size="small" type="link" onClick={async () => setTest(await ksApi.lanTestSource())}>{k('test')}</Button>
          <Popconfirm title={k('forgetConfirm')} onConfirm={async () => { await ksApi.lanForget(); setTest(null); load(); onChanged?.(); }}>
            <Button size="small" type="link" danger>{k('forget')}</Button>
          </Popconfirm>
          {test && <div><Tag color={test.ok ? 'green' : 'red'}>{test.ok ? k('reachable', { ms: test.ms }) : test.detail}</Tag></div>}
        </div>
      )}
      <Space style={{ marginBottom: 8 }}>
        <Button icon={<ReloadOutlined />} loading={scanning} onClick={scan}>{k('findCommander')}</Button>
      </Space>
      {found && (found.length === 0 ? <Text type="secondary" style={{ fontSize: 12, display: 'block' }}>{k('noneFound')}</Text> : (
        <List size="small" dataSource={found} renderItem={f => (
          <List.Item actions={[
            <Button key="p" size="small" type="primary" disabled={!f.sharing} onClick={() => setPairTarget({ url: f.url, name: f.machine_name })}>{k('pair')}</Button>,
          ]}>
            <List.Item.Meta title={f.machine_name || f.host}
                            description={<Space size={4}><Text type="secondary" style={{ fontSize: 12 }}>{f.host}</Text>
                              <Tag color={f.sharing ? 'green' : 'default'}>{f.sharing ? k('sharing') : k('notSharing')}</Tag></Space>} />
          </List.Item>
        )} />
      ))}
      <Space.Compact style={{ width: '100%', marginTop: 8 }}>
        <Input placeholder={k('manualPlaceholder')} value={manualUrl} onChange={e => setManualUrl(e.target.value)} />
        <Button disabled={!manualUrl.trim()} onClick={() => setPairTarget({ url: manualUrl.trim(), name: '' })}>{k('pair')}</Button>
      </Space.Compact>
    </Card>
  );

  return (
    <div style={{ marginBottom: 16 }}>
      <Row gutter={16}>
        {isCommander ? (
          <>
            <Col xs={24} xl={14}>{commanderCard}</Col>
            <Col xs={24} xl={10}>{platoonCard}</Col>
          </>
        ) : (
          <>
            <Col xs={24} xl={14}>{platoonCard}</Col>
            <Col xs={24} xl={10}>{commanderCard}</Col>
          </>
        )}
      </Row>

      <Modal open={!!code} footer={<Button onClick={() => setCode(null)}>{k('done')}</Button>} onCancel={() => setCode(null)}
             title={k('codeTitle')}>
        {code && (
          <div style={{ textAlign: 'center' }}>
            <Paragraph>{k('codeHint')}</Paragraph>
            <Title level={1} style={{ letterSpacing: 8, fontFamily: 'monospace', margin: '8px 0' }} copyable={{ text: code.code, icon: <CopyOutlined /> }}>
              {code.code.slice(0, 3)} {code.code.slice(3)}
            </Title>
            <Text type={remaining < 60 ? 'danger' : 'secondary'}>
              {remaining > 0 ? k('expiresIn', { m: Math.floor(remaining / 60), s: String(remaining % 60).padStart(2, '0') }) : k('expired')}
            </Text>
            <div style={{ marginTop: 12 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>{k('addresses')}</Text>
              <div><Space wrap>{status.addresses.map(a => <Tag key={a}>{a}</Tag>)}</Space></div>
            </div>
            {remaining === 0 && <Button style={{ marginTop: 12 }} onClick={newCode}>{k('newCode')}</Button>}
          </div>
        )}
      </Modal>

      <Modal open={!!pairTarget} title={k('pairTitle', { name: pairTarget?.name || pairTarget?.url })} okText={k('pair')}
             okButtonProps={{ disabled: !/^\d{6}$/.test(pairCode.replace(/\s/g, '')), loading: busy }}
             onOk={pair} onCancel={() => { setPairTarget(null); setPairCode(''); }} destroyOnClose>
        <Paragraph>{k('pairHint')}</Paragraph>
        <Input size="large" maxLength={7} value={pairCode} placeholder="123 456" style={{ fontFamily: 'monospace', letterSpacing: 4, textAlign: 'center' }}
               onChange={e => setPairCode(e.target.value.replace(/[^\d ]/g, ''))} onPressEnter={pair} />
      </Modal>
    </div>
  );
};

export default LanPanel;
