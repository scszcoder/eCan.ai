import { dailyRows, summarizeMonth, HistoryEntry } from './billingSummary';

const charge = (over: Partial<HistoryEntry>): HistoryEntry => ({
  entry_id: Math.random().toString(36), ts: '2026-10-04T10:00:00Z', type: 'charge',
  amount: -5, currency: 'CNY', status: 'success', ...over,
});

describe('summarizeMonth', () => {
  it('counts replies whether billed one row each or batched with quantity', () => {
    const s = summarizeMonth([
      charge({}), charge({ category: 'per_reply' }),
      charge({ category: 'cs_reply', quantity: 40, amount: -200 }),
    ]);
    expect(s.replies).toBe(42);
    expect(s.replyAmount).toBe(210);
    expect(s.unitPrice).toBe(5);
    expect(s.others).toEqual([]);
    expect(s.totalCharged).toBe(210);
  });

  it('keeps every other service as one line, largest first, and adds it to the total', () => {
    const s = summarizeMonth([
      charge({ quantity: 10, amount: -50 }),
      charge({ category: 'media_generation', amount: -120 }),
      charge({ category: 'knowledge_base', amount: -3 }),
      charge({ category: 'knowledge_base', amount: -4 }),
    ]);
    expect(s.others).toEqual([{ category: 'media_generation', amount: 120 }, { category: 'knowledge_base', amount: 7 }]);
    expect(s.totalCharged).toBe(50 + 120 + 7);
  });

  it('credits top-ups, ignores failed ones, and treats a debit adjustment as money taken', () => {
    const s = summarizeMonth([
      { ...charge({ type: 'topup', amount: 10000 }) },
      { ...charge({ type: 'topup', amount: 5000, status: 'failed' }) },
      { ...charge({ type: 'adjustment', amount: -6800 }) },
    ]);
    expect(s.totalCredited).toBe(10000);
    expect(s.others).toEqual([{ category: 'adjustment', amount: 6800 }]);
    expect(s.totalCharged).toBe(6800);
  });

  it('reports no single unit price when reply rows disagree', () => {
    expect(summarizeMonth([charge({ amount: -5 }), charge({ amount: -6 })]).unitPrice).toBeNull();
  });
});

describe('dailyRows', () => {
  it('groups by day, newest first, replies apart from everything else', () => {
    const rows = dailyRows([
      charge({ ts: '2026-10-03T09:00:00Z' }),
      charge({ ts: '2026-10-04T09:00:00Z', quantity: 3, amount: -15 }),
      charge({ ts: '2026-10-04T11:00:00Z', category: 'llm_usage', amount: -2 }),
      charge({ ts: '2026-10-04T12:00:00Z', type: 'topup', amount: 1000 }),
    ], (ts) => ts.slice(0, 10));
    expect(rows.map((r) => [r.date, r.replies, r.replyAmount, r.otherAmount, r.total])).toEqual([
      ['2026-10-04', 3, 15, 2, 17],
      ['2026-10-03', 1, 5, 0, 5],
    ]);
  });
});
