import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Card, Table, Button, Space, Typography, Spin, Empty, message, DatePicker, Divider } from 'antd';
import { DownloadOutlined, PrinterOutlined, ReloadOutlined, DownOutlined, UpOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { useTranslation } from 'react-i18next';
import { ipcApi } from '../../services/ipc/api';
import { Currency, HistoryEntry, dailyRows, summarizeMonth } from './billingSummary';

const { Title, Text } = Typography;

// The account's statement as the SERVER keeps it (billing_history): what the
// balance was actually debited and credited. Local token counts are not shown
// -- they are estimates, not charges. Shown the way a seller thinks about it:
// replies answered x price, plus one plain line per other service used.

function symbolFor(c: Currency): string {
  return c === 'CNY' ? '¥' : '$';
}
function fmtMinor(minor: number, c: Currency): string {
  return `${symbolFor(c)}${(Math.abs(minor) / 100).toFixed(2)}`;
}

const BillingDrilldown: React.FC = () => {
  const { t } = useTranslation();
  const [month, setMonth] = useState<Dayjs>(dayjs());
  const [currency, setCurrency] = useState<Currency>('CNY');
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchHistory = useCallback(async (m: Dayjs) => {
    setLoading(true);
    try {
      const res = await ipcApi.getBillingHistory<{ currency?: Currency; entries: HistoryEntry[] }>(
        m.startOf('month').format('YYYY-MM-DD'), m.endOf('month').format('YYYY-MM-DD'),
      );
      if (res?.success && res.data) {
        setEntries(res.data.entries || []);
        setCurrency(res.data.currency || 'CNY');
      } else {
        setEntries([]);
      }
    } catch {
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchHistory(month); }, [month, fetchHistory]);

  const summary = useMemo(() => summarizeMonth(entries), [entries]);
  const days = useMemo(() => dailyRows(entries, (ts) => dayjs(ts).format('YYYY-MM-DD')), [entries]);
  const [showDays, setShowDays] = useState(false);

  const otherName = (category: string) => t(`billing.services.${category}`, category);
  const money = (minor: number) => fmtMinor(minor, currency);
  const replyLine = summary.unitPrice != null
    ? t('billing.replyLine', '{{count}} replies × {{price}} = {{total}}', {
      count: summary.replies, price: money(summary.unitPrice), total: money(summary.replyAmount) })
    : t('billing.replyLineNoPrice', '{{count}} replies, {{total}}', {
      count: summary.replies, total: money(summary.replyAmount) });

  const dayColumns = [
    { title: t('billing.date', 'Date'), dataIndex: 'date', key: 'date' },
    { title: t('billing.replies', 'Replies'), dataIndex: 'replies', key: 'replies', align: 'right' as const },
    { title: t('billing.replyCost', 'Reply charges'), key: 'replyAmount', align: 'right' as const,
      render: (_: unknown, r: { replyAmount: number }) => money(r.replyAmount) },
    { title: t('billing.otherCost', 'Other services'), key: 'otherAmount', align: 'right' as const,
      render: (_: unknown, r: { otherAmount: number }) => (r.otherAmount ? money(r.otherAmount) : '—') },
    { title: t('billing.dayTotal', 'Total'), key: 'total', align: 'right' as const,
      render: (_: unknown, r: { total: number }) => <strong>{money(r.total)}</strong> },
  ];

  // ── Export / print ─────────────────────────────────────────────────────────
  const exportCSV = () => {
    const esc = (v: string) => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const lines = [['date', 'type', 'category', 'description', `amount_${currency}`].join(',')];
    for (const e of entries) {
      lines.push([dayjs(e.ts).format('YYYY-MM-DD'), e.type, e.category || '', esc(e.description || ''),
        (e.amount / 100).toFixed(2)].join(','));
    }
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `billing-${month.format('YYYY-MM')}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const printStatement = () => {
    const esc = (v: string) => String(v).replace(/</g, '&lt;');
    const right = 'style="text-align:right"';
    const lines = [`<tr><td>${esc(t('billing.csReplies', 'Customer-service replies'))}</td><td ${right}>${esc(replyLine)}</td></tr>`,
      ...summary.others.map((o) => `<tr><td>${esc(otherName(o.category))}</td><td ${right}>${money(o.amount)}</td></tr>`)].join('');
    const dayRows = days.map((r) => `<tr><td>${r.date}</td><td ${right}>${r.replies}</td>`
      + `<td ${right}>${money(r.replyAmount)}</td><td ${right}>${r.otherAmount ? money(r.otherAmount) : '—'}</td>`
      + `<td ${right}>${money(r.total)}</td></tr>`).join('');
    const html = `<html><head><title>Billing ${month.format('YYYY-MM')}</title>
      <style>body{font-family:system-ui,Arial,sans-serif;padding:24px}h2{margin:0 0 4px}
      table{border-collapse:collapse;width:100%;margin-top:12px}th,td{border:1px solid #ddd;padding:6px 10px;font-size:13px}
      th{background:#f5f5f5;text-align:left}tfoot td{font-weight:bold}</style></head>
      <body><h2>eCan ${t('billing.statement', 'Billing statement')}</h2>
      <div>${month.format('YYYY-MM')} · ${currency}</div>
      <table><tbody>${lines}</tbody>
      <tfoot><tr><td>${t('billing.monthTotal', 'Month total')}</td><td ${right}>${money(summary.totalCharged)}</td></tr></tfoot></table>
      <table><thead><tr><th>${t('billing.date', 'Date')}</th><th ${right}>${t('billing.replies', 'Replies')}</th>
      <th ${right}>${t('billing.replyCost', 'Reply charges')}</th><th ${right}>${t('billing.otherCost', 'Other services')}</th>
      <th ${right}>${t('billing.dayTotal', 'Total')}</th></tr></thead><tbody>${dayRows}</tbody></table></body></html>`;
    const w = window.open('', '_blank', 'width=800,height=900');
    if (!w) { message.warning(t('billing.popupBlocked', 'Allow pop-ups to print the statement')); return; }
    w.document.write(html);
    w.document.close();
    w.focus();
    w.print();
  };

  return (
    <Card
      style={{ marginTop: 16 }}
      title={<Title level={5} style={{ margin: 0 }}>{t('billing.title', 'Usage & Billing')}</Title>}
      extra={
        <Space>
          <DatePicker picker="month" value={month} onChange={(m) => m && setMonth(m)} allowClear={false} />
          <Button icon={<ReloadOutlined />} onClick={() => fetchHistory(month)} />
          <Button icon={<DownloadOutlined />} onClick={exportCSV} disabled={!entries.length}>CSV</Button>
          <Button icon={<PrinterOutlined />} onClick={printStatement} disabled={!entries.length}>{t('billing.print', 'Print')}</Button>
        </Space>
      }
    >
      {loading && !entries.length ? (
        <Spin />
      ) : !entries.length ? (
        <Empty description={t('billing.noUsage', 'No charges this month')} />
      ) : (
        <>
          <Space direction="vertical" size={6} style={{ width: '100%', maxWidth: 520 }}>
            <Space style={{ width: '100%', justifyContent: 'space-between' }}>
              <Text>{t('billing.csReplies', 'Customer-service replies')}</Text>
              <Text style={{ fontVariantNumeric: 'tabular-nums' }}>{replyLine}</Text>
            </Space>
            {summary.others.map((o) => (
              <Space key={o.category} style={{ width: '100%', justifyContent: 'space-between' }}>
                <Text type="secondary">{otherName(o.category)}</Text>
                <Text type="secondary" style={{ fontVariantNumeric: 'tabular-nums' }}>{money(o.amount)}</Text>
              </Space>
            ))}
            <Divider style={{ margin: '4px 0' }} />
            <Space style={{ width: '100%', justifyContent: 'space-between' }}>
              <Text strong>{t('billing.monthTotal', 'Month total')}</Text>
              <Text strong style={{ fontSize: 16, fontVariantNumeric: 'tabular-nums' }}>{money(summary.totalCharged)}</Text>
            </Space>
            {summary.totalCredited > 0 && (
              <Text style={{ color: '#22c55e' }}>{t('billing.monthTopup', 'Topped up')}: +{money(summary.totalCredited)}</Text>
            )}
          </Space>

          <div style={{ marginTop: 12 }}>
            <Button type="link" style={{ padding: 0 }} icon={showDays ? <UpOutlined /> : <DownOutlined />}
                    onClick={() => setShowDays((v) => !v)}>
              {showDays ? t('billing.hideDays', 'Hide daily details') : t('billing.showDays', 'Show daily details')}
            </Button>
            {showDays && (
              <Table rowKey="key" size="small" columns={dayColumns} dataSource={days}
                     pagination={{ pageSize: 31, size: 'small', hideOnSinglePage: true }} style={{ marginTop: 8 }} />
            )}
          </div>
        </>
      )}
    </Card>
  );
};

export default BillingDrilldown;
