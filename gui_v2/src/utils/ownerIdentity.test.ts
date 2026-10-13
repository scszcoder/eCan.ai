import { isSameOwner, normalizeOwner } from './ownerIdentity';

describe('owner identity', () => {
    it('treats a WeChat login and its cloud owner as the same person', () => {
        expect(isSameOwner('o3YBk2dxaRe3LKqJXCf5z3PfvD5M', 'wechat_o3YBk2dxaRe3LKqJXCf5z3PfvD5M')).toBe(true);
        expect(isSameOwner('wechat_o3YB@local', 'o3yb')).toBe(true);
        // The real CN identity suffix is `@wechat.local`; a bare-owner skill
        // must still read as owned by that same WeChat user (editor + publish).
        expect(isSameOwner('wechat_b603a407904569a4ea88f9ac', 'wechat_b603a407904569a4ea88f9ac@wechat.local')).toBe(true);
        expect(isSameOwner('wechat_b603a407904569a4ea88f9ac@wechat.local', 'wechat_b603a407904569a4ea88f9ac')).toBe(true);
        expect(normalizeOwner('wechat_x@wechat.local')).toBe('x');
    });
    it('keeps email owners exact (case-insensitive) and different people apart', () => {
        expect(isSameOwner('A@b.com', 'a@b.com')).toBe(true);
        expect(isSameOwner('a@b.com', 'c@b.com')).toBe(false);
        expect(isSameOwner('', '')).toBe(false);
        expect(normalizeOwner('wechat_x@local')).toBe('x');
    });
});
