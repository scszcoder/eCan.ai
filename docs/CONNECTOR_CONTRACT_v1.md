# eCan Connector Contract v1 (DRAFT)

Status: draft for product-owner review, 2026-10-21. Nothing here is implemented yet.

## 1. Purpose and model

Merchants run their business on systems eCan does not ship: an ERP (订单/库存),
a WMS, a logistics account (快递), sometimes a legacy database or Excel. After-sales
(售后) and store-operations agents need to read and act on those systems.

A **connector (连接器)** is the plug-in that does this:

- It is an **external MCP server**, installed and versioned separately from eCan
  (an exe, a Python/Node script, or an HTTP service on the merchant's network).
  It is **not part of the eCan package**.
- eCan connects to it (stdio or HTTP), lists its tools, and exposes them to skills.
- eCan defines **capabilities**: fixed names with versioned JSON schemas
  (`stock.check@1`, `order.reissue@1`, ...). **Prompts and skills only ever use
  capability names**, never a vendor's tool names.
- Each connector's **manifest** says which capabilities it implements and with which
  of its own tools (`"stock.check@1": "queryInventory"`).
- Vendor tools outside the contract still appear to agents as **other tools**
  (其他工具) with their own descriptions; core flows never depend on them.
- A capability no connector provides is a **known gap**: the agent is told it is
  unavailable and follows its prompt's fallback (propose, wait for the merchant).

```
skill / prompt ──uses──> capability (stock.check@1)
                              │  eCan resolves via manifest
                              ▼
                 connector "acme-erp" tool queryInventory  ──> merchant ERP
```

## 2. Manifest

Each connector ships a `ecan_connector.json` next to its executable (or serves it at
`GET <url>/ecan_connector.json` for HTTP). The merchant adds the connector on the
**插件与连接器 → 连接器** page; eCan reads the manifest, then the MCP tool list.

```json
{
  "id": "acme-erp",
  "name": "Acme ERP 连接器",
  "version": "1.2.0",
  "vendor": "Acme 软件",
  "contract": "ecan.connector@1",
  "transport": {
    "type": "stdio",
    "command": "acme_erp_connector.exe",
    "args": ["--profile", "default"],
    "env": {"ACME_DB": "${secret:acme_db_dsn}"}
  },
  "implements": {
    "order.get@1": "getOrder",
    "stock.check@1": {
      "tool": "queryInventory",
      "field_map": {"input": {"sku": "item_code"}, "output": {"available": "qty_free"}}
    },
    "order.reissue@1": "createReplacementOrder",
    "logistics.track@1": "trackParcel"
  },
  "requires_confirmation": {"order.reissue@1": true},
  "health_check": "ping",
  "data_residency": "on-premise; no data leaves the merchant LAN except tool results to eCan"
}
```

| Field | Meaning |
|---|---|
| `id` | Stable, lowercase, unique per merchant install. |
| `transport` | `stdio` (`command`, `args`, `env`) or `http` (`url`, `headers`). `${secret:name}` values come from eCan's secure store, never from the manifest file. |
| `implements` | Capability → vendor tool name, or `{tool, field_map}` when names differ. Preferred: the connector speaks our schema natively (no `field_map`). `field_map` only renames top-level fields; anything more is the connector's job. |
| `requires_confirmation` | Overrides the catalogue default per capability. A connector may only make a capability **stricter** (read → confirm), never looser. |
| `health_check` | A zero-argument tool eCan calls on connect and every 5 min; shown as status on the 连接器 page. |
| `data_residency` | Free text shown to the merchant. |

## 3. Capability catalogue v1

`side_effect`: **read** (no change), **write** (changes merchant records, no money or
goods), **money** (moves money or goods). Default confirmation: read/write = no,
money = **confirm** (§5).

| Capability | Purpose | Input | Output | Side effect | Confirm |
|---|---|---|---|---|---|
| `order.get@1` | One order with items, amounts, status | `order_id`, `id_type` (`platform`\|`erp`), `store_id?` | `Order` | read | no |
| `order.search@1` | Find a buyer's orders | `buyer_ref?` (platform buyer id / nickname), `phone_last4?`, `since?`, `until?`, `store_id?`, `page_token?`, `limit?` (≤50) | `{orders: [OrderSummary], next_page_token?}` | read | no |
| `aftersale.find@1` | After-sales requests (售后单) for an order/buyer, when the ERP mirrors them | `order_id?`, `buyer_ref?`, `status?` | `{aftersales: [AfterSale]}` | read | no |
| `aftersale.get@1` | One 售后单 | `aftersale_id` | `AfterSale` | read | no |
| `product.lookup@1` | Product facts by SKU / platform item id | `sku?`, `platform_item_id?`, `store_id?` | `{title, sku, attributes{}, variants[]}` | read | no |
| `stock.check@1` | Available stock for SKUs | `skus[]`, `warehouse?` | `{items: [{sku, available, warehouse}]}` | read | no |
| `logistics.track@1` | Parcel trace | `tracking_no`, `carrier?` | `{carrier, status, events: [{time, location, text}], delivered_at?}` | read | no |
| `return.address@1` | Return address for a store/warehouse | `store_id?`, `warehouse?` | `{name, phone, address, note?}` | read | no |
| `order.reissue@1` | 补发: create a replacement shipment | `order_id`, `items[{sku, qty}]`, `reason`, `idempotency_key` | `{reissue_id, erp_order_id, eta?}` | money | **confirm** |
| `order.cancel@1` | Cancel an unshipped order in the ERP | `order_id`, `reason`, `idempotency_key` | `{cancelled: bool, state}` | money | **confirm** |
| `refund.request@1` | Record / request a refund in the merchant's finance system | `order_id`, `amount_fen`, `reason`, `idempotency_key` | `{refund_id, state}` | money | **confirm** |
| `customer.note.write@1` *(optional)* | Write a note to the merchant's CRM | `buyer_ref`, `order_id?`, `text`, `idempotency_key` | `{note_id}` | write | no |

Shared types (all fields optional unless marked *):

- `Order`: `order_id`*, `platform`, `store_id`, `status` (`unpaid|paid|shipped|delivered|closed|refunded`),
  `items[{sku, title, qty, unit_price_fen}]`, `total_fen`, `currency`, `paid_at`,
  `shipping{carrier, tracking_no, shipped_at}`, `buyer{ref, nickname}`, `erp_order_id`.
- `OrderSummary`: `order_id`*, `status`, `total_fen`, `created_at`, `items_brief`.
- `AfterSale`: `aftersale_id`*, `order_id`*, `type` (`refund_only|return_refund|exchange|reissue`),
  `status` (`requested|approved|rejected|buyer_shipped|received|refunded|closed`),
  `amount_fen`, `reason`, `return_tracking_no`, `updated_at`.

Errors per capability: every capability may return the common codes (§4); additionally
`order.cancel` → `CONFLICT` when already shipped; `order.reissue` / `refund.request` →
`CONFLICT` when the same `idempotency_key` was used with different arguments.

### Platform actions (built by eCan, not connectors)

Actions inside a platform's seller back office — agree a return (同意退货), give the
return address, agree a refund (同意退款), reject with a reason — are **eCan platform
actions**, implemented per platform (抖店, 拼多多, 千牛) by eCan itself, the way the 运营
agent works the back office. They use the same naming style and confirmation rules so
prompts read the same:

`platform.aftersale.list@1`, `platform.aftersale.approve_return@1`,
`platform.aftersale.approve_refund@1`, `platform.aftersale.reject@1`.

The platform 售后单 is the **source of truth** for after-sales status; connectors that
mirror it (`aftersale.*`) are a convenience for merchants whose ERP already syncs it.

## 4. Common conventions

- **IDs.** `order_id` is the platform order number unless `id_type: "erp"`. Results
  carry both when known (`order_id`, `erp_order_id`). `store_id` is eCan's store id
  (e.g. `douyin-小店一号`); the connector maps it to its own shop key.
- **Money.** Integer **fen** (分) in fields ending `_fen`, plus `currency` (default `CNY`).
  Never floats.
- **Time.** ISO 8601 with offset, e.g. `2026-10-21T14:59:01+08:00`.
- **Pagination.** `limit` (default 20, max 50) + opaque `page_token`; results return
  `next_page_token` when more exist.
- **Idempotency.** Every `write`/`money` call carries `idempotency_key` (eCan sends
  `<case_id>:<capability>:<n>`). A repeat with the same key and arguments returns the
  first result; with different arguments → `CONFLICT`.
- **Errors.** Tool results that fail return `{"error": {"code", "message", "retry_after_s?"}}`:

| Code | Meaning | eCan behaviour |
|---|---|---|
| `NOT_FOUND` | No such order/sku/parcel | Tell the agent; no retry |
| `INVALID_ARGUMENT` | Bad or missing input | No retry; logged as a contract bug |
| `UNAUTHORIZED` | Connector's credentials rejected | Connector marked failed on the 连接器 page |
| `RATE_LIMITED` | Back off | Retry after `retry_after_s` (max 2) |
| `UPSTREAM_DOWN` | ERP / carrier unreachable | Retry once; agent told "system temporarily unavailable" |
| `CONFLICT` | State forbids it (already shipped) or idempotency clash | No retry; agent told why |
| `NEEDS_CONFIRMATION` | Connector requires merchant approval for this call | eCan raises an approval (§5) |

- **Timeouts.** eCan waits 10 s for read capabilities, 30 s for write/money; a timeout
  counts as `UPSTREAM_DOWN`. Connectors should answer reads in < 3 s.
- **PII.** Connectors may return full phone/address (needed for 补发), but eCan logs them
  masked (`138****1234`, address to district level) and never puts them in model prompts
  unless the step needs them. Connectors must not log eCan's buyer messages.

## 5. Confirmation model

"Confirm-level" means: **the agent prepares the action, the merchant approves it in eCan.**

1. The agent calls a confirm-level capability (`order.reissue@1` …).
2. eCan does **not** call the connector yet. It creates an **approval** (what, for whom,
   amount, evidence, the agent's reasoning) and tells the agent "submitted for approval".
3. The merchant approves or rejects with one click (eCan notification + the case view).
4. On approval eCan calls the connector with the prepared arguments and the same
   `idempotency_key`; the result goes back to the case and the owning agent.

Auto-approval: the store's 售后 rules (店铺规则 → 售后) may approve below thresholds, e.g.
"补发 ≤ ¥50 for 破损 with photo evidence". Rules can only loosen eCan's defaults, never a
connector's `requires_confirmation`.

A connector can also enforce approval on its side: return `NEEDS_CONFIRMATION` and eCan
treats the call exactly as step 2.

## 6. Versioning and compatibility

- `@1` changes are **additive only** (new optional inputs, new output fields, new error
  codes listed as optional). Connectors and eCan ignore fields they do not know.
- A breaking change is a new version (`order.get@2`). A connector may implement several
  versions; eCan uses the **highest version both sides support**.
- The manifest's `contract` (`ecan.connector@1`) versions the manifest format itself.

## 7. Case note (eCan side, not a connector capability)

The platform 售后单 is the status source of truth. eCan keeps only what no other system
has, as a thin **case note** per buyer + order:

- evidence the buyer sent in chat (image/video file references, eCan-local);
- what the agent proposed or promised, and pending approvals (§5);
- external ids created outside the platform (ERP `reissue_id`, resend tracking number);
- the **owning after-sales agent**, so every message from this buyer reaches the same
  agent across days and restarts.

Status is never stored here — it is read from the platform (`platform.aftersale.*`) or a
mirroring connector when needed.

## 8. Testing

- **Reference connector:** `fake-erp`, a small open MCP server eCan publishes as the
  starter kit. It implements every v1 capability over a JSON file, supports
  `--fail <capability>:<code>` to simulate errors, and is what merchants' integrators
  copy.
- **Conformance check:** a command in eCan (and a pytest suite) that loads a connector's
  manifest, calls each implemented capability with fixture inputs, and validates outputs
  against the JSON schemas, idempotency (repeat a write call) and error shapes. The
  连接器 page shows the result before a connector can be enabled for a skill.

## 9. Open questions for the product owner

1. **Approvals:** where does the merchant approve — eCan desktop notification only, or
   also WeChat/mobile? Who may approve when several staff use one account?
2. **Auto-approval rules:** which actions and thresholds should 店铺规则 → 售后 allow
   (补发 under ¥X with photo? 仅退款 under ¥Y?)
3. **Before approval, what may the agent tell the buyer** — propose the remedy
   ("我们给您补发") or only "已提交，商家确认后处理"?
4. **Capability set:** is anything missing for the first alpha merchants
   (e.g. `invoice.*`, `coupon.issue` for compensation, `warehouse.*`)?
5. **Hosting:** do we support HTTP connectors on the internet (needs auth + TLS rules),
   or stdio/LAN only for v1?
6. **Distribution:** do we list third-party connectors anywhere (a directory), or only
   merchants' own installs for now?
7. **Billing:** are connector calls free, or counted like tool calls on the account?
