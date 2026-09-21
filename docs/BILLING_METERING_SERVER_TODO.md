# Business-Metric Billing — Server-Side Summary & TODO

_Drafted 2026-09-21. Companion to `BILLING_TOPUP_API_CONTRACT.md`, which already
defines balance, top-up, coupons and the `billing_entries` ledger this design
writes into. Nothing here replaces that contract — business charges land in the
**same** ledger as `type: "charge"` rows._

Backend work happens in the private `eCan_lambda` repo and must ship with
**identical field names on CN TCB and AWS AppSync** (CLAUDE.md §5). camelCase
operations, snake_case fields, money in integer minor units (分 / cents).

---

## 1. Why this exists

Today customers are billed on raw LLM tokens. That is hard to explain and
expensive to educate customers on. We want to bill **business outcomes** —
¥0.05 per customer-service reply delivered, per shipping label printed, per
return handled — so the invoice reads like the customer's own business.

## 2. The trust model (read this before designing any table)

Customers can copy a public template skill and modify it, or author a brand-new
skill with the skill-editor agent. **A customer-authored artifact can therefore
never be the source of billing truth.** Any design where a skill declares its
own price is self-dealing, and an LLM reviewer is a heuristic, not a security
boundary — obfuscating a prompt past a reviewer is cheap.

So billing rests on what the **server** observes, in three tiers:

| Tier | What it bills | Trust | Applies to |
|---|---|---|---|
| **0 — Resource metering** | LLM tokens via `llm_proxy` (holds the API keys), cloud tool calls | Server-observed, not gameable | **Every skill, always** |
| **1 — Certified business pricing** | Declared meters at rate-card prices | Granted per skill after review | Skills with an approved charge plan |
| **2 — Marketplace / partner** | Tier 1 + revenue share | As Tier 1 | Published/partner skills |

**Tier 0 is the floor and the default.** A skill with no approved charge plan is
billed exactly as it is today. This is what makes the whole thing safe: gaming a
business meter can only ever push a customer *back to Tier 0*, which costs more
and is less predictable — never to zero. There is no exploit that makes work
free, because the resource the work consumes is metered by the component holding
the API keys.

Two implementation rules follow, and neither is optional:

1. **Meters are emitted only from platform-controlled code paths** — the node
   runtime and certified hook bundles. A customer-editable code node must never
   be able to call `meter.emit`, or it can fabricate or suppress billable events.
2. **Every certified plan keeps a fair-use guard.** If an event's actual resource
   cost exceeds `fair_use_factor ×` its price, the excess bills at Tier 0 rates
   and the plan is flagged for re-review. This covers both accidental margin
   blowups (Q&A prompts have hit 86K tokens) and prompt-stuffing after approval.

## 3. Charge plans for custom and copied skills

A **charge plan** binds a skill to a set of meters and prices. It is proposed by
an LLM review and approved by a human (first-party/marketplace) or auto-approved
under a no-loss guard (private skills).

**Billing fingerprint** — a hash over the *billing-relevant surface only*:
node types and topology, declared meter emit points, tool/permission grants,
hook bundles, model tier(s), and whether a code node exists. Deliberately **not**
the free-text prompt wording.

- Copy a certified template, reword the prompts → fingerprint unchanged → the
  plan **inherits**. This is the common case and it works with no review.
- Add a node, tool, model or code node → fingerprint changes → plan becomes
  `needs_review`, and the skill bills at **Tier 0** until re-approved.

Prompt wording does change token cost, and the fingerprint deliberately ignores
it — that is what the fair-use guard is for. Keep the two jobs separate:
fingerprint answers *"is this the same billing shape?"*, fair-use answers
*"is it still economic?"*.

The LLM reviewer's output is advisory and always recorded (model, version,
prompt hash, verdict, projected cost per event) so a price can be audited later.

---

## 4. Schema

Mirror the names exactly on both backends. Local SQLite mirrors `usage_meters`,
`usage_events` and `usage_period_counter` for offline display and replay; the
cloud is authoritative for money.

