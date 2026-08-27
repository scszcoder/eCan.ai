# CN WeChat OpenID Unification Milestone

**Date:** 2026-08-27
**Status:** Verified in production

## Outcome

CN web and desktop WeChat sign-in now resolve to the same canonical application
identity:

```
wechat_o3YBk2dxaRe3LKqJXCf5z3PfvD5M
```

The suffix is the raw WeChat OAuth `openid` returned for eCan's registered
WeChat application. It is stable for this WeChat app and is the correct account
key for provisioning, organization ownership, and session records.

## Why the Earlier IDs Differed

`wechat_2092809332621058048` was CloudBase's internal account `uid`, not a
WeChat OpenID. The direct browser CloudBase flow did not expose a verified raw
OpenID, so using JWT fallback fields such as `uid` created a separate,
unrecognizable account identity.

The user's WeChat client identifier (`wxid_*`) is different again. WeChat's
public OAuth API does not return or validate `wxid_*`; eCan must not use it as
an authentication or account key.

## Production Flow

```text
gui-v2 WeChat login
  -> /cn/login_callback/wechat_login.php
  -> WeChat QR authorization
  -> /cn/login_callback/wechat_login_callback.php
  -> server-side code exchange obtains raw openid
  -> application user/session provisioning
  -> /app/gui-v2/#/agents
```

The callback persists the application-issued bearer token in the modern
`webAuthSession` session storage fields and presents the account as
`wechat_<openid>`. The callback session intentionally has no Cognito expiry:
the browser token refresh service must not attempt a Cognito refresh for this
cookie-backed custom session.

## Verified Browser Routing

The current QR authorization page redirects to:

```
https://www.fastprecisiontech.com/cn/login_callback/wechat_login_callback.php
```

Older browser tabs may still point to `/app/gui-v2/#/login`. Those tabs execute
the superseded CloudBase flow and can produce the numeric internal UID. Discard
them and start a new QR login from a freshly loaded GUI-v2 login page.

## Operational Boundaries

- Do not send `wechatOpenid` to the public CloudBase GraphQL endpoint until a
  matching function version is published and routed. The public endpoint was
  verified to reject that field under its current immutable route.
- Do not treat `uid`, `sub`, or other CloudBase JWT fallback values as WeChat
  OpenIDs.
- Do not expose application bearer tokens in GraphQL errors, browser dialogs,
  logs, or documentation.
- Keep the raw OAuth code exchange server-side. It protects the WeChat app
  secret and is the authoritative source of raw OpenID.

## User-Facing Naming

Use the raw OpenID-derived account key for identity consistency. For a more
human-friendly presentation, show the WeChat OAuth nickname/avatar or a
user-managed display name alongside it; never infer a `wxid_*` value.

## Validation Completed

- Fresh web QR login redirected through the server callback.
- The callback returned the raw OpenID account key.
- Desktop login showed the same canonical `wechat_<openid>` identity.
- The CloudBase custom-login ticket subject is the raw WeChat OpenID while the
  legacy hashed eCan account key remains intact for backwards compatibility.
- The browser exchanges the ticket with CloudBase and registers the resulting
  CloudBase token with GraphQL to obtain its durable eCan bearer session.
- GraphQL function version 11 was published with regenerated Prisma metadata
  that includes `Org.owner` mapped to `agent_orgs.owner`.
- Raw SCF alias verification confirms version 11 receives `[0,100)` production
  traffic and version 10 receives the empty `[100,100)` range. The CloudBase
  `fn get-route` formatter is not reliable for this rule order.
- A fresh authenticated web session loaded owner-scoped organizations without
  GraphQL fetch errors.
- An unauthenticated GraphQL health probe returned the expected
  `UNAUTHENTICATED` response, confirming the public endpoint is available.
- CN production frontend build completed with:

  ```bash
  NODE_OPTIONS=--max-old-space-size=4096 npm run build -- --mode cn.web.production
  ```
- PHP callback syntax validation passed.