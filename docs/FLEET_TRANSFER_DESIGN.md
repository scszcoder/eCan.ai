# Fleet transfer: fetch logs, move a store with its login

_Status: client built 2026-09-24; needs the server half in
`docs/FLEET_TRANSFER_SERVER_CONTRACT.md` before anything moves._

Two jobs, one mechanism:

| job | source | receiver | who asks |
|---|---|---|---|
| **Fetch logs** | the machine whose logs you want | the machine you are sitting at | you, from the Vehicles page |
| **Move a store with its login** | the machine the store runs on now | the machine it is moving to | you, from the Stores page (any machine) |

## 1. What moves, and why all of it

A site does not flag "a login from another computer". It flags **a device
that changed**. A store keeps looking like the same device only if ALL of this
arrives together:

| part | why |
|---|---|
| cookies | the session itself |
| localStorage / IndexedDB (and the rest of the profile folder, minus caches) | platforms keep their own device ids there; a fresh id is a fresh device even with the same cookies |
| fingerprint settings (the registry record) | user agent, screen, fonts, WebGL, timezone, locale must match what the site has seen |
| proxy (host, port, user, **password**) | the network exit is the strongest signal of all. A store that ran through a proxy must keep that exact proxy |

A fresh login on the new machine is the riskier path, not the safe one.

### Cookies cannot be copied as files

On Windows the cookie database is encrypted with a key that DPAPI binds to the
Windows account on that machine (macOS: the Keychain). Copied elsewhere the
cookies read as EMPTY -- no error, just a login page later. So:

* **export**: cookies are read out of the running browser over CDP
  (`Storage.getCookies`), in the clear, into the encrypted bundle;
* **files**: the profile folder is copied WITHOUT `Cookies`, `Login Data`,
  `Web Data` (all DPAPI-encrypted), `Local State` (holds the DPAPI-wrapped key;
  Chromium makes a new one), caches, and lock/port files;
* **import**: the cookies are written back over CDP (`Storage.setCookies`) the
  first time the profile is launched on the new machine, before any page loads.

Only our own fingerprint browser's profiles move. AdsPower / Ziniao profiles
live in the vendor's app and use the vendor's own sync.

## 2. Transport: LAN when possible, cloud when not

```
            control (tiny, always via cloud: who asks, who may answer)
  requester ─────────────► cloud transfer record ◄───────── source / receiver
                                                   (picked up each heartbeat)

            data (the zip): LAN if the receiver is reachable, else cloud
  source ──── HTTP PUT to receiver's LAN listener ────► receiver       (same LAN)
  source ──── presigned PUT ─► object storage ─► presigned GET ── receiver (WAN)
```

* **The receiver listens; the source connects out.** For Fetch logs the
  receiver is the machine you are sitting at, so a Windows firewall prompt (if
  any) appears in front of you, and an unattended platoon never has to accept
  inbound connections.
* The receiver opens a one-off listener on a free port on all interfaces,
  publishes its private IPv4 addresses + port + a one-time token in the
  transfer record, and closes the listener when the transfer ends.
* The source tries each published address that is private (RFC 1918 /
  link-local; a public address is never tried -- that is the cloud path's job)
  with a 2 s connect. First that answers gets the bundle. None answers → cloud.
* So: same LAN → the data never leaves the building (no egress cost, no
  storage cost, nothing at rest in the cloud). Different networks → cloud.

### Why the control message still goes through the cloud

LAN discovery cannot prove who is asking: its fingerprint is derived from the
account e-mail, which is not a secret. Handing a live store login, or logs full
of customer chats, to anyone on the LAN who knows your e-mail is not
acceptable. The cloud record is only readable by machines signed in to the
account, so it is what authorises a transfer; the LAN only carries bytes.

## 3. End-to-end encryption

The cloud never sees plaintext, on either route.

* The receiver makes a fresh X25519 key pair per transfer and publishes only
  the public half. The private half stays in the receiver's memory.
* The source makes its own ephemeral key pair, derives the key with
  X25519 + HKDF-SHA256 (bound to the transfer id), and encrypts the zip as a
  stream of AES-256-GCM chunks (1 MiB, counter nonces, last chunk marked in the
  associated data so truncation is detected).
* Object storage holds ciphertext only, deleted when the receiver confirms, and
  expired by lifecycle after 24 h regardless.

**Trust boundary.** The server could publish a key of its own in place of the
receiver's -- i.e. it is trusted for the *integrity of the control plane*, as
it already is for logins. It is not trusted with the *data*: nothing it stores
can be decrypted by it. Signing transfers with per-machine long-term keys would
close that too; not done in v1.

If the receiver restarts mid-transfer its private key is gone and the transfer
fails; ask again.

## 4. Move a store with its login -- the sequence

1. You pick the store and the target machine, tick **Bring its login along**,
   and confirm a warning that says a logged-in seller session and its proxy
   credentials are about to be copied to that machine. Without the tick, it is
   a plain reassignment (today's behaviour).
2. The client creates the transfer (kind `profile`, source = the machine the
   store is assigned to, receiver = the target) and then reassigns the store.
3. **Target** (next heartbeat): sees the incoming transfer, opens its
   listener, publishes its key. While a login is incoming for a store, the
   target does **not** start that store (placement says "waiting for its login
   to arrive") -- starting it without the login would fail closed anyway.
4. **Source** (next heartbeat): the store is now assigned elsewhere, so its
   reconciler stops the store's agents (existing behaviour). Once none is
   running, the source reads the cookies out of the browser if it is up, closes
   the browser gracefully (so it flushes), packs the bundle, and sends it.
5. **Target** installs the profile: registry record (same id, its own
   user-data-dir path), proxy password into ITS keyring, profile files, and a
   pending-cookies file consumed at first launch. Then placement starts the
   store normally.
6. The source keeps its copy, marked `moved_to`, so nothing is destroyed by a
   transfer -- but it must not be run again while the target holds the store.

Rule check (`tests/unit/test_browser_profile_stays_local.py`, docs/
OWN_FINGERPRINT_BROWSER.md): **user-commanded** (only from the explicit move
action), **one profile** (the store's), **warned first** (the confirm dialog is
required by the IPC handler, not just the page). The cloud-bound API module
handles opaque encrypted blobs and never names a profile.

## 5. Fetch logs

The source packs its `runlogs/` with the support-zip packager
(`_add_runlogs_dir`), limited to files modified in the chosen window (default
24 h). The receiver saves `<appdata>/fleet_downloads/<machine>-<time>.zip` and
the Vehicles page offers **Open folder**.

## 6. Status and progress

`requested → ready (receiver listening) → sending (lan|cloud) → uploaded
(cloud only) → done | failed(error) | expired (24 h)`. Every step is written to
the transfer record, so any machine of the account sees the same progress.

## 7. Not in v1 (decide later)

* **A dead source.** Everything above needs the source running. Failing over
  from a machine that will not boot needs periodic snapshots stored in the
  cloud, encrypted to a key every machine of the account holds but the server
  does not -- a key-custody decision (who creates it, how a new machine gets
  it) that should be made on purpose, not slipped in.
* Resuming a half-sent transfer; per-machine signing keys; transfers between
  accounts (never).
