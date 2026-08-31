import React, { useCallback, useEffect, useState } from 'react';
import { App, Badge, Button, Space, Tooltip } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { get_ipc_api } from '../../../services/ipc_api';
import type { LLMProvider } from '../types';

type Status = 'testing' | 'available' | 'unavailable';

interface Props {
  kind: 'llm' | 'embedding' | 'rerank';
  provider: LLMProvider;
  model?: string;
}

const ProviderStatus: React.FC<Props> = ({ kind, provider, model }) => {
  const { t } = useTranslation();
  const { modal } = App.useApp();
  const configured = Boolean((provider.is_local || provider.api_key_configured) && provider.base_url && model);
  const [status, setStatus] = useState<Status>(configured ? 'testing' : 'unavailable');
  const [detail, setDetail] = useState<{ category: string; technical?: string }>({
    category: configured ? 'unknown' : 'missing_config',
  });

  const probe = useCallback(async (showError = false) => {
    if (!configured) {
      setStatus('unavailable');
      setDetail({ category: 'missing_config' });
      return;
    }
    setStatus('testing');
    let response;
    try {
      response = await get_ipc_api().lightragApi.testSystemProvider({
        kind,
        provider: provider.provider,
        model,
        host: provider.base_url || undefined,
      });
    } catch (error: any) {
      const nextDetail = { category: 'unknown', technical: error?.message || String(error) };
      setStatus('unavailable');
      setDetail(nextDetail);
      if (showError) modal.error({
        title: t('pages.settings.provider_status_unavailable_title', { provider: provider.display_name }),
        content: <div><div>{t('pages.knowledge.settings.parserProbe.errors.unknown.suggestion')}</div><div style={{ marginTop: 8, wordBreak: 'break-word' }}>{nextDetail.technical}</div></div>,
      });
      return;
    }
    const result = (response.data || {}) as { available?: boolean; category?: string; technical_detail?: string };
    if (response.success && result.available !== false) {
      setStatus('available');
      setDetail({ category: 'unknown' });
      return;
    }
    const errorDetail = (response.error?.details || {}) as { category?: string; technical_detail?: string };
    const nextDetail = {
      category: result.category || errorDetail.category || 'unknown',
      technical: result.technical_detail || errorDetail.technical_detail,
    };
    setStatus('unavailable');
    setDetail(nextDetail);
    if (showError) {
      modal.error({
        title: t('pages.settings.provider_status_unavailable_title', { provider: provider.display_name }),
        width: 520,
        content: (
          <div style={{ lineHeight: 1.65 }}>
            <div>{t(`pages.knowledge.settings.parserProbe.errors.${nextDetail.category}.reason`)}</div>
            <div style={{ marginTop: 8 }}>{t(`pages.knowledge.settings.parserProbe.errors.${nextDetail.category}.suggestion`)}</div>
            {nextDetail.technical && <><div style={{ marginTop: 12, fontWeight: 600 }}>{t('pages.knowledge.settings.parserProbe.technicalDetails')}</div><div style={{ marginTop: 6, padding: 10, borderRadius: 6, background: 'rgba(127,127,127,.1)', wordBreak: 'break-word' }}>{nextDetail.technical}</div></>}
          </div>
        ),
      });
    }
  }, [configured, kind, model, provider.base_url, provider.display_name, provider.provider, modal, t]);

  useEffect(() => { void probe(false); }, [probe]);

  const label = status === 'available'
    ? t('pages.settings.provider_status_available')
    : status === 'testing'
      ? t('pages.settings.provider_status_testing')
      : configured
        ? t('pages.settings.provider_status_unavailable')
        : t('pages.settings.provider_status_not_configured');

  return (
    <Space size={4} style={{ whiteSpace: 'nowrap' }}>
      <Badge status={status === 'available' ? 'success' : status === 'testing' ? 'processing' : 'error'} text={<span style={{ whiteSpace: 'nowrap' }}>{label}</span>} />
      <Tooltip title={status === 'unavailable' ? <div><div>{t(`pages.knowledge.settings.parserProbe.errors.${detail.category}.reason`)}</div>{detail.technical && <div style={{ marginTop: 4, wordBreak: 'break-word' }}>{detail.technical}</div>}</div> : t('pages.settings.provider_status_retest')}>
        <Button type="text" size="small" icon={<ReloadOutlined spin={status === 'testing'} />} onClick={() => void probe(true)} disabled={status === 'testing'} />
      </Tooltip>
    </Space>
  );
};

export default ProviderStatus;
