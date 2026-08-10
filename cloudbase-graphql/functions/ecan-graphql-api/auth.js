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

async function resolveIdentity(request) {
  const authorization = request.headers.get('authorization') || '';
  const token = authorization.replace(/^Bearer\s+/i, '').trim();

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
    return { sub: request.headers.get('x-ecan-test-user') || 'local-development-user' };
  }

  throw new GraphQLError('Bearer token required', {
    extensions: { code: 'UNAUTHENTICATED' },
  });
}

module.exports = { ALLOW_INSECURE_AUTH, authenticatedOwner, resolveIdentity };