# Fleet transfer — server contract (for the backend terminal)

_Client side built 2026-09-24 (`agent/fleet/`, `agent/cloud_api/transfer_api.py`).
Design: `docs/FLEET_TRANSFER_DESIGN.md`. Nothing moves until this is deployed._

The server is the **control plane only**: it records who asked for what and
hands out short-lived storage links. It never sees plaintext -- bundles are
end-to-end encrypted by the client -- and it must never try to parse one.

All actions: `POST` to `ecbAccountManager`, same route, bearer and identity rule
as `store_*` / `pod_*`. The owner is always the verified identity; the client
never sends one.

## 1. Table `fleet_transfers`

| column | type | notes |
|---|---|---|
| transfer_id | text PK | server-generated (uuid) |
| owner | text | verified identity, indexed |
| kind | text | `logs` \| `profile` |
| status | text | see §3 |
| source_vehicle_id | text | must be a vehicle of the owner |
| receiver_vehicle_id | text | must be a vehicle of the owner |
| requester_vehicle_id | text | the machine that asked; informational |
| params | jsonb | ≤ 4 KB. `logs`: `{hours}`. `profile`: `{store_id, profile_id}` |
| receiver | jsonb | ≤ 4 KB. `{pubkey, lan: {addrs: [..], port, token}}`, written by the receiver |
| route | text | `lan` \| `cloud` \| null |
| object_key | text | set by `transfer_upload_url` |
| size | bigint | bytes of ciphertext, reported by the source |
| sha256 | text | of the ciphertext, reported by the source |
| error | text | ≤ 1000 chars |
| created_at / updated_at / expires_at | timestamptz (UTC) | `expires_at = created_at + 24h` |

## 2. Actions

```jsonc
// create -- the requester. `receiver` may be set right away when the
// requester IS the receiver (Fetch logs); otherwise the receiver fills it in.
{ "action": "transfer_create",
  "input": { "kind": "logs", "source_vehicle_id": "…", "receiver_vehicle_id": "…",
             "requester_vehicle_id": "…", "params": { "hours": 24 },
             "receiver": { "pubkey": "<b64>", "lan": { "addrs": ["192.168.1.20"], "port": 53817, "token": "<b64>" } } } }
// → { success, transfer: <row> }

// list -- every active transfer where the vehicle is source, receiver or requester.
{ "action": "transfer_list", "input": { "vehicle_id": "…", "include_finished": false } }
// → { success, transfers: [<row>] }    (newest first, ≤ 50)

{ "action": "transfer_get", "input": { "transfer_id": "…" } }
// → { success, transfer: <row> }

// update -- status / receiver / route / size / sha256 / error only.
{ "action": "transfer_update",
  "input": { "transfer_id": "…", "status": "sending", "route": "lan" } }
// → { success, transfer: <row> }

// storage links -- only for status `sending` (upload) / `uploaded` (download).
{ "action": "transfer_upload_url",   "input": { "transfer_id": "…" } }
// → { success, url, object_key, expires_in }     presigned PUT, 1 h
{ "action": "transfer_download_url", "input": { "transfer_id": "…" } }
// → { success, url, expires_in }                  presigned GET, 1 h

// finish -- the receiver, after decrypting (or on failure). Deletes the object.
{ "action": "transfer_finish", "input": { "transfer_id": "…", "status": "done" } }
{ "action": "transfer_finish", "input": { "transfer_id": "…", "status": "failed", "error": "…" } }
// → { success, transfer: <row> }
```

Rows are returned camelCase (`transferId`, `sourceVehicleId`, …) like
`storeRow`; the client reads both spellings.

## 3. Status machine

```
requested ─► ready ─► sending ─► uploaded ─► done
    │          │         │           │
    └──────────┴─────────┴───────────┴──► failed | expired
```

* `ready` requires `receiver.pubkey`. `transfer_create` with a receiver goes
  straight to `ready`.
* `sending` → `done` directly is legal (the LAN route never uploads).
* Reject any other transition with `INVALID_TRANSITION`; reject every update
  after `done` / `failed` / `expired`.
* A sweep (or a check on read) turns anything past `expires_at` into
  `expired` and deletes its object.

## 4. Storage

* Bucket: the existing releases/skills account, a dedicated prefix
  `fleet-transfers/<owner>/<transfer_id>.bin`. **Private**, never CDN-fronted.
* Lifecycle rule on the prefix: delete after 1 day.
* Presigned PUT: 1 h, `Content-Type: application/octet-stream`; cap the size
  at 2 GiB (policy condition, or refuse `transfer_upload_url` when the
  reported `size` exceeds it).
* `transfer_finish` deletes the object whatever the status.

## 5. Limits and validation

* Both vehicle ids must belong to the owner (the `vehicles` rows the heartbeat
  writes). Source ≠ receiver.
* ≤ 10 non-finished transfers per owner; `TOO_MANY_TRANSFERS` beyond.
* `kind` ∈ {`logs`, `profile`}; `params` / `receiver` ≤ 4 KB each.
* Never log `receiver.lan.token`.

## 6. Tests to add

1. create → list (source sees it, receiver sees it, another owner does not).
2. create with receiver → status `ready`; without → `requested`; update with
   pubkey → `ready`.
3. illegal transitions rejected; update after `done` rejected.
4. upload_url only in `sending`; download_url only in `uploaded`; both refuse
   another owner's transfer.
5. finish deletes the object; expired sweep deletes it too.
6. a vehicle id of another owner is refused on create.

## 7. Verify end to end

With two machines on the account: Vehicles page → pick the other machine →
**Fetch logs** → the zip lands in `<appdata>/fleet_downloads/`. Repeat with the
two on different networks (phone hotspot) to exercise the cloud route.
