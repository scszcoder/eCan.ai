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
billed on resource consumption. This is what makes the whole thing safe: gaming
a business meter can only ever push a customer *back to Tier 0*, which costs
more and is less predictable — never to zero. There is no exploit that makes
work free, because the resource the work consumes is metered by the component
holding the API keys.

That "costs more" is load-bearing, and **it is not true of the code as it
stands** — see §2a.

Two implementation rules follow, and neither is optional:

1. **Meters are emitted only from platform-controlled code paths** — the node
   runtime and certified hook bundles. A customer-editable code node must never
   be able to call `meter.emit`, or it can fabricate or suppress billable events.
2. **Every certified plan keeps a fair-use guard.** If an event's actual resource
   cost exceeds `fair_use_factor ×` its price, the excess bills at Tier 0 rates
   and the plan is flagged for re-review. This covers both accidental margin
   blowups (Q&A prompts have hit 86K tokens) and prompt-stuffing after approval.

## 2a. Tier 0 pricing — 10× markup, applied server-side only

### What the code does today (measured 2026-09-21)

`agent/ec_skills/llm_pricing.py` is the client-side pricing table: USD per 1K
tokens, `(input, output)`, e.g. `deepseek-chat (0.00014, 0.00028)`,
`claude-sonnet-5 (0.002, 0.008)`, unmatched models falling to a `default` of
`(0.01, 0.02)`. `calc_cost()` is `(in/1000)*pin + (out/1000)*pout` and **applies
no markup of any kind** — grep for markup/margin/multiplier across the pricing
module and the billing handler returns nothing. Display converts to RMB at a
fixed `_USD_TO_CNY = 7.25`.

So Tier 0 is currently a **cost pass-through at vendor list price**. Two
consequences: it earns nothing, and the §2 claim that falling back to Tier 0
"costs more" is false — it costs the same as the work itself.

Worse, at list prices ¥0.05/reply does not clear cost. One Feige Q&A turn at the
observed 38–86K prompt range:

| model | 40K in / 500 out | 86K in / 500 out |
|---|---|---|
| deepseek-chat | ¥0.042 (~17% margin) | ¥0.088 — **2× underwater** |
| qwen (falls to `default`) | ¥2.97 — **59×** | ¥6.31 — **126×** |
| claude-sonnet-5 | ¥0.62 — **12×** | ¥1.28 — **26×** |

### Decision: mark Tier 0 up 10×

Approved 2026-09-21. The app is in alpha and Tier 1 is intended to go live the
same day, so the usual objection — that a 10× raise lands on customers with no
cheaper alternative to move to — does not apply here. With Tier 1 live, 10×
makes Tier 0 roughly 8× the price of a ¥0.05 certified reply, which is exactly
what the three-tier model wants: the fallback should be unattractive, and §2's
"costs more" becomes true.

**The markup belongs in `llm_proxy` (private `eCan_lambda` repo), and nowhere
else.** The proxy holds the API keys and debits the balance; it is the only
component whose number a customer actually pays. Express it as a named
configurable factor, not a literal `10`, so it can be tuned per account or
partner without a redeploy.

### Rule: `cost` and `price` stay separate

**`llm_pricing.py` must keep returning TRUE vendor cost — do not mirror the
markup into this repo.** That table feeds `token_tracker` → the local
`token_usage` table → the `llm.getBillingDaily/Hourly` IPC handlers, which
`BILLING_TOPUP_API_CONTRACT.md` §A defines as a **display** surface; the cloud
is authoritative for money. A markup applied here would change what the desktop
*shows* without changing what anyone is *charged*, so the display would disagree
with the real bill by exactly 10× — worse than doing nothing, and the
client-side-papering-over-backend anti-pattern of CLAUDE.md §5.

Keeping cost unmarked is also load-bearing for the rest of this design: the
fair-use guard compares **actual cost** against price (§3.2), `usage_event.
cost_basis` records it per event, and the margin dashboard (job 6.6) needs it.
Bake 10× into `cost_usd` and you lose the ability to measure your own margin.

The client-side follow-up is therefore *not* a markup constant — it is that any
GUI surface showing money the customer pays should render the **server's**
figure (`getBillingHistory`), rather than recomputing locally from a table that
deliberately holds cost.

### Known gap: qwen is not in the pricing table

Vendors present: `openai`, `anthropic`, `deepseek`, `google`, `default`. The CN
stack runs **qwen** (3.6/3.7/3.8) heavily, and every qwen call currently falls to
`default` `(0.01, 0.02)` — roughly GPT-4-turbo rates and nowhere near qwen's real
price. Whatever the markup, the underlying number recorded against qwen usage is
wrong today, in the expensive direction. Needs real qwen/dashscope rates before
Tier 0 pricing can be trusted for the CN fleet.

