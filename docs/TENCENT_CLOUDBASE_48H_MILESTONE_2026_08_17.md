# Tencent CloudBase 48-Hour Milestone

Date: 2026-08-17

This document records the verified Tencent CloudBase work completed during the
previous 48 hours, along with the operational paths that proved reliable.

## Production Resources

| Resource | Name / ID | Purpose |
| --- | --- | --- |
| CloudBase environment | `sccb0-d0gc5398xf028be6a` | Production environment in `ap-shanghai` |
| Production GraphQL SCF | `ecan-graphql-api` | GraphQL Yoga, Prisma, PostgreSQL |
| Isolated GraphQL SCF | `ecan-graphql-api-test` | Direct-event and temporary HTTP integration testing |
| Production WS service | `ecan-graphql-ws` | GraphQL WS bridge service |
| Isolated WS service | `ecan-graphql-ws-test` | Signed-token cloud WebSocket E2E testing |
| GraphQL route | `/api/graphql` | Public CloudBase access-service route |
| PostgreSQL resource | `postgres-khj3tzyk` | Prisma and standalone Tencent-function storage |

All healthy GraphQL function deployments use Node `20.19`, the production VPC
and subnet, and `InstallDependency=FALSE`.

## Verified Outcomes

### Prisma deployment recovery

- Repaired the production GraphQL SCF after a packaging regression caused
  `FUNCTIONS_INVOCATION_FAILED` responses.
- Production and test artifacts contain visible `prisma-client/` copies of both
  required engines:
  - `rhel-openssl-1.1.x`
  - `rhel-openssl-3.0.x`
- The Prisma wrapper is rewritten to load the visible client because CloudBase
  COS packaging omits `node_modules/.prisma`.
- The modular `tencentcloud-sdk-nodejs-scf` runtime dependency is retained for
  task scheduling.

### GraphQL CRUD parity

- Verified isolated direct-event CRUD for agents, prompts, skills, and tasks.
- Fixed PostgreSQL JSONB skill tag filtering by using `array_contains` rather
  than unsupported Prisma `hasEvery` / `hasSome` filters.
- Added and applied the `agent_tasks.source` schema migration.
- Prompt writes are PostgreSQL-authoritative and write canonical COS snapshots
  plus immutable fallback revisions when bucket versioning is unavailable.
- Prompt snapshots and skill tag fixes were promoted to production after test
  verification.

### Scheduler and task lifecycle

- Task CRUD now synchronizes Tencent SCF timer triggers through the modular SCF
  SDK.
- Production and test packaging assertions verify both Prisma engines and the
  scheduler SDK before upload.

### WebSocket parity and E2E testing

- Added an isolated `ecan-graphql-ws-test` service and a short-lived HMAC test
  token mode that is separate from production JWT auth.
- The real-cloud test opens a `graphql-ws` client, waits for `connection_ack` and
  `start_ack`, direct-invokes `publishTaskStatus` on the test API, and asserts a
  matching `data` frame.
- Found and fixed `publishTaskStatus`: it declared `TaskStatus` but returned a
  JSON string, which failed GraphQL field coercion.
- Local validations passed:
  - WS protocol: 30 checks
  - real-socket bridge: 17 checks
  - API-to-WS stack: 11 checks
  - GraphQL/WS parity: 50 checks

### Tencent standalone function ports

- Confirmed source ports already existed for `chatter`, `cloud_tester`, and
  `myAPIKeygen`, but were not deployed.
- Deployed all three as VPC-enabled Node 20 Event functions.
- Added `cloud_runs` and `ecb_api_keys` tables.
- Aligned `chatter` and `cloud_tester` with GraphQL-owned PostgreSQL schemas
  (`a2a_messages`, `account_notifications`) rather than creating conflicting
  legacy table layouts.
- Verified deployed `chatter` create/read and `myAPIKeygen` create/query/remove
  flows. `cloud_tester` validates empty batches and is configured for GraphQL;
  authenticated transport testing needs a deliberate test credential.

### Desktop WeChat session and offline queue recovery

- Diagnosed the desktop failure as a server-side bootstrap deadlock:
  `registerWeChatSession` could not run until a signed eCan session token
  existed, but it is responsible for minting that token.
