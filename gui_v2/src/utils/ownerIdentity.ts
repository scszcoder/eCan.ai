/**
 * One owner, several spellings. A CN WeChat login is `wechat_<openid>` locally
 * (`wechat_<openid>@local` in places), while the cloud stores the BARE openid
 * as the owner -- the same rule as the backend's `normalize_cloud_owner`.
 * Compared literally, a user's own cloud skill looked like someone else's:
 * read-only, with its 发布与定价 locked.
 */
export function normalizeOwner(value: unknown): string {
    let v = String(value ?? '').trim().toLowerCase();
    // Synthetic local suffix for CN logins: `@local` (older) and the real
    // current forms `@wechat.local` (WeChat) / `@phone.local` (phone OTP). The
    // cloud knows only the bare username, so strip whichever is present.
    for (const suffix of ['@wechat.local', '@phone.local', '@local']) {
        if (v.endsWith(suffix)) { v = v.slice(0, -suffix.length); break; }
    }
    if (v.startsWith('wechat_')) v = v.slice('wechat_'.length);
    return v;
}

export function isSameOwner(a: unknown, b: unknown): boolean {
    const x = normalizeOwner(a);
    return !!x && x === normalizeOwner(b);
}