## 3. Charge plans for custom and copied skills

A **charge plan** binds a skill to a set of meters and prices. It is proposed by
an LLM review and approved by a human (first-party/marketplace) or auto-approved
under a no-loss guard (private skills).

**Billing shape** — a hash over the *billing-relevant surface only*:
node types and topology, declared meter emit points, tool/permission grants,
hook bundles, model tier(s), and whether a code node exists. Deliberately **not**
the free-text prompt wording.

- Copy a certified template, reword the prompts → shape unchanged → the
  plan **inherits**. This is the common case and it works with no review.
- Add a node, tool, model or code node → shape changes → the skill bills at
  **Tier 0** until a new plan is approved.

Prompt wording does change token cost, and the billing shape deliberately ignores
it — that is what the fair-use guard is for. Keep the two jobs separate: the
shape answers *"is this the same thing we priced?"*, the fair-use guard answers
*"is it still economic?"*.

("Shape" and never "fingerprint": 指纹浏览器 owns that word in this product —
see the terminology rule recorded with the site-shape work.)

The LLM reviewer's output is advisory and always recorded (model, version,
prompt hash, verdict, projected cost per event) so a price can be audited later.

### 3.1 When a review runs — demotion is derived, promotion is triggered

**Do not store a plan status that every save has to maintain.** Store the
approved plan's `billing_shape_hash` and derive the rest:

```
effective_tier =
    plan.tier   if plan.status == 'approved'
                and shape(skill_version) == plan.billing_shape_hash
    else 0
```

Both halves are needed and they catch different things: the **status** catches a
plan the fair-use sweep suspended (job 6.5 — the shape is unchanged there, so
the hash comparison alone would keep saying "approved"), and the **hash**
catches a skill edited after approval (no job runs there, so status alone would
be stale). Either one on its own leaves a hole.

Rating does that comparison when it prices an event; the skill editor's 计费 tab
does it when it renders. No save hook, no event storm, no write amplification,
and no way for a missed trigger to leave a stale `approved` on a skill that has
changed underneath it. (`save_agent_skill` may be an autosave — anything writing
status on save would flicker mid-edit and hammer the DB.)

The property that matters: **demotion to Tier 0 is instant and automatic; only
promotion needs a review.** Billing is never blocked on an LLM. The worst case
for a customer mid-edit is that they pay usage-based rates for a while — never
that we lose money while a review queue drains.

Promotion is what gets triggered, at the moments pricing actually matters:

| Trigger | Why |
|---|---|
| Publish to marketplace | A public template needs a published price |
| First run of a new shape (a task binds this skill version and executes) | The real "this is about to cost money" moment |
| Manual 申请审核 from the 计费 tab | Customer wants per-result pricing back now |
| `subscribe_to_skill` (copying a template) | Shape matches the parent → **inherit, no review at all** |

**Not on save.** Someone rearranging nodes changes the shape 20× in an hour and
19 of those are intermediate states nobody will ever run. The hash is recomputed
on save because it is a pure function costing microseconds; the LLM runs only
when a new shape is about to earn money. Expected volume is roughly **one review
per skill version that actually gets deployed** — iterating in the editor is free.

### 3.2 Re-validation is evidence-driven, not calendar-driven

A skill whose shape never changes still drifts economically: prompt wording grows
(deliberately outside the shape), model prices move, a site change makes runs
longer. The **fair-use guard is the continuous check** — it runs on every rated
event comparing actual cost against price, which is a per-event audit and
strictly better than "re-review every 90 days". A skill only returns for review
when the data says it has gone uneconomic.

Calendar triggers stay rare and narrow: a price-book version change (re-run the
margin *projection*, not the skill review), and an annual audit for
marketplace-published plans, where a price is published to strangers.

```
every save        -> recompute shape hash (free, no LLM, no status write)
publish / 1st run -> LLM review, once per shape that gets used
every rated event -> fair-use guard (continuous economic check)
price-book change -> re-project margins
annually          -> audit marketplace-published plans only
```

**Accepted trade-off:** "first run of a new shape" means the first run of an
edited skill bills at Tier 0 while the review happens asynchronously, so a
customer can see one usage-priced turn before per-result pricing resumes. We
accept it and say so in the 计费 tab. Deferring the promotion to the next period
boundary would avoid a mid-run price change but would make the tab lie about
what the current turn costs.

---

## 4. Schema

Mirror the names exactly on both backends. Local SQLite mirrors `usage_meters`,
`usage_event` and `usage_period_total` for offline display and replay; the
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
  billing_shape_hash text,    -- see §3; the shape this plan was approved FOR
  -- Only states a human/job actually sets. 'needs_review' is deliberately NOT
  -- here: a shape mismatch is DERIVED at read time (§3.1), never written on
  -- save, so a missed trigger cannot leave a stale 'approved' behind.
  status             text,     -- 'draft' | 'approved' | 'suspended'
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