- Allowed only a one-root-field `registerWeChatSession` operation to reach its
  token-validation resolver without pre-existing GraphQL identity.
- Fixed Yoga context classification for the desktop's variable-based mutation.
- Made the session input accept either `wxAccessToken` or `wx_access_token`;
  both cannot be required because snake-case compatibility aliases otherwise
  duplicate the non-null input requirement.
- Added and applied `wechat_sessions` storage migration.
- Verified production persistent session registration. The server has an active
  session record with a 30-day expiry.
- Verified the desktop offline queue replayed and persisted both queued agents:
  `张三` and `李四`.

## Logging and Traceability

CloudBase has two useful layers, comparable to AppSync request logs and Lambda
logs on AWS:

1. Gateway/API traffic: CloudBase access logs.
2. SCF lifecycle and application output: function records with `src=system` and
   `src=app`.

Do not use raw CLS `SearchLog` or SCF `GetFunctionLogs` for this environment.
They can return empty results even when logs exist. Use CloudBase's native log
service through the CLI:

```bash
CLI=/tmp/cloudbase-cli-3.7.3/node_modules/@cloudbase/cli/dist/standalone/cli.js
ENV=sccb0-d0gc5398xf028be6a

# SCF lifecycle, return payloads, application stdout/stderr, and request IDs.
node "$CLI" logs search -e "$ENV" \
  -q 'function_name:"ecan-graphql-api"' -t 1h -l 100 --json

# API-gateway traffic for the GraphQL route.
node "$CLI" logs search -e "$ENV" \
  -q 'logType:accesslog AND path:"/api/graphql"' -t 1h -l 100 --json

# Correlate a known SCF request ID.
node "$CLI" logs search -e "$ENV" \
  -q 'function_name:"ecan-graphql-api" AND request_id:"<request-id>"' \
  -t 1h -l 100 --json
```

The SCF now logs non-sensitive GraphQL boundary telemetry:

```text
[graphql] request operation=mutation field=addAgents
[graphql] authenticated operation=mutation field=addAgents
[graphql] rejected operation=query field=reqAccountInfo code=UNAUTHENTICATED
```

Never log Authorization headers, request variables, JWTs, session tokens,
database URLs, COS signed URLs, or complete gateway access-log payloads. Gateway
logs may contain sensitive query/header data; extract only request ID, method,
path, resource name, timestamp, and status when sharing diagnostics.

## Reliable CloudBase CLI Workflows

### Inspect function configuration safely

```bash
node "$CLI" fn detail ecan-graphql-api -e "$ENV" --json
```

Check `Status`, `InstallDependency`, runtime, VPC, and environment-variable
names only. Do not print environment values.

### Direct SCF integration tests

Use a mode `0600` temporary event file, never stdin or command-line JWTs:

```bash
node "$CLI" fn invoke ecan-graphql-api-test -e "$ENV" \
  -d @/path/to/event.json --json
```

For current CLI output, inspect `data.RetMsg` for the function result and
`data.RequestId` for correlation. `InvokeResult=0` means SCF invocation
completed; GraphQL errors can still exist in the returned response body.

### Production code upload

`fn code update` reads the nearest `cloudbaserc.json`. Always invoke it from a
mode `0600` temporary directory containing a config scoped to the target
function, while passing the staged artifact as an absolute path. This avoids
accidentally updating the wrong function or changing `InstallDependency`.

### PostgreSQL

The VM cannot directly reach the private database. Use CloudBase SQL execution:

```bash
node "$CLI" db execute -e "$ENV" --json --sql 'SELECT 1'
```

Start with catalog queries, use additive idempotent DDL in a transaction, and
verify resulting columns/indexes. Do not use `--role postgres`; the managed
identity does not assume that role.

### Cloud Run WebSocket service

Use `cloudrun detail` for managed WS service status and endpoint metadata. The
SCF-to-WS bridge needs `WS_TCS_URL` plus a matching `WS_PUSH_SECRET`. Keep test
service resources and test-only auth secrets separate from production.

## Current Follow-up

- Observe WebSocket behavior after the short-lived CloudBase access token
  boundary. HTTP persistent-session and offline queue replay are verified.
- Retry GitHub push when network access is available; the backend commits after
  `47613714` remain local at this milestone.