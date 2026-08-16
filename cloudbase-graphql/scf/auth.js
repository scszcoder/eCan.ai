/**
 * Authentication helpers shared by all GraphQL resolvers.
 *
 * `resolveIdentity` is bound to the Yoga `context` factory at schema setup time;
 * `authenticatedOwner` is called by resolvers to enforce owner scoping.
 */

const { GraphQLError } = require('graphql');
const crypto = require('node:crypto');

// Local cache so the initial Yoga import does not force a TCB init for unit tests.
function getTcbApp() {
  // Lazy import to avoid pulling @cloudbase/node-sdk when not needed.
  try { return require('./tcb-init').getTcbApp(); } catch { return null; }
}

const ALLOW_INSECURE_AUTH = process.env.ALLOW_INSECURE_AUTH === 'true' && process.env.NODE_ENV !== 'production';
const DIRECT_TEST_MODE = process.env.TCB_DIRECT_TEST_MODE === 'true';
const DIRECT_TEST_PROOF = crypto.randomBytes(32).toString('hex');

function directTestHeaders(owner) {
  if (!DIRECT_TEST_MODE) throw new Error('Direct test mode is disabled');
  const subject = String(owner || '').trim();
  if (!subject || subject.length > 256) throw new Error('Direct test owner is required');
  return {
    'x-ecan-direct-test-owner': subject,
    'x-ecan-direct-test-proof': DIRECT_TEST_PROOF,
  };
}

function directTestIdentity(request) {
  if (!DIRECT_TEST_MODE) return null;
  const owner = _readHeader(request.headers, 'x-ecan-direct-test-owner');
  const proof = _readHeader(request.headers, 'x-ecan-direct-test-proof');
  if (!owner || !proof || proof.length !== DIRECT_TEST_PROOF.length) return null;
  if (!crypto.timingSafeEqual(Buffer.from(proof), Buffer.from(DIRECT_TEST_PROOF))) return null;
  return { sub: owner };
}

function authenticatedOwner(identity, requestedOwner) {
  if (!identity?.sub || identity.sub === 'anonymous') {
    throw new GraphQLError('Authentication required', {
      extensions: { code: 'UNAUTHENTICATED' },
    });
  }
  if (requestedOwner && requestedOwner !== identity.sub) {
    throw new GraphQLError('Cross-owner access is forbidden', {
      extensions: { code: 'FORBIDDEN' },
    });
  }
  return identity.sub;
}

function _readHeader(headers, name) {
  // Headers arrives as one of: `Headers` (from `new Headers(...)`), a `Map`
  // (some test/in-process paths), or a plain object (SCF integration tests).
  // `Headers` is NOT a Map subclass and exposes data only via `.get()` /
  // iteration — bare property access (`headers.authorization`) returns
  // `undefined`. Handle all three shapes uniformly.
  if (!headers) return '';
  if (typeof headers.get === 'function') {
    return headers.get(name) || headers.get(name.toLowerCase()) || '';
  }
  if (typeof headers === 'object') {
    // Plain-object path: lowercase (canonical) wins, but tolerate
    // PascalCase / UPPERCASE keys since some test helpers and a few
    // upstream proxies emit them.
    return (
      headers[name] ||
      headers[name.toLowerCase()] ||
      headers[toPascalCase(name)] ||
      headers[name.toUpperCase()] ||
      ''
    );
  }
  return '';
}

function toPascalCase(s) {
  return s.replace(/^([a-z])/, (_, c) => c.toUpperCase());
}

