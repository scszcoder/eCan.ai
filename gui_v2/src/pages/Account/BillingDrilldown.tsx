import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Card, Table, Button, Space, Typography, Spin, Empty, message, DatePicker } from 'antd';
import { DownloadOutlined, PrinterOutlined, ReloadOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { useTranslation } from 'react-i18next';
import { ipcApi } from '../../services/ipc/api';

const { Title, Text } = Typography;

// The account's statement as the SERVER keeps it (billing_history): what the
// balance was actually debited and credited. Local token counts are not shown
// -- they are estimates, not charges.
type Currency = 'CNY' | 'USD';

interface HistoryEntry {
  entry_id: string;
  ts: string;
  type: string; // topup | charge | refund | adjustment | coupon_credit
  amount: number; // minor units (fen / cents), signed
  currency: Currency;
  status: string;
  coupon_code?: string | null;
  description?: string;
  /** usage charges only: llm_usage | knowledge_base | media_generation (per-reply charges: none) */
  category?: string;
}

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

  const charges = useMemo(() => entries.filter((e) => e.type === 'charge'), [entries]);
  const credits = useMemo(() => entries.filter((e) => e.type !== 'charge' && e.status === 'success'), [entries]);
  const monthCharged = useMemo(() => charges.reduce((s, e) => s + Math.abs(e.amount), 0), [charges]);
  const monthCredited = useMemo(() => credits.reduce((s, e) => s + e.amount, 0), [credits]);

  const kind = (e: HistoryEntry) => (e.type === 'charge'
    ? t(`billing.categories.${e.category || 'per_reply'}`, e.category || 'per_reply')
    : t(`billing.types.${e.type}`, e.type));
  const signed = (e: HistoryEntry) => `${e.amount < 0 ? '-' : '+'}${fmtMinor(e.amount, e.currency || currency)}`;

  const columns = [
    { title: t('billing.date', 'Date'), key: 'ts', render: (_: unknown, e: HistoryEntry) => dayjs(e.ts).format('YYYY-MM-DD') },
    { title: t('billing.category', 'Category'), key: 'kind', render: (_: unknown, e: HistoryEntry) => kind(e) },
    { title: t('billing.description', 'Details'), dataIndex: 'description', key: 'description', ellipsis: true },
    {
      title: t('billing.amount', 'Amount'), key: 'amount', align: 'right' as const,
      render: (_: unknown, e: HistoryEntry) => (
        <Text style={{ color: e.amount < 0 ? undefined : '#22c55e' }}>{signed(e)}</Text>
      ),
    },
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
    const rows = entries.map((e) => `<tr><td>${dayjs(e.ts).format('YYYY-MM-DD')}</td><td>${kind(e)}</td>`
      + `<td>${(e.description || '').replace(/</g, '&lt;')}</td><td style="text-align:right">${signed(e)}</td></tr>`).join('');
    const html = `<html><head><title>Billing ${month.format('YYYY-MM')}</title>
      <style>body{font-family:system-ui,Arial,sans-serif;padding:24px}h2{margin:0 0 4px}
      table{border-collapse:collapse;width:100%;margin-top:12px}th,td{border:1px solid #ddd;padding:6px 10px;font-size:13px}
      th{background:#f5f5f5;text-align:left}tfoot td{font-weight:bold}</style></head>
      <body><h2>eCan ${t('billing.statement', 'Billing statement')}</h2>
      <div>${month.format('YYYY-MM')} · ${currency}</div>
      <table><thead><tr><th>${t('billing.date', 'Date')}</th><th>${t('billing.category', 'Category')}</th>
      <th>${t('billing.description', 'Details')}</th><th style="text-align:right">${t('billing.amount', 'Amount')}</th></tr></thead>
      <tbody>${rows}</tbody>
      <tfoot><tr><td colspan="3">${t('billing.monthTotal', 'Month total')}</td>
      <td style="text-align:right">-${fmtMinor(monthCharged, currency)}</td></tr></tfoot></table></body></html>`;
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
      <Space style={{ marginBottom: 12 }} size="large">
        <Text>{t('billing.monthTotal', 'Month total')}: <strong>{fmtMinor(monthCharged, currency)}</strong></Text>
        {monthCredited > 0 && (
          <Text style={{ color: '#22c55e' }}>{t('billing.monthTopup', 'Topped up')}: +{fmtMinor(monthCredited, currency)}</Text>
        )}
      </Space>

      {loading && !entries.length ? (
        <Spin />
      ) : !entries.length ? (
        <Empty description={t('billing.noUsage', 'No charges this month')} />
      ) : (
        <Table rowKey="entry_id" size="small" columns={columns} dataSource={entries}
               pagination={{ pageSize: 20, size: 'small' }} />
      )}
    </Card>
  );
};

export default BillingDrilldown;
