import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Card, Table, Button, Space, Typography, Spin, Empty, message, DatePicker } from 'antd';
import { DownloadOutlined, PrinterOutlined, ReloadOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { useTranslation } from 'react-i18next';
import { ipcApi } from '../../services/ipc/api';

const { Title, Text } = Typography;

// ─── Types (mirror the local billing IPC + cloud history contract) ───────────
type Currency = 'CNY' | 'USD';

interface DayRow {
  date: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost: number;
  cost_usd: number;
}
interface HourRow {
  hour: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost: number;
  cost_usd: number;
}
interface ModelRow {
  vendor: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  input_cost: number;
  output_cost: number;
  total_cost: number;
}
// Cloud top-up entry (server-authoritative; optional until backend ships).
interface HistoryEntry {
  entry_id: string;
  ts: string;
  type: string; // topup | charge | refund | adjustment | coupon_credit
  amount: number; // minor units, signed
  currency: Currency;
  status: string;
  coupon_code?: string | null;
  description?: string;
}

const CACHE_KEY = 'ecan.billing.daily.v1';

function symbolFor(c: Currency): string {
  return c === 'CNY' ? '¥' : '$';
}
function fmtMoney(n: number, c: Currency, dp = 2): string {
  return `${symbolFor(c)}${(n ?? 0).toFixed(dp)}`;
}
function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return `${n ?? 0}`;
}
// Top-up entries are stored in minor units; render as major.
function fmtMinor(minor: number, c: Currency): string {
  return `${symbolFor(c)}${(Math.abs(minor) / 100).toFixed(2)}`;
}

