/**
 * Turns the server's billing ledger (billing_history entries) into what a
 * seller actually wants to know: how many replies we answered, what that cost,
 * and one plain line for anything else they used.
 *
 * Everything here is derived from the SERVER's charge rows, never from local
 * counts, so the page always matches what the balance was debited.
 *
 * A per-reply charge row may arrive as one row per reply, or as one row for a
 * batch with ``quantity`` set; both count the same.
 */

export type Currency = 'CNY' | 'USD';

export interface HistoryEntry {
  entry_id: string;
  ts: string;
  type: string; // topup | charge | refund | adjustment | coupon_credit
  amount: number; // minor units (fen / cents), signed
  currency: Currency;
  status: string;
  coupon_code?: string | null;
  description?: string;
  /** charge rows: cs_reply / per_reply (or none) | llm_usage | knowledge_base | media_generation */
  category?: string | null;
  /** charge rows: how many billed units this row covers (replies for cs_reply); 1 when absent */
  quantity?: number | null;
}

/** Charge categories that mean "customer-service replies". No category = per-reply (contract). */
const REPLY_CATEGORIES = new Set(['', 'cs_reply', 'per_reply']);

export const isReplyCharge = (e: HistoryEntry): boolean =>
  e.type === 'charge' && REPLY_CATEGORIES.has(String(e.category || ''));

export interface OtherLine {
  category: string;
  amount: number; // minor units, positive = charged
}

export interface MonthSummary {
  replies: number;
  replyAmount: number; // minor units, positive
  /** minor units per reply, when every reply row agrees (else null) */
  unitPrice: number | null;
  others: OtherLine[];
  totalCharged: number; // minor units, positive (all charges, incl. replies)
  totalCredited: number; // minor units, positive (successful top-ups, coupons, refunds, credit adjustments)
}

export function summarizeMonth(entries: HistoryEntry[]): MonthSummary {
  let replies = 0;
  let replyAmount = 0;
  const prices = new Set<number>();
  const others = new Map<string, number>();
  let totalCharged = 0;
  let totalCredited = 0;

  for (const e of entries) {
    if (e.type === 'charge') {
      const amt = Math.abs(e.amount);
      totalCharged += amt;
      if (isReplyCharge(e)) {
        const q = Number(e.quantity) > 0 ? Number(e.quantity) : 1;
        replies += q;
        replyAmount += amt;
        prices.add(Math.round((amt / q) * 1000) / 1000);
      } else {
        const cat = String(e.category);
        others.set(cat, (others.get(cat) || 0) + amt);
      }
    } else if (e.status === 'success') {
      if (e.amount >= 0) {
        totalCredited += e.amount;
      } else {
        // A debit that is not a usage charge (e.g. a monthly-minimum top-up
        // adjustment): still money taken, so it is a line of its own.
        totalCharged += -e.amount;
        others.set(e.type, (others.get(e.type) || 0) - e.amount);
      }
    }
  }

  return {
    replies,
    replyAmount,
    unitPrice: prices.size === 1 ? [...prices][0] : null,
    others: [...others.entries()]
      .filter(([, amount]) => amount > 0)
      .map(([category, amount]) => ({ category, amount }))
      .sort((a, b) => b.amount - a.amount),
    totalCharged,
    totalCredited,
  };
}

export interface DayRow {
  key: string;
  date: string; // YYYY-MM-DD
  replies: number;
  replyAmount: number;
  otherAmount: number;
  total: number;
}

/** One row per day, newest first: replies and their cost, everything else as one sum. */
export function dailyRows(entries: HistoryEntry[], dayOf: (ts: string) => string): DayRow[] {
  const byDay = new Map<string, DayRow>();
  for (const e of entries) {
    const isDebit = e.type === 'charge' || (e.status === 'success' && e.amount < 0);
    if (!isDebit) continue;
    const date = dayOf(e.ts);
    const row = byDay.get(date) || { key: date, date, replies: 0, replyAmount: 0, otherAmount: 0, total: 0 };
    const amt = Math.abs(e.amount);
    if (isReplyCharge(e)) {
      row.replies += Number(e.quantity) > 0 ? Number(e.quantity) : 1;
      row.replyAmount += amt;
    } else {
      row.otherAmount += amt;
    }
    row.total += amt;
    byDay.set(date, row);
  }
  return [...byDay.values()].sort((a, b) => (a.date < b.date ? 1 : -1));
}
