# Profile Vault — server contract (CONFIG-first)

The client half is built (`agent/ec_agents/profile_vault.py`), gated OFF behind
`ECAN_PROFILE_VAULT`. It stores only a store browser profile's **CONFIG
descriptor** — the security-vetted, non-sensitive subset — so a store can be
redeployed to any machine. This document is the server half (eCan_lambda) the
client needs; implement it in that private repo, NOT here.

**Do not deploy this and flip `ECAN_PROFILE_VAULT=1` until these ops exist**, or
the client will error on every call (it is a quiet no-op while the flag is off).

## What is stored (and what is NOT)

The object is a single small JSON document = `profile_registry.descriptor(profile)`:

```json
{
  "id": "douyin-<slug>-login",
  "label": "店B",
  "store_id": "douyin-店B",
  "machine_id": "<which machine last wrote it>",
  "domain_name": "im.jinritemai.com",
  "fingerprint_profile": "win_chrome_01",
  "locale": "zh-CN",
  "browser": { "version": "" },
  "has_proxy": true,
  "login_state": "needs_login",
  "login_checked_at": 0
}
```

NEVER present (enforced client-side by `descriptor()` + its allowlist, and by
`tests/unit/test_browser_profile_stays_local.py`): `user_data_dir`, cookies /
the session, `install_salt`, and any proxy host/port/username/password. Session
STATE sync is a **separate, later phase** with its own encryption/key-custody
decision (see the Fleet-transfer "Open after v1" notes).

## Transport (mirror the skill-file-sync presigned pattern)

The desktop holds no bucket secrets. It authenticates to AppSync with the user's
bearer token and asks the backend to mint a presigned URL; then it PUTs/GETs the
descriptor JSON directly to object storage. Reuse the same bucket/credentials and
IAM the existing `requestSkillFileUploadUrl` / `requestSkillFileDownloadUrl` use.

### Object key

Namespace by the normalized cloud owner (same as prompt/skill sync —
`normalize_cloud_owner(mainwin.user)` = the bare openid / email):

```
profile-vault/<owner>/<store_id>.json
```

One descriptor per (owner, store). `store_id` may contain non-ASCII (e.g.
`douyin-店B`) — URL/key-encode as needed; the client sends it raw in the GraphQL
variable.

### GraphQL ops to add

```graphql
input StoreProfileVaultInput {
  storeId: ID!
  owner: String!
}

type StoreProfileVaultUrl {
  uploadUrl: String        # presigned PUT (upload op only)
  downloadUrl: String      # presigned GET (download op only)
  s3Key: String!
  expiresIn: Int
}

type Mutation {
  # Mint a presigned PUT for profile-vault/<owner>/<storeId>.json
  requestStoreProfileUploadUrl(input: StoreProfileVaultInput!): StoreProfileVaultUrl!
}

type Query {
  # Mint a presigned GET for the same key. If the object does not exist, return
  # a GraphQL error (the client treats any error as "nothing stored yet" and
  # falls back to seeding a fresh standard profile — it does NOT warn-spam).
  requestStoreProfileDownloadUrl(storeId: ID!, owner: String!): StoreProfileVaultUrl!
}
```

Authorization: the resolver MUST confirm the bearer's identity owns `owner`
(the openid/email) before minting a URL — exactly as the skill-file ops do — so
one account cannot read or overwrite another's profile vault.

Content-Type: the client PUTs `application/json`; set the presigned PUT to match
if your bucket enforces it.

## Client behavior (already implemented)

- `push_descriptor(profile)` — async, best-effort, fire-and-forget. Called from
  `prep_skills_run._provision_store_profile` right after a profile is
  auto-created, so a newly provisioned store's CONFIG lands in the vault. (Add
  calls from the Settings → Browser Profiles edit handler when wiring "push on
  change" for operator edits.)
- `pull_descriptor(store_id)` — synchronous, best-effort. Called at the top of
  `_provision_store_profile`: if the vault has this store's CONFIG, the new
  local profile adopts its `fingerprint_profile` / `domain_name` / `locale`
  (same login identity across machines); otherwise a fresh standard template is
  seeded. The session never travels, so the operator still signs in once.

## Rollout

1. Add the two ops + IAM to eCan_lambda; deploy to CN (and intl if used there).
2. On one machine, set `ECAN_PROFILE_VAULT=1`, deploy a store → confirm
   `profile-vault/<owner>/<store_id>.json` appears.
3. On a second (pristine) machine assigned the same store, set the flag → confirm
   the provisioned profile adopts the vault's fingerprint and only needs sign-in.
4. Flip the flag on by default once validated.

## Later: STATE sync (phase 2, deferred)

Encrypted cookie/`user_data_dir` snapshots so a redeploy can restore the live
session. Needs a key the account's machines share and the server does not hold
(see `docs/FLEET_TRANSFER_SERVER_CONTRACT.md` "Open after v1"). Do not start
until CONFIG-first is live and we confirm platforms honor a migrated session.