const BillingDrilldown: React.FC = () => {
  const { t } = useTranslation();
  const [month, setMonth] = useState<Dayjs>(dayjs());
  const [currency, setCurrency] = useState<Currency>('USD');
  const [days, setDays] = useState<DayRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [fromCache, setFromCache] = useState(false);
  // Top-ups grouped by local date (from cloud history; empty if unavailable).
  const [topupByDate, setTopupByDate] = useState<Record<string, HistoryEntry[]>>({});

  // Lazy caches keyed by date / date|hour.
  const [hourly, setHourly] = useState<Record<string, HourRow[]>>({});
  const [models, setModels] = useState<Record<string, ModelRow[]>>({});

  // ── Daily (with last-reading cache) ────────────────────────────────────────
  const fetchDaily = useCallback(async (m: Dayjs) => {
    setLoading(true);
    try {
      const res = await ipcApi.getBillingDaily<{ currency: Currency; days: DayRow[] }>(
        m.year(), m.month() + 1,
      );
      if (res?.success && res.data) {
        setDays(res.data.days || []);
        setCurrency(res.data.currency || 'USD');
        setFromCache(false);
        try {
          localStorage.setItem(CACHE_KEY, JSON.stringify({
            key: m.format('YYYY-MM'), at: Date.now(),
            currency: res.data.currency, days: res.data.days,
          }));
        } catch { /* storage may be unavailable */ }
      }
    } catch (e) {
      console.error('[Billing] daily error:', e);
      // Fall back to the last networked reading for this month, if cached.
      try {
        const raw = localStorage.getItem(CACHE_KEY);
        if (raw) {
          const c = JSON.parse(raw);
          if (c?.key === m.format('YYYY-MM')) {
            setDays(c.days || []);
            setCurrency(c.currency || 'USD');
            setFromCache(true);
          }
        }
      } catch { /* ignore */ }
    } finally {
      setLoading(false);
    }
  }, []);

  // ── Cloud top-up history (optional) ────────────────────────────────────────
  const fetchTopups = useCallback(async (m: Dayjs) => {
    const start = m.startOf('month').format('YYYY-MM-DD');
    const end = m.endOf('month').format('YYYY-MM-DD');
    try {
      const res = await ipcApi.getBillingHistory<{ entries: HistoryEntry[] }>(start, end);
      if (res?.success && res.data?.entries) {
        const grouped: Record<string, HistoryEntry[]> = {};
        for (const e of res.data.entries) {
          if (e.type !== 'topup' && e.type !== 'coupon_credit') continue;
          const d = dayjs(e.ts).format('YYYY-MM-DD');
          (grouped[d] = grouped[d] || []).push(e);
        }
        setTopupByDate(grouped);
      }
    } catch {
      // Cloud history not available yet — usage tree still renders fully.
      setTopupByDate({});
    }
  }, []);

  useEffect(() => {
    // Seed instantly from cache so the panel is never blank, then refresh.
    try {
      const raw = localStorage.getItem(CACHE_KEY);
      if (raw) {
        const c = JSON.parse(raw);
        if (c?.key === month.format('YYYY-MM')) {
          setDays(c.days || []);
          setCurrency(c.currency || 'USD');
          setFromCache(true);
        }
      }
    } catch { /* ignore */ }
    fetchDaily(month);
    fetchTopups(month);
    setHourly({});
    setModels({});
  }, [month, fetchDaily, fetchTopups]);

  const loadHourly = useCallback(async (date: string) => {
    if (hourly[date]) return;
    try {
      const res = await ipcApi.getBillingHourly<{ hours: HourRow[] }>(date);
      if (res?.success && res.data) setHourly(prev => ({ ...prev, [date]: res.data!.hours || [] }));
    } catch (e) { console.error('[Billing] hourly error:', e); }
  }, [hourly]);

  const loadModels = useCallback(async (date: string, hour: number) => {
    const key = `${date}|${hour}`;
    if (models[key]) return;
    try {
      const res = await ipcApi.getBillingHourModels<{ rows: ModelRow[] }>(date, hour);
      if (res?.success && res.data) setModels(prev => ({ ...prev, [key]: res.data!.rows || [] }));
    } catch (e) { console.error('[Billing] models error:', e); }
  }, [models]);

  const monthTotal = useMemo(() => days.reduce((s, d) => s + (d.cost || 0), 0), [days]);
  const monthTopup = useMemo(
    () => Object.values(topupByDate).flat().reduce((s, e) => s + Math.abs(e.amount), 0) / 100,
    [topupByDate],
  );

  // ── Nested tables ──────────────────────────────────────────────────────────
  const modelColumns = [
    { title: t('billing.provider', 'Provider'), dataIndex: 'vendor', key: 'vendor' },
    { title: t('billing.model', 'Model'), dataIndex: 'model', key: 'model' },
    { title: t('billing.inTokens', 'Input tokens'), dataIndex: 'input_tokens', key: 'it', align: 'right' as const, render: fmtTokens },
    { title: t('billing.outTokens', 'Output tokens'), dataIndex: 'output_tokens', key: 'ot', align: 'right' as const, render: fmtTokens },
    { title: t('billing.inCost', 'Input cost'), dataIndex: 'input_cost', key: 'ic', align: 'right' as const, render: (v: number) => fmtMoney(v, currency, 4) },
    { title: t('billing.outCost', 'Output cost'), dataIndex: 'output_cost', key: 'oc', align: 'right' as const, render: (v: number) => fmtMoney(v, currency, 4) },
    { title: t('billing.total', 'Total'), dataIndex: 'total_cost', key: 'tc', align: 'right' as const, render: (v: number) => <strong>{fmtMoney(v, currency, 4)}</strong> },
  ];

  const hourColumns = [
    { title: t('billing.hour', 'Hour'), dataIndex: 'hour', key: 'h', render: (h: number) => `${String(h).padStart(2, '0')}:00` },
    { title: t('billing.tokens', 'Tokens'), dataIndex: 'total_tokens', key: 'tt', align: 'right' as const, render: fmtTokens },
    { title: t('billing.cost', 'Cost'), dataIndex: 'cost', key: 'c', align: 'right' as const, render: (v: number) => fmtMoney(v, currency, 4) },
  ];

  const dayColumns = [
    { title: t('billing.date', 'Date'), dataIndex: 'date', key: 'date' },
    { title: t('billing.tokens', 'Tokens'), dataIndex: 'total_tokens', key: 'tt', align: 'right' as const, render: fmtTokens },
    {
      title: t('billing.topup', 'Top-up'), key: 'topup', align: 'right' as const,
      render: (_: unknown, d: DayRow) => {
        const es = topupByDate[d.date];
        if (!es || !es.length) return <Text type="secondary">—</Text>;
        const sum = es.reduce((s, e) => s + Math.abs(e.amount), 0);
        return <Text style={{ color: '#22c55e' }}>+{fmtMinor(sum, currency)}</Text>;
      },
    },
    { title: t('billing.cost', 'Cost'), dataIndex: 'cost', key: 'c', align: 'right' as const, render: (v: number) => <strong>{fmtMoney(v, currency)}</strong> },
  ];

  // ── Export / print ─────────────────────────────────────────────────────────
  const exportCSV = () => {
    const header = ['date', 'input_tokens', 'output_tokens', 'total_tokens', `cost_${currency}`, 'cost_usd'];
    const lines = [header.join(',')];
    for (const d of days) {
      lines.push([d.date, d.input_tokens, d.output_tokens, d.total_tokens, d.cost, d.cost_usd].join(','));
    }
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `billing-${month.format('YYYY-MM')}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const printStatement = () => {
    const rows = days.map(d => {
      const es = topupByDate[d.date];
      const topup = es && es.length ? `+${fmtMinor(es.reduce((s, e) => s + Math.abs(e.amount), 0), currency)}` : '';
      return `<tr><td>${d.date}</td><td style="text-align:right">${d.total_tokens}</td><td style="text-align:right;color:#16a34a">${topup}</td><td style="text-align:right">${fmtMoney(d.cost, currency)}</td></tr>`;
    }).join('');
    const html = `<html><head><title>Billing ${month.format('YYYY-MM')}</title>
      <style>body{font-family:system-ui,Arial,sans-serif;padding:24px}h2{margin:0 0 4px}
      table{border-collapse:collapse;width:100%;margin-top:12px}th,td{border:1px solid #ddd;padding:6px 10px;font-size:13px}
      th{background:#f5f5f5;text-align:left}tfoot td{font-weight:bold}</style></head>
      <body><h2>eCan ${t('billing.statement', 'Billing statement')}</h2>
      <div>${month.format('YYYY-MM')} · ${currency}</div>
      <table><thead><tr><th>${t('billing.date', 'Date')}</th><th style="text-align:right">${t('billing.tokens', 'Tokens')}</th>
      <th style="text-align:right">${t('billing.topup', 'Top-up')}</th><th style="text-align:right">${t('billing.cost', 'Cost')}</th></tr></thead>
      <tbody>${rows}</tbody>
      <tfoot><tr><td>${t('billing.total', 'Total')}</td><td></td><td style="text-align:right;color:#16a34a">+${monthTopup.toFixed(2)}</td>
      <td style="text-align:right">${fmtMoney(monthTotal, currency)}</td></tr></tfoot></table></body></html>`;
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
          <Button icon={<ReloadOutlined />} onClick={() => { setHourly({}); setModels({}); fetchDaily(month); fetchTopups(month); }} />
          <Button icon={<DownloadOutlined />} onClick={exportCSV} disabled={!days.length}>CSV</Button>
          <Button icon={<PrinterOutlined />} onClick={printStatement} disabled={!days.length}>{t('billing.print', 'Print')}</Button>
        </Space>
      }
    >
      <Space style={{ marginBottom: 12 }} size="large">
        <Text>{t('billing.monthTotal', 'Month total')}: <strong>{fmtMoney(monthTotal, currency)}</strong></Text>
        {monthTopup > 0 && <Text style={{ color: '#22c55e' }}>{t('billing.monthTopup', 'Topped up')}: +{symbolFor(currency)}{monthTopup.toFixed(2)}</Text>}
        {fromCache && <Text type="warning">{t('billing.cached', 'Showing last saved reading (offline)')}</Text>}
      </Space>

      {loading && !days.length ? (
        <Spin />
      ) : !days.length ? (
        <Empty description={t('billing.noUsage', 'No usage this month')} />
      ) : (
        <Table
          rowKey="date"
          size="small"
          columns={dayColumns}
          dataSource={days}
          pagination={false}
          expandable={{
            onExpand: (expanded, d) => { if (expanded) loadHourly(d.date); },
            expandedRowRender: (d) => {
              const hrs = hourly[d.date];
              if (!hrs) return <Spin size="small" />;
              if (!hrs.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('billing.noUsage', 'No usage')} />;
              return (
                <Table
                  rowKey="hour"
                  size="small"
                  columns={hourColumns}
                  dataSource={hrs}
                  pagination={false}
                  expandable={{
                    onExpand: (ex, hr) => { if (ex) loadModels(d.date, hr.hour); },
                    expandedRowRender: (hr) => {
                      const ms = models[`${d.date}|${hr.hour}`];
                      if (!ms) return <Spin size="small" />;
                      if (!ms.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('billing.noUsage', 'No usage')} />;
                      return <Table rowKey={(r) => `${r.vendor}/${r.model}`} size="small" columns={modelColumns} dataSource={ms} pagination={false} />;
                    },
                  }}
                />
              );
            },
          }}
        />
      )}
    </Card>
  );
};

export default BillingDrilldown;