async function resolveIdentity(request) {
  // SCF path packs headers into `event.headers` (plain object) and wraps them
  // in `new Headers(...)` before handing to Yoga, so `request.headers` is
  // always a `Headers` instance there. Local dev / tests may pass a `Map` or
  // a plain object instead — see `_readHeader`.
  const directIdentity = directTestIdentity(request);
  if (directIdentity) return directIdentity;

  const authorization = _readHeader(request.headers, 'authorization');

  // 客户端发送的格式: "{tenant_id}/@@/{jwt}" — 提取真正的 JWT
  const rawAuth = authorization.replace(/^Bearer\s+/i, '').trim();
  let token = rawAuth;

  // 处理 tenant_id/@@/jwt 格式
  if (token.includes('/@@/')) {
    const parts = token.split('/@@/');
    token = parts.length >= 2 ? parts[1] : token;
  }

  // Token 验证分三种 (按优先级):
  //   1) SCF context 注入了 user identity (TCB 注入到 function context,
  //      getUserInfo() 直读 WX_OPENID/TCB_UUID 等)。
  //      — 当 TCB API Gateway / 微信小程序 / AppSync 转发"已登录用户"的请求
  //        时, context.userInfo 就有 openid/uid。此时 token 可能是 CloudBase
  //        access_token 或任意字符串, 只要 context 有 userInfo, 直接信任
  //        (因为是 TCB 网关/SCF runtime 已认证过的身份)。
  //   2) 外部 eCan 自签 30-day session token (HS256 JWT, sub=openid)
  //      — 桌面 app / WS bridge 在 access_token 过期后用这个;
  //        与 resolvers/auth.js mintSessionToken 共用 ECAN_JWT_SECRET,
  //        与 WS 服务的 verifySessionToken 一致。
  //   3) ALLOW_INSECURE_AUTH=true 时 (本地 dev only), 用 x-ecan-test-user header。
  //
  // 历史注记: 此处曾调用 `tcbApp.auth().verifyJwt(token)`, 但该 API 在 SDK v3.x
  // 中不存在 (dist/auth/index.js 仅导出 getUserInfo / getEndUserInfo /
  // queryUserInfo / getClientCredential / createTicket / getAuthContext /
  // getClientIP). 调用直接 TypeError → 被 catch 后所有带 token 请求都被错误地
  // 全拒 'Invalid or expired access token'. 现改为显式分路径处理。

  const tcbApp = getTcbApp();
  if (tcbApp && token) {
    // 路径1: SCF context 注入了 user identity — 直接信任 TCB 网关已认证过的身份。
    const ctxUser = tcbApp.auth().getUserInfo();
    const sub = ctxUser?.uid || ctxUser?.openId || ctxUser?.customUserId;
    if (sub) return { sub };

    // 路径2: 外部 eCan 自签 30-day session token (HS256, mirrors resolvers/auth.js)。
    const sessionSub = verifySessionToken(token);
    if (sessionSub) return { sub: sessionSub };
  }

  if (ALLOW_INSECURE_AUTH) {
    const testUser = _readHeader(request.headers, 'x-ecan-test-user');
    return { sub: testUser || 'local-development-user' };
  }

  throw new GraphQLError('Bearer token required', {
    extensions: { code: 'UNAUTHENTICATED' },
  });
}

/**
 * Verify an eCan HS256 session token. Mirrors resolvers/auth.js verifySessionToken
 * and WS service trySessionToken. Returns the openid (sub claim) on success,
 * null on failure. Refuses to verify when ECAN_JWT_SECRET is not configured —
 * same fail-loud pattern as resolvers/auth.js.
 */
function verifySessionToken(token) {
  const secret = process.env.ECAN_JWT_SECRET || process.env.JWT_SECRET;
  if (!secret) return null;
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const [header, payload, sig] = parts;
    const headerObj = JSON.parse(Buffer.from(header, 'base64url').toString('utf8'));
    if (headerObj.alg !== 'HS256') return null; // OIDC tokens handled by path 1
    const expected = require('crypto')
      .createHmac('sha256', secret)
      .update(`${header}.${payload}`)
      .digest('base64url');
    if (sig !== expected) return null;
    const claims = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'));
    const now = Math.floor(Date.now() / 1000);
    if (!claims.exp || claims.exp < now) return null;
    return claims.sub || null;
  } catch {
    return null;
  }
}

module.exports = {
  ALLOW_INSECURE_AUTH,
  DIRECT_TEST_MODE,
  authenticatedOwner,
  directTestHeaders,
  resolveIdentity,
  verifySessionToken,
  _readHeader,
};