-- 4.3 Price book — versioned, effective-dated, NEVER edited in place.
-- One price per meter. It does NOT vary by plan: both plans bill the same
-- ¥0.05 reply; they differ only by the monthly minimum in 4.4.
price_book(version PK, effective_from timestamptz, currency, partner_id)
price_book_item(
  version, scenario_code, meter_code,
  unit_price_minor   bigint,
  PRIMARY KEY (version, scenario_code, meter_code)
)
account_price_override(account_id, scenario_code, meter_code,
                       unit_price_minor, effective_from)

-- 4.4 Plans & entitlement.
-- The ONLY structural difference between the two live plans is the monthly
-- minimum: subscription 6800, additional/PAYG 0.  Everything else — how an
-- event is priced, how the balance is drawn down — is identical, which is why
-- there is no per-meter quota anywhere in this schema.
plan(
  plan_id PK, plan_type text,     -- 'payg' | 'subscription'
  currency,
  minimum_charge_minor bigint,    -- 保底: billed even if usage is less (6800 | 0)
  minimum_topup_minor  bigint,    -- 50 for PAYG's ¥0.50 floor
  billing_period text, partner_id,
  version, effective_from
)
account_plan(account_id, plan_id, status,
             current_period_start, current_period_end, auto_renew)
-- Money, not units: the minimum is a spend floor across every meter, so a
-- customer running replies AND labels draws the same pot.  Makes the
-- "¥41.30 of ¥68 used" display O(1) and needs no per-meter quota.
usage_period_total(account_id, period_start,
                   charged_minor bigint, minimum_applied bool)

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
  period { minimum_charge charged_so_far remaining_to_minimum }  # subscription only
} }

