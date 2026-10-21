import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert, App, Button, Card, Col, Collapse, Descriptions, Empty, Result, Row, Select, Space, Statistic, Steps, Table, Tag, Typography,
} from 'antd';
import { CloudDownloadOutlined, DownloadOutlined, FileExcelOutlined, FileTextOutlined, InboxOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { ksApi, KSCatalogPreview, KSImportReport, KSOverview, KSPendingImport, KSProduct } from '@/services/ipc/ksApi';
import JobProgress from './JobProgress';
import { useJob } from './useJob';

const { Text, Paragraph } = Typography;

const CATALOG_EXTS = ['csv', 'xlsx', 'json', 'tsv'];
const DOC_EXTS = ['pdf', 'docx', 'txt', 'md'];

interface Props {
  overview: KSOverview | null;
  onChanged: () => void;
  onReviewDraft: (product: KSProduct, attachPath: string) => void;
}

const ReportSummary: React.FC<{ report: KSImportReport }> = ({ report }) => {
  const { t } = useTranslation();
  const k = (key: string, o?: Record<string, unknown>): string => String(t(`pages.knowledge.ks.import.${key}`, o as any));
  return (
    <>
      <Row gutter={16} style={{ marginBottom: 12 }}>
        <Col span={5}><Statistic title={k('rows')} value={report.rows_total} /></Col>
        <Col span={5}><Statistic title={k('products')} value={report.products} valueStyle={{ color: '#1677ff' }} /></Col>
        <Col span={5}><Statistic title={k('variants')} value={report.variants} /></Col>
        <Col span={5}><Statistic title={k('listings')} value={report.listings} /></Col>
        <Col span={4}><Statistic title={k('skipped')} value={report.skipped_count} valueStyle={{ color: report.skipped_count ? '#fa8c16' : undefined }} /></Col>
      </Row>
      {report.errors.map((e, i) => <Alert key={i} type="error" showIcon message={e} style={{ marginBottom: 8 }} />)}
      {(report.warning_count > 0 || report.skipped_count > 0) && (
        <Collapse
          size="small"
          items={[
            ...(report.warning_count ? [{
              key: 'w', label: <Space><Tag color="orange">{report.warning_count}</Tag>{k('warnings')}</Space>,
              children: <div style={{ maxHeight: 200, overflow: 'auto' }}>{report.warnings.map((w, i) => <div key={i}><Text style={{ fontSize: 12 }}>{w}</Text></div>)}</div>,
            }] : []),
            ...(report.skipped_count ? [{
              key: 's', label: <Space><Tag color="red">{report.skipped_count}</Tag>{k('skippedRows')}</Space>,
              children: <div style={{ maxHeight: 200, overflow: 'auto' }}>{report.skipped.map((s, i) => <div key={i}><Text style={{ fontSize: 12 }}>{k('rowN', { row: s.row })}: {s.reason}</Text></div>)}</div>,
            }] : []),
          ]}
        />
      )}
    </>
  );
};

const ImportPanel: React.FC<Props> = ({ overview, onChanged, onReviewDraft }) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const k = (key: string, o?: Record<string, unknown>): string => String(t(`pages.knowledge.ks.import.${key}`, o as any));
  const stores = overview?.stores || [];

  const [step, setStep] = useState(0);
  const [preview, setPreview] = useState<KSCatalogPreview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [report, setReport] = useState<KSImportReport | null>(null);
  const [sample, setSample] = useState<KSProduct[]>([]);
  // Store for table rows without a 店铺 column; documents have their own choice.
  const [defaultStore, setDefaultStore] = useState<string>();
  const [docsStore, setDocsStore] = useState<string>();
  const [busy, setBusy] = useState(false);
  // Catalog files an agent fetched (e.g. the store's product export) for review.
  const [pending, setPending] = useState<KSPendingImport[]>([]);
  const [pendingId, setPendingId] = useState<string>();
  const catalogJob = useJob(job => {
    if (job.status === 'succeeded') message.success(job.message || k('done'));
    onChanged();
  });
  const docsJob = useJob(job => {
    if (job.status === 'succeeded') message.success(job.message || k('done'));
    onChanged();
  });

  const loadPending = useCallback(async () => {
    try {
      setPending((await ksApi.listPendingImports()).items || []);
    } catch {
      /* older backend: no staged imports */
    }
  }, []);

  useEffect(() => {
    if (step !== 0) return undefined;
    loadPending();
    const timer = setInterval(loadPending, 15000);
    return () => clearInterval(timer);
  }, [step, loadPending]);

  const loadCatalog = async (path: string) => {
    setBusy(true);
    const reading = message.loading(k('readingFile', { file: path.split(/[\\/]/).pop() }), 0);
    try {
      const pv = await ksApi.previewCatalog(path);
      setPreview(pv);
      setMapping(pv.mapping);
      setReport(pv.report);
      setSample(pv.products_preview);
      catalogJob.clear();
      setStep(1);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      reading();
      setBusy(false);
    }
  };

  const pickCatalog = async () => {
    try {
      const paths = await ksApi.pickFiles(CATALOG_EXTS, k('catalogFiles'), false);
      if (!paths.length) return;
      setPendingId(undefined);
      await loadCatalog(paths[0]);
    } catch (e: any) {
      message.error(e.message);
    }
  };

  const reviewPending = async (item: KSPendingImport) => {
    setPendingId(item.id);
    if (item.store_id) setDefaultStore(item.store_id);
    await loadCatalog(item.path);
  };

  const dismissPending = async (item: KSPendingImport) => {
    try {
      await ksApi.dismissPendingImport(item.id);
      loadPending();
    } catch (e: any) {
      message.error(e.message);
    }
  };

  const recheck = async () => {
    if (!preview) return;
    setBusy(true);
    try {
      const r = await ksApi.recheckCatalog(preview.path, mapping);
      setReport(r.report);
      setSample(r.products_preview);
      setStep(2);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  const startImport = async () => {
    if (!preview) return;
    try {
      catalogJob.track(await ksApi.importCatalog(preview.path, mapping, defaultStore, pendingId));
      setPendingId(undefined);
      setStep(3);
    } catch (e: any) {
      message.error(e.message);
    }
  };

  const downloadTemplate = async () => {
    try {
      const dir = await ksApi.pickFolder();
      if (!dir) return;
      const { path } = await ksApi.writeCatalogTemplate(dir);
      message.success(k('templateSaved', { path }), 6);
    } catch (e: any) {
      message.error(e.message);
    }
  };

  const restart = () => {
    setPendingId(undefined);
    setStep(0);
    setPreview(null);
    setReport(null);
    catalogJob.clear();
  };

  const pickDocs = async () => {
    try {
      const paths = await ksApi.pickFiles(DOC_EXTS, k('docFiles'), true);
      if (!paths.length) return;
      if (paths.length === 1) {
        setBusy(true);
        const d = await ksApi.draftFromDocument(paths[0]);
        onReviewDraft({ ...d.draft, listings: docsStore ? [{ store_id: docsStore, platform_item_id: '' }] : [] }, d.path);
        return;
      }
      docsJob.track(await ksApi.ingestProductFiles(paths, docsStore));
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  const storeOptions = stores.map(s => ({ value: s.id, label: s.name }));
  const fieldOptions = (preview?.fields || []).map(f => ({ value: f.value, label: f.label }));
  const mappedFields = Object.values(mapping);
  const missingTitle = !mappedFields.includes('title');

  const mappingColumns = [
    { title: k('fileColumn'), dataIndex: 'header', key: 'header', width: 180, render: (h: string) => <Text strong>{h}</Text> },
    {
      title: k('sample'), key: 'sample', ellipsis: true,
      render: (_: any, r: { header: string }) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {(preview?.rows_preview || []).map(row => row[r.header]).filter(Boolean).slice(0, 3).join(' | ')}
        </Text>
      ),
    },
    {
      title: k('mapsTo'), key: 'field', width: 260,
      render: (_: any, r: { header: string }) => (
        <Select size="small" style={{ width: '100%' }} value={mapping[r.header]} options={fieldOptions}
                onChange={v => setMapping({ ...mapping, [r.header]: v })}
                status={['price', 'stock'].includes(mapping[r.header]) ? 'warning' : undefined} />
      ),
    },
  ];

  return (
    <>
      <Card title={<Space><FileExcelOutlined />{k('catalogTitle')}</Space>} size="small">
        <Paragraph type="secondary" style={{ marginBottom: 12 }}>{k('catalogIntro')}</Paragraph>
        <Steps size="small" current={step} style={{ marginBottom: 16 }}
               items={[{ title: k('stepChoose') }, { title: k('stepMap') }, { title: k('stepReview') }, { title: k('stepImport') }]} />

        {step === 0 && pending.map(item => (
          <Alert key={item.id} type="info" showIcon icon={<CloudDownloadOutlined />} style={{ marginBottom: 12 }}
                 data-testid={`ks-pending-${item.id}`}
                 message={k('pendingTitle', { file: item.file_name, rows: item.rows })}
                 description={[item.source, stores.find(s => s.id === item.store_id)?.name, new Date(item.created_at * 1000).toLocaleString()]
                   .filter(Boolean).join(' · ')}
                 action={
                   <Space direction="vertical">
                     <Button size="small" type="primary" loading={busy} onClick={() => reviewPending(item)}>{k('pendingReview')}</Button>
                     <Button size="small" onClick={() => dismissPending(item)}>{k('pendingDismiss')}</Button>
                   </Space>
                 } />
        ))}

        {step === 0 && (
          <div style={{ padding: 16, border: '1px dashed #d9d9d9', borderRadius: 8 }}>
            <Row gutter={[16, 12]} align="middle">
              <Col xs={24} md={8}><Text strong>{k('step1Label')}</Text></Col>
              <Col xs={24} md={16}>
                <Button icon={<DownloadOutlined />} onClick={downloadTemplate} data-testid="ks-download-template">{k('downloadTemplate')}</Button>
                <Paragraph type="secondary" style={{ marginTop: 6, marginBottom: 0, fontSize: 12 }}>{k('templateHint')}</Paragraph>
              </Col>
              <Col xs={24} md={8}><Text strong>{k('step2Label')}</Text></Col>
              <Col xs={24} md={16}>
                <Space wrap>
                  <Button type="primary" icon={<InboxOutlined />} loading={busy} onClick={pickCatalog}>{k('chooseFile')}</Button>
                  <Text type="secondary" style={{ fontSize: 12 }}>{k('chooseHint')}</Text>
                </Space>
                <div style={{ marginTop: 8 }}>
                  <Text type="secondary">{k('defaultStore')}</Text>
                  <Select allowClear size="small" style={{ width: 220, marginLeft: 8 }} value={defaultStore} placeholder={k('noDefaultStore')}
                          options={storeOptions} onChange={setDefaultStore} data-testid="ks-catalog-store" />
                </div>
              </Col>
            </Row>
          </div>
        )}

        {step === 1 && preview && (
          <>
            <Descriptions size="small" column={3} style={{ marginBottom: 8 }}>
              <Descriptions.Item label={k('file')}>{preview.filename}</Descriptions.Item>
              <Descriptions.Item label={k('rows')}>{preview.report.rows_total}</Descriptions.Item>
              <Descriptions.Item label={k('columns')}>{preview.headers.length}</Descriptions.Item>
            </Descriptions>
            <Alert type="info" showIcon style={{ marginBottom: 8 }} message={k('mappingHint')} />
            {missingTitle && <Alert type="error" showIcon style={{ marginBottom: 8 }} message={k('needTitle')} />}
            <Table size="small" rowKey="header" pagination={false} scroll={{ y: 360 }} columns={mappingColumns as any}
                   dataSource={preview.headers.map(h => ({ header: h }))} />
            <Space style={{ marginTop: 12 }}>
              <Button onClick={restart}>{k('back')}</Button>
              <Button type="primary" disabled={missingTitle} loading={busy} onClick={recheck}>{k('checkData')}</Button>
            </Space>
          </>
        )}

        {step === 2 && report && (
          <>
            <ReportSummary report={report} />
            {preview && preview.stores_in_file.length > 0 && (
              <Alert style={{ marginTop: 12 }} type="info" showIcon
                     message={k('storesInFile', { stores: preview.stores_in_file.join('、') })} />
            )}
            <div style={{ marginTop: 12 }}>
              <Text>{k('defaultStore')}</Text>
              <Select allowClear style={{ width: 260, marginLeft: 8 }} value={defaultStore} placeholder={k('noDefaultStore')}
                      options={storeOptions} onChange={setDefaultStore} />
            </div>
            {sample.length > 0 && (
              <Card size="small" style={{ marginTop: 12 }} title={k('sampleProducts')}>
                {sample.slice(0, 3).map((p, i) => (
                  <div key={i} style={{ marginBottom: 8 }}>
                    <Text strong>{p.title}</Text> <Text type="secondary">{p.code}</Text>
                    <div><Space size={[4, 4]} wrap>
                      {Object.entries(p.attributes).slice(0, 8).map(([a, b]) => <Tag key={a}>{a}: {b}</Tag>)}
                    </Space></div>
                  </div>
                ))}
              </Card>
            )}
            <Space style={{ marginTop: 12 }}>
              <Button onClick={() => setStep(1)}>{k('back')}</Button>
              <Button type="primary" disabled={report.errors.length > 0 || report.products === 0} onClick={startImport}>
                {k('startImport', { count: report.products })}
              </Button>
            </Space>
          </>
        )}

        {step === 3 && (
          catalogJob.job ? (
            <>
              <JobProgress job={catalogJob.job} />
              {catalogJob.job.status === 'succeeded' && (
                <Result status="success" title={catalogJob.job.message}
                        subTitle={k('resultDetail', {
                          changed: catalogJob.job.result?.changed ?? 0,
                          unchanged: catalogJob.job.result?.unchanged ?? 0,
                          chunks: catalogJob.job.result?.chunks ?? 0,
                        })}
                        extra={<Button onClick={restart}>{k('importAnother')}</Button>} />
              )}
              {['failed', 'cancelled'].includes(catalogJob.job.status) && (
                <Space style={{ marginTop: 12 }}><Button onClick={restart}>{k('startOver')}</Button></Space>
              )}
            </>
          ) : <Empty />
        )}
      </Card>

      <Card size="small" style={{ marginTop: 16 }} title={<Space><FileTextOutlined /><Text>{k('docsTitle')}</Text></Space>}>
        <Paragraph type="secondary" style={{ fontSize: 12 }}>{k('docsIntro')}</Paragraph>
        <Space wrap>
          <Button type="primary" ghost loading={busy} disabled={docsJob.running} onClick={pickDocs}>{k('chooseDocs')}</Button>
          <Text type="secondary">{k('docsStore')}</Text>
          <Select allowClear size="small" style={{ width: 220 }} value={docsStore} placeholder={k('noDefaultStore')}
                  options={storeOptions} onChange={setDocsStore} />
        </Space>
        <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 8, marginBottom: 0 }}>{k('docsHint')}</Paragraph>
        {docsJob.job && <div style={{ marginTop: 12 }}><JobProgress job={docsJob.job} /></div>}
      </Card>

      <Collapse size="small" style={{ marginTop: 16 }} items={[{
        key: 'tips', label: k('tipsTitle'),
        children: (
          <ul style={{ paddingLeft: 18, margin: 0 }}>
            <li><Text style={{ fontSize: 12 }}>{k('tip1')}</Text></li>
            <li><Text style={{ fontSize: 12 }}>{k('tip2')}</Text></li>
            <li><Text style={{ fontSize: 12 }}>{k('tip3')}</Text></li>
          </ul>
        ),
      }]} />
    </>
  );
};

export default ImportPanel;
