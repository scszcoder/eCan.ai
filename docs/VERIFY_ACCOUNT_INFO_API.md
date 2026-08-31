# verify_account_info — server-side API proposal (CN CloudBase)

**Status:** PROPOSED 2026-08-31 — client ships tolerant support (red-flag badge
reads `email_verified` / `phone_verified` / `verify_deadline` off the account
info; absent fields = no flag). Server work applies to `ecbAccountManager`
(or a sibling resolver on the CN GraphQL function).

## Why

1. **Completeness flag**: the GUI shows a red flag next to the user ID when the
   account's phone AND email are not both verified, with a 60-day grace period
   before the account goes `inactive`. The client cannot verify contacts —
   only the cloud can send/validate codes — so verification state must be
   server-authoritative and returned with account info.
2. **Top-up crediting (related, already-known gap)**: WeChat/Alipay top-ups
   charge but never credit `public.accounts.fund`
   (`gui/ipc/w2p_handlers/payment_handler.py` docstring). Until the payment
   callback credits the account server-side, the GUI can refresh forever and
   the balance will not move. The new 20-minute account poller makes balances
   live the moment crediting exists.

## Schema additions (accounts table)

```sql
ALTER TABLE accounts ADD COLUMN email_verified  boolean NOT NULL DEFAULT false;
ALTER TABLE accounts ADD COLUMN phone_verified  boolean NOT NULL DEFAULT false;
ALTER TABLE accounts ADD COLUMN verify_deadline timestamptz;  -- sign_on + 60d
```

`reqAccountInfo` (accountRows conversion) must include these three fields so
the desktop/web GUI receives them inside `acctInfo`.

## Resolver: `verify_account_info`

One action with three operations, authenticated like `ensure_account`
(CloudBase access token verified server-side; identity from the token, never
from the body):

```jsonc
// 1. start a verification (server sends the code)
{ "action": "verify_account_info", "op": "send_code",
  "channel": "email" | "phone", "accessToken": "..." }
// -> { "success": true, "cooldown_s": 60 }

// 2. confirm the code
{ "action": "verify_account_info", "op": "confirm",
  "channel": "email" | "phone", "code": "123456", "accessToken": "..." }
// -> { "success": true, "email_verified": true, "phone_verified": false,
//      "verify_deadline": "2026-10-30T00:00:00Z" }

// 3. status (idempotent; also usable by cron)
{ "action": "verify_account_info", "op": "status", "accessToken": "..." }
// -> { "success": true, "email_verified": ..., "phone_verified": ...,
//      "verify_deadline": ..., "states": "active" | "inactive" }
```

Server rules:
- `verify_deadline` = `sign_on_date + 60 days`, stamped at account creation
  (and backfilled for existing rows on first `status` call).
- A scheduled job (or lazy check inside `status` / `llm_proxy`'s account gate)
  flips `states` to `inactive` when `now > verify_deadline` and either flag is
  still false. Completing verification clears the deadline and reactivates.
- Codes: reuse the existing CloudBase SMS/email code infrastructure
  (`sms_service` / auth code store); 6 digits, 10-minute expiry, 60s cooldown.
- WeChat-only accounts have no email/phone at signup — they get both flags
  false and the 60-day clock, which is exactly the "complete your info" nudge.

## Client behavior (already shipped)

- 20-minute account-info poller (MainLayout) keeps `acctInfo` fresh.
- Red `FlagFilled` next to the user ID when either flag is explicitly false;
  hover lists what's missing + days remaining (client computes from
  `verify_deadline`, falling back to `sign_on_date + 60d`).
- Low-fund warning: when `fund <= 36` RMB, an orange "Fund running low /
  余额不足，请及时充值" scrolls across the ad-banner slot 5 passes every
  10 minutes.
