import React, { useEffect, useState } from 'react';
import { Alert, App, Button, Descriptions, Input, Modal, Radio, Space, Switch, Tag, Typography } from 'antd';
import { ExperimentOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { ksApi } from '@/services/ipc/ksApi';

const { Text, Paragraph } = Typography;

type Preset = 'app' | 'lmstudio' | 'private' | 'custom';
const PRESETS: Record<Exclude<Preset, 'app'>, { base_url: string; model: string }> = {
  lmstudio: { base_url: 'http://127.0.0.1:1234/v1', model: 'text-embedding-qwen3-embedding-8b' },
  private: { base_url: 'http://<private-server>:8001/v1', model: 'ecan-embed' },
  custom: { base_url: '', model: '' },
};

/** Choose the embedding model used by product knowledge, test it, save it. */
const EmbedderModal: React.FC<{ open: boolean; onClose: () => void; onSaved: () => void }> = ({ open, onClose, onSaved }) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const k = (key: string, o?: Record<string, unknown>): string => String(t(`pages.knowledge.ks.embedder.${key}`, o as any));
  const [preset, setPreset] = useState<Preset>('app');
  const [baseUrl, setBaseUrl] = useState('');
  const [model, setModel] = useState('');
  const [apiKey, setApiKey] = useState<string | undefined>(undefined);
  const [verifyTls, setVerifyTls] = useState(true);
  const [hasKey, setHasKey] = useState(false);
  const [test, setTest] = useState<any>(null);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setTest(null);
    setApiKey(undefined);
    ksApi.getEmbedder().then(cfg => {
      setHasKey(cfg.has_api_key);
      setVerifyTls(cfg.verify_tls);
      if (cfg.mode === 'app') { setPreset('app'); return; }
      setBaseUrl(cfg.base_url);
      setModel(cfg.model);
      setPreset(cfg.base_url.startsWith('http://127.0.0.1:1234') ? 'lmstudio' : 'custom');
    }).catch(() => undefined);
  }, [open]);

  const choose = (p: Preset) => {
    setPreset(p);
    setTest(null);
    if (p !== 'app') {
      setBaseUrl(PRESETS[p].base_url);
      setModel(PRESETS[p].model);
    }
  };

  const runTest = async () => {
    setTesting(true);
    try {
      setTest(await ksApi.testEmbedder({ base_url: baseUrl, model, api_key: apiKey, verify_tls: verifyTls }));
    } catch (e: any) {
      setTest({ error: e.message });
    } finally {
      setTesting(false);
    }
  };

  const save = async () => {
    try {
      await ksApi.setEmbedder(preset === 'app'
        ? { mode: 'app' }
        : { mode: 'openai', base_url: baseUrl, model, api_key: apiKey, verify_tls: verifyTls });
      message.success(k('saved'));
      onSaved();
      onClose();
    } catch (e: any) {
      message.error(e.message);
    }
  };

  return (
    <Modal open={open} title={k('title')} onCancel={onClose} onOk={save} okText={k('save')} width={620}
           okButtonProps={{ disabled: preset !== 'app' && (!baseUrl.trim() || !model.trim()) }} destroyOnHidden>
      <Paragraph type="secondary" style={{ fontSize: 12 }}>{k('intro')}</Paragraph>
      <Radio.Group value={preset} onChange={e => choose(e.target.value)} style={{ marginBottom: 12 }}>
        <Space direction="vertical">
          <Radio value="app">{k('presetApp')}</Radio>
          <Radio value="lmstudio">{k('presetLmstudio')}</Radio>
          <Radio value="private">{k('presetPrivate')}</Radio>
          <Radio value="custom">{k('presetCustom')}</Radio>
        </Space>
      </Radio.Group>
      {preset !== 'app' && (
        <Space direction="vertical" style={{ width: '100%' }}>
          <div>
            <Text type="secondary">{k('address')}</Text>
            <Input value={baseUrl} onChange={e => setBaseUrl(e.target.value)} placeholder="http://127.0.0.1:1234/v1" />
          </div>
          <div>
            <Text type="secondary">{k('model')}</Text>
            <Input value={model} onChange={e => setModel(e.target.value)} placeholder="Qwen3-Embedding-8B" />
          </div>
          <div>
            <Text type="secondary">{k('apiKey')}</Text>
            <Input.Password value={apiKey ?? ''} placeholder={hasKey ? k('apiKeyKept') : k('apiKeyOptional')}
                            onChange={e => setApiKey(e.target.value)} />
          </div>
          <Space>
            <Switch size="small" checked={verifyTls} onChange={setVerifyTls} />
            <Text type="secondary" style={{ fontSize: 12 }}>{k('verifyTls')}</Text>
          </Space>
          <Button icon={<ExperimentOutlined />} loading={testing} disabled={!baseUrl.trim() || !model.trim()} onClick={runTest}>
            {k('test')}
          </Button>
          {test?.error && <Alert type="error" showIcon message={k('testFailed')} description={test.error} />}
          {test && !test.error && (
            <Descriptions size="small" column={2} bordered>
              <Descriptions.Item label={k('dim')}>{test.dim}</Descriptions.Item>
              <Descriptions.Item label={k('latency')}>{test.ms} ms</Descriptions.Item>
              <Descriptions.Item label={k('related')}>{test.related}</Descriptions.Item>
              <Descriptions.Item label={k('unrelated')}>{test.unrelated}</Descriptions.Item>
              <Descriptions.Item label={k('verdict')} span={2}>
                <Tag color={test.separates ? 'green' : 'orange'}>{test.separates ? k('good') : k('weak')}</Tag>
                {test.instruction && <Tag>{k('instruction')}</Tag>}
              </Descriptions.Item>
            </Descriptions>
          )}
        </Space>
      )}
      <Alert type="info" showIcon style={{ marginTop: 12 }} message={k('reindexNote')} />
    </Modal>
  );
};

export default EmbedderModal;
