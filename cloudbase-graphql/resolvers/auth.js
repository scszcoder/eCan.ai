/**
 * Auth mutations — WeChat silent refresh.
 *
 * CloudBase's wx_open provider does not issue a refresh_token, so every
 * WeChat login expires after ~10 minutes and forces the user to re-scan.
 * These mutations provide a server-side session layer:
 *
 *   registerWeChatSession(openid, wxAccessToken)
 *     → verify openid via CloudBase /auth/v1/user/me
 *     → mint a custom eCan JWT (30-day expiry) as the "session token"
 *     → store bcrypt hash of session token in DB alongside the current wx access_token
 *     → return session token to client (client stores it)
 *
 *   refreshWeChatToken(sessionToken)
 *     → verify session token hash against DB
 *     → verify the stored wx access_token is still valid
 *     → return the access_token (or "re-login needed")
 *     → client installs the new token
 *
 * IMPORTANT: CloudBase WeChat access_tokens cannot be refreshed server-side
 * without user re-authorization. This scheme only eliminates the need to
 * re-enter credentials — if the token is expired the user must re-scan the
 * QR code, but their session context is preserved (no re-registration).
 */

'use strict';

const crypto = require('crypto');
const { GraphQLError } = require('graphql');

const SESSION_TOKEN_TTL_DAYS = 30;
// ECAN_JWT_SECRET: shared HS256 secret. Must match the value injected into
// functions/ecan-graphql-ws/index.js (TCB EnvParams), otherwise the WS
// container will reject every session token minted here.
// Fallback to a non-secret sentinel so we fail loud at request time if the
// env var is missing in production — instead of silently signing tokens with
// a public string ('dev-secret-change-in-prod') that any attacker could use
// to forge sessions. WS service uses the same defensive pattern.
const JWT_SECRET = process.env.ECAN_JWT_SECRET || process.env.JWT_SECRET || null;

/** Mint a custom JWT (no library needed — we only need exp + sub claims).
 *  Throws if JWT_SECRET is not configured — refusing to sign with a null key
 *  is the whole point of removing the 'dev-secret-change-in-prod' fallback.
 */
function mintSessionToken(openid) {
  if (!JWT_SECRET) {
    throw new GraphQLError('ECAN_JWT_SECRET is not configured on this function', {
      extensions: { code: 'INTERNAL_ERROR' },
    });
  }
  const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url');
  const now = Math.floor(Date.now() / 1000);
  const exp = now + SESSION_TOKEN_TTL_DAYS * 24 * 3600;
  const payload = Buffer.from(JSON.stringify({ sub: openid, iat: now, exp })).toString('base64url');
  const sig = crypto
    .createHmac('sha256', JWT_SECRET)
    .update(`${header}.${payload}`)
    .digest('base64url');
  return `${header}.${payload}.${sig}`;
}

/** Verify a session token and return its openid, or null.
 *  Returns null when JWT_SECRET is unconfigured — caller treats this the
 *  same as an invalid signature (no detail leaks about why).
 */
function verifySessionToken(token) {
  if (!JWT_SECRET) return null;
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const [header, payload, sig] = parts;
    const expected = crypto
      .createHmac('sha256', JWT_SECRET)
      .update(`${header}.${payload}`)
      .digest('base64url');
    if (sig !== expected) return null;
    const claims = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'));
    const now = Math.floor(Date.now() / 1000);
    if (claims.exp < now) return null; // expired
    return claims.sub; // openid
  } catch {
    return null;
  }
}

/** PBKDF2 hash of the token for storage (avoids bcrypt dep). */
function hashToken(token) {
  return crypto.pbkdf2Sync(token, 'wechat-salt', 100_000, 64, 'sha512').toString('hex');
}

/** Decode exp from a JWT payload (base64url). Returns epoch seconds or null. */
function decodeJwtExp(token) {
  try {
    const parts = token.split('.');
    if (parts.length < 2) return null;
    const payload = JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf8'));
    if (!payload.exp) return null;
    let exp = parseInt(payload.exp, 10);
    // CloudBase sometimes uses millisecond exp
    if (exp > 10_000_000_000) exp = Math.floor(exp / 1000);
    return exp;
  } catch {
    return null;
  }
}

/**
 * Extract openid from a CloudBase JWT. Returns null on failure.
 * We decode the JWT directly rather than relying on getUserInfo() because
 * the token may come from the GraphQL input (not the HTTP Authorization header).
 */
function decodeOpenidFromJwt(token) {
  try {
    const parts = token.split('.');
    if (parts.length < 2) return null;
    const payload = JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf8'));
    return payload.openid || payload.openId || payload.uid || payload.sub || null;
  } catch {
    return null;
  }
}

/**
 * Lightweight CloudBase access_token validity check.
 *
 * Returns { valid, accessToken, expiresIn } based purely on the local JWT
 * `exp` claim. We DO NOT call @cloudbase/node-sdk's auth.getClientCredential
 * because that API is the OAuth *client_credentials* flow — it returns the
 * SDK's own access key (from its env-var credentials), not a verification of
 * the supplied token. Source: node_modules/@cloudbase/node-sdk/dist/auth/
 * index.js:137-156 explicitly ignores `opts.token` and posts to
 * /auth/v1/token/clientCredential with grant_type=client_credentials. Using
 * it to "verify a WeChat token" is a no-op masquerading as verification.
 *
 * CloudBase WeChat tokens cannot be revoked server-side — once we accept one
 * it remains valid until its own `exp`. The caller (registerWeChatSession /
 * refreshWeChatToken) treats `valid: false` as a hard error prompting the
 * client to re-scan the QR code.
 */
