/**
 * Authentication helpers shared by all GraphQL resolvers.
 *
 * `resolveIdentity` is bound to the Yoga `context` factory at schema setup time;
 * `authenticatedOwner` is called by resolvers to enforce owner scoping.
 */

const { GraphQLError } = require('graphql');

// Local cache so the initial Yoga import does not force a TCB init for unit tests.
function getTcbApp() {
  // Lazy import to avoid pulling @cloudbase/node-sdk when not needed.
  try { return require('./tcb-init').getTcbApp(); } catch { return null; }
}

const ALLOW_INSECURE_AUTH = process.env.ALLOW_INSECURE_AUTH === 'true' && process.env.NODE_ENV !== 'production';

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
  const authorization = _readHeader(request.headers, 'authorization');

  // 客户端发送的格式: "{tenant_id}/@@/{jwt}" — 提取真正的 JWT
  const rawAuth = authorization.replace(/^Bearer\s+/i, '').trim();
  let token = rawAuth;

  // 处理 tenant_id/@@/jwt 格式
  if (token.includes('/@@/')) {
    const parts = token.split('/@@/');
    token = parts.length >= 2 ? parts[1] : token;
  }

  const tcbApp = getTcbApp();
  if (tcbApp && token) {
    try {
      const verified = await tcbApp.auth().verifyJwt(token);
      const sub = verified?.uid || verified?.openid || verified?.sub;
      if (sub) return { sub };
    } catch (error) {
      throw new GraphQLError('Invalid or expired access token', {
        extensions: { code: 'UNAUTHENTICATED' },
      });
    }
  }

  if (ALLOW_INSECURE_AUTH) {
    const testUser = _readHeader(request.headers, 'x-ecan-test-user');
    return { sub: testUser || 'local-development-user' };
  }

  throw new GraphQLError('Bearer token required', {
    extensions: { code: 'UNAUTHENTICATED' },
  });
}

module.exports = {
  ALLOW_INSECURE_AUTH,
  authenticatedOwner,
  resolveIdentity,
  _readHeader,
};