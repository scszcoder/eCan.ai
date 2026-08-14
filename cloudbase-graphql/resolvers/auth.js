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
const { getTcbApp } = require('../tcb-init');

const SESSION_TOKEN_TTL_DAYS = 30;
const JWT_SECRET = process.env.ECAN_JWT_SECRET || process.env.JWT_SECRET || 'dev-secret-change-in-prod';

/** Mint a custom JWT (no library needed — we only need exp + sub claims). */
function mintSessionToken(openid) {
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

/** Verify a session token and return its openid, or null. */
function verifySessionToken(token) {
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

/** Verify a CloudBase token and extract openid. Returns null on failure. */
async function getWechatOpenid(accessToken) {
  const tcbApp = getTcbApp();
  if (!tcbApp) throw new Error('CloudBase not initialized');
  const userInfo = await tcbApp.auth().getUserInfo({ token: accessToken });
  return userInfo?.openid || userInfo?.openId || null;
}

/**
 * Check if a CloudBase access_token is still valid by calling getClientCredential.
 * Returns { valid: bool, accessToken: string, expiresIn: number }.
 */
async function verifyWxAccessToken(accessToken) {
  const tcbApp = getTcbApp();
  if (!tcbApp) return { valid: false, accessToken: null, expiresIn: 0 };

  // Decode exp locally first — fast path
  const exp = decodeJwtExp(accessToken);
  const now = Math.floor(Date.now() / 1000);
  if (exp !== null && exp < now) {
    return { valid: false, accessToken: null, expiresIn: 0 };
  }

  // Server-side verify via CloudBase
  try {
    const userInfo = await Promise.race([
      tcbApp.auth().getClientCredential({ token: accessToken }),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error('verify timeout')), 5000)
      ),
    ]);
    if (!userInfo) return { valid: false, accessToken: null, expiresIn: 0 };
    return { valid: true, accessToken, expiresIn: exp !== null ? Math.max(0, exp - now) : 600 };
  } catch {
    // Fallback: trust the local JWT exp
    return { valid: exp !== null && exp > now, accessToken, expiresIn: exp !== null ? Math.max(0, exp - now) : 0 };
  }
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

    // 1. Verify the CloudBase token and extract openid
    let openid;
    try {
      openid = await getWechatOpenid(wxAccessToken);
    } catch (err) {
      throw new GraphQLError(`Failed to verify WeChat token: ${err.message}`, {
        extensions: { code: 'UNAUTHENTICATED' },
      });
    }
    if (!openid) {
      throw new GraphQLError('Could not extract openid from WeChat token', {
        extensions: { code: 'UNAUTHENTICATED' },
      });
    }

    // 2. Mint session token
    const sessionToken = mintSessionToken(openid);
    const tokenHash = hashToken(sessionToken);
    const expiresAt = new Date(Date.now() + SESSION_TOKEN_TTL_DAYS * 24 * 3600 * 1000);

    // 3. Get owner from current CloudBase JWT
    let owner = openid;
    try {
      const tcbApp = getTcbApp();
      if (tcbApp) {
        const verified = await tcbApp.auth().verifyJwt(wxAccessToken);
        owner = verified?.uid || verified?.openid || verified?.sub || openid;
      }
    } catch { /* use openid as fallback */ }

    // 4. Upsert session
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