query { getSkillChargePlan(input:{ skill_id, skill_version }) {
  status tier billing_shape_hash fair_use_factor
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

## 5a. How the two live plans actually bill

Both plans bill **the tasks the customer actually runs**, at the same per-meter
price. The subscription adds a monthly floor:

```
月度应付 = max(minimum_charge, Σ rated usage in the period)
```

- **订阅套餐 / Subscription — ¥68/month minimum.** The ¥68 is collected up front
  by the existing `createPaymentOrder(purpose:'subscription')` flow and credited
  to the balance, then **consumed by usage** at rate-card prices. Use ¥41.30 of
  it and you are still charged ¥68 — that is what "minimum" means, and the
  remainder does **not** roll over. Use ¥90 and the extra ¥22 draws from balance.
- **附加计划 / Additional (PAYG) — no minimum.** Top up (≥ ¥0.50), usage draws
  the balance down as it happens, nothing is forfeited.

It is a **money floor, not a bundled quantity.** "¥68 includes N replies" would
have to be re-answered for every new meter (labels, returns, disputes) and would
strand a customer who ran a different mix than we guessed. A money floor prices
any mix correctly on day one, which is the whole reason the meter template
exists.

## 6. Jobs

1. **Rating** — `usage_event(status=pending)` → resolve the price in effect
   **at `occurred_at`** → write a `charge` row → add to
   `usage_period_total.charged_minor` → mark `rated`. Idempotent per `event_id`.
1a. **Minimum true-up at period close** — if
   `charged_minor < plan.minimum_charge_minor`, post ONE additional `charge` row
   for the difference (description: 保底差额 / minimum commitment) and set
   `minimum_applied`. Idempotent per `(account_id, period_start)` — this job
   double-charging is the worst bug in the system, so key it accordingly.
2. **Price resolution order** — `account_price_override` → partner book →
   platform list. Record the resolved version and unit price **on the charge row**
   so an old invoice stays reproducible after a price change.
3. **Period rollover** — open the next `account_plan` period, reset counters,
   run the minimum true-up (6.1a) before the period is closed.
4. **Reconciliation** — `usage_event_intent` with no matching confirmed event
   after 24h → report, **never bill** (a failed delivery is never billed).
5. **Fair-use sweep** — events whose `cost_basis` exceeds
   `fair_use_factor × unit_price` → bill the excess at Tier 0 and set the plan
   `status = 'suspended'` (a real stored state: the shape still matches, so the
   derived check in §3.1 would keep saying "approved"). This sweep IS the
   continuous re-validation — there is no calendar re-review job.
6. **Margin dashboard** (internal) — cost per event per meter, and
   **failed-delivery cost per month**. Since failures are never billed, that is
   pure loss and also the best regression alarm the send path will ever have.

---

## 7. TODO, in dependency order

### Phase A0 — Tier 0 markup (§2a; independent of everything below)
- [ ] Apply the 10x markup in `llm_proxy` when debiting balance. Named
      configurable factor, not a literal — tunable per account/partner later.
- [ ] Do NOT mirror the markup into `agent/ec_skills/llm_pricing.py`; that table
      stays TRUE vendor cost, because fair-use, `cost_basis` and the margin
      dashboard all compare against it.
- [ ] Add real qwen / dashscope rates to the pricing table — CN's primary models
      currently fall to the `default` (0.01, 0.02) and are mispriced.
- [ ] Client follow-up: money the customer pays renders the SERVER figure
      (`getBillingHistory`), never a local recompute.
- [ ] Sanity-check the fixed `_USD_TO_CNY = 7.25` display rate while here.

### Phase A — metering, shadow mode (no money moves)
- [ ] Create `usage_meters`, `usage_event`, `usage_period_total` on CN TCB **and** AWS, identical field names.
- [ ] `reportUsageEvents` mutation, idempotent on `idempotency_key`, batch-capable.
- [ ] Seed the catalog with `cs_chat.message_replied`, including the written
      definition of what does not count (placeholders, retries, undelivered sends).
- [ ] `getUsageSummary` for the client's display.
- [ ] Client emits at the delivery-confirmed moment with key
      `feige:{store}:{talk_id}:{source_msg_id}`; keep billing tokens.
- [ ] **Run one full billing month in shadow.** Compare business-metric totals
      against token totals per customer before anything flips.

### Phase B — pricing & rating
- [ ] `plan`, `account_plan`, `price_book`, `price_book_item`, `account_price_override`, `usage_period_total`.
- [ ] Seed the two live plans: subscription `minimum_charge_minor = 6800`,
      additional `minimum_charge_minor = 0, minimum_topup_minor = 50`.
- [ ] Seed `price_book_item`: `cs_chat.message_replied = 5` (¥0.05).
- [ ] Rating job + charge rows into `billing_entries` with the full column set.
- [ ] **Minimum true-up at period close**, idempotent per `(account_id, period_start)`.
- [ ] `partner` table + `partner_id` on accounts; markup default 0.
- [ ] Period rollover; confirm the up-front ¥68 credit is consumed, not doubled.

### Phase C — custom-skill safety
- [ ] `skill_charge_plan` / `_item`; `billing_shape_hash` as a pure function of
      the billing-relevant surface (§3), recomputed on `save_agent_skill` /
      `new_agent_skill`. Hash only — **no status write on save**.
- [ ] Derive the effective tier by comparing current shape to the approved
      plan's hash (§3.1), at rating time and at 计费-tab render time. Do NOT
      add a stored status that saves must keep in sync.
- [ ] Inheritance on copy (`subscribe_to_skill`): same shape → inherit the
      parent's plan with **no review**; changed → Tier 0 until approved.
- [ ] Review triggers, and only these: marketplace publish, first run of a new
      shape, manual `requestSkillChargeReview`. Never on save.
- [ ] LLM review pipeline producing a **draft** plan + `review_evidence`.
- [ ] Auto-approve only under the no-loss guard (price ≥ projected cost × margin).
- [ ] Fair-use sweep + auto-suspend to Tier 0 — this is the continuous
      re-validation (§3.2); do not add a calendar re-review job.
- [ ] Re-project margins on a price-book version change; annual audit job
      scoped to marketplace-published plans only.
- [ ] Enforce: `meter.emit` reachable **only** from platform node runtime and
      certified hook bundles, never a customer code node.
- [ ] `getSkillChargePlan` / `requestSkillChargeReview` for the skill-editor tab;
      the tab must state that the first run of an edited skill is usage-priced
      while the review runs (§3.2 trade-off).

### Phase D — cutover
- [ ] Flip one willing customer to Tier 1; keep Tier 0 shadow running alongside.
- [ ] Reversal path (refund an event) exercised end to end.
- [ ] Second scenario (`ebay_aftersales`) to prove the template generalises with
      **zero platform changes**. If it needs any, the template is wrong.

---

## 8. Open commercial inputs

Tracked in `docs/OPEN_ITEMS.md` → 🔵 Planned work → "Open commercial decisions
for business-metric billing"; keep the two in sync when one is answered.

Settled: the ¥68 is a **monthly minimum charge**, not a bundled quantity (§5a),
and `cs_chat.message_replied` is ¥0.05. Still open, none of them blocking Phase A:

- Per-meter list prices beyond `cs_chat.message_replied` — needed before the
  second scenario (`ebay_aftersales`) can leave shadow mode.
- Whether the subscription auto-renews, and how cancellation mid-period
  interacts with the minimum (pro-rate, or charge the full floor?).
- Refund policy wording for reversals.
- Whether an unused balance on the PAYG plan expires.