```sql
-- 4.1 Meter catalog (seeded from bundle/skill manifests, not user-writable)
usage_meters(
  scenario_code      text,     -- 'cs_chat', 'ebay_aftersales'
  meter_code         text,     -- 'message_replied', 'label_printed'
  display_name_zh    text,
  display_name_en    text,
  unit               text,     -- '条', '张', '单'
  billable_definition text,    -- what counts, and explicitly what does NOT
  PRIMARY KEY (scenario_code, meter_code)
)

-- 4.2 Charge plan per skill (the certification record)
skill_charge_plan(
  plan_id            uuid PK,
  skill_id           text,
  skill_version      text,
  billing_fingerprint text,    -- see §3
  status             text,     -- 'draft' | 'approved' | 'needs_review' | 'suspended'
  tier               int,      -- 0 | 1 | 2
  derived_from_plan_id uuid,   -- set when copied from a template
  fair_use_factor    numeric,  -- default 3.0
  reviewed_by        text,     -- 'llm:<model>@<version>' | '<human>'
  review_evidence    jsonb,    -- proposal, projected cost/event, risk notes
  approved_by        text,
  approved_at        timestamptz,
  created_at         timestamptz
)
skill_charge_plan_item(
  plan_id, scenario_code, meter_code,
  unit_price_minor   bigint,
  PRIMARY KEY (plan_id, scenario_code, meter_code)
)

-- 4.3 Price book — versioned, effective-dated, NEVER edited in place
price_book(version PK, effective_from timestamptz, currency, partner_id)
price_book_item(
  version, plan_id, scenario_code, meter_code,
  included_quantity  bigint,   -- 0 for PAYG
  unit_price_minor   bigint,   -- PAYG: the price; subscription: the OVERAGE price
  tier_json          jsonb,    -- optional volume tiers
  PRIMARY KEY (version, plan_id, scenario_code, meter_code)
)
account_price_override(account_id, scenario_code, meter_code,
                       unit_price_minor, effective_from)

-- 4.4 Plans & entitlement
plan(
  plan_id PK, plan_type text,  -- 'payg' | 'subscription'
  currency, base_fee_minor bigint, billing_period text, partner_id,
  version, effective_from
)
account_plan(account_id, plan_id, status,
             current_period_start, current_period_end, auto_renew)
usage_period_counter(account_id, period_start, scenario_code, meter_code,
                     quantity_used bigint)   -- makes "3,412 / 5,000" O(1)

-- 4.5 The event ledger — append-only
usage_event(
  event_id           uuid PK,
  idempotency_key    text UNIQUE NOT NULL,   -- the whole design rests on this
  account_id, store_id, agent_id, task_id, skill_id, vehicle_id,
  scenario_code, meter_code,
  quantity           int DEFAULT 1,
  occurred_at        timestamptz,
  reported_at        timestamptz,
  status             text,   -- 'pending'|'rated'|'rejected'|'reversed'
  evidence           jsonb,  -- talk_id/msg_id, order_id, tracking_no, dispute_id
  cost_basis         jsonb,  -- tokens + model actually consumed
  source             text    -- 'client'|'proxy'|'backend'
)
usage_event_intent(     -- proxy-side shadow, reconciliation only, never billed
  idempotency_key, account_id, skill_id, meter_code, observed_at, cost_basis
)

-- 4.6 Reseller
partner(partner_id PK, name, default_markup_pct DEFAULT 0, revenue_share_pct)
-- accounts gain: partner_id (nullable)
```

**Charge rows** (into the existing `billing_entries`) must carry, from day one:
`list_amount_minor`, `billed_amount_minor`, `partner_markup_minor`,
`price_book_version`, `unit_price_minor`, `usage_event_id`. With the default 0
markup, list == billed and nothing looks different — but retrofitting a markup
dimension into a live money table later is a month of work.

---

## 5. API

```graphql
# Client → cloud. MUST be idempotent on idempotency_key; re-posting a key
# returns the original result and never double-charges.
mutation { reportUsageEvents(input:{ events:[UsageEventInput!]! }) {
  accepted    # count
  duplicates  # count, already-known keys — a success, not an error
  rejected { idempotency_key reason }
} }

query { getUsageSummary(input:{ start_date, end_date, tz_offset_minutes }) {
  currency
  days { date  meters { scenario_code meter_code quantity cost } }
  period { included_quantity quantity_used remaining }   # subscription only
} }

query { getSkillChargePlan(input:{ skill_id, skill_version }) {
  status tier billing_fingerprint fair_use_factor
  items { scenario_code meter_code unit_price_minor }
  review { reviewed_by reviewed_at projected_cost_per_event_minor notes }
} }

mutation { requestSkillChargeReview(input:{ skill_id, skill_version }) {
  plan_id status
} }
```

