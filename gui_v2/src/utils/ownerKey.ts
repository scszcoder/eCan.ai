/**
 * One account can be spelled several ways: the cloud stores a WeChat user's rows
 * under the bare openid (`o3YB…`), the web signs in as `wechat_o3YB…`, the
 * desktop as `wechat_o3YB…@local`. Compare owners through this, never raw.
 */
export function ownerKey(value: unknown): string {
  let s = String(value ?? '').trim().toLowerCase();
  if (s.startsWith('wechat_')) s = s.slice('wechat_'.length);
  if (s.endsWith('@local')) s = s.slice(0, -'@local'.length);
  return s;
}