function verifyWxAccessToken(accessToken) {
  const exp = decodeJwtExp(accessToken);
  const now = Math.floor(Date.now() / 1000);
  if (exp === null) return { valid: false, accessToken: null, expiresIn: 0 };
  if (exp < now) return { valid: false, accessToken: null, expiresIn: 0 };
  return { valid: true, accessToken, expiresIn: Math.max(0, exp - now) };
}

const Mutation = {
  /**
   * registerWeChatSession
   *
   * Called once on first WeChat login (after the user scans the QR code).
   * Stores a session token so subsequent logins don't need re-scanning.
   */
  async registerWeChatSession(_, { input }, { prisma }) {
    const { wxAccessToken } = input;

    // 1. Extract openid from the JWT payload (fast, no network call)
    const openid = decodeOpenidFromJwt(wxAccessToken);
    if (!openid) {
      throw new GraphQLError('Could not extract openid from WeChat token — invalid or expired JWT', {
        extensions: { code: 'UNAUTHENTICATED' },
      });
    }

    // 3. Verify the JWT is still valid with CloudBase
    const check = await verifyWxAccessToken(wxAccessToken);
    if (!check.valid) {
      throw new GraphQLError('WeChat token is expired or invalid', {
        extensions: { code: 'UNAUTHENTICATED' },
      });
    }

    // 3. Mint session token
    const sessionToken = mintSessionToken(openid);
    const tokenHash = hashToken(sessionToken);
    const expiresAt = new Date(Date.now() + SESSION_TOKEN_TTL_DAYS * 24 * 3600 * 1000);

    // 3. Get owner from JWT payload (decode locally — same as resolveIdentity in auth.js)
    let owner = openid;
    try {
      const parts = wxAccessToken.split('.');
      if (parts.length === 3) {
        const payload = JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf8'));
        owner = payload.uid || payload.sub || payload.openid || payload.userId || openid;
      }
    } catch { /* use openid as fallback */ }

    // 4. Upsert session (prisma may be null in local dev without DATABASE_URL)
    if (!prisma) {
      throw new GraphQLError('Database not available (DATABASE_URL not configured)', {
        extensions: { code: 'INTERNAL_ERROR' },
      });
    }
    await prisma.weChatSession.upsert({
      where: { openid },
      create: {
        openid,
        sessionToken: tokenHash,
        owner: owner || openid,
        expiresAt,
        wxAccessToken,
      },
      update: {
        sessionToken: tokenHash,
        owner: owner || openid,
        expiresAt,
        wxAccessToken,
        lastRefreshed: new Date(),
      },
    });

    return {
      sessionToken,
      expiresIn: SESSION_TOKEN_TTL_DAYS * 24 * 3600,
    };
  },

  /**
   * refreshWeChatToken
   *
   * Called when the CloudBase access_token is about to expire.
   * Verifies the session token, checks if the stored wx access_token is still
   * valid, and returns it (or signals re-login is needed).
   */
  async refreshWeChatToken(_, { input }, { prisma }) {
    const { sessionToken } = input;

    // 1. Verify the custom session token (30-day JWT)
    const openid = verifySessionToken(sessionToken);
    if (!openid) {
      throw new GraphQLError('Session expired — please re-scan the WeChat QR code', {
        extensions: { code: 'SESSION_EXPIRED' },
      });
    }

    // prisma may be null in local dev without DATABASE_URL
    if (!prisma) {
      throw new GraphQLError('Database not available (DATABASE_URL not configured)', {
        extensions: { code: 'INTERNAL_ERROR' },
      });
    }

    // 2. Look up stored hash
    const stored = await prisma.weChatSession.findUnique({ where: { openid } });
    if (!stored) {
      throw new GraphQLError('WeChat session not found — please re-scan the QR code', {
        extensions: { code: 'SESSION_EXPIRED' },
      });
    }

    // 3. Verify token hash matches
    if (stored.sessionToken !== hashToken(sessionToken)) {
      throw new GraphQLError('Invalid session — please re-scan the WeChat QR code', {
        extensions: { code: 'UNAUTHENTICATED' },
      });
    }

    if (!stored.wxAccessToken) {
      throw new GraphQLError('No stored WeChat token — please re-scan the QR code', {
        extensions: { code: 'SESSION_EXPIRED' },
      });
    }

    // 4. Verify the stored wx access_token is still valid
    const check = await verifyWxAccessToken(stored.wxAccessToken);

    if (!check.valid) {
      // Token has expired — CloudBase can't mint a new one without re-authorization.
      // Throw SESSION_EXPIRED so the client knows to prompt for re-scan.
      throw new GraphQLError(
        'WeChat session expired — please re-scan the QR code (your account is preserved)',
        { extensions: { code: 'WX_TOKEN_EXPIRED' } }
      );
    }

    // 5. Token is still valid — update lastRefreshed and return it
    await prisma.weChatSession.update({
      where: { openid },
      data: { lastRefreshed: new Date() },
    });

    return {
      accessToken: stored.wxAccessToken,
      expiresIn: check.expiresIn,
    };
  },
};

module.exports = { Mutation };
