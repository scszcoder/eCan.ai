# Store definition sync — server contract (for the backend terminal)

_Client side shipped 2026-09-24 (local `store` table, `store.create` /
`store.update`). This is the server half that lets a store's DEFINITION follow
it across machines. Placement (assign / claim / report / release) is already
live and is not changed here._

## Why

A store is now defined locally first (name, platform, URLs, login profile) and
deployed into. The cloud `stores` row only carries `label` and `platform`, and
the only way to write them is `store_assign` — which ALSO sets
`assigned_vehicle_id`. So the client can write a definition to the cloud only at
creation (a brand-new id has no assignment to clobber). Renaming a store, or a
second machine learning a store's URLs, needs a definition-only write.

## 1. New action: `store_define`

Owner-authenticated, same route and identity rule as the other `store_*`
actions on `ecbAccountManager`.

```json
{ "action": "store_define",
  "input": { "store_id": "小店一号", "label": "小店一号", "platform": "douyin",
             "store_urls": ["https://im.jinritemai.com/pc_seller_v2/main/workspace"] } }
```

- Upsert `(owner, store_id)`. Validate `store_id` with `storeIdProblem` (no
  URL-derived id).
- Writes ONLY `label`, `platform`, `store_urls`. Must NEVER touch
  `assigned_vehicle_id`, `reported_vehicle_id`, `login_state`, `profile`,
  `status`. (No action writes both desired and observed state — same rule as
  today.)
- An omitted field is left as is; an empty string / empty list clears it.
- `store_urls`: array of ≤ 10 strings, each ≤ 2048 chars, `http(s)://` only.
  Store as JSONB.
- Response: `{ success, store: <storeRow> }`.

## 2. Schema

`ALTER TABLE stores ADD COLUMN IF NOT EXISTS store_urls JSONB NOT NULL DEFAULT '[]'::jsonb;`

## 3. `store_list` / `storeRow`

Add `storeUrls` (array) to each row. Nothing else changes.

## What the client will do with it (next client change, after deploy)

- `store.create` / `store.update` call `store_define` for the definition, and
  `store_assign` only for an explicit placement change.
- The catalog seeds from `store_list` including `storeUrls`, so a second
  machine can deploy into a store defined on the first one without retyping
  its URLs.
- The browser profile id is never sent (a profile is a live session and stays
  on its machine).

## Tests to add (test-stores.js)

1. `store_define` on a new id creates the row with label/platform/urls and
   `assigned_vehicle_id` NULL.
2. `store_define` on an assigned store changes the label and leaves
   `assigned_vehicle_id` / `reported_vehicle_id` / `login_state` untouched.
3. URL-derived `store_id` refused; a non-http URL in `store_urls` refused.
4. Another account cannot define into your store (tenancy).

## Intl

No store backend exists on intl at all (docs/OPEN_ITEMS.md). Stores there are
local-only until the AWS side has the same actions.
