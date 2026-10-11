import React, { useState } from 'react';
import {
  Alert, App, Button, Card, Col, Collapse, Descriptions, Empty, Result, Row, Select, Space, Statistic, Steps, Table, Tag, Typography,
} from 'antd';
import { DownloadOutlined, FileExcelOutlined, FileTextOutlined, InboxOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { ksApi, KSCatalogPreview, KSImportReport, KSOverview, KSProduct } from '@/services/ipc/ksApi';
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
  const [defaultStore, setDefaultStore] = useState<string>();
  const [busy, setBusy] = useState(false);
  const catalogJob = useJob(job => {
    if (job.status === 'succeeded') message.success(job.message || k('done'));
    onChanged();
  });
  const docsJob = useJob(job => {
    if (job.status === 'succeeded') message.success(job.message || k('done'));
    onChanged();
  });

  const pickCatalog = async () => {
    try {
      const paths = await ksApi.pickFiles(CATALOG_EXTS, k('catalogFiles'), false);
      if (!paths.length) return;
      setBusy(true);
      const pv = await ksApi.previewCatalog(paths[0]);
      setPreview(pv);
      setMapping(pv.mapping);
      setReport(pv.report);
      setSample(pv.products_preview);
      catalogJob.clear();
      setStep(1);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setBusy(false);
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
      catalogJob.track(await ksApi.importCatalog(preview.path, mapping, defaultStore));
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
        onReviewDraft({ ...d.draft, listings: defaultStore ? [{ store_id: defaultStore, platform_item_id: '' }] : [] }, d.path);
        return;
      }
      docsJob.track(await ksApi.ingestProductFiles(paths, defaultStore));
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setBusy(false);
    }
  };

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
    <Row gutter={16}>
      <Col xs={24} xl={16}>
        <Card title={<Space><FileExcelOutlined />{k('catalogTitle')}</Space>} size="small">
          <Paragraph type="secondary" style={{ marginBottom: 12 }}>{k('catalogIntro')}</Paragraph>
          <Steps size="small" current={step} style={{ marginBottom: 16 }}
                 items={[{ title: k('stepChoose') }, { title: k('stepMap') }, { title: k('stepReview') }, { title: k('stepImport') }]} />

          {step === 0 && (
            <div style={{ textAlign: 'center', padding: 24, border: '1px dashed #d9d9d9', borderRadius: 8 }}>
              <InboxOutlined style={{ fontSize: 40, color: '#1677ff' }} />
              <Paragraph style={{ marginTop: 8 }}>{k('chooseHint')}</Paragraph>
              <Space>
                <Button type="primary" loading={busy} onClick={pickCatalog}>{k('chooseFile')}</Button>
                <Button icon={<DownloadOutlined />} onClick={downloadTemplate} data-testid="ks-download-template">{k('downloadTemplate')}</Button>
              </Space>
              <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0, fontSize: 12 }}>{k('templateHint')}</Paragraph>
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
                        options={stores.map(s => ({ value: s.id, label: s.name }))} onChange={setDefaultStore} />
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
      </Col>

      <Col xs={24} xl={8}>
        <Card title={<Space><FileTextOutlined />{k('docsTitle')}</Space>} size="small">
          <Paragraph type="secondary">{k('docsIntro')}</Paragraph>
          <div style={{ marginBottom: 12 }}>
            <Text type="secondary">{k('docsStore')}</Text>
            <Select allowClear style={{ width: '100%', marginTop: 4 }} value={defaultStore} placeholder={k('noDefaultStore')}
                    options={stores.map(s => ({ value: s.id, label: s.name }))} onChange={setDefaultStore} />
          </div>
          <Button block type="primary" ghost loading={busy} disabled={docsJob.running} onClick={pickDocs}>{k('chooseDocs')}</Button>
          <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 8 }}>{k('docsHint')}</Paragraph>
          {docsJob.job && <div style={{ marginTop: 12 }}><JobProgress job={docsJob.job} /></div>}
        </Card>
        <Card size="small" style={{ marginTop: 16 }} title={k('tipsTitle')}>
          <ul style={{ paddingLeft: 18, margin: 0 }}>
            <li><Text style={{ fontSize: 12 }}>{k('tip1')}</Text></li>
            <li><Text style={{ fontSize: 12 }}>{k('tip2')}</Text></li>
            <li><Text style={{ fontSize: 12 }}>{k('tip3')}</Text></li>
          </ul>
        </Card>
      </Col>
    </Row>
  );
};

export default ImportPanel;