`getBillingHistory`, `validateCoupon` and `createPaymentOrder` are unchanged —
see `BILLING_TOPUP_API_CONTRACT.md`.

---

## 6. Jobs

1. **Rating** — `usage_event(status=pending)` → resolve plan version in effect
   **at `occurred_at`** → consume `included_quantity` via `usage_period_counter`
   → write a `charge` row → mark `rated`. Must be idempotent per `event_id`.
2. **Price resolution order** — `account_price_override` → partner book →
   platform list. Record the resolved version and unit price **on the charge row**
   so an old invoice stays reproducible after a price change.
3. **Period rollover** — open the next `account_plan` period, reset counters,
   charge `base_fee_minor` for subscriptions.
4. **Reconciliation** — `usage_event_intent` with no matching confirmed event
   after 24h → report, **never bill** (a failed delivery is never billed).
5. **Fair-use sweep** — events whose `cost_basis` exceeds
   `fair_use_factor × unit_price` → bill the excess at Tier 0 and flag the plan
   `needs_review`.
6. **Margin dashboard** (internal) — cost per event per meter, and
   **failed-delivery cost per month**. Since failures are never billed, that is
   pure loss and also the best regression alarm the send path will ever have.

---

## 7. TODO, in dependency order

### Phase A — metering, shadow mode (no money moves)
- [ ] Create `usage_meters`, `usage_event`, `usage_period_counter` on CN TCB **and** AWS, identical field names.
- [ ] `reportUsageEvents` mutation, idempotent on `idempotency_key`, batch-capable.
- [ ] Seed the catalog with `cs_chat.message_replied`, including the written
      definition of what does not count (placeholders, retries, undelivered sends).
- [ ] `getUsageSummary` for the client's display.
- [ ] Client emits at the delivery-confirmed moment with key
      `feige:{store}:{talk_id}:{source_msg_id}`; keep billing tokens.
- [ ] **Run one full billing month in shadow.** Compare business-metric totals
      against token totals per customer before anything flips.

### Phase B — pricing & rating
- [ ] `plan`, `account_plan`, `price_book`, `price_book_item`, `account_price_override`.
- [ ] Seed the two live plans (§8) once their terms are confirmed.
- [ ] Rating job + charge rows into `billing_entries` with the full column set.
- [ ] `partner` table + `partner_id` on accounts; markup default 0.
- [ ] Period rollover + subscription base-fee charge.

### Phase C — custom-skill safety
- [ ] `skill_charge_plan` / `_item`; compute and store `billing_fingerprint`.
- [ ] Inheritance on copy: same fingerprint → inherit; changed → `needs_review` + Tier 0.
- [ ] LLM review pipeline producing a **draft** plan + `review_evidence`.
- [ ] Auto-approve only under the no-loss guard (price ≥ projected cost × margin).
- [ ] Fair-use sweep + auto-suspend to Tier 0.
- [ ] Enforce: `meter.emit` reachable **only** from platform node runtime and
      certified hook bundles, never a customer code node.
- [ ] `getSkillChargePlan` / `requestSkillChargeReview` for the skill-editor tab.

### Phase D — cutover
- [ ] Flip one willing customer to Tier 1; keep Tier 0 shadow running alongside.
- [ ] Reversal path (refund an event) exercised end to end.
- [ ] Second scenario (`ebay_aftersales`) to prove the template generalises with
      **zero platform changes**. If it needs any, the template is wrong.

---

## 8. Open commercial inputs needed before Phase B

These are decisions, not engineering, and the plan explanation page is blocked
on the first one:

- **What the ¥68/month subscription includes** — included quantity per meter,
  which features, and whether it also draws down balance for overage.
- Per-meter list prices beyond `cs_chat.message_replied` (¥0.05).
- Whether the subscription auto-renews and how cancellation is handled.
- Refund policy wording for reversals.
