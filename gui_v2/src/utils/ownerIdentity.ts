/**
 * One owner, several spellings. A CN WeChat login is `wechat_<openid>` locally
 * (`wechat_<openid>@local` in places), while the cloud stores the BARE openid
 * as the owner -- the same rule as the backend's `normalize_cloud_owner`.
 * Compared literally, a user's own cloud skill looked like someone else's:
 * read-only, with its 发布与定价 locked.
 */
export function normalizeOwner(value: unknown): string {
    let v = String(value ?? '').trim().toLowerCase();
    if (v.endsWith('@local')) v = v.slice(0, -'@local'.length);
    if (v.startsWith('wechat_')) v = v.slice('wechat_'.length);
    return v;
}

export function isSameOwner(a: unknown, b: unknown): boolean {
    const x = normalizeOwner(a);
    return !!x && x === normalizeOwner(b);
}
