# Billing & Top-up API Contract

_Last updated: 2026-09-06._

Two surfaces:

- **Local IPC** — usage stats and cost. Read from the local `token_usage`
  SQLite table; **shipped** in `gui/ipc/w2p_handlers/llm_token_usage_handler.py`.
  The frontend only displays these; it never recomputes cost.
- **Cloud GraphQL** — server-authoritative billing history, coupon validation,
  and top-up crediting. Built on **both** CN TCB and AWS AppSync with
  **identical field names** (CLAUDE.md §5). camelCase operations, snake_case
  fields. **Money is integer minor units** (分 for CNY, cents for USD).

---

## A. Local IPC — usage drill-down (shipped)

Cost is authoritative from the DB (`cost_usd`, computed at ingest by
`token_tracker`). `cost` is the display-currency value (RMB on CN builds via a
fixed 7.25, else USD). The client sends `tz_offset_minutes` (JS
`-new Date().getTimezoneOffset()`, minutes east of UTC) so day/hour buckets are
local, not the stored UTC.

```
llm.getBillingDaily   { year:int, month:int, tz_offset_minutes:int }
 → { currency:"CNY"|"USD", year, month,
     days:[ { date:"YYYY-MM-DD", input_tokens:int, output_tokens:int,
              total_tokens:int, cost:number, cost_usd:number } ] }   // days with usage

llm.getBillingHourly  { date:"YYYY-MM-DD", tz_offset_minutes:int }
 → { currency, date,
     hours:[ { hour:0..23, input_tokens, output_tokens, total_tokens,
               cost, cost_usd } ] }                                  // hours with usage

llm.getBillingHourModels { date:"YYYY-MM-DD", hour:0..23, tz_offset_minutes:int }
 → { currency, date, hour,
     rows:[ { vendor:str, model:str, input_tokens:int, output_tokens:int,
              input_cost:number, output_cost:number, total_cost:number } ] }
```

`input_cost` + `output_cost` == `total_cost` always: the stored total is
apportioned by tokens × per-direction price (ratio only; the total is never
recomputed). All three costs are in the display currency.

The frontend merges cloud top-ups (below) into the day rows by local date.

---

## B. Cloud GraphQL — server-authoritative (to build on CN + AWS)

### 1. Billing / top-up history

Client buckets `entries` by local day to render top-ups alongside the usage
day rows.

```graphql
query { getBillingHistory(input:{ start_date:"YYYY-MM-DD", end_date:"YYYY-MM-DD" }) {
  currency
  balance                 # current fund, minor units
  entries {
    entry_id
    ts                    # ISO8601 UTC
    type                  # "topup" | "charge" | "refund" | "adjustment" | "coupon_credit"
    amount                # signed minor units (topup +, charge -)
    currency
    status                # "success" | "pending" | "failed"
    order_id              # nullable
    coupon_code           # nullable
    description
  }
} }
```

### 2. Coupon preview (read-only, no side effects)

Advisory only — never trusted for the actual charge. Returns both a price
discount and a bonus credit so it covers either coupon style.

```graphql
query { validateCoupon(input:{ code:"SAVE20", amount:5000, currency:"CNY", purpose:"topup" }) {
  valid
  code
  discount_type           # "percent" | "fixed" | "bonus"
  discount_value          # percent: 0..100 ; fixed/bonus: minor units
  pay_amount              # what the user pays, minor units
  credit_amount           # what the balance receives, minor units
  currency
  reason                  # why invalid, when valid=false
  min_amount              # nullable, minor units
  expires_at              # nullable ISO8601
} }
```

- **Discount coupon**: `pay_amount < amount`, `credit_amount == pay_amount`.
- **Bonus coupon**: `pay_amount == amount`, `credit_amount > amount`.

### 3. Create payment order with coupon

Extends the existing `create_payment_order`. This is the **authoritative**
coupon validation.

```graphql
mutation { createPaymentOrder(input:{ amount:5000, currency:"CNY", purpose:"topup", coupon_code:"SAVE20" }) {
  order_id
  out_trade_no            # used by the pay page + notify webhook
  original_amount
  pay_amount              # charge the user this
  credit_amount           # credit the balance this on success
  discount
  coupon_applied          # bool
  coupon_code
  currency
} }
```

### 4. Redemption on settle (no client call)

The notify/credit webhook credits `credit_amount` and records the redemption
**idempotently, keyed on `out_trade_no`**, enforcing per-user and total-use
limits server-side, so retries can't double-spend a coupon.

---

## Desktop top-up wiring

CN desktop already creates the order before showing the QR. With coupons:
`payment_topup` calls `createPaymentOrder(amount, coupon_code)`, gets
`pay_amount` + `out_trade_no`, then opens the pay page for that order. Intl uses
Stripe promotion codes at checkout, so `validateCoupon` and the coupon field map
to a Stripe promo code and no `createPaymentOrder` is needed there.

## Non-negotiables

- Server validates the coupon at order creation, every time; the preview is
  never trusted for the charge.
- Identical field names on CN and AWS; no per-backend renaming.
- Idempotent redemption keyed on `out_trade_no`; per-user + total caps server-side.
- Minor-unit integers for all money.
